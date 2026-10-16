# Phase 0 — Archive and clean layout

Created local tag `zh-v2` at `92aa438`, exported the stopped Neo4j database, verified the archive with `neo4j-admin database load --info`, then cleared 28,832 nodes and removed the old schema indexes. Only the repository's Chinese implementation was removed; parent applications were not edited.

| Check | Result |
|---|---|
| Archive | `E:\medical project\backups\neo4j-zh-v2.dump` |
| Compressed bytes | 66,993,117 |
| Archive contents | 63 files; 307,081,133 uncompressed bytes |
| SHA256 | `1c8d823c9f9aca8ccdd4af0cccb065ee9cb615ae765f7a40edd6cde57435f088` |
| Database after cleanup | 0 nodes |
| Unit evaluation | 1 layout test; rerun after correcting fixture path |
| QA test repetitions | Not applicable: English system and dataset do not exist until phases 1–2 |

Added src layout, declared dependencies, repository-local Python 3.12 environment and caches, decision log, architecture skeleton and English configuration example. Existing parent credentials are present and were not printed or modified. The only background service is the Neo4j console started by this task on localhost:7687/7474; it will be stopped at completion.

Known issues/deviations: the desktop sandbox helper cannot launch processes (`setup refresh had errors`); reviewed commands run outside the failing sandbox. JDK 21 is reused from the existing PyCharm installation. No downloads outside the task allowlist and no push.
