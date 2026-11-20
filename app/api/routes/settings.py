from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings, save_runtime_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    keitaro_url: str | None = None
    keitaro_api_key: str | None = None
    default_domain_id: int | None = None
    default_group_id: int | None = None
    default_traffic_source_id: int | None = None
    default_offer_id: int | None = None
    google_redirect_url: str | None = None
    campaign_name_prefix: str | None = None


@router.get("")
def read_settings() -> dict[str, Any]:
    return {"settings": get_settings().to_public_dict(mask_secrets=True)}


@router.post("")
def update_settings(payload: SettingsUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    s = save_runtime_config(data)
    return {"settings": s.to_public_dict(mask_secrets=True), "saved": True}