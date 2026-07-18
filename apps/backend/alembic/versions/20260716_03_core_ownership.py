"""Add user ownership to legacy résumé, job, improvement, and tracker records."""

import sqlalchemy as sa
from alembic import op

revision = "20260716_03"
down_revision = "20260716_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in ("resumes", "jobs", "improvements", "applications"):
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "user_id" not in columns:
            op.add_column(
                table,
                sa.Column(
                    "user_id", sa.String(), nullable=False, server_default="local-user"
                ),
            )
        indexes = {index["name"] for index in inspector.get_indexes(table)}
        if f"ix_{table}_user_id" not in indexes:
            op.create_index(f"ix_{table}_user_id", table, ["user_id"])
    master_index = next(
        (
            index
            for index in inspector.get_indexes("resumes")
            if index["name"] == "ux_resumes_single_master"
        ),
        None,
    )
    if master_index and master_index.get("column_names") != ["user_id", "is_master"]:
        op.drop_index("ux_resumes_single_master", table_name="resumes")
        master_index = None
    if master_index is None:
        op.create_index(
            "ux_resumes_single_master",
            "resumes",
            ["user_id", "is_master"],
            unique=True,
            postgresql_where=sa.text("is_master = true"),
            sqlite_where=sa.text("is_master = 1"),
        )


def downgrade() -> None:
    op.drop_index("ux_resumes_single_master", table_name="resumes")
    op.create_index(
        "ux_resumes_single_master",
        "resumes",
        ["is_master"],
        unique=True,
        sqlite_where=sa.text("is_master = 1"),
    )
    for table in ("applications", "improvements", "jobs", "resumes"):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
