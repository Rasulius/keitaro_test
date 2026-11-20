from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.keitaro.client import get_keitaro_client, KeitaroAPIError

router = APIRouter(prefix="/api", tags=["offers"])


@router.get("/offers/search")
def search_offers(q: str = Query("", description="Search by ID or name")):
    client = get_keitaro_client()
    try:
        offers = client.list_offers()
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))

    q = (q or "").strip().lower()
    items = []
    for o in offers:
        oid = o.get("id")
        name = o.get("name") or ""
        hay = f"{oid} {name}".lower()
        if not q or q in hay:
            items.append({
                "id": oid,
                "name": name,
                "state": o.get("state"),
                "group_id": o.get("group_id"),
            })
        if len(items) >= 50:
            break
    return {"items": items}


@router.get("/reference/domains")
def list_domains():
    try:
        return {"items": get_keitaro_client().list_domains()}
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/reference/groups")
def list_groups(type: str = Query("campaigns")):
    try:
        return {"items": get_keitaro_client().list_groups(type=type)}
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/reference/traffic-sources")
def list_traffic_sources():
    try:
        return {"items": get_keitaro_client().list_traffic_sources()}
    except KeitaroAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
