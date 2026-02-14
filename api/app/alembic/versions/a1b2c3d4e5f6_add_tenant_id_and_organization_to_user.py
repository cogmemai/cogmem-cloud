"""Add tenant_id and organization to User

Revision ID: a1b2c3d4e5f6
Revises: fe56fa70289e
Create Date: 2026-02-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'fe56fa70289e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('tenant_id', sa.String(length=255), nullable=True))
    op.add_column('user', sa.Column('organization', sa.String(length=255), nullable=True))
    op.create_index('ix_user_tenant_id', 'user', ['tenant_id'])


def downgrade():
    op.drop_index('ix_user_tenant_id', table_name='user')
    op.drop_column('user', 'organization')
    op.drop_column('user', 'tenant_id')
