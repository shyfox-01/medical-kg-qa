"""The final graph query's result entities are always reported (D087), fictional entities only."""

from medkg.qa.answer import ensure_reported
from tests.unit.test_review_regressions import Model, app, both


def test_complete_answers_are_unchanged():
    assert ensure_reported('Asterol and Brinex are listed.',['Asterol','Brinex'])==(
        'Asterol and Brinex are listed.',None)
    assert ensure_reported('anything',[])==('anything',None)


def test_missing_names_are_appended_once():
    text,done = ensure_reported('Asterol is indicated.',['Asterol','Brinex','Brinex',None])
    assert done=='appended' and text.endswith('Also recorded in the knowledge graph: Brinex.')


def test_an_answer_naming_no_result_is_replaced_by_the_results():
    text,done = ensure_reported('There are no drugs listed for this disease.',['Asterol','Brinex'])
    assert done=='replaced' and text.splitlines()[1:]==['- Asterol','- Brinex']


def test_name_matching_ignores_case_and_punctuation():
    assert ensure_reported('ASTEROL, brinex.',['Asterol','Brinex'])[1] is None


def test_a_name_inside_a_longer_reported_name_is_still_missing():
    text,done = ensure_reported('- late onset Orion fever',['late onset Orion fever','Orion fever'])
    assert done=='appended' and text.endswith('Also recorded in the knowledge graph: Orion fever.')
    assert ensure_reported('Orion fever; late onset Orion fever',['late onset Orion fever','Orion fever'])[1] is None


def test_pipeline_appends_what_the_model_left_out(monkeypatch):
    result = app(monkeypatch,Model(text='Asterol is recorded.',plan=both('indications'))).ask(
        'What are Asterol and Brinex indicated for?')
    assert result['answer_completed']=='appended' and 'Brinex' in result['answer']


def test_count_answers_are_not_completed(monkeypatch):
    class CountStore:
        executed_statements = []

        def read(self,*args,**kwargs):
            return []

        def run_generated(self,statement,params):
            from medkg.graph.store import QueryResult
            return QueryResult([{'count':2,'sources':['fictional']}],statement)
    pipeline = app(monkeypatch,Model(text='Count: 2'))
    pipeline.store = CountStore()
    result = pipeline.ask('How many diseases is Asterol indicated for?')
    assert 'answer_completed' not in result and result['answer'].startswith('Count: 2')


def test_safety_refusal_is_not_overridden(monkeypatch):
    result = app(monkeypatch,Model(text='Take two tablets of Asterol daily.',plan=both('indications'))).ask(
        'What are Asterol and Brinex indicated for?')
    assert result['refused'] and result['safety']=='dosage' and 'answer_completed' not in result


def test_uid_mentions_decide_completeness():
    from medkg.qa.linker import Linker
    from medkg.qa.verify import entities_in_text
    entities = [{'uid':'fiction:group','label':'Disease','name':'Orion fever',
                 'synonyms':['late onset Orion fever']},
                {'uid':'fiction:late','label':'Disease','name':'late onset Orion fever',
                 'synonyms':['Orion fever caused by ORX1']},
                {'uid':'fiction:lyra','label':'Disease','name':'Lyra disease','synonyms':['LD-7 syndrome']}]
    linker = Linker(entities)
    # A shared name credits the entity whose own name it is; an echoed synonym that
    # contains "Orion fever" does not report the group.
    answer = '- late onset Orion fever (Orion fever caused by ORX1)\n- LD-7 syndrome'
    mentioned = entities_in_text(answer,linker)
    assert mentioned=={'fiction:late','fiction:lyra'}
    text,done = ensure_reported(answer,['Orion fever','late onset Orion fever','Lyra disease'],
                                ['fiction:group','fiction:late','fiction:lyra'],mentioned)
    assert done=='appended' and text.endswith('Also recorded in the knowledge graph: Orion fever.')


def test_a_new_list_line_ends_a_name_spelt_with_a_comma():
    from medkg.qa.linker import Linker
    from medkg.qa.verify import entities_in_text, verify_answer
    linker = Linker([{'uid':'fiction:gasp','label':'Phenotype','name':'Orion gasp','synonyms':[]},
                     {'uid':'fiction:central','label':'Phenotype','name':'Central Orion gasp','synonyms':[]},
                     {'uid':'fiction:inverted','label':'Disease','name':'Orion gasp, central','synonyms':[]}])
    rows = [{'uid':'fiction:gasp','name':'Orion gasp'},{'uid':'fiction:central','name':'Central Orion gasp'}]
    answer = 'Recorded phenotypes:\n- Orion gasp\n- Central Orion gasp'
    mentioned = entities_in_text(answer,linker)
    assert mentioned=={'fiction:gasp','fiction:central'}
    assert entities_in_text('Orion gasp, central is recorded.',linker)=={'fiction:inverted'}

    class Model:
        def chat(self,messages):
            raise AssertionError('a supported list needs no revision')
    # Neither a false unsupported entity (a revision call) nor a falsely missing row.
    assert verify_answer(Model(),'Which phenotypes?',answer,rows,linker)==answer
    assert ensure_reported(answer,[r['name'] for r in rows],[r['uid'] for r in rows],mentioned)==(answer,None)


def test_short_symbols_fall_back_to_text_matching():
    assert ensure_reported('- AR\n- ORX1',['AR','ORX1'],['fiction:ar','fiction:orx1'],{'fiction:orx1'})[1] is None
