"""Prepare immutable blind review copies and audit completion without inventing labels."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from eval.judge import agreement

ROOT = Path(__file__).resolve().parents[1]
QUEUES = {
    'judge':('eval/human_labels/judge_calibration_todo.jsonl','human_supported'),
    'extraction':('eval/human_labels/extraction_review_todo.jsonl','human_supported'),
    'quarantine':('eval/human_labels/extraction_repair_review_todo.jsonl','human_supported'),
    'text':('eval/datasets/text_v1.jsonl','review_status'),
}
HUMAN_FIELDS = {'human_supported','human_linking_correct','human_note','review_status'}
HIDDEN_FIELDS = {'judge_supported','judge_reason','confidence'}


def merge_blind(original: list[dict],blind: list[dict]) -> tuple[list[dict],int]:
    """Import only human decisions; ids and evidence must remain identical."""
    by_id = {r['id']:r for r in blind}
    if len(by_id)!=len(blind) or len({r['id'] for r in original})!=len(original) or set(by_id)!={r['id'] for r in original}:
        raise ValueError('Blind review ids must match exactly without duplicates')
    updated,changed = [],0
    for row in original:
        review = by_id[row['id']]
        immutable = {k:v for k,v in row.items() if k not in HUMAN_FIELDS|HIDDEN_FIELDS}
        if immutable!={k:v for k,v in review.items() if k not in HUMAN_FIELDS|HIDDEN_FIELDS}:
            raise ValueError('Blind review changed original evidence or metadata')
        for key in ('human_supported','human_linking_correct'):
            if key in review and review[key] is not None and not isinstance(review[key],bool):
                raise ValueError('Human decisions must be JSON booleans or null')
        if review.get('review_status') not in (None,'todo','draft','reviewed'):
            raise ValueError('Unknown review status')
        if not isinstance(review.get('human_note',''),str) or len(review.get('human_note',''))>4000:
            raise ValueError('Human note must be a bounded string')
        revised = dict(row)
        if review.get('review_status')=='reviewed' or any(isinstance(review.get(k),bool)
                for k in ('human_supported','human_linking_correct')):
            revised.update({k:v for k,v in review.items() if k in HUMAN_FIELDS})
        changed += revised!=row
        updated.append(revised)
    return updated,changed


def apply_review(source: Path,raw: bytes,revised: list[dict],backup: Path) -> None:
    """Keep failed atomic-import intermediates within ignored private storage."""
    backup.mkdir(parents=True,exist_ok=True)
    saved = backup/(source.stem+'-'+hashlib.sha256(raw).hexdigest()+'.jsonl')
    if not saved.exists():
        saved.write_bytes(raw)
    if saved.read_bytes()!=raw:
        raise ValueError('Human review backup verification failed')
    if source.read_bytes()!=raw:
        raise ValueError('Human review source changed during import')
    with tempfile.NamedTemporaryFile(dir=backup,suffix='.pending',delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(''.join(json.dumps(row)+'\n' for row in revised),encoding='utf8')
        temporary.replace(source)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-blind',action='store_true')
    parser.add_argument('--apply-blind',action='store_true',help='Import human decisions with evidence checks and backups')
    parser.add_argument('--output',default='eval/runs/followup_human_review_summary.json')
    args = parser.parse_args()
    summary = {'human_labels_created_by_agent':0,'queues':{},'judge_status':'uncalibrated'}
    prepared = []
    if args.apply_blind:
        # Validate all queues before changing any file.
        for name,(relative,_) in QUEUES.items():
            source,target = ROOT/relative,ROOT/f'eval/human_labels/{name}_blind_todo.jsonl'
            raw = source.read_bytes()
            original = [json.loads(line) for line in raw.decode('utf8').splitlines()]
            blind = [json.loads(line) for line in target.read_text(encoding='utf8').splitlines()]
            revised,changed = merge_blind(original,blind)
            if changed:
                prepared.append((source,raw,revised))
        backup = ROOT/'.cache/human-review-import'
        for source,raw,revised in prepared:
            apply_review(source,raw,revised,backup)
    summary['queues_imported_from_human_blind_files'] = len(prepared)
    for name,(relative,label) in QUEUES.items():
        source = ROOT/relative
        raw = source.read_bytes()
        rows = [json.loads(line) for line in raw.decode('utf8').splitlines()]
        if label=='review_status':
            labelled = sum(r.get(label)=='reviewed' for r in rows)
        else:
            labelled = sum(isinstance(r.get(label),bool) for r in rows)
        target = ROOT/f'eval/human_labels/{name}_blind_todo.jsonl'
        if args.prepare_blind and not target.exists():
            blind = [{k:v for k,v in r.items() if k not in
                     ('judge_supported','judge_reason','confidence')} for r in rows]
            target.write_text(''.join(json.dumps(r)+'\n' for r in blind),encoding='utf8')
        summary['queues'][name] = {'items':len(rows),'human_labelled':labelled,
            'remaining':len(rows)-labelled,'source':relative,
            'source_sha256':hashlib.sha256(raw).hexdigest(),
            'blind_copy':str(target.relative_to(ROOT)) if target.exists() else None}
    summary['calibration'] = agreement(ROOT/QUEUES['judge'][0])
    summary['judge_status'] = summary['calibration']['status']
    Path(args.output).write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
