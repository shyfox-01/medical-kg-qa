"""One reasoning chain from the question to the answer (D127), fictional entities only."""

import copy
import json

from medkg.graph.guard import CypherRejected
from medkg.graph.store import QueryResult
from medkg.qa import chain
from tests.unit.test_review_regressions import Model, app

QUESTION = 'Explain how Asterol and Brinex compare.'
BOTH = ['fiction:drug-a','fiction:drug-b']


class Script(Model):
    """Replies in order through native tool calls; keeps every conversation it was sent.
    A step is a tool call, a string is answer text, and a dict with tool_calls is sent as it is."""

    def __init__(self,*replies):
        super().__init__()
        self.replies,self.seen = list(replies),[]

    def call(self,messages,tools,*args,**kwargs):
        self.usage['calls'] += 1
        self.seen.append(copy.deepcopy(messages))
        self.thinking = [*getattr(self,'thinking',[]),kwargs.get('think',False)]
        reply = self.replies.pop(0)
        if reply is None:
            raise ValueError('Empty completion')   # as the client reports a reply with nothing in it
        if isinstance(reply,str):
            return {'content':reply,'tool_calls':[]}
        if 'tool_calls' in reply:
            return reply
        arguments = json.dumps({'thought':reply['thought'],**reply['args']})
        return {'content':'','tool_calls':[{'id':f'call_{self.usage["calls"]}','name':reply['tool'],
                                            'arguments':arguments}]}


def step(tool,thought='',**args):
    return {'thought':thought,'tool':tool,'args':args}


def ask(monkeypatch,model,question=QUESTION):
    pipeline = app(monkeypatch,model)
    pipeline.settings.reasoning = 'chain'
    return pipeline,pipeline.ask(question)


def test_one_conversation_carries_the_question_to_its_answer(monkeypatch):
    model = Script(step('relation','Both side effect lists are needed.',intent='side_effects',uids=BOTH),
                   'Each drug has one recorded side effect:\n- Asterol: Amber spots\n- Brinex: Indigo spots')
    _,result = ask(monkeypatch,model)
    assert result['route']=='chain' and result['response_status']=='answered'
    assert result['answer'].startswith('Each drug has one recorded side effect:\n- Asterol: Amber spots')
    assert model.usage['calls']==2
    # The answer is written in the same conversation: the first call and its observation are there.
    second = model.seen[1]
    assert second[2]['role']=='assistant' and 'Both side effect lists are needed.' in json.dumps(second[2]['tool_calls'])
    assert second[3]['role']=='tool' and second[3]['tool_call_id']==second[2]['tool_calls'][0]['id']
    assert second[3]['content'].startswith('Observation 1. The rows are side effects')
    assert 'Asterol: Amber spots' in second[3]['content'] and 'Brinex: Indigo spots' in second[3]['content']
    assert [s['tool'] for s in result['chain']]==['relation','answer']
    assert result['chain'][0]['thought']=='Both side effect lists are needed.'
    assert result['queries'][0]['description'].startswith('The rows are side effects')
    assert {'Amber spots','Indigo spots'} <= {r.get('name') for r in result['contexts']}


