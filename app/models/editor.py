from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CampaignBinding(Base):
    __tablename__ = "campaign_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    streams: Mapped[list["StreamState"]] = relationship(
        "StreamState", back_populates="campaign", cascade="all, delete-orphan"
    )


class StreamState(Base):
    __tablename__ = "stream_states"
    __table_args__ = (
        UniqueConstraint("campaign_binding_id", "keitaro_stream_id", name="uq_stream_campaign_keitaro"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_binding_id: Mapped[int] = mapped_column(ForeignKey("campaign_bindings.id", ondelete="CASCADE"), nullable=False)
    keitaro_stream_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Keitaro stream metadata snapshot needed for update/push (schema, type, action_type, filters, etc.)
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Last published state as known by wrapper (offers with weights/pin/status)
    published_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Current draft state
    draft_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Known offers registry for this stream: {offer_id: {offer_id, name}}
    known_offers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    is_dirty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    campaign: Mapped[CampaignBinding] = relationship("CampaignBinding", back_populates="streams")
