# Design decisions

The decisions that shape the system and how it is evaluated. Code comments and the
evaluation notes cite them by ID (for example `D105`); IDs follow the order in which
the decisions were made.

## How changes are evaluated

- A change is designed on development data (dev splits, fresh benchmark batches,
  LLM-generated development sets), never on a test split, and must be a general rule
  rather than a fix for one question.
- Every change is checked question by question (fixed, still failing, regressed) in
  paired runs against a frozen copy of the previous code, on every question where
  its code path can act; those questions are found offline.
- Held-out test sets run once per system version and are reported as they are. The
  sealed v3 test has been used twice in total and is closed.
- Development sets written with an LLM are labelled as such; no label is presented
  as a human or clinical judgement.

## Decisions

| Area | Decision | ID |
|---|---|---|
| Graph | Orient Disease→Disease edges only from MONDO `is_a`; drop reciprocal CSV duplicates | D004 |
| Evaluation | Black-box process boundary; gold computed from the CSV transform, not the graph | D008 |
| Extraction | BioRED labels map to graph relations only where the meaning is the same (drug interactions); associations and correlations never become contraindications | D011 |
| Retrieval | Bound rows, hops, anchors and evidence size; disclose truncation | D015 |
| Extraction | FDA label extraction is measured on a fixed sample with a review queue; a confidence score or agreement with PrimeKG never approves an extracted relation | D017 |
| Service | SSE streams only the verified final answer; metadata-only OpenTelemetry spans | D019 |
| Provenance | Keep both sides of PrimeKG/FDA conflicts, each with its source | D021 |
| Extraction | FDA assertions only between existing entities, each backed by a verbatim quote | D024, D028 |
| Planning | Malformed plans are repaired within the retry limit; only a resolved graph question may then fall back to guarded Text2Cypher, and Cypher written into a plan is never executed | D038 |
| Safety | A deterministic scope gate refuses credential, prompt-extraction, override, OS-command and database-write requests before any model call | D045 |
| Safety | Refuse first-person crises, doses and diagnoses; answer impersonal knowledge questions | D047, D061 |
| Retrieval | Expansion rows carry relation type and direction | D047 |
| Linking | Common-word aliases need upper case; same-name Disease/Phenotype resolved by the asked relation | D047, D048 |
| Retrieval | Empty single-template result falls back to documents about the anchor | D048 |
| Vocabulary | Brand and lay names from MeSH, openFDA and MedlinePlus with collision rules | D049, D060 |
| Benchmark | v2: common entities, natural wording, clinical multi-hop, sensitive terms | D050 |
| Benchmark | Vector control paragraphs include catalog synonyms | D051 |
| Measurement | API-error rule: rerun whole rounds, never single questions | D054, D058 |
| Planning | Planner boolean flags accept only unambiguous encodings (0/1, true/false) | D062 |
| LLM | Shared pacing after timeouts, HTTP 429 and 5xx (10–60 s, honouring Retry-After); a failed answer is never retried silently | D063 |
| Linking | One-edit typo matching for long drug names | D065 |
| Vocabulary | Quarantine 28 alias mappings rejected by source review, reversibly at query time | D072 |
| Scoring | Entity support is reported separately from (unevaluated) semantic support | D073 |
| Routing | "Drugs for both A and B" uses a deterministic intersection template instead of generated Cypher | D082 |
| LLM | Keep the cloud model as default; local open-weight models are supported and measured on dev | D083, D084 |
| Answer | Name mappings (brand → canonical name) and the meaning of each executed query are given to the answer model as evidence | D085 |
| Evaluation | Stage-wise diagnosis and per-question ledgers decide whether a fix worked | D086, D089 |
| Answer | Rows of the final graph query are always reported; the model words, code completes | D087 |
| Linking, routing | Truncated group labels no longer shadow diseases; "drugs that cause X" and "when not to use X" are routed correctly | D088 |
| Benchmark | v3: capability coverage, perturbations, fresh batches per fix round, a sealed test run once | D091–D094 |
| Evaluation | v3 failure severity separates declines, incomplete and wrong answers, and policy breaches | D095 |
| Demo | Self-contained web page shows answers, routes, executed Cypher and evidence; no frontend build | D096 |
| Benchmark | LiveQA v2: NLM focus/keyword pairs, exact catalog links, CSV gold, paired original/summary wording | D097 |
| Benchmark | Fresh v3 batch b3, frozen before RxNorm and routing changes, with all previous anchors excluded | D098 |
| Vocabulary | RxNorm single-ingredient brands with unique Drug joins, global unsafe-name exclusion and corpus-word filters | D099 |
| Safety / benchmark | Recognize IU and units in dose guards; verify LiveQA in memory without requiring v1 | D100 |
| Vocabulary | Keep RxNorm aliases exact-only through openFDA parsing, verify Neo4j before apply, exclude 45 reviewed names and quarantine 11 Pentastarch aliases | D101 |
| Answer | Decline empty verified bodies; recognize bounded opening decline paraphrases | D102 |
| Safety | Answer the knowledge part with a fixed notice; keep emergencies, dose-only requests and personal decisions blocked | D103 |
| Safety | Personal medication decisions without a dose are blocked; "Can I take A with B?" is answered behind a notice | D104 |
| Linking | Corrected names are confirmed ("Did you mean …?") or used with a visible note; vector matches never become silent anchors | D105 |
| Linking | A match that covers part of a phrase ("jock itch" → ITCH) is checked by the model choosing among catalog entries; a different choice is asked back, never used silently | D106 |
| Linking | Names with a missing or extra space ("heartfailure", "para cetamol") are matched without spaces and used with a note | D107 |
| Routing | An unrouted question about one name without a relation word is read by the model as a choice with probabilities: a clear reading is answered with a note, a spread one is asked | D108 |
| Linking | The end of a contraction or possessive ("what's", "mother's") never starts a name, so "What's warfarin" is Warfarin, not (S)-Warfarin | D109 |
| Evaluation | Intent is measured on MedicationQA's human labels, mapping fixed before one run: 16 → 43 of 197 answered with the labelled intent, 3 → 5 with another | D110 |
| Safety | Strengths, amounts needed, counts per day, booster intervals and infusion rates are dose requests | D111 |
| Routing | A yes/no question about one drug and one disease or phenotype checks that pair, answered in code: b4 32 → 40 of 40 | D112 |
| Linking, routing | Relation nouns are not names; "prescribed for" asks indications; interactions among three to six drugs are stated pair by pair in code | D113 |
| Linking | MedlinePlus topic titles become lay disease names when their MeSH heading means the same disease ("Collapsed Lung", "Pinworms"); reviewed | D114 |
| Retrieval | Text chunks come from the vector and full-text indexes merged by rank fusion (gold chunk in the top 8: 67% → 94% on the text test split); a cross-encoder was measured and left off | D115 |
| Linking | A lower-case word matching only an acronym or gene symbol ("hard" → HARDS) is checked by the model: dropped as an ordinary word, asked back as another entry, or kept | D116 |
| Safety | Personal messages the rules pass are read once more by the model for a possible emergency; the reading can only escalate (20/20 LLM-generated emergencies, 4 real LiveQA ones, no false alarm found) | D117 |
| Linking | Several spellings of an asked-back name are ordered by the question; unlikely ones are left out, and the user still confirms | D118 |
| Retrieval | A generated graph query that returns nothing for a named entity is followed by a text search of the documents about it ("Can diazepam lower blood pressure?") | D119 |
| Linking | A misspelt name run into other words ("hyptotension make me dizzy") is linked on its own when it is an unknown word that a spelling match links | D120 |
| Linking | A MedlinePlus topic title named as written settles the names inside it: an asked-back name resolves to the page's entry, a page about no entity leaves the text to answer | D121 |
| Web page | Offered options are stacked likeliest first; "None of these" and "Something else" put the question back to rephrase, with the name selected | D122 |
| Web page | Chat layout with the question box at the bottom; how an answer was found is folded; sources are listed once per document as links (FDA labels on DailyMed) | D123 |
| Answer | A list from one template query about one entity is written in code with the number recorded ("The knowledge graph records 58 side effects of Metformin"); when 25 rows come back, a count query gives the total and the first 25 by name are listed. The model only restated these rows, sometimes with "(Count: 1)" after each | D124 |
| Web page | The answer is set for reading (larger type, lines of about 70 characters, real paragraphs and lists); graph lists are chips; safety notices are amber callouts and emergencies red; a follow-up shows how it was read ("Read as: …"); each answer offers up to three related questions that one count query shows the graph has records for | D125 |
| Scoring | A new line or bullet in an answer ends every entity name, also one spelt with a comma, in the scorer and in the answer checks (unsupported entities, completeness); a comma or semicolon inside one line still keeps such a name ("apnea, central sleep") | D126 |
| Planning | Questions no template answers go to a reasoning chain (`REASONING=chain`, the default; `plan` keeps the one-shot planner): the model calls one tool at a time (overview, relation, Cypher, text, cannot answer) by function calling and reads each result before the next, in one conversation, and refers to a found list as `$N` instead of copying it. Code still runs and checks every call (uids, relation directions, query parameters) and the answer (unsupported names, rows left out, a condition of the question no lookup used, found rows denied). Revised on 379 earlier planner questions (test splits included) to a tie, 230 of 315; then a fresh batch b5, run once with both under a rule committed beforehand, decided: 66 of 75 against 60, at about 2.8 times the prompt tokens and a slower tail | D127 |
