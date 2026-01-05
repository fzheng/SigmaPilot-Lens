"""Add prompts table for database-backed prompt storage

Revision ID: 0003
Revises: 0002
Create Date: 2025-12-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Prompts table for database-backed prompt storage
    op.create_table(
        'prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('prompt_type', sa.String(20), nullable=False),
        sa.Column('model_name', sa.String(50), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(100), nullable=True),
    )

    # Index for looking up active prompts by name and version
    op.create_index('idx_prompts_name_version', 'prompts', ['name', 'version'])

    # Index for filtering by prompt type
    op.create_index('idx_prompts_type', 'prompts', ['prompt_type'])

    # Index for finding wrapper prompts by model
    op.create_index('idx_prompts_model_name', 'prompts', ['model_name'])

    # Index for finding active prompts
    op.create_index('idx_prompts_is_active', 'prompts', ['is_active'])

    # Unique constraint: only one active prompt per name+version
    op.create_unique_constraint(
        'uq_prompts_name_version_active',
        'prompts',
        ['name', 'version'],
        postgresql_where=sa.text('is_active = true')
    )


def downgrade() -> None:
    op.drop_table('prompts')
