from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai import FakeLLMGateway
from app.ai.tasks import process_ai_run
from app.config import Settings
from app.dependencies import Actor
from app.errors import AppError
from app.models import AIRun, Base, Requirement
from app.repositories import DomainRepository
from app.schemas.domain import RunStatus
from app.seed import seed_demo
from app.services import WorkflowService


SessionFactory = sessionmaker[Session]


class FaultInjectingGateway(FakeLLMGateway):
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def analyze(self, requirement_text: str, knowledge: dict[str, str]):
        self.calls += 1
        raise self.error


@pytest.fixture()
def session_factory() -> Iterator[SessionFactory]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        seed_demo(session)
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        ai_task_mode="celery",
        dev_auth_enabled=True,
        seed_demo=False,
    )


def enqueue_analysis_run(factory: SessionFactory, settings: Settings) -> str:
    with factory() as session:
        requirement = session.scalar(select(Requirement))
        assert requirement is not None
        run, created = WorkflowService(
            DomainRepository(session), settings
        )._queue_run(
            Actor(tenant_id=requirement.tenant_id, user_id="dev-user"),
            requirement,
            "ANALYSIS",
            f"worker-retry-{uuid4()}",
            {"requirement_revision": requirement.revision, "options": {}},
        )
        assert created is True
        session.commit()
    return run.id


def load_run(factory: SessionFactory, run_id: str) -> AIRun:
    with factory() as session:
        run = session.get(AIRun, run_id)
        assert run is not None
        session.expunge(run)
        return run


def test_transient_exception_rolls_back_claim_and_run_can_be_retried(
    session_factory: SessionFactory, settings: Settings
) -> None:
    run_id = enqueue_analysis_run(session_factory, settings)
    gateway = FaultInjectingGateway(RuntimeError("temporary provider outage"))

    with pytest.raises(RuntimeError, match="temporary provider outage"):
        with session_factory() as session:
            service = WorkflowService(
                DomainRepository(session), settings, gateway=gateway
            )
            service.process_run(
                "demo-tenant", run_id, retry_unexpected=True
            )

    persisted = load_run(session_factory, run_id)
    assert gateway.calls == 1
    assert persisted.status == RunStatus.QUEUED
    assert persisted.started_at is None
    assert persisted.finished_at is None
    assert persisted.error_code is None

    with session_factory() as session:
        retried = WorkflowService(
            DomainRepository(session), settings, gateway=FakeLLMGateway()
        ).process_run("demo-tenant", run_id, retry_unexpected=True)
        session.commit()

    assert retried.status == RunStatus.SUCCEEDED
    assert retried.result_type == "ANALYSIS"
    assert retried.result_id is not None


def test_retries_exhausted_persists_bounded_terminal_failure(
    session_factory: SessionFactory, settings: Settings
) -> None:
    run_id = enqueue_analysis_run(session_factory, settings)

    with session_factory() as session:
        failed = WorkflowService(
            DomainRepository(session), settings
        ).fail_run_after_retries("demo-tenant", run_id)
        session.commit()

    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "AI_RUN_RETRIES_EXHAUSTED"
    assert failed.finished_at is not None

    persisted = load_run(session_factory, run_id)
    assert persisted.status == RunStatus.FAILED
    assert persisted.error_code == "AI_RUN_RETRIES_EXHAUSTED"
    assert persisted.error_message == (
        "Transient AI processing failed after bounded retries."
    )
    assert persisted.finished_at is not None


def test_app_error_is_terminal_and_not_rethrown_for_worker_retry(
    session_factory: SessionFactory, settings: Settings
) -> None:
    run_id = enqueue_analysis_run(session_factory, settings)
    gateway = FaultInjectingGateway(
        AppError(422, "PROVIDER_REQUEST_REJECTED", "request cannot be processed")
    )

    with session_factory() as session:
        failed = WorkflowService(
            DomainRepository(session), settings, gateway=gateway
        ).process_run("demo-tenant", run_id, retry_unexpected=True)
        session.commit()

    assert gateway.calls == 1
    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "PROVIDER_REQUEST_REJECTED"
    assert failed.error_message == "request cannot be processed"

    persisted = load_run(session_factory, run_id)
    assert persisted.status == RunStatus.FAILED
    assert persisted.error_code == "PROVIDER_REQUEST_REJECTED"
    assert persisted.finished_at is not None


def test_unexpected_inline_error_does_not_persist_provider_details(
    session_factory: SessionFactory, settings: Settings
) -> None:
    run_id = enqueue_analysis_run(session_factory, settings)
    gateway = FaultInjectingGateway(
        RuntimeError("provider secret token=do-not-persist")
    )
    with session_factory() as session:
        failed = WorkflowService(
            DomainRepository(session), settings, gateway=gateway
        ).process_run("demo-tenant", run_id)
        session.commit()

    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "AI_RUN_FAILED"
    assert failed.error_message == "AI processing failed unexpectedly."
    assert "token" not in failed.error_message


def test_worker_rejects_executor_version_drift(
    session_factory: SessionFactory, settings: Settings
) -> None:
    run_id = enqueue_analysis_run(session_factory, settings)
    drifted = settings.model_copy(update={"prompt_version": "new-prompt-v2"})
    with session_factory() as session:
        failed = WorkflowService(
            DomainRepository(session), drifted, gateway=FakeLLMGateway()
        ).process_run("demo-tenant", run_id)
        session.commit()

    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "AI_RUN_EXECUTOR_VERSION_MISMATCH"
    assert failed.result_id is None


def test_celery_task_has_bounded_late_ack_retry_policy() -> None:
    assert process_ai_run.max_retries == 3
    assert process_ai_run.acks_late is True
    assert process_ai_run.reject_on_worker_lost is True
    assert process_ai_run.soft_time_limit == 110
    assert process_ai_run.time_limit == 120
