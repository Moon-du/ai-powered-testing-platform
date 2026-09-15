# Open Decisions Before Production Pilot

None of these items blocks the first local vertical slice. They must be resolved before their corresponding production capability is enabled.

| Decision | Needed input | Current development default |
| --- | --- | --- |
| Regulatory position | Whether this is an engineering aid or a formal QMS/validated record system | Engineering aid; not a formal compliance record system |
| Tenancy and knowledge visibility | Single enterprise vs multi-tenant deployment and whether knowledge may cross tenant boundaries | Multi-tenant-shaped model; knowledge never crosses a tenant |
| Product scope | Which product types are in the P0 pilot | Electronic Pipette only |
| Domain knowledge | Expert-approved modules, functions, risks, rules, patterns, failure modes, and trial requirements | PRD examples marked as demo seed |
| LLM and data boundary | Provider, model, endpoint, credentials, budget, residency, retention, and whether proprietary text may leave the enterprise | Deterministic local fake provider |
| Retrieval | Embedding model, representative documents, chunking evaluation set, and quality thresholds | Structured deterministic retrieval |
| Identity | OIDC issuer, audience, claims, tenant model, and role mapping | Development identity adapter only |
| Deployment | Target platform, TLS, DNS, secret manager, network policy, backup, RPO/RTO, and availability objectives | Local Docker Compose |
| Compliance | Data classification, retention/deletion, audit retention, legal/regulatory controls, and incident process | Minimal safe logging; no sensitive full-text logs |
| Import | Required P0 file types, size/page limits, malware scanning, OCR, and encrypted-file behavior | DOCX and text adapter first |
| Export | Existing TMS Excel/CSV template and field mapping | Replaceable platform-owned schema |
| Trial acceptance | Product-aware quality rubric, acceptance/edit/reject thresholds, time-saved target, and test corpus | Metrics collected without pass threshold |
| Nonfunctional targets | p95 latency, concurrency, AI timeout, browser support, accessibility, and capacity | Testable qualitative PRD baseline |

Before real files are enabled, the pilot also needs explicit limits and controls for file size, MIME/magic-byte validation, malware and active-content scanning, parser isolation, retention, and deletion across the database, vector index, object storage, queues, and backups.
