from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class CreateCampaignRequest(BaseModel):
    name: str = Field(..., description="Campaign base name; prefix will be applied")
    country_code: str = Field(..., description="Geo country code, e.g. AU")
    offer_id: int = Field(..., description="Keitaro offer ID for default stream")
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None
    google_url: str | None = None


class AddOfferRequest(BaseModel):
    keitaro_stream_id: int
    offer_id: int
    name: str | None = None


class StreamOfferActionRequest(BaseModel):
    keitaro_stream_id: int
    offer_id: int


class PinOfferRequest(BaseModel):
    keitaro_stream_id: int
    offer_id: int
    pinned: bool
    share: int | None = None


class StreamActionRequest(BaseModel):
    keitaro_stream_id: int


class SearchOffersResponse(BaseModel):
    items: list[dict[str, Any]]
