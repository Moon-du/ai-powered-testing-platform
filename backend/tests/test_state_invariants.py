from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import analyze_and_approve, progress_to_scenarios


def _generate_nominal_case(
    client: TestClient, requirement_id: str
) -> tuple[dict, dict, dict]:
    scenarios = progress_to_scenarios(client, requirement_id)
    nominal = next(item for item in scenarios["items"] if item["code"] == "SCN-NOMINAL")
    reviewed = client.post(
        f"/api/v1/scenario-batches/{scenarios['id']}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [nominal["id"]],
            "expected_revisions": {nominal["id"]: nominal["asset_revision"]},
        },
    ).json()
    nominal = next(item for item in reviewed["items"] if item["id"] == nominal["id"])
    run = client.post(
        f"/api/v1/scenario-batches/{scenarios['id']}/test-cases/generate",
        json={"mode": "SELECTED", "selected_ids": [nominal["id"]]},
    )
    assert run.status_code == 202, run.text
    cases = client.get(
        f"/api/v1/test-case-batches/{run.json()['result_id']}"
    ).json()
    return reviewed, nominal, cases


def test_rejecting_approved_analysis_stales_all_downstream(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenarios, _nominal, cases = _generate_nominal_case(client, ids["requirement"])
    risk_batch = client.get(
        f"/api/v1/risk-batches/{scenarios['source_risk_batch_id']}"
    ).json()
    analysis = client.get(
        f"/api/v1/analyses/{risk_batch['source_analysis_id']}"
    ).json()
    rejected = client.post(
        f"/api/v1/analyses/{analysis['id']}/review",
        json={"action": "REJECT", "expected_revision": analysis["asset_revision"], "rejection_reason": "INCORRECT"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert client.get(f"/api/v1/risk-batches/{risk_batch['id']}").json()[
        "status"
    ] == "STALE"
    assert client.get(f"/api/v1/scenario-batches/{scenarios['id']}").json()[
        "status"
    ] == "STALE"
    assert client.get(f"/api/v1/test-case-batches/{cases['id']}").json()[
        "status"
    ] == "STALE"
    actions = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()["available_actions"]
    assert "REVIEW_RISKS" not in actions
    assert "REVIEW_SCENARIOS" not in actions
    assert "REVIEW_TEST_CASES" not in actions


def test_rejecting_approved_risk_stales_scenarios_and_cases(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenarios, nominal, cases = _generate_nominal_case(client, ids["requirement"])
    risk_batch = client.get(
        f"/api/v1/risk-batches/{scenarios['source_risk_batch_id']}"
    ).json()
    boundary = next(item for item in risk_batch["items"] if item["code"] == "RISK-BOUNDARY")
    rejected_risk = client.post(
        f"/api/v1/risk-batches/{risk_batch['id']}/review",
        json={
            "action": "REJECT",
            "rejection_reason": "INCORRECT",
            "risk_ids": [boundary["id"]],
            "expected_revisions": {boundary["id"]: boundary["asset_revision"]},
        },
    )
    assert rejected_risk.status_code == 200, rejected_risk.text
    assert client.get(f"/api/v1/scenario-batches/{scenarios['id']}").json()[
        "status"
    ] == "STALE"
    assert client.get(f"/api/v1/test-case-batches/{cases['id']}").json()[
        "status"
    ] == "STALE"
    actions = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()["available_actions"]
    assert "REVIEW_RISKS" in actions
    assert "REVIEW_TEST_CASES" not in actions


def test_rejecting_approved_scenario_stales_cases(
    client: TestClient, ids: dict[str, str]
) -> None:
    fresh_scenarios, fresh_nominal, fresh_cases = _generate_nominal_case(
        client, ids["requirement"]
    )
    rejected_scenario = client.post(
        f"/api/v1/scenario-batches/{fresh_scenarios['id']}/review",
        json={
            "action": "REJECT",
            "rejection_reason": "INCORRECT",
            "scenario_ids": [fresh_nominal["id"]],
            "expected_revisions": {
                fresh_nominal["id"]: fresh_nominal["asset_revision"]
            },
        },
    )
    assert rejected_scenario.status_code == 200, rejected_scenario.text
    assert client.get(
        f"/api/v1/test-case-batches/{fresh_cases['id']}"
    ).json()["status"] == "STALE"


def test_item_edits_recompute_parent_batch_status(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenarios = progress_to_scenarios(client, ids["requirement"])
    approved_scenarios = client.post(
        f"/api/v1/scenario-batches/{scenarios['id']}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [item["id"] for item in scenarios["items"]],
            "expected_revisions": {
                item["id"]: item["asset_revision"] for item in scenarios["items"]
            },
        },
    ).json()
    assert approved_scenarios["status"] == "APPROVED"
    nominal = next(
        item for item in approved_scenarios["items"] if item["code"] == "SCN-NOMINAL"
    )
    case_run = client.post(
        "/api/v1/testcases/generate",
        json={
            "scenario_batch_id": scenarios["id"],
            "mode": "SELECTED",
            "scenario_ids": [nominal["id"]],
        },
    ).json()
    cases = client.get(
        f"/api/v1/test-case-batches/{case_run['result_id']}"
    ).json()
    case = cases["items"][0]
    approved_cases = client.post(
        f"/api/v1/test-case-batches/{cases['id']}/review",
        json={
            "action": "APPROVE",
            "test_case_ids": [case["id"]],
            "expected_revisions": {case["id"]: case["asset_revision"]},
        },
    ).json()
    assert approved_cases["status"] == "APPROVED"
    case = approved_cases["items"][0]
    edited_case = client.patch(
        f"/api/v1/test-cases/{case['id']}",
        json={
            "title": "Human-edited nominal case",
            "configuration": {"unit": "µL", "calibration_profile": "EP-300"},
            "expected_revision": case["asset_revision"],
        },
    )
    assert edited_case.status_code == 200, edited_case.text
    assert client.get(f"/api/v1/test-case-batches/{cases['id']}").json()[
        "status"
    ] == "HUMAN_EDITED"

    edited_scenario = client.patch(
        f"/api/v1/scenarios/{nominal['id']}",
        json={
            "title": "Human-edited nominal scenario",
            "expected_revision": nominal["asset_revision"],
        },
    )
    assert edited_scenario.status_code == 200, edited_scenario.text
    assert client.get(f"/api/v1/scenario-batches/{scenarios['id']}").json()[
        "status"
    ] == "HUMAN_EDITED"

    risk_batch = client.get(
        f"/api/v1/risk-batches/{scenarios['source_risk_batch_id']}"
    ).json()
    assert risk_batch["status"] == "APPROVED"
    risk = risk_batch["items"][0]
    edited_risk = client.patch(
        f"/api/v1/risks/{risk['id']}",
        json={
            "title": "Human-edited risk",
            "expected_revision": risk["asset_revision"],
        },
    )
    assert edited_risk.status_code == 200, edited_risk.text
    assert client.get(f"/api/v1/risk-batches/{risk_batch['id']}").json()[
        "status"
    ] == "HUMAN_EDITED"


def test_stale_propagation_includes_previously_rejected_assets(
    client: TestClient, ids: dict[str, str]
) -> None:
    analysis = analyze_and_approve(client, ids["requirement"])
    risk_run = client.post(
        f"/api/v1/analyses/{analysis['id']}/risks/generate",
        json={"mode": "ALL"},
    ).json()
    batch = client.get(f"/api/v1/risk-batches/{risk_run['result_id']}").json()
    risk = batch["items"][0]
    rejected = client.post(
        f"/api/v1/risk-batches/{batch['id']}/review",
        json={
            "action": "REJECT",
            "rejection_reason": "INCORRECT",
            "risk_ids": [risk["id"]],
            "expected_revisions": {risk["id"]: risk["asset_revision"]},
        },
    )
    assert rejected.status_code == 200, rejected.text
    requirement = client.get(
        f"/api/v1/requirements/{ids['requirement']}"
    ).json()
    client.patch(
        f"/api/v1/requirements/{ids['requirement']}",
        json={
            "title": "Semantically updated requirement",
            "expected_revision": requirement["revision"],
            "change_summary": "Force downstream invalidation.",
        },
    )
    refreshed = client.get(f"/api/v1/risk-batches/{batch['id']}").json()
    assert next(item for item in refreshed["items"] if item["id"] == risk["id"])[
        "status"
    ] == "STALE"


def test_workflow_exposes_regeneration_actions_at_each_gate(
    client: TestClient, ids: dict[str, str]
) -> None:
    run = client.post(f"/api/v1/requirements/{ids['requirement']}/analyze").json()
    workflow = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()
    assert "REGENERATE_ANALYSIS" in workflow["available_actions"]
    analysis = client.get(f"/api/v1/analyses/{run['result_id']}").json()
    client.post(
        f"/api/v1/analyses/{analysis['id']}/review",
        json={"action": "APPROVE", "expected_revision": analysis["asset_revision"]},
    )
    risk_run = client.post(
        f"/api/v1/analyses/{analysis['id']}/risks/generate",
        json={"mode": "ALL"},
    ).json()
    workflow = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()
    assert "REGENERATE_RISKS" in workflow["available_actions"]
    risks = client.get(f"/api/v1/risk-batches/{risk_run['result_id']}").json()
    client.post(
        f"/api/v1/risk-batches/{risks['id']}/review",
        json={
            "action": "APPROVE",
            "risk_ids": [item["id"] for item in risks["items"]],
            "expected_revisions": {
                item["id"]: item["asset_revision"] for item in risks["items"]
            },
        },
    )
    scenario_run = client.post(
        f"/api/v1/risk-batches/{risks['id']}/scenarios/generate",
        json={"mode": "ALL"},
    ).json()
    workflow = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()
    assert "REGENERATE_SCENARIOS" in workflow["available_actions"]
    scenarios = client.get(
        f"/api/v1/scenario-batches/{scenario_run['result_id']}"
    ).json()
    nominal = next(item for item in scenarios["items"] if item["code"] == "SCN-NOMINAL")
    client.post(
        f"/api/v1/scenario-batches/{scenarios['id']}/review",
        json={
            "action": "APPROVE",
            "scenario_ids": [nominal["id"]],
            "expected_revisions": {nominal["id"]: nominal["asset_revision"]},
        },
    )
    client.post(
        f"/api/v1/scenario-batches/{scenarios['id']}/test-cases/generate",
        json={"mode": "SELECTED", "selected_ids": [nominal["id"]]},
    )
    workflow = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()
    assert "REGENERATE_TEST_CASES" in workflow["available_actions"]


def test_case_approval_requires_execution_ready_configuration(
    client: TestClient, ids: dict[str, str]
) -> None:
    _scenarios, _nominal, cases = _generate_nominal_case(
        client, ids["requirement"]
    )
    case = cases["items"][0]
    emptied = client.patch(
        f"/api/v1/test-cases/{case['id']}",
        json={
            "configuration": {},
            "expected_revision": case["asset_revision"],
        },
    )
    assert emptied.status_code == 200, emptied.text
    blocked = client.post(
        f"/api/v1/test-case-batches/{cases['id']}/review",
        json={
            "action": "APPROVE",
            "test_case_ids": [case["id"]],
            "expected_revisions": {
                case["id"]: emptied.json()["asset_revision"]
            },
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "WORKFLOW_GATE_BLOCKED"


def test_regenerating_analysis_invalidates_old_approved_chain(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenarios, _nominal, cases = _generate_nominal_case(
        client, ids["requirement"]
    )
    risk_batch = client.get(
        f"/api/v1/risk-batches/{scenarios['source_risk_batch_id']}"
    ).json()
    old_analysis_id = risk_batch["source_analysis_id"]
    regenerated = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze",
        headers={"Idempotency-Key": "regenerate-analysis-new-run"},
    )
    assert regenerated.status_code == 202, regenerated.text
    assert regenerated.json()["result_id"] != old_analysis_id
    assert client.get(f"/api/v1/analyses/{old_analysis_id}").json()[
        "status"
    ] == "SUPERSEDED"
    assert client.get(f"/api/v1/risk-batches/{risk_batch['id']}").json()[
        "status"
    ] == "STALE"
    assert client.get(f"/api/v1/scenario-batches/{scenarios['id']}").json()[
        "status"
    ] == "STALE"
    assert client.get(f"/api/v1/test-case-batches/{cases['id']}").json()[
        "status"
    ] == "STALE"
    actions = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()["available_actions"]
    assert "REVIEW_RISKS" not in actions
    assert "REVIEW_SCENARIOS" not in actions
    assert "REVIEW_TEST_CASES" not in actions


def test_regenerating_risks_invalidates_old_scenario_and_case_chain(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenarios, _nominal, cases = _generate_nominal_case(
        client, ids["requirement"]
    )
    old_risk_batch = client.get(
        f"/api/v1/risk-batches/{scenarios['source_risk_batch_id']}"
    ).json()
    regenerated = client.post(
        f"/api/v1/analyses/{old_risk_batch['source_analysis_id']}/risks/generate",
        json={"mode": "ALL"},
        headers={"Idempotency-Key": "regenerate-risks-new-run"},
    )
    assert regenerated.status_code == 202, regenerated.text
    assert regenerated.json()["result_id"] != old_risk_batch["id"]
    assert client.get(f"/api/v1/risk-batches/{old_risk_batch['id']}").json()[
        "status"
    ] == "SUPERSEDED"
    assert client.get(f"/api/v1/scenario-batches/{scenarios['id']}").json()[
        "status"
    ] == "STALE"
    assert client.get(f"/api/v1/test-case-batches/{cases['id']}").json()[
        "status"
    ] == "STALE"
    actions = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()["available_actions"]
    assert "REVIEW_RISKS" in actions
    assert "REVIEW_SCENARIOS" not in actions
    assert "REVIEW_TEST_CASES" not in actions


def test_regenerating_scenarios_invalidates_old_case_chain(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenarios, _nominal, cases = _generate_nominal_case(
        client, ids["requirement"]
    )
    regenerated = client.post(
        f"/api/v1/risk-batches/{scenarios['source_risk_batch_id']}/scenarios/generate",
        json={"mode": "ALL"},
        headers={"Idempotency-Key": "regenerate-scenarios-new-run"},
    )
    assert regenerated.status_code == 202, regenerated.text
    assert regenerated.json()["result_id"] != scenarios["id"]
    assert client.get(f"/api/v1/scenario-batches/{scenarios['id']}").json()[
        "status"
    ] == "SUPERSEDED"
    assert client.get(f"/api/v1/test-case-batches/{cases['id']}").json()[
        "status"
    ] == "STALE"
    actions = client.get(
        f"/api/v1/requirements/{ids['requirement']}/workflow"
    ).json()["available_actions"]
    assert "REVIEW_SCENARIOS" in actions
    assert "REVIEW_TEST_CASES" not in actions


def test_noop_risk_edit_does_not_falsely_stale_downstream(
    client: TestClient, ids: dict[str, str]
) -> None:
    scenarios, _nominal, cases = _generate_nominal_case(
        client, ids["requirement"]
    )
    risk_batch = client.get(
        f"/api/v1/risk-batches/{scenarios['source_risk_batch_id']}"
    ).json()
    risk = next(item for item in risk_batch["items"] if item["code"] == "RISK-BOUNDARY")
    edited = client.patch(
        f"/api/v1/risks/{risk['id']}",
        json={
            "title": risk["title"],
            "expected_revision": risk["asset_revision"],
        },
    )
    assert edited.status_code == 200, edited.text
    assert client.get(f"/api/v1/scenario-batches/{scenarios['id']}").json()[
        "status"
    ] != "STALE"
    assert client.get(f"/api/v1/test-case-batches/{cases['id']}").json()[
        "status"
    ] != "STALE"
