"""Add llm_configs table for runtime API key management

Revision ID: 0002
Revises: 0001
Create Date: 2025-12-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # LLM Configs table for runtime API key management
    op.create_table(
        'llm_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('model_name', sa.String(50), nullable=False, unique=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('model_id', sa.String(100), nullable=False),
        sa.Column('timeout_ms', sa.Integer(), nullable=False, server_default='30000'),
        sa.Column('max_tokens', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('prompt_path', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validation_status', sa.String(20), nullable=True),
    )
    op.create_index('idx_llm_configs_model_name', 'llm_configs', ['model_name'])
    op.create_index('idx_llm_configs_enabled', 'llm_configs', ['enabled'])


def downgrade() -> None:
    op.drop_table('llm_configs')
