"""Cache normalized posting embeddings by description hash."""

import sqlalchemy as sa
from alembic import op

revision = "20260716_06"
down_revision = "20260716_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("job_postings")
    }
    if "embedding_json" not in columns:
        op.add_column(
            "job_postings",
            sa.Column(
                "embedding_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
        )
    if "embedding_model" not in columns:
        op.add_column(
            "job_postings",
            sa.Column(
                "embedding_model",
                sa.String(),
                nullable=False,
                server_default="local-feature-v1",
            ),
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("job_postings")
    }
    if "embedding_model" in columns:
        op.drop_column("job_postings", "embedding_model")
    if "embedding_json" in columns:
        op.drop_column("job_postings", "embedding_json")
