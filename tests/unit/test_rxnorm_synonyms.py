"""RxNorm brand joins use small, handwritten RRF records only (D099, D101)."""

from pathlib import Path

import pytest

from medkg_data import synonyms as S

ENTITIES = [
    {'uid': 'DrugBank:DB90001', 'label': 'Drug', 'name': 'Asteric acid', 'synonyms': []},
    {'uid': 'DrugBank:DB90002', 'label': 'Drug', 'name': 'Brinex', 'synonyms': ['Brinexate']},
    {'uid': 'HPO:90001', 'label': 'Phenotype', 'name': 'Brinex', 'synonyms': []},
]

STOP_WORDS = {
    'julie', 'ella', 'nikita', 'muse', 'propel', 'thrive', 'react', 'clarus', 'compro',
    'curae', 'utopic', 'inova', 'allday', 'today', 'focus', 'prevail', 'relief', 'clear',
    'correct', 'ultra',
}

REVIEW_EXCLUSIONS = (
    'Hextend', 'K-Phos', 'Listerine', 'Chloraseptic', 'Aleve Arthritis Pain',
    'Unisom Sleep', 'Clinidine', 'Morning After', 'Option 2', 'My Choice', 'Your Choice',
    'My Way', 'New Day', 'Take Action', 'Her Style', "Doctor's Choice", 'Perfect Choice',
    "Kid's Choice", 'Fiber Choice', 'Deep Sea', 'Sea Soft', 'Simply Sleep', 'Healthy Mama',
    'Comfort Shield', 'Aqua Care', 'The Magic Bullet', 'Acne-Clear', 'Blink Dry Eye',
    'Sojourn', 'P & S', 'Terrell', 'Tobi', 'Dotti', 'Alora', 'Avita', 'Antara', 'Flanders',
    'Medicone', 'Stangard', 'Appearex', 'Vectical', 'OraVerse', 'Mitigare', 'Hurricaine',
    'IsoDitrate',
)

SALT_CATIONS = (
    'potassium', 'sodium', 'calcium', 'magnesium', 'zinc', 'iron', 'lithium',
    'aluminum', 'aluminium', 'ammonium',
)


def conso(rxcui: str, tty: str, name: str, *, sab: str = 'RXNORM',
          suppress: str = 'N') -> str:
    fields = [''] * 18
    fields[0], fields[11], fields[12] = rxcui, sab, tty
    fields[14], fields[16] = name, suppress
    return '|'.join(fields) + '|\n'


def rel(first: str, second: str, *, rela: str = 'tradename_of',
        sab: str = 'RXNORM') -> str:
    fields = [''] * 16
    fields[0], fields[4], fields[7], fields[10] = first, second, rela, sab
    return '|'.join(fields) + '|\n'


def rrf(tmp_path: Path, concepts: list[str], relations: list[str]) -> Path:
    (tmp_path / 'RXNCONSO.RRF').write_text(''.join(concepts), encoding='utf8')
    (tmp_path / 'RXNREL.RRF').write_text(''.join(relations), encoding='utf8')
    return tmp_path


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('relation', ['tradename_of', 'has_tradename'])
def test_single_ingredient_brand_accepts_both_edge_orientations(tmp_path, reverse, relation):
    endpoints = ('10', '20') if reverse else ('20', '10')
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('20', 'BN', 'Brinexa')],
                    [rel(*endpoints, rela=relation)])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == [
        ('DrugBank:DB90002', 'Brinexa', 'rxnorm:20')]