def test_invalid_and_empty_replies_are_answered_in_the_chain(monkeypatch):
    broken = {'content':'','tool_calls':[{'id':'c2','name':'relation','arguments':'{"intent": '}]}
    model = Script('Asterol is better.',broken,{'content':'','tool_calls':[]},
                   step('relation',intent='side_effects',uids=BOTH),
                   'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert result['response_status']=='answered' and model.usage['calls']==5
    assert 'Not done: no observation has records yet' in model.seen[1][-1]['content']
    assert model.seen[2][-1]=={'role':'tool','tool_call_id':'c2',
                               'content':'Not done: the arguments of relation are not a JSON object.'}
    assert 'the reply was empty or could not be read' in model.seen[3][-1]['content']


def test_too_many_invalid_replies_end_in_an_answer_or_a_decline(monkeypatch):
    empty = {'content':'','tool_calls':[]}
    model = Script(step('relation',intent='side_effects',uids=BOTH),empty,empty,empty,empty,
                   'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert result['chain_fallback']=='invalid_replies' and result['response_status']=='answered'
    assert model.seen[-1][-1]['content'].startswith('No more lookups. Reply now with the answer text')
    _,declined = ask(monkeypatch,Script(empty,empty,empty,empty))
    assert declined['answer'].startswith(chain.DECLINE) and declined['decline_reason']=='no valid lookup'


def test_a_repeated_lookup_is_sent_back_to_its_observation(monkeypatch):
    look = step('relation',intent='side_effects',uids=BOTH)
    model = Script(look,look,'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert 'this repeats observation 1' in model.seen[2][-1]['content']
    assert result['response_status']=='answered' and len(result['queries'])==1


def test_a_call_written_as_json_text_is_still_a_call():
    reply = {'content':'```json\n{"tool": "text", "thought": "Look.", "args": {"query": "One\nTwo"}}\n```'}
    assert chain.action(reply)==('Look.','text',{'query':'One\nTwo'},None)


def test_a_decline_is_a_decline(monkeypatch):
    model = Script(step('cannot_answer',reason='No comparison is recorded.'))
    _,result = ask(monkeypatch,model)
    assert result['answer'].startswith(chain.DECLINE) and result['refused']
    assert result['response_status']=='unsupported' and result['decline_reason']=='No comparison is recorded.'


def test_a_decline_written_as_text_is_a_decline(monkeypatch):
    model = Script('I cannot answer this from the provided evidence.')
    _,result = ask(monkeypatch,model)
    assert result['answer'].startswith(chain.DECLINE) and model.usage['calls']==1


def test_text_before_any_record_is_asked_once_then_declined(monkeypatch):
    model = Script('Asterol is better.','Asterol is still better.')
    _,result = ask(monkeypatch,model)
    assert result['answer'].startswith(chain.DECLINE) and model.usage['calls']==2


def test_the_last_entity_of_a_generated_row_is_its_result():
    row = {'drug_uid':'fiction:drug-a','drug_name':'Asterol','phenotype_uid':'fiction:phenotype-a',
           'phenotype_name':'Amber spots'}
    named = chain.named(row)
    assert (named['uid'],named['name'])==('fiction:phenotype-a','Amber spots')
    assert chain.line(named)=='Amber spots [fiction:phenotype-a] (drug_name Asterol)'


def test_an_answer_that_uses_none_of_the_last_list_is_asked_back(monkeypatch):
    model = Script(step('relation',intent='interactions',uids=['fiction:drug-a']),
                   step('relation',intent='side_effects',uids=BOTH),
                   'The records do not compare them.','Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert ('Check: observation 2 records 2 entities, and the answer names none of them'
            in model.seen[-1][-1]['content'])
    assert result['answer'].startswith('Amber spots and Indigo spots are recorded.') and result['answer_revised']


def test_an_unsupported_name_gets_one_revision_in_the_chain(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=BOTH),
                   '- Amber spots\n- Orion syndrome','- Amber spots\n- Indigo spots')
    _,result = ask(monkeypatch,model)
    assert 'Check: the answer names ["Orion syndrome"]' in model.seen[2][-1]['content']
    assert result['answer_revised'] and 'Orion syndrome' not in result['answer']


def test_a_name_still_unsupported_after_the_revision_is_removed(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=BOTH),
                   '- Amber spots\n- Orion syndrome','- Amber spots\n- Orion syndrome')
    _,result = ask(monkeypatch,model)
    assert 'Orion syndrome' not in result['answer'] and 'Some entries were removed' in result['answer']


def test_what_the_question_names_is_not_unsupported(monkeypatch):
    text = 'Neither is recorded for Orion syndrome; Amber spots and Indigo spots are recorded.'
    model = Script(step('relation',intent='side_effects',uids=BOTH),text,text)
    _,result = ask(monkeypatch,model,'Explain how Asterol and Brinex compare in Orion syndrome.')
    # Orion syndrome is asked about once (no lookup used it), then the same answer stands.
    assert 'Check: the question also names ["Orion syndrome"], which no lookup used' in model.seen[2][-1]['content']
    assert 'answer_revised' not in result and model.usage['calls']==3 and result['answer'].startswith(text)


def test_a_condition_no_lookup_used_is_looked_up(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=['fiction:drug-a']),'Amber spots is recorded.',
                   step('relation',intent='side_effects',uids=['fiction:drug-b']),
                   'Asterol has Amber spots and Brinex has Indigo spots.')
    _,result = ask(monkeypatch,model)
    assert 'Check: the question also names ["Brinex"]' in model.seen[2][-1]['content']
    assert [s['tool'] for s in result['chain']]==['relation','relation','answer']
    assert result['answer'].startswith('Asterol has Amber spots and Brinex has Indigo spots.')


