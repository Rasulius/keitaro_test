from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.keitaro.client import get_keitaro_client, KeitaroAPIError
from app.schemas.api import CreateCampaignRequest
from app.services.campaign_service import create_campaign_with_streams
from app.services import editor_service

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("")
def list_campaigns(
    q: str | None = Query(None, description="Filter campaigns by name substring"),
    state: str | None = Query(None, description="Filter by campaign state, e.g. active"),
    active_only: bool = Query(False, description="Return only active campaigns"),
):
    client = get_keitaro_client()
    try:
        campaigns = client.list_campaigns(limit=200)
        items = campaigns
        if q:
            ql = q.lower().strip()
            if ql:
                items = [c for c in items if ql in str(c.get("name", "")).lower()]
        if active_only or (state and state.lower().strip() == "active"):
            items = [c for c in items if str(c.get("state", "")).lower() == "active"]
        elif state:
            sl = state.lower().strip()
            if sl:
                items = [c for c in items if str(c.get("state", "")).lower() == sl]
        return {"items": items}
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("")
def create_campaign(payload: CreateCampaignRequest, db: Session = Depends(get_db)):
    client = get_keitaro_client()
    try:
        result = create_campaign_with_streams(
            db,
            client,
            name=payload.name,
            country_code=payload.country_code,
            offer_id=payload.offer_id,
            domain_id=payload.domain_id,
            group_id=payload.group_id,
            traffic_source_id=payload.traffic_source_id,
            google_url=payload.google_url,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{campaign_id}/editor")
def get_editor_state(campaign_id: int, db: Session = Depends(get_db)):
    return editor_service.get_campaign_editor_state(db, campaign_id)


@router.post("/{campaign_id}/fetch")
def fetch_streams(campaign_id: int, db: Session = Depends(get_db)):
    client = get_keitaro_client()
    try:
        return editor_service.fetch_campaign_streams(db, client, campaign_id)
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