def test_proposals_deduplicate_rows_and_sort_without_counting_duplicate_edges(tmp_path):
    concepts = [conso('10', 'IN', 'Brinex'), conso('11', 'IN', 'Asteric acid'),
                conso('21', 'BN', 'Zenibrand'), conso('20', 'BN', 'Brinexa'),
                conso('22', 'BN', 'Astrabrand'), conso('20', 'BN', 'Brinexa')]
    directory = rrf(tmp_path, concepts, [rel('21', '10'), rel('20', '10'), rel('22', '11'),
                                         rel('20', '10'), rel('10', '20', rela='has_tradename')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == [
        ('DrugBank:DB90001', 'Astrabrand', 'rxnorm:22'),
        ('DrugBank:DB90002', 'Brinexa', 'rxnorm:20'),
        ('DrugBank:DB90002', 'Zenibrand', 'rxnorm:21'),
    ]


@pytest.mark.parametrize('ingredient', ['BRINEX', 'Brinexate', 'Brinex citrate'])
def test_ingredient_joins_drug_names_synonyms_and_terminal_salts(tmp_path, ingredient):
    directory = rrf(tmp_path, [conso('10', 'IN', ingredient), conso('20', 'BN', 'Brinexa')],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == [
        ('DrugBank:DB90002', 'Brinexa', 'rxnorm:20')]


def test_ingredient_matching_accepts_exact_only_aliases(tmp_path):
    entities = [dict(ENTITIES[0], exact_synonyms=['Asterate'])]
    directory = rrf(tmp_path, [conso('10', 'IN', 'ASTERATE'), conso('20', 'BN', 'Astrabrand')],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, entities, set()) == [
        ('DrugBank:DB90001', 'Astrabrand', 'rxnorm:20')]


@pytest.mark.parametrize('field_name', ['synonyms', 'exact_synonyms'])
@pytest.mark.parametrize('legitimate_owner', [False, True])
def test_ingredient_matching_enforces_hetastarch_quarantine(
        tmp_path, field_name, legitimate_owner):
    entities = [{'uid': 'DrugBank:DB09111', 'label': 'Drug', 'name': 'Pentastarch',
                 field_name: ['Hetastarch']}]
    if legitimate_owner:
        entities.append({'uid': 'DrugBank:DB09106', 'label': 'Drug',
                         'name': 'Hydroxyethyl Starch', field_name: ['Hetastarch']})
    directory = rrf(tmp_path, [conso('10', 'IN', 'Hetastarch'),
                               conso('20', 'BN', 'Fictionalbrand')], [rel('20', '10')])
    proposals, report = S.rxnorm_proposal_report(directory, entities, set())
    expected = [('DrugBank:DB09106', 'Fictionalbrand', 'rxnorm:20')] if legitimate_owner else []
    assert proposals == expected
    assert report['rxnorm_excluded_by_rule']['ingredient_unlinked'] == int(not legitimate_owner)


@pytest.mark.parametrize('cation', SALT_CATIONS)
def test_salt_fallback_does_not_link_to_a_bare_cation(tmp_path, cation):
    entities = [{'uid': 'DrugBank:DB90003', 'label': 'Drug', 'name': cation, 'synonyms': []}]
    directory = rrf(tmp_path, [conso('10', 'IN', cation.upper() + ' phosphate'),
                               conso('20', 'BN', 'Mineralbrand')], [rel('20', '10')])
    proposals, report = S.rxnorm_proposal_report(directory, entities, set())
    assert proposals == []
    assert report['rxnorm_excluded_by_rule']['ingredient_unlinked'] == 1


@pytest.mark.parametrize('ingredient', ['potassium', 'potassium phosphate'])
def test_cation_guard_preserves_exact_ingredient_names(tmp_path, ingredient):
    entities = [{'uid': 'DrugBank:DB90003', 'label': 'Drug', 'name': ingredient, 'synonyms': []}]
    directory = rrf(tmp_path, [conso('10', 'IN', ingredient),
                               conso('20', 'BN', 'Mineralbrand')], [rel('20', '10')])
    assert S.rxnorm_proposals(directory, entities, set()) == [
        ('DrugBank:DB90003', 'Mineralbrand', 'rxnorm:20')]


def test_exact_salt_name_takes_precedence_over_active_moiety(tmp_path):
    entities = ENTITIES + [
        {'uid': 'DrugBank:DB90003', 'label': 'Drug', 'name': 'Brinex citrate', 'synonyms': []}]
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex citrate'), conso('20', 'BN', 'Brinexa')],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, entities, set()) == [
        ('DrugBank:DB90003', 'Brinexa', 'rxnorm:20')]


def test_ambiguous_exact_salt_name_is_not_rescued_by_unique_moiety(tmp_path):
    entities = ENTITIES + [
        {'uid': 'DrugBank:DB90003', 'label': 'Drug', 'name': 'Brinex citrate', 'synonyms': []},
        {'uid': 'DrugBank:DB90004', 'label': 'Drug', 'name': 'Other ingredient',
         'synonyms': ['Brinex citrate']},
    ]
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex citrate'), conso('20', 'BN', 'Brinexa')],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, entities, set()) == []


@pytest.mark.parametrize('ingredient', ['Unknown ingredient', 'Shared ingredient'])
def test_unmatched_and_ambiguous_ingredients_are_skipped(tmp_path, ingredient):
    entities = [dict(entity, synonyms=[*entity['synonyms'], 'Shared ingredient'])
                for entity in ENTITIES]
    directory = rrf(tmp_path, [conso('10', 'IN', ingredient), conso('20', 'BN', 'Brinexa')],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, entities, set()) == []


@pytest.mark.parametrize('reason', ['combination', 'unmatched', 'ambiguous', 'no_ingredient'])
@pytest.mark.parametrize('reverse', [False, True])
def test_unsafe_brand_name_vetoes_other_rxcuis_regardless_of_order(tmp_path, reason, reverse):
    entities = ENTITIES + [
        {'uid': 'DrugBank:DB90003', 'label': 'Drug', 'name': 'Shared ingredient', 'synonyms': []},
        {'uid': 'DrugBank:DB90004', 'label': 'Drug', 'name': 'Other ingredient',
         'synonyms': ['Shared ingredient']},
    ]
    concepts = [conso('10', 'IN', 'Brinex'), conso('20', 'BN', 'Star-Brand'),
                conso('21', 'BN', 'STAR BRAND')]
    relations = [rel('20', '10')]
    if reason == 'combination':
        concepts.append(conso('11', 'IN', 'Asteric acid'))
        relations += [rel('21', '10'), rel('21', '11')]
    elif reason in {'unmatched', 'ambiguous'}:
        ingredient = 'Unknown ingredient' if reason == 'unmatched' else 'Shared ingredient'
        concepts.append(conso('11', 'IN', ingredient))
        relations.append(rel('21', '11'))
    if reverse:
        concepts.reverse()
        relations.reverse()
    directory = rrf(tmp_path, concepts, relations)
    assert S.rxnorm_proposals(directory, entities, set()) == []


def test_two_distinct_ingredient_rxcuis_are_unsafe_even_if_they_join_the_same_drug(tmp_path):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('11', 'IN', 'Brinex citrate'),
                               conso('20', 'BN', 'Mixedbrand')],
                    [rel('20', '10'), rel('20', '11')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []


@pytest.mark.parametrize('other_name,accepted', [('Brinexate', True),
                                                ('Asteric acid', False),
                                                ('Unknown ingredient', False)])
def test_multiple_active_spellings_of_one_ingredient_must_resolve_consistently(
        tmp_path, other_name, accepted):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('10', 'IN', other_name),
                               conso('20', 'BN', 'Brinexa')], [rel('20', '10')])
    expected = [('DrugBank:DB90002', 'Brinexa', 'rxnorm:20')] if accepted else []
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == expected