def test_a_lookup_can_use_the_entities_of_an_earlier_observation(monkeypatch):
    # Interactions of Asterol return Asterol and Brinex; ["$1"] asks for their side effects.
    model = Script(step('relation',intent='interactions',uids=['fiction:drug-a']),
                   step('relation',intent='side_effects',uids=['$1']),
                   'Amber spots is recorded.')
    _,result = ask(monkeypatch,model)
    assert result['queries'][1]['params']['uids']==BOTH
    # The chained result answers the question, so every name in it is reported (D087).
    assert result['answer_completed']=='appended' and 'Indigo spots' in result['answer']


def test_unknown_uids_wrong_labels_and_label_targets_are_sent_back(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=['fiction:nobody']),
                   step('relation',intent='drugs_for',uids=BOTH),
                   step('relation',intent='side_effects',uids=['fiction:drug-a'],target='Phenotype'),
                   step('relation',intent='side_effects',uids=BOTH),
                   'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert "unknown uids ['fiction:nobody']" in model.seen[1][-1]['content']
    assert 'drugs_for needs Disease uids' in model.seen[2][-1]['content']
    # An argument the tool does not take is left out: the third reply is an ordinary lookup.
    assert model.seen[3][-1]['content'].startswith('Observation 1. The rows are side effects')
    assert 'target' not in result['queries'][0]['params']
    assert result['response_status']=='answered'


def test_a_rejected_query_is_sent_back_to_be_repaired(monkeypatch):
    model = Script(step('cypher',query='MATCH (n) DETACH DELETE n'),
                   step('relation',intent='side_effects',uids=BOTH),
                   'Amber spots and Indigo spots are recorded.')
    pipeline = app(monkeypatch,model)
    pipeline.settings.reasoning = 'chain'
    run = pipeline.store.run_generated

    def guarded(statement,params):
        if 'DELETE' in statement:
            raise CypherRejected('Write and procedure operations are not allowed')
        return run(statement,params)
    pipeline.store.run_generated = guarded
    result = pipeline.ask(QUESTION)
    assert 'Not done: Write and procedure operations are not allowed' in model.seen[1][-1]['content']
    assert result['response_status']=='answered'


def test_lookups_are_capped(monkeypatch):
    looks = [step('relation',intent=intent,uids=BOTH)
             for intent in ('targets','indications','contraindications','side_effects','off_label')]
    model = Script(*looks,'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert 'No lookups remain' in model.seen[4][-1]['content']
    assert 'no lookups remain' in model.seen[5][-1]['content']
    assert sum(s['tool']=='relation' for s in result['chain'])==4


def test_older_observations_are_shortened_to_stay_inside_the_window(monkeypatch):
    passages = [{'uid':f'chunk:{i}','text':'word '*400,'title':f'Page {i}','source':'medlineplus',
                 'url':f'https://medlineplus.gov/{i}.html','section':'summary'} for i in range(4)]
    model = Script(step('text',query='Asterol'),step('text',query='Brinex'),'Asterol and Brinex are described.')
    pipeline = app(monkeypatch,model)
    pipeline.settings.reasoning = 'chain'
    pipeline._hybrid_tool = lambda name,args: QueryResult(passages,'')
    opening = [{'role':'system','content':chain.system()},{'role':'user','content':'x'*200}]
    # Room for one full search, not two.
    pipeline.settings.llm_context = chain.tokens(opening)+chain.COMPLETION+1200
    pipeline.ask(QUESTION)
    last = [m['content'] for m in model.seen[-1] if (m['content'] or '').startswith('Observation')]
    assert last[0].endswith('(passages shortened)') and not last[1].endswith('(passages shortened)')


def test_graph_results_are_summarised_for_the_model():
    rows = [{'uid':f'p:{i}','name':f'Spot {i:02d}','source':'primekg'} for i in range(25)]
    full,short = chain.graph_facts(1,'The rows are side effects of Asterol.',rows,58)
    assert '58 recorded; the first 25 by name: Spot 00 [p:0]; Spot 01 [p:1]' in full
    assert full.endswith('Sources: PrimeKG. "$1" stands for all of these entities, in a lookup or in the answer.')
    assert 'Spot 07 [p:7] …' in short and 'Spot 08' not in short
    assert chain.graph_facts(2,'The rows are genes of Orion syndrome.',[])[0].endswith(
        'No rows: nothing of this is recorded in the graph.')
    assert chain.line({'name':'Asterol','conflict':True,'kind':'enzyme'})=='Asterol (kind enzyme) [sources disagree]'


def test_generated_columns_read_as_uid_and_name():
    row = chain.named({'drug_uid':'fiction:drug-a','drug_name':'Asterol','interaction_source':'fictional'})
    assert row=={'uid':'fiction:drug-a','name':'Asterol','interaction_source':'fictional'}
    assert chain.line(row)=='Asterol [fiction:drug-a] (interaction_source fictional)'


def test_the_answer_gives_a_list_by_its_reference(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=BOTH),
                   'Each drug has one recorded side effect:\n$1\nBoth are recorded in PrimeKG [fiction:drug-a].')
    _,result = ask(monkeypatch,model)
    assert result['answer'].startswith('Each drug has one recorded side effect:\n'
                                       '- Asterol: Amber spots\n- Brinex: Indigo spots\nBoth are recorded in PrimeKG.')
    assert model.usage['calls']==2 and 'answer_completed' not in result


