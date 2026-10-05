# Architecture

The English baseline separates ingestion, guarded graph retrieval, planning, answer composition, and external evaluation. Text retrieval and answer verification extend the baseline in phase 3. The public boundary is `ask(question, history)` over HTTP; evaluation never imports QA internals.

```mermaid
flowchart LR
  Sources[PrimeKG / MONDO / HPO] --> Ingest[Canonical filtering and orientation]
  Ingest --> Graph[Neo4j]
  Text[MedlinePlus / openFDA] --> Chunks[Sections and embeddings]
  Chunks --> Graph
  Q[English question] --> Safety[Safety and language gates]
  Safety --> Link[Resolve history and link entities]
  Link --> Route[Templates or validated planner]
  Route --> Retrieve[Guarded Cypher / vector / fulltext / expansion]
  Graph --> Retrieve
  Retrieve --> Answer[Answer with code-generated sources]
  Answer --> Verify[Evidence entity verification]
  Verify --> API[CLI / HTTP / SSE]
```

Synthetic CI evidence and real-data research measurements are reported separately. Neither establishes clinical effectiveness.
