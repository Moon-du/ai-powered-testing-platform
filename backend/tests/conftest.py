from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.main import create_app
from app.models import Base, Requirement
from app.seed import seed_demo


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        seed_demo(session)
        seed_demo(session, tenant_id="tenant-b", user_id="bob")
        session.commit()

    settings = Settings(
        app_env="development",
        database_url="sqlite+pysqlite:///:memory:",
        ai_task_mode="inline",
        dev_auth_enabled=True,
        seed_demo=False,
    )
    application = create_app(settings=settings, session_factory=factory)
    with TestClient(application) as test_client:
        test_client.headers.update(
            {"X-Tenant-Id": "demo-tenant", "X-User-Id": "dev-user"}
        )
        yield test_client


@pytest.fixture()
def ids(client: TestClient) -> dict[str, str]:
    project = client.get("/api/v1/projects").json()["items"][0]
    requirement = client.get(
        f"/api/v1/projects/{project['id']}/requirements"
    ).json()["items"][0]
    return {"project": project["id"], "requirement": requirement["id"]}


def analyze_and_approve(client: TestClient, requirement_id: str) -> dict:
    run = client.post(
        f"/api/v1/requirements/{requirement_id}/analyze",
        headers={"Idempotency-Key": f"analyze-{requirement_id}"},
    )
    assert run.status_code == 202, run.text
    assert run.json()["status"] == "SUCCEEDED"
    analysis_id = run.json()["result_id"]
    analysis = client.get(f"/api/v1/analyses/{analysis_id}").json()
    reviewed = client.post(
        f"/api/v1/analyses/{analysis_id}/review",
        json={"action": "APPROVE", "expected_revision": analysis["asset_revision"]},
    )
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def progress_to_scenarios(client: TestClient, requirement_id: str) -> dict:
    analysis = analyze_and_approve(client, requirement_id)
    risk_run = client.post(
        f"/api/v1/analyses/{analysis['id']}/risks/generate",
        json={"mode": "ALL"},
        headers={"Idempotency-Key": f"risks-{requirement_id}"},
    )
    assert risk_run.status_code == 202, risk_run.text
    assert risk_run.json()["status"] == "SUCCEEDED"
    risk_batch_id = risk_run.json()["result_id"]
    risk_batch = client.get(f"/api/v1/risk-batches/{risk_batch_id}").json()
    review = client.post(
        f"/api/v1/risk-batches/{risk_batch_id}/review",
        json={
            "action": "APPROVE",
            "risk_ids": [item["id"] for item in risk_batch["items"]],
            "expected_revisions": {
                item["id"]: item["asset_revision"] for item in risk_batch["items"]
            },
        },
    )
    assert review.status_code == 200, review.text
    scenario_run = client.post(
        f"/api/v1/risk-batches/{risk_batch_id}/scenarios/generate",
        json={"mode": "ALL"},
        headers={"Idempotency-Key": f"scenarios-{requirement_id}"},
    )
    assert scenario_run.status_code == 202, scenario_run.text
    assert scenario_run.json()["status"] == "SUCCEEDED"
    return client.get(
        f"/api/v1/scenario-batches/{scenario_run.json()['result_id']}"
    ).json()

