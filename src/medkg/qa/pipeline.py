"""QA boundary returns answer, contexts, executed queries, route and trace id."""

import copy
import json
import time
from collections import OrderedDict

from medkg.config import ROOT, Settings
from medkg.graph.store import GraphStore
from medkg.llm import LLMClient
from medkg.qa import answer, planner, safety, session
from medkg.qa.linker import Linker
from medkg.qa.router import is_count, route
from medkg.retrieval import templates, text2cypher
from medkg.tracing import request_trace, span


class Pipeline:
    def __init__(self, settings: Settings | None = None, store=None, llm=None, entities=None,
                 mode: str = 'hybrid'):
        self.settings = settings or Settings()
        self.store = store or GraphStore(self.settings)
        self.llm = llm or LLMClient(self.settings)
        self.linker = Linker(entities if entities is not None else self.store.entities())
        self.mode = mode
        self.cache = OrderedDict()

    def close(self) -> None:
        self.store.close()

    def ask(self, question: str, history: list[dict] | None = None) -> dict:
        start, history = time.perf_counter(), history or []
        before = dict(self.llm.usage)
        with request_trace() as trace_id:
            result = {'answer':'','contexts':[],'route':'','cypher':[],'queries':[],
                      'trace_id':trace_id,'safety':'none','focus':[],'intent':None,
                      'failure_stage':None,'refused':False,'truncated':False}
            with span('safety'):
                assessment = safety.assess(question,self.settings.safety_region)
                result['safety'] = assessment.category
                if assessment.blocked:
                    result.update(answer=assessment.message,route='safety',refused=True)
                    return self._finish(result,start,before)
                if not safety.english(question):
                    result.update(answer='This demo supports English questions only.',route='language',refused=True)
                    return self._finish(result,start,before)
            key = json.dumps([question,history,self.mode,self.settings.phase],sort_keys=True)
            if self.settings.cache and key in self.cache:
                expires,cached = self.cache[key]
                if expires>time.monotonic():
                    result = copy.deepcopy(cached)
                    result.update(trace_id=trace_id,cache_hit=True)
                    return self._finish(result,start,before)
                del self.cache[key]
            stage = 'linking'
            try:
                with span('linking'):
                    resolved,previous = session.resolve(question,history)
                    candidates = self.linker.in_question(resolved)
                    result['candidates'] = self.linker.describe(candidates)
                    result['focus'] = [c.name for c in candidates if not c.ambiguous][:2]
                stage = 'routing'
                with span('routing'):
                    intent = route(resolved,candidates,previous)
                    result['intent'] = intent
                    if self.mode=='vector':
                        steps = [planner.Step(tool='vector_search',args={'query':resolved})]
                        result['route'] = 'vector'
                    elif intent:
                        label = templates.SPECS[intent][0]
                        steps = [planner.Step(tool='template',args={'intent':intent,
                                  'uids':[c.uid for c in candidates if c.label==label],
                                  'count':is_count(resolved)})]
                        result['route'] = 'template'
                    else:
                        steps = planner.plan(self.llm,resolved,result['candidates'],self.settings.phase).steps
                        result['route'] = 'planner'
                rows,outputs = [],[]
                stage = 'query'
                for number,step in enumerate(steps,1):
                    with span('tool.'+step.tool,step=number) as attrs:
                        args = self._resolve_args(step.args,outputs)
                        params = {}
                        if step.tool=='out_of_scope':
                            result.update(answer='I cannot answer this from the supported medical knowledge base. Please clarify ambiguous entities if applicable.',refused=True)
                            return self._finish(result,start,before)
                        if step.tool=='template':
                            query,params = templates.query(**args)
                            retrieved = self.store.run_generated(query,params)
                        elif step.tool=='text2cypher':
                            retrieved = text2cypher.retrieve(self.store,self.llm,args.get('question',resolved),result['candidates'])
                            params = getattr(retrieved,'params',{})
                        else:
                            retrieved = self._hybrid_tool(step.tool,args)
                        attrs['rows'] = len(retrieved.rows)
                        if retrieved.stmt:
                            result['cypher'].append(retrieved.stmt)
                            result['queries'].append({'cypher':retrieved.stmt,'params':params})
                        outputs.append(retrieved.rows)
                        rows.extend(retrieved.rows)
                        result['truncated'] |= retrieved.truncated
                result['contexts'] = rows + [{'uid':c.uid,'name':c.name,'role':'anchor'} for c in candidates]
                stage = 'generation'
                if not rows:
                    result.update(answer='No supporting evidence was retrieved.',refused=True)
                else:
                    with span('generation'):
                        result['answer'] = self.llm.chat(answer.messages(question,rows))
                    if self.settings.phase>=3:
                        stage = 'verification'
                        with span('verification'):
                            from medkg.qa.verify import verify_answer
                            result['answer'] = verify_answer(self.llm,question,result['answer'],rows,self.linker)
                result['answer'] = answer.finalize(result['answer'],rows,result['truncated'])
            except Exception as exc:
                result.update(answer='The request could not be completed. Please retry or simplify the question.',
                              failure_stage=stage,error_type=type(exc).__name__)
            if self.settings.cache and not result['failure_stage']:
                self.cache[key] = (time.monotonic()+self.settings.cache_ttl,copy.deepcopy(result))
                if len(self.cache)>256:
                    self.cache.popitem(last=False)
            return self._finish(result,start,before)

    def _resolve_args(self,args: dict,outputs: list[list[dict]]) -> dict:
        def resolve(value):
            if isinstance(value,str) and value.startswith('$step'):
                index = int(value[5:])-1
                return sorted({row['uid'] for row in outputs[index] if row.get('uid')})
            if isinstance(value,list):
                result = []
                for item in value:
                    resolved = resolve(item)
                    result.extend(resolved if isinstance(resolved,list) else [resolved])
                return result
            if isinstance(value,dict):
                return {k:resolve(v) for k,v in value.items()}
            return value
        return resolve(args)

    def _hybrid_tool(self,name: str,args: dict):
        if self.settings.phase<3:
            raise ValueError('Hybrid tools disabled')
        from medkg.retrieval import expand, fulltext, vector
        return {'expand':expand.search,'fulltext':fulltext.search,'vector_search':vector.search}[name](
            self.store,**args,**({'mode':self.mode} if name=='vector_search' else {}))

    def _finish(self,result: dict,start: float,before: dict) -> dict:
        result['latency_s'] = time.perf_counter()-start
        result['usage'] = {k:self.llm.usage[k]-before[k] for k in before}
        return result


def local_pipeline(phase: int | None = None,mode: str = 'hybrid') -> Pipeline:
    settings = Settings()
    if phase is not None:
        settings.phase = phase
    path = ROOT/'data/processed/entities.json'
    entities = json.loads(path.read_text(encoding='utf8')) if path.exists() else None
    pipeline = Pipeline(settings,entities=entities,mode=mode)
    vectors = path.parent/'alias_vectors.npy'
    aliases = path.parent/'vector_aliases.json'
    if vectors.exists() and aliases.exists():
        import numpy as np

        from medkg.embeddings import Embeddings
        pipeline.linker = Linker(entities or pipeline.store.entities(), Embeddings(),
                                np.load(vectors,mmap_mode='r'),json.loads(aliases.read_text(encoding='utf8')))
    return pipeline