def test_a_reference_answers_even_when_it_is_not_the_last_list(monkeypatch):
    model = Script(step('relation',intent='interactions',uids=['fiction:drug-a']),
                   step('relation',intent='side_effects',uids=['fiction:drug-a']),
                   'Two drugs are recorded:\n- $1')
    _,result = ask(monkeypatch,model)
    assert result['answer'].startswith('Two drugs are recorded:\n- Asterol\n- Brinex')
    assert model.usage['calls']==3 and 'answer_revised' not in result


def test_references_to_several_observations_and_to_none(monkeypatch):
    model = Script(step('relation',intent='interactions',uids=['fiction:drug-a']),
                   step('relation',intent='side_effects',uids=['$1','$3']),
                   step('relation',intent='side_effects',uids=['$1','fiction:drug-a']),
                   'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert 'there is no observation 3: one "$N" stands for every entity' in model.seen[2][-1]['content']
    assert result['queries'][1]['params']['uids']==BOTH


def test_a_call_without_its_query_says_what_it_gave():
    reply = {'tool_calls':[{'name':'cypher','arguments':{'thought':'x','cypher':'MATCH (n) RETURN n'}}]}
    try:
        chain.action(reply)
    except ValueError as exc:
        assert str(exc)=="cypher takes ['query'] and optionally ['params']; the call gave ['cypher']"
    else:
        raise AssertionError('a call without its query was accepted')
    # Arguments wrapped in the params object are unwrapped.
    wrapped = {'tool_calls':[{'name':'cypher','arguments':{'params':{'query':'MATCH (n) RETURN n','thought':'x'}}}]}
    assert chain.action(wrapped)==('x','cypher',{'query':'MATCH (n) RETURN n'},wrapped['tool_calls'][0])


def test_generated_queries_are_checked_before_they_run(monkeypatch):
    model = Script(step('cypher',query="MATCH (d:Drug {uid:'DrugBank:DB99999'}) RETURN d.uid AS uid"),
                   step('cypher',query='MATCH (d:Drug {uid:$drug}) RETURN d.uid AS uid'),
                   step('cypher',query='MATCH (d:Drug {uid:$drug}) RETURN d.uid AS uid',params={'drug':'drugbank:A'}),
                   step('relation',intent='side_effects',uids=BOTH),
                   'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    told = [model.seen[i][-1]['content'] for i in range(1,4)]
    assert "unknown uids ['DrugBank:DB99999']; use the uids of the linked entities or of the observations" in told[0]
    assert 'the query uses $drug: give their values in params' in told[1]
    assert "unknown uids ['drugbank:A']" in told[2]
    assert len(result['queries'])==1 and result['response_status']=='answered'


def test_rows_that_are_the_starting_entity_are_sent_back(monkeypatch):
    model = Script(step('cypher',query="MATCH (d:Drug {uid:'fiction:drug-a'})-->(x) RETURN d.uid AS uid, d.name AS name"),
                   step('relation',intent='side_effects',uids=BOTH),
                   'Amber spots and Indigo spots are recorded.')
    pipeline = app(monkeypatch,model)
    pipeline.settings.reasoning = 'chain'
    run = pipeline.store.run_generated

    def generated(statement,params):
        if '-->' in statement:
            return QueryResult([{'uid':'fiction:drug-a','name':'Asterol'}]*2,statement)
        return run(statement,params)
    pipeline.store.run_generated = generated
    result = pipeline.ask(QUESTION)
    assert ('every row is Asterol itself: return uid and name of the entities the question asks for'
            in model.seen[1][-1]['content'])
    assert result['response_status']=='answered'


def test_list_columns_are_shown():
    row = {'uid':'fiction:drug-a','name':'Asterol','diseases':['Orion syndrome','Vega fever'],'sources':['x']}
    assert chain.line(row)=='Asterol [fiction:drug-a] (diseases Orion syndrome, Vega fever)'


def test_an_empty_reply_is_asked_again_with_thinking(monkeypatch):
    model = Script(None,step('relation',intent='side_effects',uids=BOTH),None,None,
                   'Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert model.thinking==[False,True,False,True,False]
    assert result['chain_rejected']==['empty reply, asked again with thinking','empty reply, asked again with thinking',
                                      'empty reply']
    assert result['response_status']=='answered'


def test_a_list_the_model_finds_does_not_answer_is_not_appended(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=BOTH),
                   'Nothing recorded explains how they compare.',
                   'These side effects do not say how the drugs compare, so nothing recorded answers this.')
    _,result = ask(monkeypatch,model)
    assert 'Check: observation 1 records 2 entities' in model.seen[2][-1]['content']
    assert 'answer_completed' not in result and 'Amber spots' not in result['answer']


def test_uids_are_written_as_recorded_and_queries_follow_the_schema(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=['FICTION:DRUG-A','drug-b']),
                   step('cypher',query="MATCH (d:Drug)-[:INTERACTS_WITH]-(x:Drug) WHERE d.uid IN ['drug-a'] "
                                       "RETURN x.uid AS uid, x.name AS name"),
                   step('cypher',query="MATCH (p:Phenotype)-[:HAS_SIDE_EFFECT]->(d:Drug {uid:$d}) RETURN p.uid AS uid",
                        params={'d':'Fiction:Drug-A'}),
                   'Asterol and Brinex interact; Amber spots and Indigo spots are recorded.')
    _,result = ask(monkeypatch,model)
    assert result['queries'][0]['params']['uids']==BOTH
    assert "WHERE d.uid IN ['fiction:drug-a']" in result['queries'][1]['cypher']
    assert ('the query cannot match: (Phenotype)-[HAS_SIDE_EFFECT]->(Drug), but HAS_SIDE_EFFECT goes from Drug '
            'to Phenotype') in model.seen[3][-1]['content']
    assert chain.mismatches('MATCH (g:Gene)<-[:ASSOCIATED_WITH]-(d:Disease)<-[r:TARGETS]-(b:Drug) RETURN b')==[
        '(Disease)<-[TARGETS]-(Drug), but TARGETS goes from Drug to Gene']
    assert chain.mismatches('MATCH (a:Drug)-[:INTERACTS_WITH]-(b:Drug), (b)-[:INDICATED_FOR]->(:Disease) RETURN b')==[]


def test_parameters_given_beside_the_query_are_its_params():
    reply = {'tool_calls':[{'name':'cypher','arguments':{'thought':'x','query':'MATCH (d:Drug {uid:$drug}) RETURN d',
                                                         'drug':'fiction:drug-a','other':1}}]}
    assert chain.action(reply)[2]=={'query':'MATCH (d:Drug {uid:$drug}) RETURN d','params':{'drug':'fiction:drug-a'}}


def test_an_answer_that_says_none_were_found_is_checked_once(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=BOTH),
                   'No side effects were found for either drug.','Each drug has one recorded side effect:\n$1')
    _,result = ask(monkeypatch,model)
    assert ('Check: the answer says none were found, but observation 1 found 2: ["Amber spots", "Indigo spots"]'
            in model.seen[2][-1]['content'])
    assert model.thinking==[False,False,True]
    assert result['answer'].startswith('Each drug has one recorded side effect:\n- Asterol: Amber spots')
    # Said again after the check, it stands: no other check asks about the same rows.
    model = Script(step('relation',intent='side_effects',uids=BOTH),
                   'No side effects were found for either drug.','None of these compare the drugs.')
    _,result = ask(monkeypatch,model)
    assert model.usage['calls']==3 and result['answer'].startswith('None of these compare the drugs.')
    # "No," answering a yes-or-no question is not a denial of the rows.
    model = Script(step('relation',intent='side_effects',uids=BOTH),'No, Amber spots is recorded only for Asterol.')
    _,result = ask(monkeypatch,model)
    assert model.usage['calls']==2


