from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.keitaro.client import KeitaroClient, KeitaroAPIError
from app.models.editor import CampaignBinding, StreamState
from app.services.weight import recalc_shares, validate_pins


def _jload(s: str | None, default):
    if not s:
        return deepcopy(default)
    try:
        return json.loads(s)
    except Exception:
        return deepcopy(default)


def _jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _ensure_campaign_binding(db: Session, campaign: dict) -> CampaignBinding:
    kid = int(campaign["id"])
    binding = db.query(CampaignBinding).filter(CampaignBinding.keitaro_campaign_id == kid).first()
    if not binding:
        binding = CampaignBinding(keitaro_campaign_id=kid, name=campaign.get("name"), alias=campaign.get("alias"))
        db.add(binding)
        db.flush()
    else:
        binding.name = campaign.get("name") or binding.name
        binding.alias = campaign.get("alias") or binding.alias
    return binding


def _extract_stream_offers(stream: dict) -> list[dict]:
    # Keitaro returns offers as list of objects with offer_id, share, state, ...
    out = []
    for o in (stream.get("offers") or []):
        offer_id = o.get("offer_id") or o.get("id")
        if offer_id is None:
            continue
        out.append(
            {
                "offer_id": int(offer_id),
                "name": o.get("name") or str(offer_id),
                "share": int(o.get("share") or 0),
                "keitaro_state": o.get("state") or "active",
            }
        )
    return out


def _normalize_offers_from_keitaro(kt_offers: list[dict], prev_known: dict, prev_pins: dict[int, bool]) -> list[dict]:
    # prev_pins: offer_id -> pinned from previous wrapper state (if present)
    offers = []
    for o in kt_offers:
        oid = int(o["offer_id"])
        offers.append(
            {
                "offer_id": oid,
                "name": o.get("name") or prev_known.get(str(oid), {}).get("name") or str(oid),
                "share": int(o.get("share") or 0),
                "pinned": bool(prev_pins.get(oid, False)),
                "status": "active",
            }
        )
    return recalc_shares(offers)


def _merge_fetch_state(stream: dict, state: StreamState | None) -> tuple[dict, dict, dict, dict]:
    """Return (meta, published, draft, known_offers) after fetch merge.

    Strategy:
    - Treat Keitaro as source of truth for currently active offers in stream.
    - Preserve names from known registry when missing.
    - Preserve pin flags for offers that remain active and were known.
    - Any previously known offer missing from Keitaro becomes status 'removed' (archived, share 0)
      so it can be brought back (sync of external deletions).
    - Resulting state is clean (not dirty): draft == published.
    """
    kt_offers = _extract_stream_offers(stream)
    kt_ids = {int(o["offer_id"]) for o in kt_offers}

    prev_known = _jload(state.known_offers_json, {}) if state else {}
    prev_published = _jload(state.published_json, {"offers": []}) if state else {"offers": []}
    prev_draft = _jload(state.draft_json, {"offers": []}) if state else {"offers": []}

    # collect pin info from previous draft preferred, else published
    prev_pin_map: dict[int, bool] = {}
    for src in (prev_draft.get("offers") or []) + (prev_published.get("offers") or []):
        try:
            prev_pin_map[int(src["offer_id"])] = bool(src.get("pinned", False))
        except Exception:
            pass

    merged_active = _normalize_offers_from_keitaro(kt_offers, prev_known, prev_pin_map)

    # update known registry with active KT offers
    known = dict(prev_known)
    for o in merged_active:
        known[str(o["offer_id"])] = {"offer_id": o["offer_id"], "name": o.get("name") or str(o["offer_id"])}

    # add removed-known offers (missing from KT) as archived
    # include any from previous published/draft/known that are not in KT
    seen = {o["offer_id"] for o in merged_active}
    prev_all_ids = set()
    for src in (prev_published.get("offers") or []) + (prev_draft.get("offers") or []):
        try:
            prev_all_ids.add(int(src.get("offer_id")))
        except Exception:
            pass
    for k in list(known.keys()):
        try:
            prev_all_ids.add(int(k))
        except Exception:
            pass

    removed_offers = []
    for oid in sorted(prev_all_ids):
        if oid in kt_ids or oid in seen:
            continue
        meta = known.get(str(oid), {})
        removed_offers.append(
            {
                "offer_id": oid,
                "name": meta.get("name") or str(oid),
                "share": 0,
                "pinned": bool(prev_pin_map.get(oid, False)),
                "status": "removed",
            }
        )

    merged_offers = merged_active + removed_offers
    merged_offers = recalc_shares(merged_offers)

    # meta for pushing back (preserve stream config)
    meta = {
        "id": stream.get("id"),
        "campaign_id": stream.get("campaign_id"),
        "type": stream.get("type"),
        "name": stream.get("name"),
        "schema": stream.get("schema"),
        "action_type": stream.get("action_type"),
        "action_payload": stream.get("action_payload"),
        "action_options": stream.get("action_options"),
        "position": stream.get("position"),
        "weight": stream.get("weight"),
        "state": stream.get("state"),
        "collect_clicks": stream.get("collect_clicks"),
        "filter_or": stream.get("filter_or"),
        "filters": stream.get("filters") or [],
        "landings": stream.get("landings") or [],
        "triggers": stream.get("triggers") or [],
        "comments": stream.get("comments"),
    }

    snapshot = {"offers": merged_offers}
    return meta, deepcopy(snapshot), deepcopy(snapshot), known


