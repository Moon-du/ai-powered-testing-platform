# P0 Bootstrap Defaults

Status: Accepted for the first vertical slice  
Date: 2026-09-11

## Context

The master PRD is sufficient to begin the Electronic Pipette vertical slice, but several entities and state transitions used by its API and Definition of Done are not explicitly present in the field-level model. This record makes the minimum engineering interpretations visible and reversible.

## Decisions

1. The initial product catalog contains only an Electronic Pipette demo knowledge pack. Its content is marked as demo data until a domain expert approves it.
2. `RequirementAssertion`, generation batch, import job, export job, project membership, and review/version metadata are first-class persisted concepts because the PRD's workflow and traceability rules require them.
3. Editable assets carry an integer `revision`. Mutations require `expected_revision`; a mismatch returns `RESOURCE_VERSION_CONFLICT`.
4. `ACCEPT` in the risk workflow maps to the canonical persisted review status `APPROVED`. The API may keep user-facing action labels while storage uses one status vocabulary.
5. Expected behavior uses `DEFINED`, `CLARIFICATION_REQUIRED`, and `UNDEFINED`. A scenario may exist with a clarification requirement, but a test case containing an unresolved expected result cannot be approved.
6. Published knowledge-pack versions are immutable. Projects pin a pack ID and version. A future explicit upgrade operation will create an audit event and mark affected downstream assets stale.
7. Project-context changes increment `context_revision`. The AI run stores requirement, pack, context, and prompt versions as its reproducibility snapshot.
8. The first import adapter supports DOCX and plain text. PDF, XLSX, and OCR remain adapters behind the same job contract.
9. Development and automated tests use a clearly gated development identity adapter. Non-development startup must reject this adapter; the production boundary is OIDC/JWT.
10. AI behavior starts with a deterministic `FakeLLMGateway`. Provider and embedding choices stay behind configuration-backed interfaces.
11. Batch review updates selected items atomically. The latest non-superseded batch is the active batch returned by the workflow aggregate.
12. The first export format is a replaceable platform-owned CSV/XLSX schema for approved cases and steps.
13. P0 is an engineering-assistance system, not a formal QMS or validated record system. The data model remains tenant-aware, and product knowledge is shareable only inside one tenant.
14. Uploaded content is evidence, never an instruction source. Retrieval and generation must preserve tenant/project filters and reject out-of-scope knowledge references.

## Consequences

These decisions allow an offline, deterministic workflow test without inventing production identity, model, OCR, or TMS details. Production rollout still requires the decisions tracked in `docs/open-decisions.md`.
