from __future__ import annotations

from copy import deepcopy
from typing import Any


def _active_offers(offers: list[dict]) -> list[dict]:
    return [o for o in offers if o.get("status") == "active"]


def recalc_shares(offers: list[dict]) -> list[dict]:
    """Recalculate shares for active offers.

    - Active offers participate and total must be 100.
    - Pinned active offers keep their share.
    - Unpinned active offers split the remaining share equally.
    - Removed/archived offers get share 0.
    - Deterministic rounding so sum of active shares is exactly 100.
    """
    result = deepcopy(offers)
    active = [o for o in result if o.get("status") == "active"]

    # removed -> 0
    for o in result:
        if o.get("status") != "active":
            o["share"] = 0

    if not active:
        return result

    pinned = [o for o in active if o.get("pinned")]
    unpinned = [o for o in active if not o.get("pinned")]

    pinned_sum = sum(int(o.get("share") or 0) for o in pinned)
    # Clamp pinned_sum into [0,100] defensively
    if pinned_sum < 0:
        pinned_sum = 0
    if pinned_sum > 100:
        # keep as-is but normalization below will try to handle; better to cap
        pinned_sum = 100

    remaining = 100 - pinned_sum
    if remaining < 0:
        remaining = 0

    if unpinned:
        base = remaining // len(unpinned)
        extra = remaining % len(unpinned)
        for idx, o in enumerate(unpinned):
            o["share"] = base + (1 if idx < extra else 0)
    else:
        # all active are pinned; distribute any rounding remainder/deficit to first pinned
        # to keep total 100 when possible
        diff = 100 - sum(int(o.get("share") or 0) for o in pinned)
        if pinned and diff != 0:
            pinned[0]["share"] = int(pinned[0].get("share") or 0) + diff

    # Final safety normalization for active total
    active_total = sum(int(o.get("share") or 0) for o in result if o.get("status") == "active")
    if active and active_total != 100:
        diff = 100 - active_total
        # adjust first unpinned else first active
        target = unpinned[0] if unpinned else active[0]
        target["share"] = int(target.get("share") or 0) + diff

    # Ensure ints and non-negative
    for o in result:
        o["share"] = int(o.get("share") or 0)
        if o["share"] < 0:
            o["share"] = 0
        o["pinned"] = bool(o.get("pinned", False))
    return result


def validate_pins(offers: list[dict]) -> tuple[bool, str | None]:
    active = _active_offers(offers)
    pinned = [o for o in active if o.get("pinned")]
    pinned_sum = sum(int(o.get("share") or 0) for o in pinned)
    if pinned_sum > 100:
        return False, "Сумма закреплённых весов превышает 100%"
    if pinned and len(pinned) == len(active) and pinned_sum != 100:
        return False, "Все активные офферы закреплены, но сумма весов не равна 100%"
    return True, None
