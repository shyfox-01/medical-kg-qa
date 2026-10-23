"""Reversible, pair-specific quarantine from the October 2026 source reviews.

These 39 mappings have positive source evidence against exact identity (28 from
2026-10-09 and 11 from the 2026-10-24 RxNorm review). This is
an engineering exclusion, not clinical validation. The 66 uncertain mappings are
unchanged. Original catalog/source bytes remain available for a later review.
See docs/history/reports/ai-review-2026-10-09.md and decision D072.
"""

from medkg_data.lexicon import normalize

REVIEW_ID = 'ai-source-review-2026-10-09'
EXCLUDED_ALIASES: dict[str, frozenset[str]] = {
    'DrugBank:DB00026': frozenset({
        'il 1ra', 'il1 febrile inhibitor', 'interleukin 1 receptor antagonist protein',
        'urine derived il1 inhibitor', 'urine il 1 inhibitor',
    }),
    'DrugBank:DB00027': frozenset({
        'gramicidin', 'gramicidin a', 'gramicidin a 1', 'gramicidin b', 'gramicidin c',
        'gramicidin j', 'gramicidin k', 'gramicidin nf', 'gramicidin p', 'gramicidin s',
    }),
    'DrugBank:DB00039': frozenset({'fibroblast growth factor 7', 'keratinocyte growth factor'}),
    'DrugBank:DB00105': frozenset({
        'ifn alpha 2', 'interferon alfa 2a', 'interferon alpha 2', 'interferon alpha a',
        'leif a', 'recombinant interferon alpha 2a',
    }),
    'DrugBank:DB00394': frozenset({'beclometasone', 'beclomethasone'}),
    'DrugBank:DB00431': frozenset({
        'benzene hexachloride', 'epsilon hexachlorocyclohexane',
        'eta hexachlorocyclohexane',
    }),
    # 2026-10-24 RxNorm review: all 13 Pentastarch synonyms came from MeSH
    # D006895, a broader hydroxyethyl starch class. Keep Pentaspan/Pentafraction;
    # quarantine the other products/class names. Hetastarch belongs to
    # Hydroxyethyl Starch (DrugBank:DB09106), not Pentastarch.
    'DrugBank:DB09111': frozenset({
        '2 hydroxyethyl starche', 'elohe', 'haes steril', 'hemohe', 'hespan',
        'hetastarch', 'hydroxyethyl starch 130 kd 0 4 substitution',
        'hydroxyethyl starch 130 0 4', 'hydroxyethyl starch derivative',
        'hydroxyethylated starche', 'plasmasteril',
    }),
}


def is_excluded(uid: str, alias: str) -> bool:
    """Exclude a reviewed entity/alias pair, never the alias for every owner."""
    return normalize(alias) in EXCLUDED_ALIASES.get(uid, ())


def allowed_names(entity: dict) -> list[str]:
    """Keep canonical identities and unrelated/uncertain synonyms untouched."""
    return [entity['name'], *(alias for alias in entity.get('synonyms') or []
                             if not is_excluded(entity['uid'], alias))]


def exact_names(entity: dict) -> list[str]:
    """Include exact-only aliases without admitting them to fuzzy/vector matching."""
    return [*allowed_names(entity), *(alias for alias in entity.get('exact_synonyms') or []
                                     if not is_excluded(entity['uid'], alias))]
