"""Create the complete user-owned resume and scout schema."""

from alembic import op

from app.models import Base

revision = "20260716_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Deliberately non-destructive: production artifacts and audit history must
    # never be dropped by an automated rollback.
    pass