def fetch_campaign_streams(db: Session, client: KeitaroClient, campaign_id: int) -> dict:
    campaign = client.get_campaign(campaign_id)
    streams = client.get_campaign_streams(campaign_id)
    binding = _ensure_campaign_binding(db, campaign)

    by_kt: dict[int, StreamState] = {s.keitaro_stream_id: s for s in binding.streams}
    result_streams = []

    for st in streams:
        kt_id = int(st["id"])
        state = by_kt.get(kt_id)
        meta, published, draft, known = _merge_fetch_state(st, state)
        if not state:
            state = StreamState(
                campaign_binding_id=binding.id,
                keitaro_stream_id=kt_id,
                name=st.get("name"),
                meta_json=_jdump(meta),
                published_json=_jdump(published),
                draft_json=_jdump(draft),
                known_offers_json=_jdump(known),
                is_dirty=False,
            )
            db.add(state)
        else:
            state.name = st.get("name") or state.name
            state.meta_json = _jdump(meta)
            state.published_json = _jdump(published)
            state.draft_json = _jdump(draft)
            state.known_offers_json = _jdump(known)
            state.is_dirty = False
        db.flush()
        result_streams.append(serialize_stream_state(state))

    db.commit()
    return {
        "campaign": {
            "id": campaign.get("id"),
            "name": campaign.get("name"),
            "alias": campaign.get("alias"),
        },
        "streams": result_streams,
    }


def serialize_stream_state(state: StreamState) -> dict:
    meta = _jload(state.meta_json, {})
    draft = _jload(state.draft_json, {"offers": []})
    published = _jload(state.published_json, {"offers": []})
    return {
        "stream_state_id": state.id,
        "keitaro_stream_id": state.keitaro_stream_id,
        "name": state.name or meta.get("name"),
        "type": meta.get("type"),
        "schema": meta.get("schema"),
        "is_dirty": state.is_dirty,
        "has_offers": len((meta.get("offers") or []) + (draft.get("offers") or []) + (published.get("offers") or [])) > 0 or bool(draft.get("offers") or published.get("offers")),
        "draft": draft,
        "published": published,
        "meta": {
            "action_type": meta.get("action_type"),
            "action_payload": meta.get("action_payload"),
            "filters": meta.get("filters") or [],
        },
    }


def get_campaign_editor_state(db: Session, campaign_id: int) -> dict:
    binding = db.query(CampaignBinding).filter(CampaignBinding.keitaro_campaign_id == campaign_id).first()
    if not binding:
        return {"campaign": {"id": campaign_id}, "streams": [], "needs_fetch": True}
    streams = (
        db.query(StreamState)
        .filter(StreamState.campaign_binding_id == binding.id)
        .order_by(StreamState.keitaro_stream_id.asc())
        .all()
    )
    return {
        "campaign": {
            "id": binding.keitaro_campaign_id,
            "name": binding.name,
            "alias": binding.alias,
        },
        "streams": [serialize_stream_state(s) for s in streams],
        "needs_fetch": len(streams) == 0,
    }


def _get_stream_state(db: Session, keitaro_stream_id: int) -> StreamState:
    state = db.query(StreamState).filter(StreamState.keitaro_stream_id == keitaro_stream_id).first()
    if not state:
        raise ValueError("Stream state not found. Fetch streams first.")
    return state


def _save_draft(state: StreamState, offers: list[dict]):
    state.draft_json = _jdump({"offers": recalc_shares(offers)})
    state.is_dirty = True


def add_offer_to_stream(db: Session, keitaro_stream_id: int, offer: dict) -> dict:
    state = _get_stream_state(db, keitaro_stream_id)
    draft = _jload(state.draft_json, {"offers": []})
    offers = draft.get("offers") or []
    oid = int(offer["id"] if "id" in offer else offer["offer_id"])
    name = offer.get("name") or str(oid)

    # if exists as removed -> reactivate; if exists active -> no-op duplicate
    found = None
    for o in offers:
        if int(o.get("offer_id")) == oid:
            found = o
            break
    if found:
        if found.get("status") != "active":
            found["status"] = "active"
            # keep pinned/share, recalc will adjust
        else:
            # already active, just ensure name updated
            found["name"] = name
    else:
        offers.append({"offer_id": oid, "name": name, "share": 0, "pinned": False, "status": "active"})

    known = _jload(state.known_offers_json, {})
    known[str(oid)] = {"offer_id": oid, "name": name}
    state.known_offers_json = _jdump(known)

    _save_draft(state, offers)
    db.commit()
    db.refresh(state)
    return serialize_stream_state(state)


