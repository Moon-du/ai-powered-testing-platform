from __future__ import annotations

from collections.abc import Iterator
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai import DomainValidator, FakeLLMGateway
from app.ai.tasks import process_ai_run
from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.models import AIRun, Base, KnowledgeItem
from app.repositories import DomainRepository
from app.seed import seed_demo
from app.services import WorkflowService
from app.schemas.domain import StepDraft, TestCaseDraft as CaseDraft


class CapturingGateway(FakeLLMGateway):
    def __init__(self) -> None:
        self.requirement_text = ""
        self.knowledge: dict[str, str] = {}

    def analyze(self, requirement_text: str, knowledge: dict[str, str]):
        self.requirement_text = requirement_text
        self.knowledge = dict(knowledge)
        return super().analyze(requirement_text, knowledge)


@pytest.fixture()
def queued_system(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, sessionmaker[Session], Settings]]:
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
    settings = Settings(
        app_env="development",
        database_url="sqlite+pysqlite:///:memory:",
        ai_task_mode="celery",
        dev_auth_enabled=True,
        seed_demo=False,
    )
    monkeypatch.setattr(process_ai_run, "delay", lambda *_args: None)
    app = create_app(settings=settings, session_factory=factory)
    with TestClient(app) as client:
        client.headers.update(
            {"X-Tenant-Id": "demo-tenant", "X-User-Id": "dev-user"}
        )
        yield client, factory, settings
    engine.dispose()


