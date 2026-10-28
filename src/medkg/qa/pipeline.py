"""QA boundary returns answer, contexts, executed queries, route and trace id."""

import copy
import json
import re
import time
from collections import OrderedDict

from medkg.config import ROOT, Settings
from medkg.graph.store import GraphStore
from medkg.llm import LLMClient
from medkg.qa import answer, confirm, planner, safety, scope, session
from medkg.qa import intent as intents
from medkg.qa.linker import Linker, label_choices
from medkg.qa.router import has_relation_cue, is_count, route, wants_shared
from medkg.retrieval import templates, text2cypher
from medkg.tracing import request_trace, span
from medkg_data.lexicon import normalize


class Pipeline:
    def __init__(self, settings: Settings | None = None, store=None, llm=None, entities=None,
                 mode: str = 'hybrid'):
        self.settings = settings or Settings()
        self.store = store or GraphStore(self.settings)
        self.llm = llm or LLMClient(self.settings)
        self.linker = Linker(entities if entities is not None else self.store.entities())
        self.titles = None   # MedlinePlus topic titles, read on the first question (D121)
        self.mode = mode
        self.cache = OrderedDict()

    def close(self) -> None:
        self.store.close()

    def ask(self, question: str, history: list[dict] | None = None) -> dict:
        start, history = time.perf_counter(), history or []
        before = dict(self.llm.usage)
        if hasattr(self.store,'executed_statements'):
            self.store.executed_statements.clear()
        with request_trace() as trace_id:
            result = {'answer':'','contexts':[],'route':'','cypher':[],'queries':[],
                      'trace_id':trace_id,'safety':'none','focus':[],'intent':None,
                      'failure_stage':None,'refused':False,'truncated':False}
            with span('safety'):
                # Block, answer the knowledge part with a fixed notice, or pass (D103).
                # A named drug makes "how much X a day" a dose request (D111).
                named = self.linker.question_mentions(question,exact_only=True)[0]
                triage = safety.triage(question,self.settings.safety_region,
                                       drug_named=any(c.label=='Drug' for c in named))
                # A personal message the rules did not read as an emergency is read once more
                # by the model; the reading can only escalate to the emergency reply (D117).
                if triage.category not in ('crisis','emergency'):
                    urgent = safety.emergency_reading(self.llm,question)
                    if urgent is not None:
                        result['emergency_reading'] = round(urgent,3)
                        if urgent>=safety.ESCALATE_AT:
                            triage = safety.escalated(triage,self.settings.safety_region)
                result['safety'] = triage.category
                if triage.mode=='block':
                    result.update(answer=triage.message,route='safety',refused=True)
                    return self._finish(result,start,before)
                caveat = triage.mode=='caveat'
                if caveat:
                    result['safety_mode'] = 'caveat'
                asked = triage.question if caveat else question
                caution = safety.CAUTION if caveat else ''
                notices = [triage.notice] if caveat else []
                cautions = list(notices)   # the notices shown as a caution, not as a reading (D125)
                if not safety.english(question):
                    result.update(answer='This demo supports English questions only.',route='language',refused=True)
                    return self._finish(result,start,before)
            with span('scope'):
                if scope.blocked(question):
                    result.update(answer=scope.MESSAGE,route='scope',refused=True)
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
                with span('linking') as attrs:
                    resolved,previous = session.resolve(asked,history)
                    # A follow-up is shown as it was read ("its" -> the previous answer's entity).
                    if resolved!=asked:
                        result['read_as'] = resolved
                    candidates,unresolved = self.linker.question_mentions(resolved)
                    result['candidates'] = self.linker.describe(candidates)
                    result['unresolved_mentions'] = unresolved
                    result['focus'] = [c.name for c in candidates if not c.ambiguous][:2]
                    attrs['candidates'] = len(candidates)
                quarantined = self.linker.quarantined_mentions(unresolved)
                if quarantined:
                    result.update(
                        answer='This name does not uniquely identify a supported drug. '
                               'Please provide the exact drug name before I continue.',
                        route='linking', refused=True, quarantined_mentions=quarantined)
                    return self._finish(result,start,before)
                # Corrected names are confirmed by the user, or used with a visible note (D105).
                checked = confirm.review(self.linker,candidates,unresolved)
                # A MedlinePlus topic named as written settles the names inside it (D121).
                if self.titles is None:
                    self.titles = topic_titles(self.store)
                checked = confirm.by_title(resolved,checked,self.titles)
                # A partly matched phrase ("iron overdose" -> Iron) is checked by the model (D106).
                judge = confirm.model_judge(self.llm)
                # Several spellings of an asked-back name are ordered by the question (D118).
                if checked.suggestions:
                    checked = confirm.rank_suggestions(resolved,checked,judge)
                if not checked.suggestions:
                    checked = confirm.check_phrases(self.linker,resolved,checked,judge,typed=question)
                # A lower-case word that matched only an acronym ("hard" -> HARDS) is checked too (D116).
                if not checked.suggestions:
                    checked = confirm.check_words(self.linker,resolved,checked,judge,typed=question)
                # A name the model checks asked back may be settled by a title too (D121).
                checked = confirm.by_title(resolved,checked,self.titles)
                if checked.ignored:
                    result['ignored_words'] = checked.ignored
                if checked.suggestions:
                    result.update(answer=confirm.clarification(checked.suggestions),route='linking',
                                  refused=True,suggestions=confirm.describe(checked.suggestions))
                    return self._finish(result,start,before)
                candidates,unresolved = checked.kept,checked.unresolved
                result['candidates'] = self.linker.describe(candidates)
                result['unresolved_mentions'] = unresolved
                result['focus'] = [c.name for c in candidates if not c.ambiguous][:2]
                if checked.corrections:
                    result['corrections'] = confirm.describe(checked.corrections)
                    notices.append(confirm.correction_notice(checked.corrections))
                # A name with several readings of one label (two diseases called
                # "open-angle glaucoma") is resolved by the user, not guessed (D093).
                if candidates and label_choices(candidates) is None:
                    options = [c for c in candidates if c.ambiguous]
                    listed = '; '.join(f'{c.name} ({c.label}, {c.uid})' for c in options[:6])
                    mention = options[0].mention or options[0].name
                    result.update(answer=f'"{mention}" matches several entries in the knowledge graph: {listed}. '
                                         'Which one do you mean?',
                                  route='linking',refused=True,clarification=[c.uid for c in options])
                    return self._finish(result,start,before)
                stage = 'routing'
                with span('routing') as attrs:
                    intent = None if unresolved else route(resolved,candidates,previous)
                    if unresolved and 'interact' in resolved.casefold():
                        result.update(answer='Please clarify the unresolved drug names before checking interactions.',
                                      route='linking',refused=True)
                        return self._finish(result,start,before)
                    # No rule fits a question about one name and no relation word is used
                    # ("What is the purpose of X?"): the model reads which question is meant (D108).
                    reading = None
                    if (intent is None and not unresolved and self.mode!='vector' and candidates
                            and len({c.span for c in candidates})==1 and not is_count(resolved,candidates)
                            and not has_relation_cue(resolved,candidates)):
                        region = self.settings.safety_region
                        reading = intents.read(self.llm,resolved,candidates,
                                               allowed=lambda q:safety.triage(q,region).mode!='block')
                    if reading:
                        result['intent_reading'] = {'mode':reading.mode,'other':round(reading.other,3),
                                                    'options':reading.offered(len(reading.ranked))}
                        if reading.mode=='ask':
                            # Safety and correction notices stay in front of the question.
                            asked_back = intents.clarification(reading)
                            result.update(answer='\n'.join([*notices,'',asked_back]) if notices else asked_back,
                                          route='intent',refused=True,intent_options=reading.offered(),
                                          notices=notes(notices,cautions))
                            return self._finish(result,start,before)
                        if reading.mode=='answer':
                            # Answered, but the guess is shown and the other questions are offered.
                            intent = reading.ranked[0][0]
                            notices.append(intents.note(reading))
                            result['intent_options'] = reading.offered(intents.OFFER+1)[1:]
                    result['intent'] = intent
                    # "What about X?" repeats the previous question, which is shown (D125).
                    if previous and intent==previous and 'read_as' not in result:
                        anchor = next((c for c in candidates if c.label==templates.SPECS[intent][0]),None)
                        if anchor:
                            result['read_as'] = intents.phrase(intent,anchor)
                    if self.mode=='vector':
                        steps = [planner.Step(tool='vector_search',args={'query':resolved})]
                        result['route'] = 'vector'
                    elif intent:
                        label,other = templates.SPECS[intent][:2]
                        # The route may have chosen one label of a same-name pair.
                        anchors = [c for c in candidates if c.label==label]
                        result['focus'] = [c.name for c in anchors][:2]
                        args = {'intent':intent,'uids':[c.uid for c in anchors],'count':is_count(resolved,candidates),
                                'shared':wants_shared(resolved,anchors)}
                        # A yes/no question about a drug and a disease checks that one pair (D112).
                        targets = [c for c in candidates if c.label==other and other!=label]
                        if (len(targets)==1 and intent in templates.PAIR_PHRASES and len(anchors)==1
                                and not args['count']):
                            args['target'] = targets[0].uid
                            result['focus'] = [anchors[0].name,targets[0].name]
                        steps = [planner.Step(tool='template',args=args)]
                        result['route'] = 'template'
                    else:
                        planned = planner.plan(self.llm,resolved,result['candidates'],self.settings.phase)
                        steps = planned.steps
                        if planned._fallback_reason:
                            result['planning_fallback'] = planned._fallback_reason
                        result['route'] = 'planner'
                    attrs.update(route=result['route'],steps=len(steps))
                rows,outputs = [],[]
                # Result rows of the final graph query step, when they are the answer: the only
                # graph step, or one chained on earlier outputs. Two independent lists left
                # for the model to intersect are not (D087).
                answer_rows,graph_steps = [],0
                stage = 'query'
                for number,step in enumerate(steps,1):
                    with span('tool.'+step.tool,step=number) as attrs:
                        partial_references = []
                        args = self._resolve_args(step.args,outputs,partial_references)
                        result['truncated'] |= bool(partial_references)
                        if args.get('count') and result['truncated']:
                            result.update(answer=answer.finalize(
                                'An exact count is unavailable because an earlier retrieval was incomplete.',
                                rows,True),refused=True)
                            return self._finish(result,start,before)
                        params,description = {},None
                        if step.tool=='out_of_scope':
                            result.update(answer='I cannot answer this from the supported medical knowledge base. Please clarify ambiguous entities if applicable.',refused=True)
                            return self._finish(result,start,before)
                        if step.tool=='template':
                            query,params = templates.query(**args)
                            description = templates.describe(args['intent'],[
                                self.linker.entities.get(uid,{}).get('name',uid) for uid in args['uids']],
                                bool(args.get('count')),bool(args.get('shared')),
                                self.linker.entities.get(args['target'],{}).get('name') if args.get('target') else None)
                            retrieved = self.store.run_generated(query,params)
                        elif step.tool=='text2cypher':
                            asked = args.get('question',resolved)
                            retrieved = text2cypher.retrieve(self.store,self.llm,asked,result['candidates'])
                            params = getattr(retrieved,'params',{})
                            description = text2cypher.describe(asked)
                        else:
                            retrieved = self._hybrid_tool(step.tool,args)
                        attrs['rows'] = len(retrieved.rows)
                        if retrieved.stmt:
                            result['cypher'].append(retrieved.stmt)
                            result['queries'].append({'cypher':retrieved.stmt,'params':params,
                                                      **({'description':description} if description else {})})
                        outputs.append(retrieved.rows)
                        if step.tool in ('template','text2cypher'):
                            graph_steps += 1
                            chained = '"$step' in json.dumps(step.args)
                            answer_rows = list(retrieved.rows) if graph_steps==1 or chained else []
                        else:
                            answer_rows = []
                        rows.extend(retrieved.rows)
                        result['truncated'] |= retrieved.truncated
                        # Graph first, text second: most diseases have no phenotype
                        # edges (e.g. gout) but do have documents about them. A generated
                        # query that finds nothing ("Can diazepam lower blood pressure?") is
                        # followed the same way, by the documents about the named entities (D119).
                        about = (args['uids'] if step.tool=='template' else
                                 list(dict.fromkeys(c.uid for c in candidates))[:25]
                                 if step.tool=='text2cypher' else [])
                        if (about and not retrieved.rows and len(steps)==1
                                and not step.args.get('target')
                                and self.mode=='hybrid' and self.settings.phase>=3):
                            text = self._hybrid_tool('vector_search',{'query':resolved,'uids':about})
                            rows.extend(text.rows)
                            result['retrieval_fallback'] = 'vector_search'
                            attrs['fallback_rows'] = len(text.rows)
                partial = False
                if self.mode!='vector' and self.settings.phase>=3:
                    with span('tool.conflict_evidence') as attrs:
                        pair_target = steps[0].args.get('target') if len(steps)==1 else None
                        claims,partial = self._conflicting_claims(candidates,rows,intent,pair_target)
                        rows = claims + rows
                        result['truncated'] |= partial
                        attrs['rows'] = len(claims)
                result['contexts'] = rows + [{'uid':c.uid,'name':c.name,'role':'anchor'} for c in candidates]
                evidence_uids = sorted({uid for row in rows for uid in row.get('evidence',[]) or []})
                # Only 25 supporting chunks are attached; say so instead of implying completeness.
                result['truncated'] |= len(evidence_uids)>25
                if evidence_uids:
                    documents = self.store.read('MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk) '
                        'WHERE c.uid IN $uids RETURN c.uid AS uid,c.text AS text,c.section AS section, '
                        'd.url AS url,d.source AS source,d.title AS title LIMIT 25',{'uids':evidence_uids[:25]})
                    rows = [r for r in rows if r.get('relation') and r.get('conflict')] + documents + [
                        r for r in rows if not (r.get('relation') and r.get('conflict'))]
                    result['contexts'].extend(documents)
                stage = 'generation'
                rows, bounded = answer.bound_evidence(rows)
                result['truncated'] |= bounded
                query_evidence,partial_queries = answer.bound_queries(result['queries'])
                result['truncated'] |= partial_queries
                result['contexts'] = rows + [{'uid':c.uid,'name':c.name,'role':'anchor'} for c in candidates]
                if query_evidence:
                    result['contexts'].append({'role':'executed_graph_queries','queries':query_evidence})
                # Brand names, lay terms and typos are linked to canonical entities; say so
                # explicitly rather than rely on the answer model knowing the mapping (D085).
                entities = [{'mention':c.mention or c.name,'entity':c.name,'uid':c.uid,'type':c.label}
                            for c in candidates if not c.ambiguous]
                # "Does A interact with B?" answered by the pairwise template: a returned row
                # is a recorded interaction, stated in code rather than worded by the model,
                # which denied returned rows (D092).
                pair = steps[0].args.get('uids',[]) if result['route']=='template' and len(steps)==1 else []
                recorded = (intent=='interactions' and len(pair)==2 and not steps[0].args.get('count')
                            and not steps[0].args.get('shared') and bool(answer_rows))
                # A list about one entity from one template query is stated in code, with the
                # number recorded: the model only restated the rows, and sometimes added
                # "(Count: 1)" to each of them (D124).
                listed = (len(pair)==1 and bool(answer_rows) and not steps[0].args.get('count')
                          and not steps[0].args.get('shared') and not steps[0].args.get('target'))
                empty_answer = False
                # "Is X used to treat Y?" answered by the pair template: whether the graph
                # records that one pair, stated in code like the interaction pair (D112).
                target = steps[0].args.get('target') if result['route']=='template' and len(steps)==1 else None
                if target:
                    by_uid = {c.uid:c for c in candidates}
                    result['answer'] = templates.pair_verdict(intent,self._written(by_uid,steps[0].args['uids'][0]),
                                                              self._written(by_uid,target),bool(answer_rows))
                    # About a person or a population: what the graph records is not advice for them.
                    if not caveat and re.search(safety.PERSONAL+'|'+safety.POPULATION,resolved,re.I):
                        notices.append(safety.NOTICES['medication_decision'])
                        cautions.append(notices[-1])
                elif (intent=='interactions' and len(pair)>2 and not steps[0].args.get('count')
                      and not steps[0].args.get('shared')):
                    # Interactions among several drugs: every pair, stated in code (D113).
                    by_uid = {c.uid:c for c in candidates}
                    result['answer'] = templates.interaction_verdict(
                        {uid:self._written(by_uid,uid) for uid in pair},pair,answer_rows)
                elif not rows:
                    result.update(answer='No supporting evidence was retrieved.',refused=True)
                elif recorded:
                    first,second = (self.linker.entities.get(uid,{}).get('name',uid) for uid in pair)
                    result['answer'] = f'Yes. The knowledge graph records an interaction between {first} and {second}.'
                elif listed:
                    # The list query's row limit is settled by a count (D124); the supporting
                    # chunks and conflicting claims may still be partial. The bounds on what a
                    # model is sent do not apply: no model words this answer.
                    result['truncated'] = partial or len(evidence_uids)>25
                    result['answer'],result['listing'] = self._listing(intent,pair[0],candidates,answer_rows,result)
                    result['conflicts'] = answer.claims(rows)
                else:
                    # Target synonyms stay in the contexts (scoring, verification) but are not
                    # shown to the answer model, which echoed them as extra entities (D092).
                    shown = [{k:v for k,v in row.items() if k!='synonyms'} for row in rows]
                    with span('generation'):
                        result['answer'] = self.llm.chat(answer.messages(resolved,shown,queries=query_evidence,
                                                                         entities=entities,caution=caution))
                    if self.settings.phase>=3:
                        stage = 'verification'
                        with span('verification'):
                            from medkg.qa.verify import verify_answer
                            result['answer'] = verify_answer(self.llm,resolved,result['answer'],result['contexts'],self.linker,
                                                             query_evidence,entities,caution)
                    # Verification notices and source footers are not an answer (D102).
                    body = re.split(r'(?m)^\s*(?:Sources:|Research demo;)',result['answer'],maxsplit=1)[0]
                    body = body.replace('Some entries were removed because their entities '
                                        'were not supported by retrieved evidence.','')
                    empty_answer = not any(char.isalnum() for char in body)
                    if empty_answer:
                        result.update(answer='No supporting evidence was retrieved.',refused=True)
                    with span('output_safety'):
                        violation = safety.output_violation(result['answer'])
                        if violation:
                            result.update(answer=violation.message,safety=violation.category,refused=True,
                                          output_blocked=True)
                            result.pop('intent_options',None)
                    # A safety refusal stands; otherwise the answer rows must be reported.
                    if not result['refused'] and answer_rows and not any('count' in r for r in answer_rows):
                        from medkg.qa.verify import entities_in_text
                        names = [row.get('name') or self.linker.entities.get(row.get('uid'),{}).get('name')
                                 for row in answer_rows]
                        result['answer'],completed = answer.ensure_reported(
                            result['answer'],names,[row.get('uid') for row in answer_rows],
                            entities_in_text(result['answer'],self.linker))
                        if completed:
                            result['answer_completed'] = completed
                # An emptied answer is finalized like the no-evidence decline: disclaimer, no sources.
                result['answer'] = (answer.finalize(result['answer'],[],False) if empty_answer
                                    else answer.finalize(result['answer'],rows,result['truncated']))
                # The same sources, one entry per document, for the web page (D123).
                result['sources'] = [] if empty_answer else answer.sources(rows)
                # Questions the graph can answer next about the same entity (D125).
                subject = next((c for c in candidates if not c.ambiguous and (
                    result['route']!='template' or c.uid in pair[:1])),None)
                if subject and not result['refused'] and not result.get('intent_options'):
                    result['related'] = self._related(subject,intent)
            except Exception as exc:
                result.update(answer='The request could not be completed. Please retry or simplify the question.',
                              failure_stage=stage,error_type=type(exc).__name__)
            # A caveat reply leads with its notice, including a decline ("no interaction is
            # recorded" still answers the question). Only an output-safety refusal falls back
            # to the block message, as before D103.
            # Name corrections (D105) are noted the same way.
            if notices and not result['failure_stage']:
                if result.get('output_blocked'):
                    if caveat:
                        result.update(answer=triage.message,route='safety',refused=True)
                else:
                    # Detect a decline before the notice hides the reply's opening sentence.
                    if answer.unsupported_response(result['answer']):
                        result['refused'] = True
                    result['answer'] = '\n'.join(notices)+'\n\n'+result['answer']
                    result['notices'] = notes(notices,cautions)
            if self.settings.cache and not result['failure_stage']:
                self.cache[key] = (time.monotonic()+self.settings.cache_ttl,copy.deepcopy(result))
                if len(self.cache)>256:
                    self.cache.popitem(last=False)
            return self._finish(result,start,before)

    def _resolve_args(self,args: dict,outputs: list[list[dict]],partial: list | None = None) -> dict:
        def resolve(value):
            if isinstance(value,str) and value.startswith('$step'):
                index = int(value[5:])-1
                ids = set()
                for row in outputs[index]:
                    ids.update(row.get('entity_uids') or ([row['uid']] if row.get('uid') else []))
                if len(ids)>25 and partial is not None:
                    partial.append(index)
                return sorted(ids)[:25]
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

    def _listing(self,intent: str,uid: str,candidates: list,rows: list[dict],result: dict) -> tuple[str,dict]:
        """The answer to a one-entity list question, written in code, and the same list for the
        web page (D124). One query returns at most 25 rows; when it is full, the number
        recorded is counted by a second query and the first 25 by name are listed."""
        # One row per target and source: an entity recorded by two sources is listed once,
        # in conflict when either record is.
        listed = {}
        for row in rows:
            item = listed.setdefault(row.get('uid') or row.get('name'),
                                     {'name':row.get('name') or row.get('uid'),'uid':row.get('uid'),'conflict':False})
            item['conflict'] |= bool(row.get('conflict'))
        items = list(listed.values())
        total = len(items)
        if len(rows)>=25:
            query,params = templates.query(intent,[uid],count=True)
            counted = self.store.run_generated(query,params)
            name = self.linker.entities.get(uid,{}).get('name',uid)
            result['cypher'].append(counted.stmt)
            result['queries'].append({'cypher':counted.stmt,'params':params,
                                      'description':templates.describe(intent,[name],True)})
            total = max(total,int((counted.rows or [{}])[0].get('count') or 0))
        result['truncated'] |= total>len(items)
        anchor = self._written({c.uid:c for c in candidates},uid)
        return (templates.list_answer(intent,anchor,[item['name'] for item in items],total),
                {'summary':templates.list_summary(intent,anchor,total),'items':items,'total':total})

    def _related(self,subject,intent: str | None) -> list[dict]:
        """Up to three template questions about the answered entity that the graph has
        records for (D125); none when they cannot be counted."""
        offered = [i for i in RELATED.get(subject.label,()) if i!=intent]
        try:
            rows = self.store.read(templates.counts(subject.label,offered),{'uid':subject.uid}) if offered else []
        except Exception:
            return []
        found = rows[0] if rows and isinstance(rows[0],dict) else {}
        return [{'intent':i,'question':intents.phrase(i,subject)} for i in offered
                if isinstance(found.get(i),int) and found[i]>0][:3]

    def _written(self,by_uid: dict,uid: str) -> str:
        """The name as the user wrote it, with the catalog name when they differ (D112)."""
        name = self.linker.entities.get(uid,{}).get('name',uid)
        candidate = by_uid.get(uid)
        mention = candidate.mention if candidate and candidate.method=='exact' else None
        if mention and normalize(mention)!=normalize(name):
            return f'{mention} ({name})'
        return name

    def _conflicting_claims(self,candidates,rows,intent,target=None):
        if intent not in {'indications','drugs_for','contraindications','contraindicated_drugs'} and not any(
            r.get('conflict') for r in rows):
            return [],False
        anchors = [c.uid for c in candidates if not c.ambiguous]
        # A pair check concerns only its own pair, even when no row was returned (D112).
        targets = [target] if target else sorted({r['uid'] for r in rows if r.get('uid')})[:25]
        if not anchors:
            return [],False
        claims = self.store.read('MATCH (a:Drug)-[r:INDICATED_FOR|CONTRAINDICATED_FOR]->(b:Disease) '
            'WHERE r.conflict=true AND ((a.uid IN $anchors AND (size($targets)=0 OR b.uid IN $targets)) '
            'OR (b.uid IN $anchors AND (size($targets)=0 OR a.uid IN $targets))) '
            'RETURN a.uid AS subject_uid,a.name AS subject,b.uid AS object_uid,b.name AS object,'
            'type(r) AS relation,r.source AS source,r.evidence AS evidence,true AS conflict LIMIT 26',
            {'anchors':anchors[:25],'targets':targets})
        return claims[:25],len(claims)>25

    def _hybrid_tool(self,name: str,args: dict):
        if self.settings.phase<3:
            raise ValueError('Hybrid tools disabled')
        from medkg.retrieval import expand, fulltext, vector
        return {'expand':expand.search,'fulltext':fulltext.search,'vector_search':vector.search}[name](
            self.store,**args,**({'mode':self.mode} if name=='vector_search' else {}))

    def _finish(self,result: dict,start: float,before: dict) -> dict:
        if result['failure_stage']:
            result['response_status'] = 'error'
        elif result['route'] in ('safety','language','scope') or (
                result['safety']!='none' and result.get('safety_mode')!='caveat'):
            result['response_status'] = 'refused'
        elif result['refused'] or answer.unsupported_response(result['answer']):
            result.update(response_status='unsupported',refused=True)
        else:
            result['response_status'] = 'answered'
        result['latency_s'] = time.perf_counter()-start
        result['usage'] = {k:self.llm.usage[k]-before[k] for k in before}
        result['executed_statements'] = list(getattr(self.store,'executed_statements',result['cypher']))
        with span('request.result',route=result['route'],rows=len(result['contexts']),
                  safety_category=result['safety'],failure_stage=result['failure_stage'] or '',
                  error_type=result.get('error_type',''),request_latency_s=result['latency_s'],
                  **result['usage']):
            pass
        return result


# The questions offered after an answer, by the label of the answered entity, in this order (D125).
RELATED = {
    'Drug': ('indications','side_effects','interactions','contraindications','targets'),
    'Disease': ('drugs_for','phenotypes','genes','subtypes','contraindicated_drugs'),
    'Phenotype': ('diseases_for','drugs_with_side_effect'),
    'Gene': ('associated_diseases','targeting_drugs'),
}


def notes(notices: list[str],cautions: list[str]) -> list[dict]:
    """The notices in front of an answer, for the web page: a caution (safety) or a note on
    how the question was read (a corrected name, the question answered) (D125)."""
    return [{'kind':'caution' if notice in cautions else 'reading','text':line}
            for notice in notices for line in notice.split('\n') if line.strip()]


def topic_titles(store) -> dict[str,set[str]]:
    """Normalized MedlinePlus topic titles and the entities each page is about (D121)."""
    titles = {}
    for row in store.read('MATCH (d:Document {source:"medlineplus"}) OPTIONAL MATCH (d)-[:ABOUT]->(e) '
                          'RETURN d.title AS title,collect(e.uid) AS about',{}):
        key = normalize(row.get('title') or '')
        if key:
            titles.setdefault(key,set()).update(row.get('about') or [])
    return titles


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
