"""Scope AI-run idempotency to the actor and record the request hash.

Revision ID: 0002_ai_run_idempotency
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_ai_run_idempotency"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _unique_columns() -> list[str] | None:
    for constraint in sa.inspect(op.get_bind()).get_unique_constraints("ai_runs"):
        if constraint.get("name") == "uq_ai_run_idempotency":
            return list(constraint.get("column_names") or [])
    return None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("ai_runs")
    }
    if "actor_id" not in columns or "request_hash" not in columns:
        with op.batch_alter_table("ai_runs") as batch:
            if "actor_id" not in columns:
                batch.add_column(sa.Column("actor_id", sa.String(200), nullable=True))
            if "request_hash" not in columns:
                batch.add_column(sa.Column("request_hash", sa.String(64), nullable=True))

        op.execute(
            sa.text(
                "UPDATE ai_runs SET actor_id = 'legacy-unknown' "
                "WHERE actor_id IS NULL"
            )
        )
        op.execute(
            sa.text(
                "UPDATE ai_runs SET request_hash = 'legacy-unavailable' "
                "WHERE request_hash IS NULL"
            )
        )
        with op.batch_alter_table("ai_runs") as batch:
            batch.alter_column(
                "actor_id", existing_type=sa.String(200), nullable=False
            )
            batch.alter_column(
                "request_hash", existing_type=sa.String(64), nullable=False
            )

    target = [
        "tenant_id",
        "project_id",
        "actor_id",
        "run_type",
        "idempotency_key",
    ]
    existing = _unique_columns()
    if existing != target:
        with op.batch_alter_table("ai_runs") as batch:
            if existing is not None:
                batch.drop_constraint("uq_ai_run_idempotency", type_="unique")
            batch.create_unique_constraint("uq_ai_run_idempotency", target)

    indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("ai_runs")
    }
    if "ix_ai_runs_actor_id" not in indexes:
        op.create_index("ix_ai_runs_actor_id", "ai_runs", ["actor_id"])


def downgrade() -> None:
    existing = _unique_columns()
    legacy = ["tenant_id", "project_id", "run_type", "idempotency_key"]
    if existing != legacy:
        with op.batch_alter_table("ai_runs") as batch:
            if existing is not None:
                batch.drop_constraint("uq_ai_run_idempotency", type_="unique")
            batch.create_unique_constraint("uq_ai_run_idempotency", legacy)

    indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("ai_runs")
    }
    if "ix_ai_runs_actor_id" in indexes:
        op.drop_index("ix_ai_runs_actor_id", table_name="ai_runs")
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("ai_runs")
    }
    with op.batch_alter_table("ai_runs") as batch:
        if "request_hash" in columns:
            batch.drop_column("request_hash")
        if "actor_id" in columns:
            batch.drop_column("actor_id")

