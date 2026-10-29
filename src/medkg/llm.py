"""Bounded OpenAI-compatible JSON/text calls with a task-wide persistent ledger."""

import json
import math
import os
import re
import time
import uuid
from contextlib import contextmanager
from email.utils import parsedate_to_datetime

from openai import APIConnectionError, APIStatusError, OpenAI

from medkg.config import ROOT, Settings
from medkg.tracing import span

MAX_PROVIDER_BACKOFF = 60.0
# Request bodies that disable thinking. A local qwen3.5 with thinking left on spends
# the whole completion budget reasoning and returns empty content.
THINKING_OFF = {'thinking': {'thinking': {'type': 'disabled'}},  # GLM
                'reasoning_effort': {'reasoning_effort': 'none'}}  # OpenAI-style, Ollama
# And that enable it: Gemma 4 sometimes reasons with thinking off, and its reasoning is then
# dropped, leaving an empty reply; allowed to reason, it goes on to reply (D127).
THINKING_ON = {'thinking': {'thinking': {'type': 'enabled'}},
               'reasoning_effort': {'reasoning_effort': 'low'}}


def provider_backoff(exc: Exception, failures: int) -> float:
    """Bound shared pacing after transient failures; never retry the failed request."""
    transient = isinstance(exc,APIConnectionError) or (
        isinstance(exc,APIStatusError) and (exc.status_code==429 or exc.status_code>=500))
    if not transient:
        return 0.0
    delay = min(MAX_PROVIDER_BACKOFF,10.0*2**min(max(failures-1,0),3))
    if isinstance(exc,APIStatusError):
        retry_after = exc.response.headers.get('retry-after','')
        try:
            requested = float(retry_after)
        except ValueError:
            try:
                requested = parsedate_to_datetime(retry_after).timestamp()-time.time()
            except (ValueError,TypeError,OverflowError):
                requested = 0.0
        if requested>0:
            delay = max(delay,min(requested,MAX_PROVIDER_BACKOFF))
    return delay


def parse_json(raw: str) -> dict:
    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.S).strip()
    match = re.search(r'```(?:json)?\s*(.*?)```', text, flags=re.S)
    if match:
        text = match[1]
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == '{':
            try:
                result, _ = decoder.raw_decode(text[i:])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue
    raise ValueError('Completion is not a JSON object')


@contextmanager
def ledger_lock(path, timeout: float = 5):
    """Hold an OS-owned mutex; abrupt worker exit must not strand a lock.

    Native lock files are persistent: removing them while another process holds
    the inode would create two independent locks on POSIX. Legacy exclusive-
    creation locks require explicit owner inspection and manual recovery.
    Running clients from different lock protocol versions together is unsupported.
    """
    import errno

    path.parent.mkdir(parents=True, exist_ok=True)
    native = path.with_name(path.name+'.oslock')
    descriptor = os.open(native, os.O_CREAT | os.O_RDWR, 0o600)
    deadline, acquired = time.monotonic()+timeout, False
    if os.name=='nt':
        import msvcrt
        def acquire():
            os.lseek(descriptor,0,os.SEEK_SET)
            msvcrt.locking(descriptor,msvcrt.LK_NBLCK,1)
        def release():
            os.lseek(descriptor,0,os.SEEK_SET)
            msvcrt.locking(descriptor,msvcrt.LK_UNLCK,1)
    else:
        import fcntl
        def acquire():
            fcntl.flock(descriptor,fcntl.LOCK_EX | fcntl.LOCK_NB)
        def release():
            fcntl.flock(descriptor,fcntl.LOCK_UN)
    try:
        while True:
            legacy = path.exists()
            if not legacy:
                try:
                    acquire()
                    acquired = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES,errno.EAGAIN):
                        raise
            if time.monotonic()>=deadline:
                reason = ('Legacy usage lock present; inspect its owner before recovery'
                          if legacy else 'Usage mutex busy; bounded lock timeout')
                raise RuntimeError(reason)
            time.sleep(0.05)
        yield
    finally:
        try:
            if acquired:
                release()
        finally:
            os.close(descriptor)

