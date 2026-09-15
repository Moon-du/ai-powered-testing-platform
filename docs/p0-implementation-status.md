# P0 Implementation Status

Baseline date: 2026-09-11

This repository implements the first end-to-end vertical slice prescribed by the
master PRD: Electronic Pipette / Volume Setting. It is an engineering baseline,
not a claim that every P0 epic is production-complete.

## Delivered vertical slice

- Product Type and immutable Knowledge Pack version pinning.
- Tenant-aware projects, project membership, role gates, and Project Context.
- Manual Requirement intake, immutable revisions, and Atomic Assertions.
- Deterministic four-stage AI pipeline behind a replaceable `LLMGateway`.
- Immutable, worker-consumed AI input snapshots with redacted public lineage,
  request-scoped idempotency, active-run admission, atomic claim, bounded retry,
  and timeout behavior.
- Analysis, Risk, Scenario, and Test Case review workflows.
- Version conflicts, retained/superseded versions, and downstream `STALE` propagation.
- Knowledge references, Why Generated, requirement gaps, traceability, and coverage.
- Undefined expected behavior remains `CLARIFICATION_REQUIRED`; the scenario may be
  reviewed, but the related test case cannot be approved until an authoritative
  expected result is supplied.
- Mixed review batches support item-level selection: defined scenarios and
  execution-ready cases can progress without approving clarification items.
- Execution/approval gates require structured Case configuration plus non-empty
  step action, test data, and expected result.
- Vue review workspace, local Docker topology, CI, migration, unit tests, and browser
  smoke coverage.

## P0 capability map

| PRD capability | Current state | Next increment |
| --- | --- | --- |
| Product/Knowledge foundation | Vertical-slice complete | Expert-review the demo seed; add admin governance and more product types |
| Project/Context | Vertical-slice complete | Add document-backed project knowledge and richer ownership/team UI |
| Requirement intake | Manual path complete | Add safe DOCX/Text import, candidate preview, source location, then PDF/XLSX/OCR |
| Requirement analysis | Deterministic slice complete | Add editable analysis fields, richer question handling, and real-provider evaluation |
| Risk/Scenario/Test Case | Deterministic slice complete, including item-level review and execution-ready fields | Add richer inline editing and regenerate-feedback modes |
| Review/version/stale | Core gates complete | Add append-only review/audit events and version-history UI |
| Traceability/Coverage | Core read models complete | Add graph drill-down and quality filters |
| Export | Not started | Add approved/non-stale CSV and Excel export after the target TMS column mapping is confirmed |
| Async runtime | Celery dispatch, per-requirement admission lock, atomic claim, immutable snapshot, bounded retries, and timeout exist | Add transactional outbox, cancellation, DLQ, and stuck-run reconciliation |
| Identity | Safe development adapter only | Add enterprise OIDC/JWT and map enterprise groups to project roles |
| Retrieval/LLM | Structured retrieval + Fake LLM | Evaluate approved embedding/model providers with representative documents |

## Verification snapshot

- Backend: 35 pytest tests passed with 88% branch coverage, including workflow,
  security, immutable-snapshot, state-invariant, migration, idempotency, and worker
  fault-injection coverage.
- Database: Alembic upgraded fresh and simulated legacy SQLite databases through
  the execution-ready field migration; PostgreSQL migration enables `vector` when
  available.
- Contract: OpenAPI 3.1 with 42 paths; canonical generate/workflow/traceability/coverage
  paths are present.
- Frontend: TypeScript production build passed; 12 Vitest tests passed; two
  Playwright flows (wizard smoke and mixed-clarification core workflow) passed in
  Microsoft Edge.
- Docker Compose syntax was parsed, but containers were not started because Docker is
  not installed on the current host. CI now validates Compose expansion and builds
  both application images.

## Explicit production debts

- The greenfield `0001` migration is metadata-driven. Before a production pilot,
  freeze/squash it into a reviewed explicit PostgreSQL baseline and run the full
  migration suite against the target PostgreSQL version.
- Transactional outbox/reconciliation, append-only review/audit events, real OIDC,
  real-provider evaluation, safe document ingestion, and approved export remain
  release boundaries rather than implied capabilities.
- The current Ant Design bundle builds successfully but should be split before a
  performance-sensitive pilot.

## Inputs needed before the corresponding work starts

The current slice has no blocking dependency on user-provided data. Before a pilot or
the next integration increment, resolve the decisions in `open-decisions.md`, especially:

1. expert-approved Electronic Pipette knowledge seed and a golden requirement set;
2. enterprise OIDC issuer/claims/role mapping;
3. approved LLM/embedding provider, data-egress, residency, retention, and budget;
4. target deployment/security/compliance boundary;
5. accepted import formats/limits and the existing TMS CSV/Excel export template.
