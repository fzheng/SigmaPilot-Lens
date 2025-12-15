"""Initial schema for SigmaPilot Lens

Revision ID: 0001
Revises:
Create Date: 2025-12-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # API Keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('key_prefix', sa.String(16), nullable=False),
        sa.Column('is_admin', sa.Boolean(), default=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_api_keys_key_hash', 'api_keys', ['key_hash'])

    # Events table
    op.create_table(
        'events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.String(36), nullable=False, unique=True),
        sa.Column('idempotency_key', sa.String(255), nullable=True, unique=True),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('signal_direction', sa.String(20), nullable=False),
        sa.Column('entry_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('size', sa.Numeric(20, 8), nullable=False),
        sa.Column('liquidation_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('ts_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('feature_profile', sa.String(50), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(), nullable=False),
        sa.Column('api_key_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('api_keys.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_events_event_id', 'events', ['event_id'])
    op.create_index('idx_events_idempotency_key', 'events', ['idempotency_key'])
    op.create_index('idx_events_symbol', 'events', ['symbol'])
    op.create_index('idx_events_status', 'events', ['status'])
    op.create_index('idx_events_received_at', 'events', ['received_at'])
    op.create_index('idx_events_source', 'events', ['source'])
    op.create_index('idx_events_symbol_received', 'events', ['symbol', 'received_at'])

    # Enriched Events table
    op.create_table(
        'enriched_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.event_id'), nullable=False),
        sa.Column('feature_profile', sa.String(50), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False, server_default='hyperliquid'),
        sa.Column('provider_version', sa.String(50), nullable=True),
        sa.Column('market_data', postgresql.JSONB(), nullable=False),
        sa.Column('ta_data', postgresql.JSONB(), nullable=False),
        sa.Column('levels_data', postgresql.JSONB(), nullable=True),
        sa.Column('derivs_data', postgresql.JSONB(), nullable=True),
        sa.Column('constraints', postgresql.JSONB(), nullable=False),
        sa.Column('data_timestamps', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('quality_flags', postgresql.JSONB(), nullable=False),
        sa.Column('enriched_payload', postgresql.JSONB(), nullable=False),
        sa.Column('enriched_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('enrichment_duration_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_enriched_event_id', 'enriched_events', ['event_id'])

    # Model Decisions table
    op.create_table(
        'model_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.event_id'), nullable=False),
        sa.Column('model_name', sa.String(50), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=True),
        sa.Column('prompt_version', sa.String(50), nullable=True),
        sa.Column('prompt_hash', sa.String(64), nullable=True),
        sa.Column('decision', sa.String(30), nullable=False),
        sa.Column('confidence', sa.Numeric(4, 3), nullable=False),
        sa.Column('entry_plan', postgresql.JSONB(), nullable=True),
        sa.Column('risk_plan', postgresql.JSONB(), nullable=True),
        sa.Column('size_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('reasons', postgresql.JSONB(), nullable=False),
        sa.Column('decision_payload', postgresql.JSONB(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='ok'),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('raw_response', sa.Text(), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_decisions_event_id', 'model_decisions', ['event_id'])
    op.create_index('idx_decisions_model_name', 'model_decisions', ['model_name'])
    op.create_index('idx_decisions_decision', 'model_decisions', ['decision'])
    op.create_index('idx_decisions_evaluated_at', 'model_decisions', ['evaluated_at'])
    op.create_index('idx_decisions_model_status', 'model_decisions', ['model_name', 'status'])
    op.create_index('idx_decisions_event_model', 'model_decisions', ['event_id', 'model_name'])

    # Processing Timeline table
    op.create_table(
        'processing_timeline',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.String(36), sa.ForeignKey('events.event_id'), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_timeline_event_id', 'processing_timeline', ['event_id'])

    # DLQ Entries table
    op.create_table(
        'dlq_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.String(36), nullable=True),
        sa.Column('stage', sa.String(30), nullable=False),
        sa.Column('reason_code', sa.String(50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_dlq_event_id', 'dlq_entries', ['event_id'])
    op.create_index('idx_dlq_stage', 'dlq_entries', ['stage'])
    op.create_index('idx_dlq_reason_code', 'dlq_entries', ['reason_code'])
    op.create_index('idx_dlq_created_at', 'dlq_entries', ['created_at'])
    op.create_index('idx_dlq_stage_reason', 'dlq_entries', ['stage', 'reason_code'])


def downgrade() -> None:
    op.drop_table('dlq_entries')
    op.drop_table('processing_timeline')
    op.drop_table('model_decisions')
    op.drop_table('enriched_events')
    op.drop_table('events')
    op.drop_table('api_keys')
