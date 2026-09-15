"""Add execution-ready configuration and step test data.

Revision ID: 0003_execution_ready_test_data
Revises: 0002_ai_run_idempotency
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_execution_ready_test_data"
down_revision = "0002_ai_run_idempotency"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if "configuration_json" not in _columns("test_cases"):
        with op.batch_alter_table("test_cases") as batch:
            batch.add_column(
                sa.Column(
                    "configuration_json",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'{}'"),
                )
            )
        with op.batch_alter_table("test_cases") as batch:
            batch.alter_column(
                "configuration_json", existing_type=sa.JSON(), server_default=None
            )

    if "test_data" not in _columns("test_steps"):
        with op.batch_alter_table("test_steps") as batch:
            batch.add_column(
                sa.Column(
                    "test_data",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'{}'"),
                )
            )
        with op.batch_alter_table("test_steps") as batch:
            batch.alter_column(
                "test_data", existing_type=sa.JSON(), server_default=None
            )


def downgrade() -> None:
    if "test_data" in _columns("test_steps"):
        with op.batch_alter_table("test_steps") as batch:
            batch.drop_column("test_data")
    if "configuration_json" in _columns("test_cases"):
        with op.batch_alter_table("test_cases") as batch:
            batch.drop_column("configuration_json")
