"""Создание таблицы проектов."""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("organization_name", sa.Text(), nullable=False),
        sa.Column("opo_name", sa.Text(), nullable=False),
        sa.Column("opo_registration_number", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("projects")

