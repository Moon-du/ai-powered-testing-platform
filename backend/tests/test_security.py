from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.main import create_app
from app.models import Base


def test_production_cannot_enable_development_identity_headers() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", dev_auth_enabled=True)


def test_spoofed_identity_headers_are_rejected_without_oidc() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        app_env="production",
        dev_auth_enabled=False,
        seed_demo=False,
        database_url="sqlite+pysqlite:///:memory:",
    )
    app = create_app(settings=settings, session_factory=factory)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/projects",
            headers={"X-Tenant-Id": "victim", "X-User-Id": "admin"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OIDC_NOT_CONFIGURED"


def test_project_role_matrix(client: TestClient, ids: dict[str, str]) -> None:
    for user_id, role in (
        ("editor-user", "EDITOR"),
        ("reviewer-user", "REVIEWER"),
        ("viewer-user", "VIEWER"),
    ):
        response = client.post(
            f"/api/v1/projects/{ids['project']}/members",
            json={"user_id": user_id, "role": role},
        )
        assert response.status_code == 201, response.text

    editor_headers = {
        "X-Tenant-Id": "demo-tenant",
        "X-User-Id": "editor-user",
    }
    run = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze",
        headers=editor_headers,
    )
    assert run.status_code == 202, run.text
    analysis = client.get(
        f"/api/v1/analyses/{run.json()['result_id']}", headers=editor_headers
    ).json()
    editor_review = client.post(
        f"/api/v1/analyses/{analysis['id']}/review",
        headers=editor_headers,
        json={"action": "APPROVE", "expected_revision": analysis["asset_revision"]},
    )
    assert editor_review.status_code == 403

    reviewer_headers = {
        "X-Tenant-Id": "demo-tenant",
        "X-User-Id": "reviewer-user",
    }
    reviewer_review = client.post(
        f"/api/v1/analyses/{analysis['id']}/review",
        headers=reviewer_headers,
        json={"action": "APPROVE", "expected_revision": analysis["asset_revision"]},
    )
    assert reviewer_review.status_code == 200, reviewer_review.text
    reviewer_edit = client.patch(
        f"/api/v1/requirements/{ids['requirement']}",
        headers=reviewer_headers,
        json={
            "title": "Reviewer edit allowed by the P0 permission matrix",
            "expected_revision": 1,
            "change_summary": "",
        },
    )
    assert reviewer_edit.status_code == 200, reviewer_edit.text

    viewer_headers = {
        "X-Tenant-Id": "demo-tenant",
        "X-User-Id": "viewer-user",
    }
    assert client.get(
        f"/api/v1/requirements/{ids['requirement']}", headers=viewer_headers
    ).status_code == 200
    viewer_generate = client.post(
        f"/api/v1/requirements/{ids['requirement']}/analyze",
        headers=viewer_headers,
    )
    assert viewer_generate.status_code == 403
