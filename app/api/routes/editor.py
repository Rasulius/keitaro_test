from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.keitaro.client import get_keitaro_client, KeitaroAPIError
from app.schemas.api import AddOfferRequest, StreamOfferActionRequest, PinOfferRequest, StreamActionRequest
from app.services import editor_service

router = APIRouter(prefix="/api/editor", tags=["editor"])


@router.post("/offers/add")
def add_offer(payload: AddOfferRequest, db: Session = Depends(get_db)):
    client = get_keitaro_client()
    try:
        # Resolve offer name from Keitaro if not provided
        name = payload.name
        if not name:
            try:
                off = client.get_offer(payload.offer_id)
                name = off.get("name") or str(payload.offer_id)
            except Exception:
                name = str(payload.offer_id)
        return editor_service.add_offer_to_stream(
            db,
            payload.keitaro_stream_id,
            {"id": payload.offer_id, "name": name},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/offers/remove")
def remove_offer(payload: StreamOfferActionRequest, db: Session = Depends(get_db)):
    try:
        return editor_service.remove_offer_from_stream(db, payload.keitaro_stream_id, payload.offer_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/offers/bring-back")
def bring_back(payload: StreamOfferActionRequest, db: Session = Depends(get_db)):
    try:
        return editor_service.bring_back_offer(db, payload.keitaro_stream_id, payload.offer_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/offers/pin")
def pin_offer(payload: PinOfferRequest, db: Session = Depends(get_db)):
    try:
        return editor_service.set_offer_pin(
            db, payload.keitaro_stream_id, payload.offer_id, payload.pinned, payload.share
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/streams/push")
def push_stream(payload: StreamActionRequest, db: Session = Depends(get_db)):
    client = get_keitaro_client()
    try:
        return editor_service.push_stream_to_keitaro(db, client, payload.keitaro_stream_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/streams/cancel")
def cancel_stream(payload: StreamActionRequest, db: Session = Depends(get_db)):
    try:
        return editor_service.cancel_stream(db, payload.keitaro_stream_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
