"""Bounded OpenAI-compatible JSON/text calls with a task-wide persistent ledger."""

import json
import os
import re
import time
import uuid
from contextlib import contextmanager

from openai import BadRequestError, OpenAI

from medkg.config import ROOT, Settings


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
def ledger_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 5
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise RuntimeError('Usage ledger locked; inspect abandoned process before retrying')
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        path.unlink()


class LLMClient:
    def __init__(self, settings: Settings | None = None, model: str | None = None):
        self.settings = settings or Settings()
        self.settings.require(llm=True)
        self.model = model or self.settings.llm_model
        self.client = OpenAI(api_key=self.settings.llm_api_key, base_url=self.settings.llm_base_url,
                             timeout=self.settings.llm_timeout, max_retries=0)
        self.usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'seconds': 0.0}
        self.ledger = ROOT/'eval/runs/usage_log.jsonl'

    def _record(self, record: dict) -> None:
        with self.ledger.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(record)+'\n')

    def chat(self, messages: list[dict], max_tokens: int = 1400) -> str:
        reserve = sum(len(m['content'].encode('utf8')) + 100 for m in messages) + max_tokens
        identifier = str(uuid.uuid4())
        lock = self.ledger.with_suffix('.lock')
        with ledger_lock(lock):
            records = [json.loads(line) for line in self.ledger.read_text(encoding='utf8').splitlines()] if self.ledger.exists() else []
            balances = {}
            for r in records:
                balances[r['call_id']] = r.get('charged_tokens', r.get('reserved_tokens', 0))
            if sum(balances.values()) + reserve > self.settings.token_budget:
                raise RuntimeError('Task token budget exhausted')
            self._record({'call_id': identifier, 'status': 'reserved', 'reserved_tokens': reserve,
                          'model': self.model, 'timestamp': time.time()})
        started = time.perf_counter()
        tokens, status = {}, 'failed'
        try:
            kwargs = dict(model=self.model, messages=messages, temperature=0, max_tokens=max_tokens)
            try:
                response = self.client.chat.completions.create(**kwargs,
                    extra_body={'thinking': {'type': 'disabled'}})
            except BadRequestError as exc:
                if 'thinking' not in str(exc).lower():
                    raise
                response = self.client.chat.completions.create(**kwargs)
            usage = response.usage
            tokens = {'prompt_tokens': usage.prompt_tokens, 'completion_tokens': usage.completion_tokens} if usage else {}
            content = (response.choices[0].message.content or '').strip()
            if not content:
                raise ValueError('Empty completion')
            status = 'complete'
            return content
        finally:
            elapsed = time.perf_counter()-started
            charged = sum(tokens.values()) if tokens else reserve
            with ledger_lock(lock):
                self._record({'call_id': identifier, 'status': status, 'charged_tokens': charged,
                              **tokens, 'seconds': elapsed, 'model': self.model, 'timestamp': time.time()})
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
        return {'steps': [{'tool': 'out_of_scope', 'args': {}}]}

    def chat(self, messages: list[dict], max_tokens: int = 1400) -> str:
        self.usage['calls'] += 1
        data = json.loads(messages[-1]['content'].split('<evidence>')[1].split('</evidence>')[0])
        rows = data['rows']
        if rows and 'count' in rows[0]:
            return f"Count: {rows[0]['count']}"
        names = sorted({r['name'] for r in rows if r.get('name')})
        return '\n'.join('- '+n for n in names) or 'No supporting evidence was retrieved.'
