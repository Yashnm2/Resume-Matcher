"""Persist per-pack LLM usage and provider-reported cost."""

import sqlalchemy as sa
from alembic import op

revision = "20260716_05"
down_revision = "20260716_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("artifact_packs")
    }
    if "llm_usage_json" not in columns:
        op.add_column(
            "artifact_packs",
            sa.Column(
                "llm_usage_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    op.drop_column("artifact_packs", "llm_usage_json")
