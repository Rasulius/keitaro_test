from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class KeitaroAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class KeitaroClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or settings.keitaro_base).rstrip("/")
        self.api_key = api_key or settings.keitaro_api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Api-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        if not self.base_url or not self.api_key:
            raise KeitaroAPIError("Keitaro URL or API key is not configured")
        url = f"{self.base_url}/admin_api/v1{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, headers=self._headers(), params=params, json=json)
        except httpx.HTTPError as e:
            raise KeitaroAPIError(f"HTTP error: {e}") from e

        if resp.status_code >= 400:
            detail: Any
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise KeitaroAPIError(
                f"Keitaro API error {resp.status_code}: {detail}",
                status_code=resp.status_code,
                payload=detail,
            )
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except Exception:
            return resp.text

    # --- campaigns ---
    def list_campaigns(self, limit: int = 200, offset: int = 0) -> list[dict]:
        return self._request("GET", "/campaigns", params={"limit": limit, "offset": offset}) or []

    def get_campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", json=payload)

    def update_campaign(self, campaign_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/campaigns/{campaign_id}", json=payload)

    # --- streams (flows) ---
    def get_campaign_streams(self, campaign_id: int) -> list[dict]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams") or []

    def get_stream(self, stream_id: int) -> dict:
        return self._request("GET", f"/streams/{stream_id}")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        # Keitaro expects PUT to /streams/{id}
        return self._request("PUT", f"/streams/{stream_id}", json=payload)

    def delete_stream(self, stream_id: int) -> dict | None:
        return self._request("DELETE", f"/streams/{stream_id}")

    # --- offers ---
    def list_offers(self) -> list[dict]:
        return self._request("GET", "/offers") or []

    def get_offer(self, offer_id: int) -> dict:
        return self._request("GET", f"/offers/{offer_id}")

    # --- reference data ---
    def list_domains(self) -> list[dict]:
        return self._request("GET", "/domains") or []

    def list_groups(self, type: str = "campaigns") -> list[dict]:
        return self._request("GET", "/groups", params={"type": type}) or []

    def list_traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources") or []


# Convenience singleton-style accessor (uses current settings)
def get_keitaro_client() -> KeitaroClient:
    return KeitaroClient()
