# Backend

Python 3.12+ FastAPI modular monolith for the Electronic Pipette vertical slice.
Routers only translate HTTP input/output; workflow gates live in services, persistence
is isolated in repositories, and AI output crosses the `LLMGateway` boundary as typed
Pydantic models before domain validation and persistence.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
$env:DATABASE_URL = "sqlite:///./local.db"
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

The default production-style database URL is PostgreSQL. Tests replace it with an
isolated in-memory SQLite engine and do not require PostgreSQL, Redis, MinIO, or a
real model:

```powershell
pytest
```

Use `X-User-Id: dev-user` for the seeded project while development auth is enabled.
Generation endpoints always return HTTP 202 with an AI run. `AI_TASK_MODE=inline`
runs the deterministic fake provider in-process; `celery` dispatches it to the worker.
The browser supplies an `Idempotency-Key` for every generation action. The API replays
an identical request for the same actor and rejects reuse of that key with different
request content. It also rejects a second active run of the same type for a requirement,
even when the caller supplies another key. Workers consume the private immutable input
snapshot; API responses expose only redacted lineage identifiers, versions, and hashes.

Membership roles map to the PRD permission levels as follows: `EDITOR` is a
`PROJECT_MEMBER`, `REVIEWER` is a `PROJECT_REVIEWER` (and therefore also inherits
generate/edit capability), `OWNER` has project-admin capability, and `VIEWER` is a
read-only extension. Only `OWNER` may manage project membership.

## Electronic Pipette demo

The idempotent seed creates tenant `demo-tenant`, project `EP-DEMO`, Knowledge Pack
EP `1.0`, and requirement `EP-REQ-001`:

> User can configure dispensing volume from 10 µL to 300 µL.

The fake provider produces assertion A01, boundary and persistence-gap risks, and
Nominal/Min/Max/Below/Above/Persistence scenarios. Below, Above, and Persistence
remain `CLARIFICATION_REQUIRED` with a null expected result; review cannot approve
the resulting Test Cases until a human supplies authoritative behavior. Scenarios
may still be approved as reviewed test intent and passed through the strong Gate.
An approvable Test Case must include structured configuration and steps with non-empty
action, test data, and expected result. Generation options that the deterministic P0
provider does not implement are rejected with `GENERATION_OPTION_UNSUPPORTED` rather
than being silently ignored.

Canonical generation calls are:

- `POST /api/v1/requirements/{id}/analyze`
- `POST /api/v1/risks/generate` with `analysis_id`
- `POST /api/v1/scenarios/generate` with `risk_batch_id`
- `POST /api/v1/testcases/generate` with `scenario_batch_id`

Nested resource aliases are also exposed for review-workbench navigation. Every
mutation that edits or reviews a versioned asset requires `expected_revision`;
mismatches return `RESOURCE_VERSION_CONFLICT` (409). Requirement semantic changes
mark Analysis through Test Case stale, while Scenario semantic changes only mark
downstream Test Cases stale.

## Deliberate P0 boundaries

- Production OIDC/JWT verification is not included. Outside development mode the
  API rejects client-supplied identity headers with `OIDC_NOT_CONFIGURED` rather
  than trusting them.
- Real LLM providers, embedding/pgvector retrieval, document import/OCR, export,
  MinIO artifacts, and TMS integration remain replaceable boundaries.
- Celery dispatch is implemented without a transactional outbox; deployments that
  need guaranteed delivery should add an outbox before production use.
- The initial migration uses SQLAlchemy metadata for a greenfield schema and enables
  PostgreSQL's `vector` extension, but no vector column is needed by this first slice.
