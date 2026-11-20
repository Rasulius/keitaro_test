"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-11-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("keitaro_campaign_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("alias", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_campaign_bindings_keitaro_campaign_id"), "campaign_bindings", ["keitaro_campaign_id"], unique=True)

    op.create_table(
        "stream_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("campaign_binding_id", sa.Integer(), nullable=False),
        sa.Column("keitaro_stream_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=False),
        sa.Column("published_json", sa.Text(), nullable=False),
        sa.Column("draft_json", sa.Text(), nullable=False),
        sa.Column("known_offers_json", sa.Text(), nullable=False),
        sa.Column("is_dirty", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_binding_id"], ["campaign_bindings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("campaign_binding_id", "keitaro_stream_id", name="uq_stream_campaign_keitaro"),
    )
    op.create_index(op.f("ix_stream_states_keitaro_stream_id"), "stream_states", ["keitaro_stream_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_stream_states_keitaro_stream_id"), table_name="stream_states")
    op.drop_table("stream_states")
    op.drop_index(op.f("ix_campaign_bindings_keitaro_campaign_id"), table_name="campaign_bindings")
    op.drop_table("campaign_bindings")