class LLMClient:
    def __init__(self, settings: Settings | None = None, model: str | None = None):
        self.settings = settings or Settings()
        self.settings.require(llm=True)
        if self.settings.llm_thinking_param not in THINKING_OFF:
            raise ValueError('LLM_THINKING_PARAM must be one of: '+', '.join(THINKING_OFF))
        self.model = model or self.settings.llm_model
        self.client = OpenAI(api_key=self.settings.llm_api_key, base_url=self.settings.llm_base_url,
                             timeout=self.settings.llm_timeout, max_retries=0)
        self.usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'seconds': 0.0}
        self.no_logprobs = False
        self.ledger = ROOT/'eval/runs/usage_log.jsonl'

    def _record(self, record: dict) -> None:
        with self.ledger.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(record)+'\n')

    def _pacing_state(self) -> dict:
        path = self.ledger.with_name('llm_backoff.json')
        if not path.exists():
            return {'failures':0,'not_before':0.0}
        state = json.loads(path.read_text(encoding='utf8'))
        if (not isinstance(state,dict) or type(state.get('failures')) is not int
                or not 0<=state['failures']<=4
                or type(state.get('not_before')) not in (int,float)
                or not 0<=state['not_before']<float('inf')):
            raise RuntimeError('Invalid provider pacing state')
        return state

    def _save_pacing(self, failures: int, delay: float) -> None:
        # Caller owns the cross-process provider mutex; replacement is atomic.
        path = self.ledger.with_name('llm_backoff.json')
        pending = path.with_suffix('.tmp')
        pending.write_text(json.dumps({'failures':failures,
            'not_before':time.time()+delay if delay else 0.0}),encoding='utf8')
        pending.replace(path)

    def chat(self, messages: list[dict], max_tokens: int = 1400, top_logprobs: int = 0,
             sink: list | None = None) -> str:
        before = dict(self.usage)
        with span('llm',model=self.model,**{'openinference.span.kind':'LLM'}) as attrs:
            try:
                return self._chat(messages,max_tokens,top_logprobs,sink)
            finally:
                attrs.update({k:self.usage[k]-before[k] for k in before})

    def call(self, messages: list[dict], tools: list[dict], max_tokens: int = 1400, think: bool = False) -> dict:
        """One reply that may call the declared tools (D127): its text and its tool calls, each
        with an id, a name and the arguments as a JSON string. Models with native function
        calling (Gemma 4) emit calls in their own format, which the server parses. think lets
        the model reason before it replies; the reasoning is not returned."""
        before = dict(self.usage)
        with span('llm',model=self.model,**{'openinference.span.kind':'LLM'}) as attrs:
            try:
                return self._chat(messages,max_tokens,tools=tools,think=think)
            finally:
                attrs.update({k:self.usage[k]-before[k] for k in before})

    def choose(self, messages: list[dict], options: int) -> dict[int, float] | None:
        """Probabilities of the replies 0..options, read from the first output token (D108).

        The model answers with one number; the log-probabilities of its first token give a
        distribution over the options, as a decision model would. A reply that is not one
        of the numbers ("None", "The") counts as 0, "something else". None when the
        endpoint returns no log-probabilities; after that the endpoint is not asked again.
        """
        if self.no_logprobs:
            return None
        sink: list = []
        try:
            self.chat(messages, max_tokens=1, top_logprobs=min(20, options + 5), sink=sink)
        except ValueError:
            pass                                  # an empty first token: its probabilities still count
        if not sink:
            self.no_logprobs = True
            return None
        scores = dict.fromkeys(range(options + 1), 0.0)
        for item in sink:
            token = item.token.strip()
            number = int(token) if re.fullmatch(r'[0-9]', token) else None
            scores[number if number is not None and number <= options else 0] += math.exp(item.logprob)
        total = sum(scores.values())
        return {k: v / total for k, v in scores.items() if v} if total else None

    def _chat(self, messages: list[dict], max_tokens: int = 1400, top_logprobs: int = 0,
              sink: list | None = None, tools: list[dict] | None = None, think: bool = False):
        reserve = sum(len((m.get('content') or '').encode('utf8')) + 100
                      + (len(json.dumps(m['tool_calls'])) if m.get('tool_calls') else 0) for m in messages) + max_tokens
        identifier = str(uuid.uuid4())
        lock = self.ledger.with_suffix('.lock')
        with ledger_lock(lock):
            if self.settings.token_budget is not None:
                records = [json.loads(line) for line in self.ledger.read_text(encoding='utf8').splitlines()] if self.ledger.exists() else []
                balances = {}
                for r in records:
                    balances[r['call_id']] = r.get('charged_tokens', r.get('reserved_tokens', 0))
                if sum(balances.values()) + reserve > self.settings.token_budget:
                    raise RuntimeError('Configured token budget exhausted')
            self._record({'call_id': identifier, 'status': 'reserved', 'reserved_tokens': reserve,
                          'model': self.model, 'run_id':os.getenv('MEDKG_RUN_ID','interactive'),
                          'timestamp': time.time()})
        started = time.perf_counter()
        tokens, status, failure = {}, 'failed', {}
        try:
            kwargs = dict(model=self.model, messages=messages, temperature=0, max_tokens=max_tokens)
            if top_logprobs:
                kwargs.update(logprobs=True, top_logprobs=top_logprobs)
            if tools:
                kwargs['tools'] = tools
            # The existing free endpoint rejects concurrent requests (HTTP 429).
            # A process-shared slot bounds concurrency without SDK retry storms;
            # LLM_COOLDOWN_S (default 1) spaces calls and can be 0 for paid providers.
            with ledger_lock(self.ledger.with_name('llm_call.lock'),timeout=120):
                pacing = self._pacing_state()
                wait = min(MAX_PROVIDER_BACKOFF,max(0.0,pacing['not_before']-time.time()))
                if wait:
                    time.sleep(wait)
                try:
                    response = self.client.chat.completions.create(**kwargs,
                        extra_body=(THINKING_ON if think else THINKING_OFF)[self.settings.llm_thinking_param])
                except Exception as exc:
                    failures = min(pacing['failures']+1,4)
                    delay = provider_backoff(exc,failures)
                    self._save_pacing(failures if delay else 0,delay)
                    failure = {'error_type':type(exc).__name__,'backoff_seconds':delay}
                    raise
                else:
                    self._save_pacing(0,0.0)
                finally:
                    if self.settings.llm_cooldown>0:
                        time.sleep(self.settings.llm_cooldown)
            usage = response.usage
            tokens = {'prompt_tokens': usage.prompt_tokens, 'completion_tokens': usage.completion_tokens} if usage else {}
            if top_logprobs and sink is not None:
                logprobs = response.choices[0].logprobs
                sink.extend(logprobs.content[0].top_logprobs if logprobs and logprobs.content else [])
            message = response.choices[0].message
            content = (message.content or '').strip()
            if tools is not None:
                calls = [{'id':call.id,'name':call.function.name,'arguments':call.function.arguments}
                         for call in message.tool_calls or []]
                if not content and not calls:
                    raise ValueError('Empty completion')
                status = 'complete'
                return {'content':content,'tool_calls':calls}
            if not content:
                raise ValueError('Empty completion')
            status = 'complete'
            return content
        finally:
            elapsed = time.perf_counter()-started
            charged = sum(tokens.values()) if tokens else reserve
            with ledger_lock(lock):
                self._record({'call_id': identifier, 'status': status, 'charged_tokens': charged,
                              **tokens, **failure, 'seconds': elapsed, 'model': self.model,
                              'timestamp': time.time()})
            self.usage['calls'] += 1
            for key in ('prompt_tokens', 'completion_tokens'):
                self.usage[key] += tokens.get(key, 0)
            self.usage['seconds'] += elapsed

    def chat_json(self, messages: list[dict], max_tokens: int = 1400) -> dict:
        return parse_json(self.chat(messages, max_tokens))