def test_report_accounts_for_each_brand_once_and_global_unsafe_veto(tmp_path):
    concepts = [conso('10', 'IN', 'Brinex'), conso('11', 'IN', 'Asteric acid'),
                conso('12', 'IN', 'Unknown ingredient'), conso('20', 'BN', 'Goodbrand'),
                conso('21', 'BN', 'Mixedbrand'), conso('22', 'BN', 'MIXEDBRAND'),
                conso('23', 'BN', 'Noingredient'), conso('24', 'BN', 'Unresolvedbrand'),
                conso('25', 'BN', 'Julie')]
    relations = [rel('20', '10'), rel('21', '10'), rel('21', '11'), rel('22', '10'),
                 rel('24', '12'), rel('25', '10')]
    directory = rrf(tmp_path, concepts, relations)
    proposals, report = S.rxnorm_proposal_report(directory, ENTITIES, set())
    assert proposals == S.rxnorm_proposals(directory, ENTITIES, set()) == [
        ('DrugBank:DB90002', 'Goodbrand', 'rxnorm:20')]
    assert report['rxnorm_brands_considered'] == 6
    assert report['rxnorm_proposed'] == 1
    excluded = report['rxnorm_excluded_by_rule']
    assert excluded == {
        'no_ingredient': 1, 'multiple_ingredients': 1, 'ingredient_unlinked': 1,
        'ingredient_ambiguous': 0, 'review_excluded': 0, 'unusable': 0,
        'parenthesized_or_reformulated': 0,
        'stop_word': 1, 'lowercase_word': 0, 'unsafe_name': 1,
    }
    assert sum(excluded.values()) + len(proposals) == report['rxnorm_brands_considered']


def test_stop_list_matches_the_manually_reviewed_names():
    assert S.RXNORM_STOP == STOP_WORDS


def test_review_exclusion_list_has_exactly_the_45_reviewed_names():
    assert len(S.RXNORM_EXCLUDE) == len(REVIEW_EXCLUSIONS) == 45
    assert S.RXNORM_EXCLUDE == {S.normalize(name) for name in REVIEW_EXCLUSIONS}


