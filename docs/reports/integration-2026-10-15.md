# Integration and live-interface verification — 2026-10-15

The requested integration round completes with **19 passing integration tests**
and **677 passing non-integration tests**. Live CLI, HTTP and SSE generation also
complete in a bounded smoke round. The first live group includes one provider
timeout; a single complete-group retry succeeds. This verifies exercised paths,
not comprehensive answer accuracy, clinical effectiveness or service availability.

## Coverage and results

| Check | Result | Boundary |
|---|---|---|
| Isolated graph/interface integration | 18 passed in 8.88 seconds | Real Neo4j, fictional fixtures, FakeLLM; includes four new regression/interface tests |
| Existing research graph vs frozen CSV | 1 passed in 29.17 seconds | Read-only node and PrimeKG relationship comparison |
| Non-integration regression suite | 677 passed in 11.66 seconds | 19 integration tests deselected |
| Ruff and cached-artifact integrity | Passed; all nine artifact checks pass | Existing source/catalog/vector/frozen-dataset checks |
| Cached CPU vector retrieval | Eight results in each mode | Neo4j vector search and local pure-vector corpus; downloads disabled |
| Research indexes | All 16 online | Existing database, no index rebuild |
| First live-provider group | 3/4 completed | CLI pure-vector generation hit APITimeoutError at the configured 60-second deadline |
| Single complete-group retry | 4/4 completed | Same four requests, provider/model and timeout; no selective failure rerun |
| Quarantined alias through HTTP | Clarification, zero model calls | Real catalog and initialized public API |
| Shutdown | Verified | Owned database processes exited; ports 7474, 7687 and 18080 closed |

The integration tests cover guarded counts/reverse queries, graph traversal,
fulltext/vector indexes, conflict evidence, truncation, planner fallback and scoped
reconciliation. New tests exercise the public CLI subprocess, stdio conversation
focus and HTTP/SSE with a real fixture database. SSE chunks reconstruct exactly
the verified final answer and carry its trace ID. The fourth new test reproduces
the fixture-import guard defect described below.

The research graph contains 15,774 diseases, 7,957 drugs, 9,433 phenotypes, 9,811
genes, 1,264 documents and 4,693 chunks. Its complete node/relation counts match
before and after both live groups; no synthetic nodes are present. The read-only
CSV comparison checks the declared source counts, not medical completeness.

## Repairs

The synthetic-test fixture previously allowed mixed imports by default when an
optional environment flag was absent. It now always requires a separate empty or
fictional-only database and closes its driver if setup fails. README separates
fixture testing from the read-only research count check.

The loader's guard also missed nodes with no UID because a negated Cypher string
predicate on null does not become true. A temporary isolated sentinel reproduced
the problem: the regression test failed before the fix and passed afterward.
The guard now explicitly rejects missing UIDs. Only the newly created sentinel
was removed; existing databases and earlier cache files were retained.

Local orchestration encountered two Windows cleanup edges. PowerShell's serialized
creation timestamp lost sub-millisecond precision, so identity comparison now uses
the recorded precision together with PID, command line and ancestry. The initial
HTTP cleanup checked its port immediately after launcher exit; it was still
reachable at that instant and closed by the next independent check. The retry
explicitly stops the owned process tree and uses a bounded port-closure check.
The original assertion and recovered first-round results remain disclosed. These
changes are to local test helpers; no QA prompt or provider behavior was changed.

## Live requests and accounting

The predeclared operational inputs are a hybrid CLI count question, a vector CLI
definition question, a hybrid HTTP list question and a hybrid SSE count question.
They use public README-style asthma examples, not frozen test questions or earlier
QA outputs. API health/readiness and alias quarantine are checked separately.
Count answers equal the retrieved count of 87, and the SSE assembly checks pass.
The definition/list answers were not assigned semantic or clinical labels.

The existing provider/model configuration remains unchanged. The run uses cached
embeddings offline, cache disabled, a 60-second provider timeout, two-second
cooldown and zero SDK retries. The initial 10,201,771-token cumulative ledger is
bounded at 10,301,771 for this task, below the earlier approved 11,344,304 cap.
The first group charges 20,079 conservative tokens, including the timeout; the
complete-group retry adds 7,039. Total added usage is **27,118** across eight calls,
ending at **10,228,889**. No failed-call charge or historical reservation is reset.

The successful retry confirms current reachability for these requests. The initial
timeout remains evidence that the external free interface can be unreliable.
No additional retries, benchmark runs, downloads, installations or human labels
were added. Existing Starlette TestClient deprecation and Neo4j optional-match
aggregation notices do not fail the checks; dependency upgrades are outside this
verification.

## Evidence and preserved state

The [aggregate record](../../eval/runs/integration_2026_10_15_summary.json) indexes
test XML, both smoke groups, fixture regression evidence, graph checks, hashes and
shutdown records. Private logs, local configurations and the isolated database
remain under `.cache/integration-2026-10-15/`; they are not available from a fresh
public clone. The original research installation configuration is untouched;
temporary service configurations and logs stay inside the project.

All 82 preserved data, queue and prior-review files match their initial hashes.
The prior reports remain historical records. Only the fixture safety guard,
integration tests, README and verification documentation enter the local commit.
No task-owned service remains running, and no push or merge is performed.