def remove_offer_from_stream(db: Session, keitaro_stream_id: int, offer_id: int) -> dict:
    state = _get_stream_state(db, keitaro_stream_id)
    draft = _jload(state.draft_json, {"offers": []})
    offers = draft.get("offers") or []
    found = False
    for o in offers:
        if int(o.get("offer_id")) == int(offer_id):
            o["status"] = "removed"
            o["share"] = 0
            found = True
            break
    if not found:
        # if not present at all, add as removed (defensive)
        known = _jload(state.known_offers_json, {})
        name = (known.get(str(offer_id)) or {}).get("name") or str(offer_id)
        offers.append({"offer_id": int(offer_id), "name": name, "share": 0, "pinned": False, "status": "removed"})
    _save_draft(state, offers)
    db.commit()
    db.refresh(state)
    return serialize_stream_state(state)


def bring_back_offer(db: Session, keitaro_stream_id: int, offer_id: int) -> dict:
    state = _get_stream_state(db, keitaro_stream_id)
    draft = _jload(state.draft_json, {"offers": []})
    offers = draft.get("offers") or []
    for o in offers:
        if int(o.get("offer_id")) == int(offer_id):
            o["status"] = "active"
            break
    else:
        known = _jload(state.known_offers_json, {})
        name = (known.get(str(offer_id)) or {}).get("name") or str(offer_id)
        offers.append({"offer_id": int(offer_id), "name": name, "share": 0, "pinned": False, "status": "active"})
    _save_draft(state, offers)
    db.commit()
    db.refresh(state)
    return serialize_stream_state(state)


def set_offer_pin(db: Session, keitaro_stream_id: int, offer_id: int, pinned: bool, share: int | None = None) -> dict:
    state = _get_stream_state(db, keitaro_stream_id)
    draft = _jload(state.draft_json, {"offers": []})
    offers = draft.get("offers") or []
    for o in offers:
        if int(o.get("offer_id")) == int(offer_id):
            if o.get("status") == "active":
                o["pinned"] = bool(pinned)
                if share is not None and pinned:
                    o["share"] = max(0, min(100, int(share)))
            break
    ok, err = validate_pins(recalc_shares(deepcopy(offers)))
    if not ok:
        raise ValueError(err)
    _save_draft(state, offers)
    db.commit()
    db.refresh(state)
    return serialize_stream_state(state)


def cancel_stream(db: Session, keitaro_stream_id: int) -> dict:
    state = _get_stream_state(db, keitaro_stream_id)
    state.draft_json = state.published_json
    state.is_dirty = False
    db.commit()
    db.refresh(state)
    return serialize_stream_state(state)


def _build_stream_update_payload(state: StreamState) -> dict:
    meta = _jload(state.meta_json, {})
    draft = _jload(state.draft_json, {"offers": []})
    offers = draft.get("offers") or []

    ok, err = validate_pins(offers)
    if not ok:
        raise ValueError(err)

    # Only active offers are sent to Keitaro
    active = [o for o in offers if o.get("status") == "active"]
    kt_offers = [
        {"offer_id": int(o["offer_id"]), "share": int(o.get("share") or 0), "state": "active"}
        for o in active
    ]

    payload: dict[str, Any] = {
        "campaign_id": meta.get("campaign_id"),
        "type": meta.get("type") or "regular",
        "name": meta.get("name") or state.name,
        "schema": meta.get("schema") or "landings",
        "action_type": meta.get("action_type") or "http",
        "state": meta.get("state") or "active",
        "offers": kt_offers,
    }
    # include optional fields if present
    for key in ("action_payload", "action_options", "position", "weight", "collect_clicks", "filter_or", "filters", "landings", "triggers", "comments"):
        val = meta.get(key)
        if val is not None:
            payload[key] = val
    # Keitaro may require filters/landings arrays even if empty in some cases; safe to include
    payload.setdefault("filters", [])
    payload.setdefault("landings", [])
    return payload


def push_stream_to_keitaro(db: Session, client: KeitaroClient, keitaro_stream_id: int) -> dict:
    state = _get_stream_state(db, keitaro_stream_id)
    payload = _build_stream_update_payload(state)
    try:
        updated = client.update_stream(keitaro_stream_id, payload)
    except KeitaroAPIError:
        raise

    # After successful push, published becomes current draft (including archived entries)
    draft = _jload(state.draft_json, {"offers": []})
    state.published_json = _jdump(draft)
    state.is_dirty = False

    # refresh meta from Keitaro response when possible (preserve our known/pins logic separately)
    if isinstance(updated, dict):
        meta = _jload(state.meta_json, {})
        for k in ("type", "name", "schema", "action_type", "action_payload", "action_options", "position", "weight", "state", "collect_clicks", "filter_or", "filters", "landings", "triggers", "comments", "campaign_id"):
            if k in updated:
                meta[k] = updated.get(k)
        state.meta_json = _jdump(meta)

    db.commit()
    db.refresh(state)
    return serialize_stream_state(state)
