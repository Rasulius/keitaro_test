from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.keitaro.client import KeitaroClient
from app.models.editor import CampaignBinding


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"[^a-z0-9\-]+", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "campaign"


def build_campaign_name(name: str) -> str:
    name = (name or "").strip()
    prefix = settings.campaign_name_prefix or ""
    if prefix and not name.startswith(prefix):
        return f"{prefix}{name}" if name else prefix.rstrip("_")
    return name or prefix.rstrip("_") or "test_campaign"


def create_campaign_with_streams(
    db: Session,
    client: KeitaroClient,
    *,
    name: str,
    country_code: str,
    offer_id: int,
    domain_id: int | None = None,
    group_id: int | None = None,
    traffic_source_id: int | None = None,
    google_url: str | None = None,
) -> dict[str, Any]:
    """Create a Keitaro campaign with 2 streams as required by the test task.

    Stream 1 (regular): catches users from specified country and redirects to Google.
    Stream 2 (default): sends remaining traffic to selected offer.
    """
    campaign_name = build_campaign_name(name)
    alias = _slugify(campaign_name)

    domain_id = domain_id if domain_id is not None else settings.default_domain_id
    group_id = group_id if group_id is not None else settings.default_group_id
    traffic_source_id = traffic_source_id if traffic_source_id is not None else settings.default_traffic_source_id
    google_url = (google_url or settings.google_redirect_url or "https://google.com").strip()

    country = (country_code or "").strip().upper()
    if not country:
        raise ValueError("Гео-код страны обязателен")
    if not offer_id:
        raise ValueError("ID оффера обязателен")

    campaign_payload: dict[str, Any] = {
        "name": campaign_name,
        "alias": alias,
        "state": "active",
        "type": "position",
    }
    if domain_id:
        campaign_payload["domain_id"] = int(domain_id)
    if group_id:
        campaign_payload["group_id"] = int(group_id)
    if traffic_source_id:
        campaign_payload["traffic_source_id"] = int(traffic_source_id)

    created_campaign = client.create_campaign(campaign_payload)
    campaign_id = int(created_campaign["id"])

    # Stream 1: geo -> redirect to Google
    # Using schema "action" + action_type "http" + action_payload URL is a common mapping;
    # if your Keitaro version expects schema "redirect", adjust accordingly.
    stream_geo = {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": f"Geo {country} -> Google",
        "state": "active",
        "schema": "action",
        "action_type": "http",
        "action_payload": google_url,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [
            {
                "name": "country",
                "mode": "accept",
                "payload": [country],
            }
        ],
        "offers": [],
        "landings": [],
    }

    # Stream 2: default -> selected offer
    stream_offer = {
        "campaign_id": campaign_id,
        "type": "default",
        "name": f"Default -> Offer {int(offer_id)}",
        "state": "active",
        "schema": "landings",
        "action_type": "http",
        "collect_clicks": True,
        "filter_or": False,
        "filters": [],
        "offers": [
            {
                "offer_id": int(offer_id),
                "share": 100,
                "state": "active",
            }
        ],
        "landings": [],
    }

    created_streams = []
    errors = []
    try:
        created_streams.append(client.create_stream(stream_geo))
    except Exception as e:
        errors.append(f"Stream 1 (geo): {e}")
    try:
        created_streams.append(client.create_stream(stream_offer))
    except Exception as e:
        errors.append(f"Stream 2 (offer): {e}")

    # Persist local binding
    binding = db.query(CampaignBinding).filter(CampaignBinding.keitaro_campaign_id == campaign_id).first()
    if not binding:
        binding = CampaignBinding(
            keitaro_campaign_id=campaign_id,
            name=created_campaign.get("name") or campaign_name,
            alias=created_campaign.get("alias") or alias,
        )
        db.add(binding)
    else:
        binding.name = created_campaign.get("name") or campaign_name
        binding.alias = created_campaign.get("alias") or alias
    db.commit()

    return {
        "campaign": created_campaign,
        "streams": created_streams,
        "errors": errors,
    }
