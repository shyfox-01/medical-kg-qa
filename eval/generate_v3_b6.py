"""Fresh v3 batch measuring the system once, after the D127 latency and name changes.

    python -m eval.generate_v3_b6 --dry-run  # counts and 25 samples; no model or writes
    python -m eval.generate_v3_b6            # reword, then freeze dataset and manifest

Built like b5 (b3 at twice the size, rewording by an independent model), with anchors
disjoint from every earlier structured set, b5 included. Protocol, fixed before any run:
one frozen copy of the code answers all of b6 once with the default settings; the
questions whose final turn took the reasoning chain are also answered once by the code b5
measured (.cache/frozen-b5, REASONING=chain), so the changes made since b5 (D129) are
compared on fresh questions. They stay when the new code passes at least as many of those
questions, otherwise they are withdrawn. Results are reported as they are; nothing is
changed from them before they are reported.
"""

from eval import generate_v3_b5 as b5
from eval.generate_v3 import ROOT

DATASET = ROOT / 'eval/datasets/structured_v3_b6.jsonl'
MANIFEST = ROOT / 'eval/datasets/MANIFEST_v3_b6.json'
SEED_B6 = 3071
PREVIOUS_DATASETS = (*b5.PREVIOUS_DATASETS, 'structured_v3_b5.jsonl')


def main() -> None:
    b5.main('b6', SEED_B6, DATASET, MANIFEST, PREVIOUS_DATASETS, __doc__)


if __name__ == '__main__':
    main()