class FakeLLM:
    """Protocol fixture only; never used for real-data performance claims."""

    def __init__(self):
        self.usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'seconds': 0.0}

    def chat_json(self, messages: list[dict], max_tokens: int = 1400) -> dict:
        self.usage['calls'] += 1
        payload = json.loads(messages[1]['content'])
        question = payload.get('question','').casefold()
        if 'two hops from asterol' in question:
            if '"cypher"' in messages[0]['content']:
                return {'cypher':'MATCH (a:Drug {uid:$uid})-[r1:INDICATED_FOR]->(:Disease)'
                    '-[r2:HAS_PHENOTYPE]->(p:Phenotype) RETURN DISTINCT p.uid AS uid,p.name AS name,'
                    '[r1.source,r2.source] AS sources,false AS conflict,[] AS evidence LIMIT 25',
                    'params':{'uid':'synthetic:drug-a'}}
            return {'steps':[{'tool':'text2cypher','args':{'question':payload['question']}}]}
        if 'find virell syndrome by fulltext' in question:
            return {'steps':[{'tool':'fulltext','args':{'query':'Virell','label':'Disease'}},
                {'tool':'template','args':{'intent':'genes','uids':'$step1'}}]}
        return {'steps': [{'tool': 'out_of_scope', 'args': {}}]}

    def chat(self, messages: list[dict], max_tokens: int = 1400) -> str:
        self.usage['calls'] += 1
        data = json.loads(messages[-1]['content'].split('<evidence>')[1].split('</evidence>')[0])
        rows = data['rows']
        counts = [r['count'] for r in rows if 'count' in r]
        if counts:
            return f"Count: {counts[0]}"
        names = sorted({r['name'] for r in rows if r.get('name')})
        return '\n'.join('- '+n for n in names) or 'No supporting evidence was retrieved.'