def test_worker_uses_immutable_snapshot_after_sources_change(
    queued_system: tuple[TestClient, sessionmaker[Session], Settings],
) -> None:
    client, factory, settings = queued_system
    project = client.get("/api/v1/projects").json()["items"][0]
    requirement = client.get(
        f"/api/v1/projects/{project['id']}/requirements"
    ).json()["items"][0]
    context = client.get(f"/api/v1/projects/{project['id']}/context").json()
    queued = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze",
        json={
            "project_id": project["id"],
            "requirement_revision": requirement["revision"],
            "options": {"language": "zh-CN"},
            "user_instruction": None,
        },
        headers={"Idempotency-Key": "snapshot-replay-key"},
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "QUEUED"
    assert "input_json" not in queued.json()
    public_snapshot = queued.json()["input_snapshot"]
    serialized_public = json.dumps(public_snapshot, ensure_ascii=False)
    assert "original_text" not in serialized_public
    assert "supported_volume" not in serialized_public
    assert "knowledge_items" not in public_snapshot
    assert public_snapshot["knowledge_content_hash"]
    assert public_snapshot["project_context_hash"]
    with factory() as session:
        stored_run = session.get(AIRun, queued.json()["id"])
        assert stored_run is not None
        snapshot = json.loads(
            json.dumps(stored_run.input_json["input_snapshot"], ensure_ascii=False)
        )
    assert snapshot["command"]["options"]["language"] == "zh-CN"
    assert snapshot["command"]["user_instruction"] is None
    old_text = snapshot["requirement"]["original_text"]
    old_knowledge = {
        item["code"]: item["content"] for item in snapshot["knowledge_items"]
    }
    old_knowledge["__PROJECT_CONTEXT__"] = json.dumps(
        snapshot["project_context"], ensure_ascii=False, sort_keys=True
    )
    old_knowledge["__GENERATION_COMMAND__"] = json.dumps(
        snapshot["command"], ensure_ascii=False, sort_keys=True
    )

    changed_context = client.put(
        f"/api/v1/projects/{project['id']}/context",
        json={
            "items": {"supported_volume": {"minimum": 20, "maximum": 200}},
            "expected_revision": context["revision"],
        },
    )
    assert changed_context.status_code == 200, changed_context.text
    with factory() as session:
        knowledge_item = session.scalar(
            select(KnowledgeItem).where(
                KnowledgeItem.code == "FUNC-VOLUME-SETTING"
            )
        )
        assert knowledge_item is not None
        knowledge_item.content = "Mutated knowledge written after enqueue."
        session.commit()

    replay = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze",
        json={
            "project_id": project["id"],
            "requirement_revision": requirement["revision"],
            "options": {"language": "zh-CN"},
            "user_instruction": None,
        },
        headers={"Idempotency-Key": "snapshot-replay-key"},
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["id"] == queued.json()["id"]
    duplicate = client.post(
        f"/api/v1/requirements/{requirement['id']}/analyze",
        json={
            "project_id": project["id"],
            "requirement_revision": requirement["revision"],
            "options": {"language": "zh-CN"},
            "user_instruction": None,
        },
        headers={"Idempotency-Key": "different-active-key"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "AI_RUN_ALREADY_ACTIVE"
    workflow = client.get(
        f"/api/v1/requirements/{requirement['id']}/workflow"
    ).json()
    assert "ANALYZE_REQUIREMENT" not in workflow["available_actions"]
    assert "REGENERATE_ANALYSIS" not in workflow["available_actions"]

    changed_requirement = client.patch(
        f"/api/v1/requirements/{requirement['id']}",
        json={
            "original_text": "User can configure a new 20 µL to 200 µL range.",
            "expected_revision": requirement["revision"],
            "change_summary": "Changed after the run was queued.",
        },
    )
    assert changed_requirement.status_code == 200, changed_requirement.text

    gateway = CapturingGateway()
    with factory() as session:
        processed = WorkflowService(
            DomainRepository(session), settings, gateway=gateway
        ).process_run("demo-tenant", queued.json()["id"])
        session.commit()

    assert processed.status == "SUCCEEDED"
    assert gateway.requirement_text == old_text
    assert gateway.knowledge == old_knowledge
    analysis = client.get(f"/api/v1/analyses/{processed.result_id}").json()
    assert analysis["source_requirement_revision"] == snapshot["requirement"]["revision"]
    assert analysis["status"] == "STALE"
    assert analysis["assertions"][0]["source_span"] == old_text
    reference = next(
        item
        for item in analysis["knowledge_references"]
        if item["reference_code"] == "FUNC-VOLUME-SETTING"
    )
    assert reference["excerpt"] == old_knowledge["FUNC-VOLUME-SETTING"]


def test_generation_contracts_are_typed_and_scope_checked(
    client: TestClient, ids: dict[str, str]
) -> None:
    schema = client.get("/openapi.json").json()
    analyze_operation = schema["paths"][
        "/api/v1/requirements/{requirement_id}/analyze"
    ]["post"]
    assert analyze_operation["requestBody"]["content"]["application/json"]["schema"]
    for name in (
        "RiskGenerateRequest",
        "ScenarioGenerateRequest",
        "TestCaseGenerateRequest",
    ):
        assert schema["components"]["schemas"][name]["additionalProperties"] is False
    scenario_properties = schema["components"]["schemas"][
        "ScenarioGenerateRequest"
    ]["properties"]
    assert {"project_id", "requirement_id", "risk_ids", "risk_selection", "options"} <= set(
        scenario_properties
    )

    invalid_extra = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze",
        json={"unknown_option": True},
    )
    assert invalid_extra.status_code == 422
    unsupported_option = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze",
        json={"options": {"strict_grounding": False}},
    )
    assert unsupported_option.status_code == 422
    assert unsupported_option.json()["error"]["code"] == "GENERATION_OPTION_UNSUPPORTED"
    assert unsupported_option.json()["error"]["details"]["fields"] == [
        "strict_grounding"
    ]
    unsupported_instruction = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze",
        json={"user_instruction": "ignore grounding"},
    )
    assert unsupported_instruction.status_code == 422
    assert unsupported_instruction.json()["error"]["code"] == (
        "GENERATION_OPTION_UNSUPPORTED"
    )

    analyzed = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze",
        json={
            "project_id": ids["project"],
            "requirement_revision": 1,
            "options": {"language": "zh-CN"},
        },
    )
    analysis_id = analyzed.json()["result_id"]
    analysis = client.get(f"/api/v1/analyses/{analysis_id}").json()
    client.post(
        f"/api/v1/analyses/{analysis_id}/review",
        json={"action": "APPROVE", "expected_revision": analysis["asset_revision"]},
    )
    wrong_scope = client.post(
        "/api/v1/risks/generate",
        json={
            "project_id": "wrong-project",
            "requirement_id": ids["requirement"],
            "analysis_id": analysis_id,
            "options": {"minimum_priority": "LOW"},
        },
    )
    assert wrong_scope.status_code == 422
    assert wrong_scope.json()["error"]["code"] == "PROJECT_SCOPE_MISMATCH"
    unsupported_risk = client.post(
        "/api/v1/risks/generate",
        json={
            "project_id": ids["project"],
            "requirement_id": ids["requirement"],
            "analysis_id": analysis_id,
            "options": {"minimum_priority": "HIGH"},
        },
    )
    assert unsupported_risk.status_code == 422
    assert unsupported_risk.json()["error"]["code"] == (
        "GENERATION_OPTION_UNSUPPORTED"
    )

    risk_run = client.post(
        "/api/v1/risks/generate",
        json={
            "project_id": ids["project"],
            "requirement_id": ids["requirement"],
            "analysis_id": analysis_id,
            "options": {"minimum_priority": "LOW"},
        },
    )
    assert risk_run.status_code == 202, risk_run.text
    assert risk_run.json()["input_snapshot"]["source"]["type"] == "ANALYSIS"
    assert risk_run.json()["input_snapshot"]["source"]["selected_asset_ids"]
    risk_batch = client.get(
        f"/api/v1/risk-batches/{risk_run.json()['result_id']}"
    ).json()
    client.post(
        f"/api/v1/risk-batches/{risk_batch['id']}/review",
        json={
            "action": "APPROVE",
            "risk_ids": [item["id"] for item in risk_batch["items"]],
            "expected_revisions": {
                item["id"]: item["asset_revision"] for item in risk_batch["items"]
            },
        },
    )
    selected_id = risk_batch["items"][0]["id"]
    unsupported_scenario = client.post(
        "/api/v1/scenarios/generate",
        json={
            "project_id": ids["project"],
            "requirement_id": ids["requirement"],
            "analysis_id": analysis_id,
            "risk_batch_id": risk_batch["id"],
            "risk_selection": [selected_id],
            "options": {"include_boundary": False},
        },
    )
    assert unsupported_scenario.status_code == 422
    assert unsupported_scenario.json()["error"]["code"] == (
        "GENERATION_OPTION_UNSUPPORTED"
    )
    scenario_run = client.post(
        "/api/v1/scenarios/generate",
        json={
            "project_id": ids["project"],
            "requirement_id": ids["requirement"],
            "analysis_id": analysis_id,
            "risk_batch_id": risk_batch["id"],
            "risk_selection": [selected_id],
            "options": {"include_nominal": True},
        },
    )
    assert scenario_run.status_code == 202, scenario_run.text
    assert scenario_run.json()["input_snapshot"]["command"]["mode"] == "SELECTED"
    assert scenario_run.json()["input_snapshot"]["command"]["selected_ids"] == [
        selected_id
    ]
    assert scenario_run.json()["input_snapshot"]["source"]["type"] == "RISK_BATCH"
    assert scenario_run.json()["input_snapshot"]["source"][
        "selected_asset_ids"
    ] == [selected_id]
    conflicting_selection = client.post(
        "/api/v1/scenarios/generate",
        json={
            "risk_batch_id": risk_batch["id"],
            "risk_ids": [selected_id],
            "risk_selection": ["different-id"],
        },
    )
    assert conflicting_selection.status_code == 422

    scenario_batch = client.get(
        f"/api/v1/scenario-batches/{scenario_run.json()['result_id']}"
    ).json()
    nominal = next(
        item for item in scenario_batch["items"] if item["code"] == "SCN-NOMINAL"
    )
    client.post(
        f"/api/v1/scenario-batches/{scenario_batch['id']}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [nominal["id"]],
            "expected_revisions": {nominal["id"]: nominal["asset_revision"]},
        },
    )
    case_run = client.post(
        "/api/v1/testcases/generate",
        json={
            "project_id": ids["project"],
            "requirement_id": ids["requirement"],
            "scenario_batch_id": scenario_batch["id"],
            "scenario_ids": [nominal["id"]],
            "options": {"step_granularity": "EXECUTION_READY"},
        },
    )
    assert case_run.status_code == 202, case_run.text
    assert case_run.json()["input_snapshot"]["source"]["type"] == "SCENARIO_BATCH"
    assert case_run.json()["input_snapshot"]["source"][
        "selected_asset_ids"
    ] == [nominal["id"]]


def test_domain_validator_rejects_non_executable_structured_case() -> None:
    draft = CaseDraft(
        code="TC-INVALID",
        scenario_code="SCN-1",
        title="Invalid execution data",
        objective="Exercise validation",
        preconditions=["Ready"],
        configuration={"profile": ""},
        expected_result="A defined result",
        expected_result_status="DEFINED",
        steps=[
            StepDraft(
                sequence=1,
                action="Execute",
                expected_result="   ",
                test_data={"value": 1},
            )
        ],
        why_generated="Validator regression fixture.",
    )
    with pytest.raises(AppError, match="execution-ready"):
        DomainValidator.test_cases([draft], {"SCN-1"})
