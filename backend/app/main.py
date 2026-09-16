from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.ai import LLMGateway
from app.bootstrap import ensure_reference_product_types
from app.api import api_router
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.errors import install_error_handlers


def create_app(
    settings: Settings | None = None,
    session_factory: Callable[[], Session] | None = None,
    llm_gateway: LLMGateway | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    active_session_factory = session_factory or SessionLocal

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if active_settings.app_env == "development":
            with active_session_factory() as session:
                ensure_reference_product_types(session)
                session.commit()
        yield

    application = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.session_factory = active_session_factory
    application.state.llm_gateway = llm_gateway
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(application)

    @application.get("/health/live", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(api_router, prefix=active_settings.api_v1_prefix)
    return application


app = create_app()
