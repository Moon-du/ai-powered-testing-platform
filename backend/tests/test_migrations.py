from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.config import get_settings


def _config(database_path: Path, monkeypatch) -> tuple[Config, str]:
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "alembic")
    )
    return config, database_url


def test_execution_ready_fields_migrate_fresh_and_legacy_schema(
    monkeypatch,
) -> None:
    artifact_dir = Path(__file__).parents[1] / ".pytest_cache" / "migration-dbs"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    fresh_path = artifact_dir / f"fresh-{token}.db"
    legacy_path = artifact_dir / f"legacy-{token}.db"
    try:
        fresh_config, fresh_url = _config(fresh_path, monkeypatch)
        command.upgrade(fresh_config, "head")
        fresh_engine = create_engine(fresh_url)
        assert "configuration_json" in {
            item["name"] for item in inspect(fresh_engine).get_columns("test_cases")
        }
        assert "test_data" in {
            item["name"] for item in inspect(fresh_engine).get_columns("test_steps")
        }
        fresh_engine.dispose()

        legacy_config, legacy_url = _config(legacy_path, monkeypatch)
        command.upgrade(legacy_config, "0002_ai_run_idempotency")
        legacy_engine = create_engine(legacy_url)
        with legacy_engine.begin() as connection:
            # 0001 is metadata-driven in this greenfield slice, so remove the new
            # columns to faithfully emulate a database produced by the old model.
            connection.execute(
                text("ALTER TABLE test_cases DROP COLUMN configuration_json")
            )
            connection.execute(text("ALTER TABLE test_steps DROP COLUMN test_data"))
        legacy_engine.dispose()

        command.upgrade(legacy_config, "head")
        migrated_engine = create_engine(legacy_url)
        assert "configuration_json" in {
            item["name"]
            for item in inspect(migrated_engine).get_columns("test_cases")
        }
        assert "test_data" in {
            item["name"]
            for item in inspect(migrated_engine).get_columns("test_steps")
        }
        migrated_engine.dispose()
    finally:
        get_settings.cache_clear()
        fresh_path.unlink(missing_ok=True)
        legacy_path.unlink(missing_ok=True)
