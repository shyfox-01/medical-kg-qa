"""Shared lexical rules for matching catalog aliases inside free English text.

Ontology synonyms include acronyms and gene symbols that are also ordinary
English words (WAS, HAS, LET, TEN, SET). In free text such an alias counts as an
entity mention only when it is written as an acronym, i.e. in upper case. Both
the QA linker/verifier and the independent scorer apply this rule.
"""

import re

GENERIC_ANCHORS = frozenset({
    'disease', 'diseases', 'condition', 'conditions', 'disorder', 'disorders',
    'medical condition', 'disease or disorder', 'diseases and disorders', 'other disease',
    # "syndrome" is a synonym of the MONDO class "syndromic disease" (D093).
    'syndrome', 'syndromes',
})

# Common English words that collide with catalog aliases. Deliberately excludes
# words that users write in lower case to mean a medical concept (cold, pain,
# itch, rash, scar, ache, fever ...).
COMMON_WORDS = frozenset('''
a an the this that these those i me my mine we us our ours you your yours he him his she her
hers it its they them their theirs who whom whose which what where when why how all any both
each every either neither few more most less least other another some such no nor not only own
same so than too very just also then there here now once again ever never always often still
yet else even much many

one two three four five six seven eight nine ten eleven twelve twenty thirty forty fifty
hundred thousand first second third last next half

about above across after against along among around as at before behind below beneath beside
between beyond but by down during except for from in inside into like near of off on onto out
outside over past per since through throughout till to toward towards under until up upon via
with within without and or if because while although though unless whether whereas

am is are was were be been being have has had having do does did doing done can could will
would shall should may might must ought need dare

get gets got gotten getting let lets letting make makes made making put puts putting set sets
setting run runs ran running go goes went gone going come comes came coming take takes took
taken taking give gives gave given giving see sees saw seen seeing know knows knew known say
says said tell tells told ask asks asked use uses used using find finds found keep keeps kept
help helps show shows showed shown try tries tried call calls called want wants wanted look
looks looked feel feels felt seem seems seemed leave leaves left hold holds held bring brings
brought begin began begun turn turns turned move moves moved live lives lived play plays played
pay pays paid meet meets met sit sat stand stood lose lost add adds added cut cuts hit hits beat
fit fits mean means meant read reads sell sells sold send sends sent build built buy bought cast
rest plan plans scan scans work works worked change changes act acts aim aims end ends start
starts stop stops open opens close closes fill fix pass test tests check checks report reports
list lists note notes sign signs mark marks link links map maps form forms place point points
track type types cover covers care cares win won hope hoped wish lead led

bad good big small large high low long short new old young great little max min mad sad hot cold
top red best better worst worse full free fine real sure able ready

man men woman women kid kids son sons daughter mom dad baby cat cats dog dogs pan pans pin pins
hat hats jet jets kit kits tank tanks cap caps app apps ace aces gal day days week weeks year
years time times way ways thing things part parts side sides air fire fires sea sun car cars bed
beds box home house job jobs key keys line lines name names number numbers people person
world area areas case cases group groups problem problems question questions fact facts eye
'''.split())

# 'cold' is listed because the bare word is far more often the adjective; the
# common cold is still matched by its multi-word aliases ("common cold").


LIST_BREAK = re.compile(r'[,;\n\u2022]')
# A line break or bullet starts the next list item: it ends every name, even one whose
# own spelling has a comma ("apnea, central sleep" is not "Apnea\n- Central sleep apnea", D126).
ITEM_BREAK = re.compile(r'[\n\u2022]')


def list_breaks(text: str, separator: re.Pattern = LIST_BREAK) -> set[int]:
    """Indices of word tokens followed by a list separator (comma, semicolon, line
    break, bullet) before the next token. "Arthralgia, Arthritis" is two names, not
    the alias "arthralgia arthritis" of a third entity."""
    spans = [m.span() for m in re.finditer(r'\w+', text)]
    return {i for i in range(len(spans) - 1) if separator.search(text[spans[i][1]:spans[i + 1][0]])}


def crosses_break(start: int, size: int, breaks: set[int]) -> bool:
    return any(j in breaks for j in range(start, start + size - 1))


def normalize(text: str) -> str:
    """Alias key: case-folded words without punctuation, with a crude plural strip."""
    words = re.sub(r'[^\w\s]', ' ', text.casefold()).split()
    return ' '.join(w[:-1] if len(w) > 4 and w.endswith('s') and not w.endswith(('ss', 'is', 'us'))
                    else w for w in words)


def ambiguous_word(key: str, span: str) -> bool:
    """True when a single-word alias match is an ordinary English word, not an acronym."""
    return key in COMMON_WORDS and not (len(span) > 1 and span.isupper())