@pytest.mark.parametrize('brand', REVIEW_EXCLUSIONS)
def test_review_exclusions_use_normalized_names_and_are_counted(tmp_path, brand):
    normalized_variant = S.normalize(brand).upper()
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'),
                               conso('20', 'BN', normalized_variant)], [rel('20', '10')])
    proposals, report = S.rxnorm_proposal_report(directory, ENTITIES, set())
    assert proposals == []
    assert report['rxnorm_excluded_by_rule']['review_excluded'] == 1
    assert sum(report['rxnorm_excluded_by_rule'].values()) == 1


@pytest.mark.parametrize('brand', sorted(STOP_WORDS))
def test_reviewed_common_words_and_person_names_are_rejected(tmp_path, brand):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('20', 'BN', brand.upper())],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []


@pytest.mark.parametrize('brand', ['Brinexa (Old)', 'Brinexa REFORMULATED',
                                 'Reformulated Brinexa', 'Brinexa ('])
def test_parenthesized_and_reformulated_brands_are_rejected(tmp_path, brand):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('20', 'BN', brand)],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []


def test_reformulated_filter_requires_a_whole_word(tmp_path):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'),
                               conso('20', 'BN', 'Reformulatedness')], [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == [
        ('DrugBank:DB90002', 'Reformulatedness', 'rxnorm:20')]


@pytest.mark.parametrize('brand', ['', 'ab', 'Brand, Brinex', 'Z' * 61])
def test_brand_must_pass_existing_usable_policy(tmp_path, brand):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('20', 'BN', brand)],
                    [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []


def test_lowercase_corpus_words_only_veto_normalized_single_word_brands(tmp_path):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('20', 'BN', 'BRINEXA'),
                               conso('21', 'BN', 'Brinexa Plus'),
                               conso('22', 'BN', 'Brinexa-Plus')],
                    [rel('20', '10'), rel('21', '10'), rel('22', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, {'brinexa', 'plus'}) == [
        ('DrugBank:DB90002', 'Brinexa Plus', 'rxnorm:21'),
        ('DrugBank:DB90002', 'Brinexa-Plus', 'rxnorm:22'),
    ]


@pytest.mark.parametrize('suppressed_tty', ['BN', 'IN'])
@pytest.mark.parametrize('suppress', ['Y', 'O', 'E'])
def test_suppressed_concepts_cannot_supply_brands_or_ingredients(tmp_path, suppressed_tty, suppress):
    concepts = [conso('10', 'IN', 'Brinex', suppress=suppress if suppressed_tty == 'IN' else 'N'),
                conso('20', 'BN', 'Brinexa', suppress=suppress if suppressed_tty == 'BN' else 'N')]
    directory = rrf(tmp_path, concepts, [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []


@pytest.mark.parametrize('suppress', ['', 'N'])
def test_empty_and_n_suppress_values_are_accepted(tmp_path, suppress):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex', suppress=suppress),
                               conso('20', 'BN', 'Brinexa', suppress=suppress)], [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == [
        ('DrugBank:DB90002', 'Brinexa', 'rxnorm:20')]


@pytest.mark.parametrize('foreign_row', ['brand', 'ingredient', 'relation'])
def test_non_rxnorm_rows_are_ignored_in_both_rrf_files(tmp_path, foreign_row):
    directory = rrf(tmp_path, [
        conso('10', 'IN', 'Brinex', sab='OTHER' if foreign_row == 'ingredient' else 'RXNORM'),
        conso('20', 'BN', 'Brinexa', sab='OTHER' if foreign_row == 'brand' else 'RXNORM'),
    ], [rel('20', '10', sab='OTHER' if foreign_row == 'relation' else 'RXNORM')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []


@pytest.mark.parametrize('brand_tty,ingredient_tty', [('BN', 'PIN'), ('BN', 'SCD'),
                                                   ('SBD', 'IN'), ('BN', 'BN'), ('IN', 'IN')])
def test_only_brand_to_ingredient_edges_count(tmp_path, brand_tty, ingredient_tty):
    directory = rrf(tmp_path, [conso('10', ingredient_tty, 'Brinex'),
                               conso('20', brand_tty, 'Brinexa')], [rel('20', '10')])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []


@pytest.mark.parametrize('relation', ['has_ingredient', 'ingredient_of', ''])
def test_non_tradename_relations_do_not_establish_brand_joins(tmp_path, relation):
    directory = rrf(tmp_path, [conso('10', 'IN', 'Brinex'), conso('20', 'BN', 'Brinexa')],
                    [rel('20', '10', rela=relation)])
    assert S.rxnorm_proposals(directory, ENTITIES, set()) == []
