"""Track private object-storage paths for application packs."""

import sqlalchemy as sa
from alembic import op

revision = "20260716_04"
down_revision = "20260716_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("artifact_packs")
    }
    if "storage_manifest" not in columns:
        op.add_column(
            "artifact_packs",
            sa.Column(
                "storage_manifest",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    op.drop_column("artifact_packs", "storage_manifest")
