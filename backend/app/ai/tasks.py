from __future__ import annotations

from app.ai.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.repositories import DomainRepository
from app.services import WorkflowService


@celery_app.task(
    bind=True,
    name="ai.process_run",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    soft_time_limit=110,
    time_limit=120,
)
def process_ai_run(
    _task, tenant_id: str, run_id: str
) -> dict[str, str | None]:
    try:
        with SessionLocal() as session:
            service = WorkflowService(DomainRepository(session), get_settings())
            run = service.process_run(
                tenant_id, run_id, retry_unexpected=True
            )
            session.commit()
    except Exception as exc:
        retries = int(getattr(_task.request, "retries", 0))
        if retries < int(_task.max_retries or 0):
            raise _task.retry(exc=exc, countdown=min(2 ** (retries + 1), 30))
        with SessionLocal() as session:
            service = WorkflowService(DomainRepository(session), get_settings())
            run = service.fail_run_after_retries(tenant_id, run_id)
            session.commit()
    return {
        "id": run.id,
        "status": run.status,
        "result_type": run.result_type,
        "result_id": run.result_id,
    }
