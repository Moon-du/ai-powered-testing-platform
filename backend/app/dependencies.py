from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Header, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    user_id: str


def get_current_actor(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> Actor:
    settings: Settings = request.app.state.settings
    if settings.app_env == "development" and settings.dev_auth_enabled:
        return Actor(
            tenant_id=x_tenant_id or "local-tenant",
            user_id=x_user_id or "dev-user",
        )
    raise AppError(
        503,
        "OIDC_NOT_CONFIGURED",
        "Production identity validation is not configured in this vertical slice.",
    )
