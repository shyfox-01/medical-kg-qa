# Implementation decisions

Each entry records a decision, its reason, and alternatives. All runtime and data artifacts remain local.

## D001 — Environment and scope

Use Python 3.12 in the repository `.venv`. Store pip, model, and temporary caches inside the repository to respect the write boundary. Do not alter the parent application's environment. Alternative: a shared E-drive environment; rejected because task scope permits no writes there.

## D002 — Archived evaluation

Preserve the Chinese implementation and its evaluation in the local `zh-v2` tag only. Its saturated keyword benchmark is not comparable to the new entity-set benchmark and is not clinical validation.

## D003 — Task execution

The explicit task authorization covers local phase commits without further confirmation. Docker execution is skipped locally if unavailable; CI configuration is supplied and remote CI remains unverified until the user pushes.