def test_a_list_written_out_is_not_repeated_by_its_reference(monkeypatch):
    model = Script(step('relation',intent='side_effects',uids=BOTH),
                   'Each drug has one recorded side effect:\n- Asterol: Amber spots\n- Brinex: Indigo spots\n\n$1')
    _,result = ask(monkeypatch,model)
    assert result['answer'].count('Amber spots')==1
    model = Script(step('relation',intent='interactions',uids=['fiction:drug-a']),
                   'One drug is recorded:\n- Brinex (fiction:drug-b)\n$1')
    _,result = ask(monkeypatch,model)
    assert result['answer'].startswith('One drug is recorded:\n- Brinex\n') and '- Asterol' not in result['answer']


def test_a_choice_from_collected_rows_is_not_padded_with_the_rest(monkeypatch):
    query = ("MATCH (d:Drug)-[:INTERACTS_WITH]-(x:Drug) WHERE x.uid IN ['fiction:drug-a','fiction:drug-b'] "
             "RETURN d.uid AS uid, d.name AS name, collect(x.name) AS interacts_with")
    rows = [{'uid':'fiction:drug-a','name':'Asterol','interacts_with':['Brinex','Cetrix']},
            {'uid':'fiction:drug-b','name':'Brinex','interacts_with':['Cetrix']}]
    model = Script(step('cypher',query=query),'Only Asterol interacts with both.\n- Asterol')
    pipeline = app(monkeypatch,model)
    pipeline.settings.reasoning = 'chain'
    pipeline.store.run_generated = lambda statement,params: QueryResult(rows,statement)
    result = pipeline.ask(QUESTION)
    assert 'Rows of the Cypher query; each meets all its conditions.' in model.seen[1][-1]['content']
    assert 'answer_completed' not in result and 'Brinex' not in result['answer']
    # Without a collected column, rows the answer leaves out are still added.
    model = Script(step('cypher',query=query),'Asterol interacts.\n- Asterol')
    pipeline = app(monkeypatch,model)
    pipeline.settings.reasoning = 'chain'
    pipeline.store.run_generated = lambda statement,params: QueryResult([{k: r[k] for k in ('uid','name')} for r in rows],
                                                                        statement)
    result = pipeline.ask(QUESTION)
    assert result['answer_completed']=='appended' and 'Brinex' in result['answer']


