"""Добавление снимков организации и ОПО."""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "organization_snapshot_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "opo_snapshot_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "opo_snapshot_json")
    op.drop_column("projects", "organization_snapshot_json")
