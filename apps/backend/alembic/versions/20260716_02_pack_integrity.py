"""Add application-pack idempotency and verification metadata."""

import sqlalchemy as sa
from alembic import op

revision = "20260716_02"
down_revision = "20260716_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("artifact_packs")}
    if "generation_key" not in columns:
        op.add_column(
            "artifact_packs", sa.Column("generation_key", sa.String(), nullable=True)
        )
    if "verification_json" not in columns:
        op.add_column(
            "artifact_packs",
            sa.Column(
                "verification_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
    indexes = {index["name"] for index in inspector.get_indexes("artifact_packs")}
    if "ix_artifact_packs_generation_key" not in indexes:
        op.create_index(
            "ix_artifact_packs_generation_key", "artifact_packs", ["generation_key"]
        )


def downgrade() -> None:
    op.drop_index("ix_artifact_packs_generation_key", table_name="artifact_packs")
    op.drop_column("artifact_packs", "verification_json")
    op.drop_column("artifact_packs", "generation_key")
