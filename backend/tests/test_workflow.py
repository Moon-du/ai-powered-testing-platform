from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from tests.conftest import analyze_and_approve, progress_to_scenarios


def test_project_and_tenant_isolation(client: TestClient, ids: dict[str, str]) -> None:
    other_tenant = client.get(
        "/api/v1/projects",
        headers={"X-Tenant-Id": "tenant-b", "X-User-Id": "bob"},
    ).json()["items"][0]
    other_requirement = client.get(
        f"/api/v1/projects/{other_tenant['id']}/requirements",
        headers={"X-Tenant-Id": "tenant-b", "X-User-Id": "bob"},
    ).json()["items"][0]

    cross_tenant = client.get(
        f"/api/v1/requirements/{other_requirement['id']}"
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    cross_project_member = client.get(
        f"/api/v1/requirements/{ids['requirement']}",
        headers={"X-Tenant-Id": "demo-tenant", "X-User-Id": "intruder"},
    )
    assert cross_project_member.status_code == 404


def test_create_project_wizard_contract(client: TestClient) -> None:
    product = client.get("/api/v1/product-types").json()["items"][0]
    pack = client.get(
        f"/api/v1/product-types/{product['id']}/knowledge-packs"
    ).json()["items"][0]
    created = client.post(
        "/api/v1/projects",
        json={
            "project_code": "EP-WIZARD",
            "name": "Wizard-created project",
            "description": "Contract compatibility check.",
            "product_type_id": product["id"],
            "knowledge_pack_id": pack["id"],
            "knowledge_pack_version": pack["version"],
            "product_variant": "Electronic Pipette",
            "project_version": "1.0",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["product_type"]["code"] == "ELECTRONIC_PIPETTE"
    assert created.json()["knowledge_pack_id"] == pack["id"]
    context = client.get(
        f"/api/v1/projects/{created.json()['id']}/knowledge-context"
    )
    assert context.status_code == 200, context.text
    assert context.json()["knowledge_pack_version"] == "1.0"
    assert context.json()["counts"]["TESTING_RULE"] == 2


def test_project_can_be_created_without_product_type_or_knowledge_pack(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"project_code": "UNCLASSIFIED-1", "name": "待分类项目"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["product_type_id"] is None
    assert response.json()["knowledge_pack_id"] is None
    assert response.json()["knowledge_pack_version"] is None


def test_project_knowledge_file_is_private_and_versioned(client: TestClient) -> None:
    product = client.get("/api/v1/product-types").json()["items"][0]
    preset = client.get(
        f"/api/v1/product-types/{product['id']}/knowledge-packs"
    ).json()["items"][0]
    original_summary = preset["summary"]
    response = client.post(
        "/api/v1/projects",
        json={
            "project_code": "PRIVATE-KNOWLEDGE-1",
            "name": "项目私有知识",
            "product_type_id": product["id"],
            "knowledge_pack_id": preset["id"],
            "knowledge_pack_version": preset["version"],
        },
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]

    uploaded = client.post(
        f"/api/v1/projects/{project_id}/knowledge/files?bump_version=false",
        files={"files": ("guide.txt", "项目专属校准流程。", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["knowledge_pack_id"] != preset["id"]
    assert uploaded.json()["knowledge_pack_version"] == preset["version"]
    document = next(
        item for item in uploaded.json()["items"] if item["title"] == "guide.txt"
    )

    updated = client.put(
        f"/api/v1/projects/{project_id}/knowledge/items/{document['code']}?bump_version=true",
        json={
            "item_type": "DOCUMENT",
            "title": "项目校准指南",
            "content": "更新后的项目专属校准流程。",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["knowledge_pack_version"] != preset["version"]

    presets_after = client.get(
        f"/api/v1/product-types/{product['id']}/knowledge-packs"
    ).json()["items"]
    unchanged = next(item for item in presets_after if item["id"] == preset["id"])
    assert unchanged["summary"] == original_summary


def test_requirement_analysis_succeeds_without_knowledge_pack(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"project_code": "NO-PACK-AI", "name": "无知识包分析"},
    ).json()
    requirement = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json={
            "requirement_code": "REQ-NO-PACK",
            "title": "无知识包需求",
            "original_text": "系统应在操作完成后显示成功状态。",
        },
    )
    assert requirement.status_code == 201, requirement.text

    run = client.post(
        f"/api/v1/requirements/{requirement.json()['id']}/analyze"
    )
    assert run.status_code == 202, run.text
    assert run.json()["status"] == "SUCCEEDED"
    assert run.json()["error_code"] is None


def test_deleting_last_project_knowledge_item_restores_none(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"project_code": "EMPTY-KNOWLEDGE", "name": "空知识项目"},
    ).json()
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/knowledge/files",
        files={"files": ("only.txt", "唯一知识条目。", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text

    item_code = uploaded.json()["items"][0]["code"]
    deleted = client.delete(
        f"/api/v1/projects/{project['id']}/knowledge/items/{item_code}"
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["items"] == []
    assert deleted.json()["knowledge_pack_id"] is None
    assert deleted.json()["knowledge_pack_version"] is None


def test_delete_project_removes_private_knowledge_and_project_access(
    client: TestClient,
) -> None:
    project = client.post(
        "/api/v1/projects",
        json={"project_code": "DELETE-ME", "name": "待删除项目"},
    ).json()
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/knowledge/files",
        files={"files": ("private.txt", "仅属于待删除项目。", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    private_pack_id = uploaded.json()["knowledge_pack_id"]
    requirement = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json={
            "requirement_code": "REQ-DELETE",
            "title": "待删除需求",
            "original_text": "本需求随项目删除。",
        },
    )
    assert requirement.status_code == 201, requirement.text

    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert client.get(f"/api/v1/knowledge-packs/{private_pack_id}").status_code == 404


def test_human_gates_and_executable_case(client: TestClient, ids: dict[str, str]) -> None:
    run = client.post(f"/api/v1/requirements/{ids['requirement']}/analyze")
    assert run.status_code == 202
    analysis_id = run.json()["result_id"]

    blocked_risk = client.post(
        f"/api/v1/analyses/{analysis_id}/risks/generate", json={"mode": "ALL"}
    )
    assert blocked_risk.status_code == 409
    assert blocked_risk.json()["error"]["code"] == "WORKFLOW_GATE_BLOCKED"

    analysis = client.get(f"/api/v1/analyses/{analysis_id}").json()
    approved = client.post(
        f"/api/v1/analyses/{analysis_id}/review",
        json={"action": "APPROVE", "expected_revision": analysis["asset_revision"]},
    ).json()
    risk_run = client.post(
        f"/api/v1/analyses/{approved['id']}/risks/generate",
        json={"mode": "ALL"},
    )
    risk_batch_id = risk_run.json()["result_id"]
    blocked_scenario = client.post(
        f"/api/v1/risk-batches/{risk_batch_id}/scenarios/generate",
        json={"mode": "ALL"},
    )
    assert blocked_scenario.status_code == 409

    risk_batch = client.get(f"/api/v1/risk-batches/{risk_batch_id}").json()
    client.post(
        f"/api/v1/risk-batches/{risk_batch_id}/review",
        json={
            "action": "APPROVE",
            "risk_ids": [item["id"] for item in risk_batch["items"]],
            "expected_revisions": {
                item["id"]: item["asset_revision"] for item in risk_batch["items"]
            },
        },
    )
    scenario_run = client.post(
        f"/api/v1/risk-batches/{risk_batch_id}/scenarios/generate",
        json={"mode": "ALL"},
    )
    scenario_batch_id = scenario_run.json()["result_id"]
    blocked_case = client.post(
        f"/api/v1/scenario-batches/{scenario_batch_id}/test-cases/generate",
        json={"mode": "ALL"},
    )
    assert blocked_case.status_code == 409

    scenario_batch = client.get(
        f"/api/v1/scenario-batches/{scenario_batch_id}"
    ).json()
    nominal = next(item for item in scenario_batch["items"] if item["code"] == "SCN-NOMINAL")
    reviewed = client.post(
        f"/api/v1/scenario-batches/{scenario_batch_id}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [nominal["id"]],
            "expected_revisions": {nominal["id"]: nominal["asset_revision"]},
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    case_run = client.post(
        f"/api/v1/scenario-batches/{scenario_batch_id}/test-cases/generate",
        json={"mode": "SELECTED", "selected_ids": [nominal["id"]]},
    )
    assert case_run.status_code == 202, case_run.text
    assert case_run.json()["status"] == "SUCCEEDED"
    case_batch = client.get(
        f"/api/v1/test-case-batches/{case_run.json()['result_id']}"
    ).json()
    assert len(case_batch["items"]) == 1
    generated_case = case_batch["items"][0]
    assert generated_case["configuration_json"] == {
        "product": "Electronic Pipette",
        "operating_mode": "VOLUME_SETTING",
        "unit": "µL",
    }
    assert generated_case["steps"]
    assert generated_case["steps"][1]["test_data"] == {
        "configured_volume_uL": 150
    }
    assert generated_case["why_generated"]
    assert generated_case["knowledge_references"]


def test_optimistic_version_conflict(client: TestClient, ids: dict[str, str]) -> None:
    run = client.post(f"/api/v1/requirements/{ids['requirement']}/analyze").json()
    analysis = client.get(f"/api/v1/analyses/{run['result_id']}").json()
    response = client.post(
        f"/api/v1/analyses/{analysis['id']}/review",
        json={"action": "APPROVE", "expected_revision": 99},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_VERSION_CONFLICT"
    assert response.json()["error"]["details"]["actual_revision"] == 1


def test_requirement_semantic_change_propagates_stale(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenario_batch = progress_to_scenarios(client, ids["requirement"])
    nominal = next(item for item in scenario_batch["items"] if item["code"] == "SCN-NOMINAL")
    client.post(
        f"/api/v1/scenario-batches/{scenario_batch['id']}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [nominal["id"]],
            "expected_revisions": {nominal["id"]: nominal["asset_revision"]},
        },
    )
    case_run = client.post(
        f"/api/v1/scenario-batches/{scenario_batch['id']}/test-cases/generate",
        json={"mode": "SELECTED", "selected_ids": [nominal["id"]]},
    ).json()
    case_batch_id = case_run["result_id"]

    requirement = client.get(
        f"/api/v1/requirements/{ids['requirement']}"
    ).json()
    updated = client.patch(
        f"/api/v1/requirements/{ids['requirement']}",
        json={
            "original_text": "User can configure dispensing volume from 10 µL to 250 µL.",
            "change_summary": "Maximum changed after design review.",
            "expected_revision": requirement["revision"],
        },
    )
    assert updated.status_code == 200, updated.text

    workflow = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()
    assert workflow["active_assets"]["analysis"]["status"] == "STALE"
    assert workflow["active_assets"]["risk_batch"]["status"] == "STALE"
    assert workflow["active_assets"]["scenario_batch"]["status"] == "STALE"
    assert client.get(
        f"/api/v1/test-case-batches/{case_batch_id}"
    ).json()["status"] == "STALE"


def test_undefined_expected_result_flows_to_case_but_blocks_case_approval(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenario_batch = progress_to_scenarios(client, ids["requirement"])
    undefined = [
        item
        for item in scenario_batch["items"]
        if item["code"] in {"SCN-BELOW", "SCN-ABOVE", "SCN-PERSISTENCE"}
    ]
    assert len(undefined) == 3
    assert all(item["expected_result"] is None for item in undefined)
    assert all(
        item["expected_result_status"] == "CLARIFICATION_REQUIRED"
        and item["blocking_questions_json"]
        for item in undefined
    )

    response = client.post(
        f"/api/v1/scenario-batches/{scenario_batch['id']}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [item["id"] for item in scenario_batch["items"]],
            "expected_revisions": {
                item["id"]: item["asset_revision"]
                for item in scenario_batch["items"]
            },
        },
    )
    assert response.status_code == 200, response.text

    case_run = client.post(
        "/api/v1/testcases/generate",
        json={"scenario_batch_id": scenario_batch["id"], "mode": "ALL"},
    )
    assert case_run.status_code == 202, case_run.text
    case_batch = client.get(
        f"/api/v1/testcase-batches/{case_run.json()['result_id']}"
    ).json()
    undefined_cases = [
        item
        for item in case_batch["items"]
        if item["expected_result_status"] == "CLARIFICATION_REQUIRED"
    ]
    assert len(undefined_cases) == 3
    assert all(item["expected_result"] is None for item in undefined_cases)
    blocked = client.post(
        f"/api/v1/test-case-batches/{case_batch['id']}/review",
        json={
            "action": "APPROVE",
            "test_case_ids": [undefined_cases[0]["id"]],
            "expected_revisions": {
                undefined_cases[0]["id"]: undefined_cases[0]["asset_revision"]
            },
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "WORKFLOW_GATE_BLOCKED"

    risk_batch_id = scenario_batch["source_risk_batch_id"]
    risks = client.get(f"/api/v1/risk-batches/{risk_batch_id}").json()["items"]
    persistence = next(item for item in risks if item["code"] == "RISK-PERSISTENCE")
    assert persistence["requirement_gap"] is True

    coverage = client.get(
        f"/api/v1/projects/{ids['project']}/coverage"
    ).json()
    assert coverage["issues"]["undefined_expected_behaviors"] >= 3
    assert coverage["issues"]["requirement_gaps"] == 1


def test_scenario_semantic_edit_marks_case_stale(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenario_batch = progress_to_scenarios(client, ids["requirement"])
    nominal = next(item for item in scenario_batch["items"] if item["code"] == "SCN-NOMINAL")
    review = client.post(
        f"/api/v1/scenario-batches/{scenario_batch['id']}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [nominal["id"]],
            "expected_revisions": {nominal["id"]: nominal["asset_revision"]},
        },
    ).json()
    reviewed_nominal = next(
        item for item in review["items"] if item["id"] == nominal["id"]
    )
    case_run = client.post(
        "/api/v1/testcases/generate",
        json={
            "scenario_batch_id": scenario_batch["id"],
            "mode": "SELECTED",
            "scenario_ids": [nominal["id"]],
        },
    ).json()
    case_batch_id = case_run["result_id"]

    changed = client.patch(
        f"/api/v1/scenario-batches/{scenario_batch['id']}/scenarios/{nominal['id']}",
        json={
            "intent": "Configure 160 µL and verify the selected setting.",
            "expected_revision": reviewed_nominal["asset_revision"],
        },
    )
    assert changed.status_code == 200, changed.text
    stale_batch = client.get(f"/api/v1/testcase-batches/{case_batch_id}").json()
    assert stale_batch["status"] == "STALE"
    assert stale_batch["items"][0]["status"] == "STALE"


def test_canonical_generation_aliases(client: TestClient, ids: dict[str, str]) -> None:
    analysis = analyze_and_approve(client, ids["requirement"])
    risk_run = client.post(
        "/api/v1/risks/generate",
        json={"analysis_id": analysis["id"], "mode": "ALL"},
    )
    assert risk_run.status_code == 202, risk_run.text
    risk_batch = client.get(
        f"/api/v1/risk-batches/{risk_run.json()['result']['id']}"
    ).json()
    client.post(
        f"/api/v1/risk-batches/{risk_batch['id']}/review",
        json={
            "action": "APPROVE",
            "risk_ids": [item["id"] for item in risk_batch["risks"]],
            "expected_revisions": {
                item["id"]: item["asset_revision"] for item in risk_batch["risks"]
            },
        },
    )
    scenario_run = client.post(
        "/api/v1/scenarios/generate",
        json={"risk_batch_id": risk_batch["id"], "mode": "ALL"},
    )
    assert scenario_run.status_code == 202, scenario_run.text
    scenario_batch = client.get(
        f"/api/v1/scenario-batches/{scenario_run.json()['result_id']}"
    ).json()
    nominal = next(item for item in scenario_batch["scenarios"] if item["code"] == "SCN-NOMINAL")
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
            "scenario_batch_id": scenario_batch["id"],
            "mode": "SELECTED",
            "scenario_ids": [nominal["id"]],
        },
    )
    assert case_run.status_code == 202, case_run.text
    assert case_run.json()["task_type"] == "TEST_CASE"


def test_regeneration_keeps_and_supersedes_prior_batch(
    client: TestClient, ids: dict[str, str]
) -> None:
    analysis = analyze_and_approve(client, ids["requirement"])
    first = client.post(
        "/api/v1/risks/generate",
        json={"analysis_id": analysis["id"], "mode": "ALL"},
        headers={"Idempotency-Key": "risk-version-1"},
    ).json()
    second = client.post(
        "/api/v1/risks/generate",
        json={"analysis_id": analysis["id"], "mode": "ALL"},
        headers={"Idempotency-Key": "risk-version-2"},
    ).json()
    first_batch = client.get(
        f"/api/v1/risk-batches/{first['result_id']}"
    ).json()
    second_batch = client.get(
        f"/api/v1/risk-batches/{second['result_id']}"
    ).json()
    assert first_batch["status"] == "SUPERSEDED"
    assert all(item["status"] == "SUPERSEDED" for item in first_batch["items"])
    assert second_batch["revision"] == first_batch["revision"] + 1
    assert second_batch["supersedes_id"] == first_batch["id"]


def test_idempotency_replays_identical_request_and_rejects_key_reuse(
    client: TestClient, ids: dict[str, str]
) -> None:
    headers = {"Idempotency-Key": "analysis-stable-key"}
    first = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze", headers=headers
    )
    replay = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze", headers=headers
    )
    assert first.status_code == replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]
    assert first.json()["actor_id"] == "dev-user"
    snapshot = first.json()["input_snapshot"]
    assert snapshot["knowledge_pack_id"]
    assert snapshot["format_version"] == 1
    assert snapshot["requirement"]["revision"] == 1
    assert snapshot["requirement"]["id"] == ids["requirement"]
    assert snapshot["requirement"]["semantic_hash"]
    assert snapshot["knowledge_pack_version"] == "1.0"
    assert snapshot["project_context_revision"] == 1
    assert snapshot["project_context_hash"]
    assert snapshot["knowledge_content_hash"]
    assert "knowledge_items" not in snapshot
    assert "original_text" not in snapshot["requirement"]
    assert snapshot["prompt_version"] == "deepseek-v1"
    assert snapshot["validator_version"] == "p0-domain-v1"
    assert snapshot["policy_version"] == "p0-guardrail-v1"
    workflow = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()
    assert workflow["current_stage"] == "ANALYSIS_REVIEW"
    assert "REVIEW_ANALYSIS" in workflow["available_actions"]
    assert workflow["requirement_id"] == ids["requirement"]

    another = client.post(
        f"/api/v1/projects/{ids['project']}/requirements",
        json={
            "requirement_code": "EP-REQ-IDEMPOTENCY",
            "title": "Second requirement",
            "original_text": "User can select a saved program.",
        },
    )
    assert another.status_code == 201, another.text
    conflict = client.post(
        f"/api/v1/requirements/{another.json()['id']}/analyze", headers=headers
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_celery_idempotent_replay_dispatches_only_once(
    client: TestClient, ids: dict[str, str], monkeypatch: MonkeyPatch
) -> None:
    from app.ai.tasks import process_ai_run

    dispatched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        process_ai_run,
        "delay",
        lambda tenant_id, run_id: dispatched.append((tenant_id, run_id)),
    )
    client.app.state.settings.ai_task_mode = "celery"
    headers = {"Idempotency-Key": "celery-stable-key"}

    first = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze", headers=headers
    )
    replay = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze", headers=headers
    )

    assert first.status_code == replay.status_code == 202
    assert first.json()["id"] == replay.json()["id"]
    assert first.json()["status"] == "QUEUED"
    assert dispatched == [("demo-tenant", first.json()["id"])]
