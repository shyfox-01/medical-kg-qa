"""Build English comparison reports from completed aggregate artifacts only."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


def pct(value):
    return f'{100*value:.2f}%' if value is not None else 'n/a'


def comparisons(models):
    lines = ['| Category | Cases/model | v0 | v1 hybrid | Pure vector |',
             '|---|---:|---:|---:|---:|']
    for category in sorted(models['v0']['categories']):
        values = [model['categories'][category] for model in models.values()]
        lines.append(f"| {category} | {values[0]['questions']} | "+' | '.join(
            pct(v['pass_rate_mean'])+f" (std {100*v['pass_rate_std']:.2f} pp)" for v in values)+' |')
    return '\n'.join(lines)


def details(models):
    lines = ['| Model/category | P / R / F1 | Execution exact / coverage | Faithful | Refusal | Median / p90 seconds | Calls / tokens |',
             '|---|---|---|---|---|---|---|']
    for name,model in models.items():
        for category,value in model['categories'].items():
            refusal = value.get('correct_refusal_rate',value.get('false_refusal_rate'))
            lines.append(f'| {name}/{category} | '+
                ' / '.join(pct(value[key]) for key in ('precision','recall','f1'))+
                f" | {pct(value['execution_accuracy'])} / {value['execution_coverage']} | {pct(value['faithful'])} | {pct(refusal)} | "+
                f"{value['latency_median_s']:.4f} / {value['latency_p90_s']:.4f} | {value['llm_calls']} / {value['tokens']} |")
    return '\n'.join(lines)


def run_description(name,model):
    return (f"{name}: {model['evaluated_questions']}/{model['total_available']} test questions, "
        f"three pass rates {model['pass_rate_rounds']}; mean {pct(model['pass_rate_mean'])}, "
        f"population std {100*model['pass_rate_std']:.2f} percentage points. "
        f"Inconsistent ids: {model['inconsistent_ids']}; failure stages: {model['failure_stages']}. "
        f"Redline regressions: {model.get('redline_regressions', 'baseline, not applicable')}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--final',action='store_true',help='Write final summary after phase-4 engineering checks')
    args = parser.parse_args()
    models = {name:read(f'eval/runs/{file}_summary.json') for name,file in
              [('v0','v0'),('v1','v1'),('vector','vector')]}
    if any(model['rounds']!=3 for model in models.values()):
        raise SystemExit('Require three completed rounds for every model')
    if len({tuple(model['evaluated_ids']) for model in models.values()})!=1:
        raise SystemExit('Comparison requires identical structured test ids')
    text = {name:read(f'eval/runs/{file}_text_summary.json') for name,file in
            [('v1','v1'),('vector','vector')]}
    extraction,biored = read('eval/runs/extraction_summary.json'),read('eval/runs/biored_summary.json')
    judge,text_data = read('eval/runs/judge_summary.json'),read('eval/runs/text_dataset_summary.json')
    counts = read('data/processed/text_counts.json')
    corpus = read('data/processed/vector_progress.json')
    if corpus['completed']!=corpus['total']:
        raise SystemExit('Vector corpus must be complete')
    table = comparisons(models)
    descriptions = '\n\n'.join(run_description(n,m) for n,m in models.items())
    text_table = ('| Text model | Sample/available | Three rates | Mean / std | Failures |\n'
                  '|---|---:|---|---|---|\n'+ '\n'.join(
        f"| {n} | {m['evaluated_questions']}/{m['total_available']} | {m['pass_rate_rounds']} | "
        f"{pct(m['pass_rate_mean'])} / {100*m['pass_rate_std']:.2f} pp | {m['failure_stages']} |" for n,m in text.items()))
    limits = (
        'The same 54 of 240 structured test cases were repeated three times; every safety/adversarial '
        'test case is included, but only three per other category. Text measurements use the same '
        'eight of 48 test drafts, repeated three times. All 400 structured and 80 text questions remain '
        'available. Only 24 structured questions were naturally paraphrased; others retain authored/template wording. '
        'BioRED uses 12 sampled test abstracts. FDA extraction uses 80/592 eligible chunks. '
        'Text drafts, extraction confidence and judge labels have not been human validated. '
        'Strict quote scoring can reject correct paraphrases; catalog entity membership does not prove '
        'sentence truth. Refusal scores use explicit pipeline refusal state and can miss implicit refusal wording. '
        'Execution accuracy covers only generated Cypher and compares the last generated query for multi-tool plans; '
        'trusted-only retrieval has null execution coverage. CSV gold reflects the structured snapshot; '
        'independently sourced FDA additions are not new clinical gold. Reported latency includes normal local '
        'load and provider behavior, including concurrent bounded CPU embedding work; it is not a controlled '
        'dedicated-machine benchmark. No result establishes clinical effectiveness or general benchmark performance.')
    phase3 = f'''# Phase 3 — Text, hybrid retrieval and independent vector control

Imported all {counts['documents']['medlineplus']} English MedlinePlus summaries and
{counts['documents']['openfda']} linked FDA labels in {sum(counts['chunks'].values())} chunks.
openFDA used exactly {counts['openfda_requests']} requests: {counts['openfda']['labels']}
returned labels, {counts['openfda']['unlinked_labels']} unlinked and
{counts['openfda']['ambiguous_labels']} ambiguous matches; document deduplication
and successful linking yield the stated final coverage. The initial 17 unusable
queries remain charged. No source outside the authorized list was downloaded.

Added section chunking, cached 384-dimensional embeddings, ABOUT/MENTIONS,
source-filtered top-eight vectors, English fulltext and bounded two-hop expansion,
validated four-step plans/backward references and known-entity answer verification.
FDA added 782 new aliases; previous alias vectors were reused. The independent
pure-vector corpus has {corpus['total']} fully embedded records: 42,975 entity
paragraphs plus 4,693 text chunks. Full paragraph text is stored; embedding uses
the model's 512-token window and generation uses disclosed evidence limits.

BioRED entity-pair detection F1: {biored['pair_detection']['f1']:.4f}; native typed
relation F1: {biored['native_typed_relations']['f1']:.4f}; {biored['errors']} failed
call. Its Chemical–Disease relations are not contraindication gold. The mapping
and non-mappings are recorded in decisions D011.

FDA extraction produced {extraction['unique_assertions']} unique linked assertions:
{extraction['relations']}; recorded PrimeKG agreement {pct(extraction['primekg_agreement_rate'])},
{extraction['conflicts']} conflict, both sources retained. {extraction['cached_failed_chunks']}
sampled chunks retain failed extraction/parse outcomes. The initial pass had 30
failures; bounded recovery/final sampling is in D017. The unlinked-mention audit
contains {extraction['unlinked_mentions']} entries including diagnostic/recovery
calls, not unique entities. Random 30-assertion review is generated locally.

## Structured measurements

{table}

{descriptions}

## Text measurements and pending calibration

{text_table}

All 80 questions are draft (40 text-only / 40 mixed; 32 dev / 48 test).
Grounding-checked LLM drafts: {text_data['llm_grounding_checked']}; others use
declared fallbacks. Seven structurally invalid selections were repaired before
text testing, preserving ids/splits. No questions were removed based on test score.
The 100-item sentence queue covers {judge['unique_questions']} questions:
{judge['system_claims']} actual system claims and {judge['draft_claims']} draft claims,
with {judge['judge_labelled']} uncalibrated judge labels and zero human labels.
The annotation guide explains sentence sampling and blind human review.

## Checks, limitations and deviations

51 mechanism/evaluation unit checks and both real-data count/access integration
checks pass. Preparatory fictional retrieval checks also pass after streaming
expansion avoided a global-neighborhood-sort timeout. Lint passes. Provider HTTP
429 during concurrent preliminary runs led to process-shared serialized calls;
interrupted preliminary runs are excluded from completed metrics but remain in
the local usage ledger. The token cap remains enforced. All raw/derived details,
private graph gold and human queues are ignored by Git; public text drafts and
aggregate summaries are committed. No push.

{limits}

v1 does **not** improve the overall structured sampled score over v0. The added
mechanisms are implemented and measured; this run does not justify claiming
that hybrid retrieval improves overall answer accuracy. The vector control's
redline outcomes are a diagnostic, not a deployable fallback approval.
'''
    (ROOT/'docs/history/reports/phase-3.md').write_text(phase3,encoding='utf8')
    if not args.final:
        print('Wrote phase-3 report from completed aggregate summaries')
        return
    phase4 = read('eval/runs/phase4_summary.json')
    if phase4['rounds']!=3 or phase4['evaluated_ids']!=models['v0']['evaluated_ids']:
        raise SystemExit('Phase-4 delivery validation must repeat the identical structured sample three times')
    engineering = read('eval/runs/api_summary.json')
    fixture = read('eval/runs/ci_summary.json')
    delivery = read('eval/runs/delivery_summary.json')
    summary = f'''# Final research and engineering summary

The Chinese baseline was archived in local tag zh-v2 and a verified Neo4j dump.
The repository now contains an English src-layout research system, independent
evaluation, structured and text ingestion, hybrid/pure-vector retrieval, source
and conflict handling, verification, CLI, FastAPI/SSE, OpenTelemetry and synthetic
CI/container configuration. See phase-0 through phase-4 reports for exact checks
and deviations. Local commits only; no push or history rewrite.

## Identical structured test comparison

{table}

{descriptions}

## Category metrics and resource measurements

Execution coverage counts question-round observations. Refusal means correct
refusal for controls and false refusal for retrieval categories. Tokens are
provider-reported; conservative failed-call charges are in the task usage ledger.

{details(models)}

## Draft text comparison

{text_table}

No v0 text score exists because v0 predates text ingestion and the text corpus.
v1's sampled structured score is lower than v0's; no overall improvement claim
is supported. Repeat standard deviation describes these three runs on the same
sample, not population uncertainty. Pure-vector redline regressions remain
explicit in its summary and must not be suppressed.

## Phase 4 delivery validation

{run_description('Phase 4 hybrid',phase4)}

Phase-4 engineering checks: 57 unit tests plus six native Neo4j integration
tests passed; lint passed. Real HTTP/SSE checks: {sum(engineering['checks'].values())}
of {len(engineering['checks'])} passed. The fictional CI protocol/gate used
{fixture['evaluated_questions']} cases for three rounds with mean pass
{pct(fixture['pass_rate_mean'])}; its FakeLLM score is not a medical benchmark.
Conservative settled/reserved task tokens: {delivery['conservative_charged_or_reserved_tokens']:,}
of 15,000,000 at the final audit. Docker/Phoenix/remote-CI execution remains unverified.
Detailed checks, score scope and final process cleanup are in phase-4.md.

## Human work remaining

- Review 100 sentence claims in eval/human_labels/judge_calibration_todo.jsonl,
  then compute human/judge agreement. Current status: uncalibrated.
- Review 30 linked extraction assertions in eval/human_labels/extraction_review_todo.jsonl,
  including entity linking, verbatim evidence, class/drug substitutions and conflicts.
- Review every one of the 80 draft text questions; graph-derived answers/gold are
  local in ignored eval/datasets/text_graph_gold.jsonl. Do not publish that file.

The review guide is eval/human_labels/README.md. Human queues are local and ignored,
not absent or automatically approved. BioRED F1 and source agreement are extraction
diagnostics, not evidence that contraindications are medically reliable.

## Limitations and deferred verification

{limits}

Docker is absent locally: configuration/build are delegated to the supplied CI
workflow, which has not run remotely because no push was authorized. No Docker
images were pulled. Optional OTLP/Phoenix export is implemented/documented but
requires an existing receiver and was not tested against Phoenix. The phase-4
report distinguishes endpoint/tracing/fixture checks from research accuracy.
This system is not clinically validated and must not guide diagnosis, dosage or
treatment. No upstream institution endorses it.
'''
    (ROOT/'docs/history/reports/summary.md').write_text(summary,encoding='utf8')
    overview = '| Stage/model | Structured sample | Mean pass / std |\n|---|---:|---|\n'
    overview += '\n'.join(f"| {name} | {m['evaluated_questions']}/{m['total_available']} x 3 | "
        f"{pct(m['pass_rate_mean'])} / {100*m['pass_rate_std']:.2f} pp |" for name,m in models.items())
    overview += (f"\n| Phase 4 hybrid | {phase4['evaluated_questions']}/{phase4['total_available']} x 3 | "
                 f"{pct(phase4['pass_rate_mean'])} / {100*phase4['pass_rate_std']:.2f} pp |")
    (ROOT/'docs/history/reports/overview_table.md').write_text(overview+'\n',encoding='utf8')
    print('Wrote phase-3 report, final comparison and overview table from completed summaries')


if __name__=='__main__':
    main()