def test_a_missing_parameter_is_told_it_can_be_a_reference(monkeypatch):
    query = 'MATCH (d:Drug)-[:INTERACTS_WITH]-(x:Drug) WHERE d.uid IN $drugs RETURN x.uid AS uid, x.name AS name'
    model = Script(step('relation',intent='interactions',uids=['fiction:drug-a']),
                   step('cypher',query=query,params={}),
                   step('cypher',query=query,params={'drugs':['$1']}),
                   'Asterol and Brinex interact.')
    _,result = ask(monkeypatch,model)
    assert ('the query uses $drugs: give their values in params; the entities an observation found are given '
            'as "$N", as in {"drugs": "$1"}') in model.seen[2][-1]['content']
    assert result['queries'][1]['params']['drugs']==BOTH
    # A parameter for one value is not told about lists.
    model = Script(step('relation',intent='interactions',uids=['fiction:drug-a']),
                   step('cypher',query='MATCH (d:Drug {uid:$drug}) RETURN d.uid AS uid',params={}),
                   'Asterol and Brinex interact.')
    ask(monkeypatch,model)
    assert model.seen[2][-1]['content']=='Not done: the query uses $drug: give their values in params.'
    # A call repeated inside its params is the call.
    reply = {'tool_calls':[{'name':'cypher','arguments':{'query':query,'params':{'query':query,'thought':'x',
                                                                                  'drugs':'$1'}}}]}
    assert chain.action(reply)[2]=={'query':query,'params':{'drugs':'$1'}}

