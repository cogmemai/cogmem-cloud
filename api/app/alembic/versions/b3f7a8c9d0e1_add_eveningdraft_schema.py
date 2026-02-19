"""Add eveningdraft schema and user table

Revision ID: b3f7a8c9d0e1
Revises: 1a31ce608336
Create Date: 2026-02-19 08:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b3f7a8c9d0e1"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the eveningdraft schema
    op.execute("CREATE SCHEMA IF NOT EXISTS eveningdraft")

    # Create the eveningdraft.user table
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="eveningdraft",
    )
    op.create_index(
        "ix_eveningdraft_user_email",
        "user",
        ["email"],
        unique=True,
        schema="eveningdraft",
    )
    op.create_index(
        "ix_eveningdraft_user_tenant_id",
        "user",
        ["tenant_id"],
        unique=False,
        schema="eveningdraft",
    )


def downgrade() -> None:
    op.drop_index("ix_eveningdraft_user_tenant_id", table_name="user", schema="eveningdraft")
    op.drop_index("ix_eveningdraft_user_email", table_name="user", schema="eveningdraft")
    op.drop_table("user", schema="eveningdraft")
    op.execute("DROP SCHEMA IF EXISTS eveningdraft")
