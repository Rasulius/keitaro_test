from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
RUNTIME_CONFIG_PATH = BASE_DIR / "runtime_config.json"

_RUNTIME_FIELDS = {
    "keitaro_url",
    "keitaro_api_key",
    "database_url",
    "default_domain_id",
    "default_group_id",
    "default_traffic_source_id",
    "default_offer_id",
    "google_redirect_url",
    "campaign_name_prefix",
}


class AppSettings(BaseSettings):
    keitaro_url: str = ""
    keitaro_api_key: str = ""
    database_url: str = "sqlite:///./app.db"

    default_domain_id: int | None = None
    default_group_id: int | None = None
    default_traffic_source_id: int | None = None
    default_offer_id: int | None = None
    google_redirect_url: str = "https://google.com"

    campaign_name_prefix: str = "test_user_"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "default_domain_id",
        "default_group_id",
        "default_traffic_source_id",
        "default_offer_id",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def keitaro_base(self) -> str:
        return (self.keitaro_url or "").rstrip("/")

    def to_runtime_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in _RUNTIME_FIELDS}

    def to_public_dict(self, mask_secrets: bool = True) -> dict[str, Any]:
        data = self.to_runtime_dict()
        if mask_secrets and data.get("keitaro_api_key"):
            key = str(data["keitaro_api_key"])
            data["keitaro_api_key_masked"] = (key[:4] + "…" + key[-4:]) if len(key) > 8 else "••••••"
            data["keitaro_api_key_set"] = True
            data["keitaro_api_key"] = ""
        else:
            data["keitaro_api_key_set"] = bool(data.get("keitaro_api_key"))
            data["keitaro_api_key_masked"] = ""
        return data


def _load_runtime_config() -> dict[str, Any]:
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _build_settings() -> AppSettings:
    # Base from .env/env/defaults, then apply runtime config overrides for non-empty values.
    s = AppSettings()
    runtime = _load_runtime_config()
    for k, v in runtime.items():
        if k not in _RUNTIME_FIELDS:
            continue
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            # allow clearing strings except keep db default sane? treat empty as "not set" for most fields
            if k == "database_url":
                continue
            setattr(s, k, "")
            continue
        setattr(s, k, v)
    # Re-validate/coerce types via assignment through model fields where needed
    # (simple casts for ints)
    for k in ("default_domain_id", "default_group_id", "default_traffic_source_id", "default_offer_id"):
        val = getattr(s, k)
        if val in (None, ""):
            setattr(s, k, None)
        else:
            try:
                setattr(s, k, int(val))
            except Exception:
                setattr(s, k, None)
    return s


_settings_instance: AppSettings = _build_settings()


class SettingsProxy:
    def __getattr__(self, name: str):
        return getattr(_settings_instance, name)

    def __setattr__(self, name: str, value):
        setattr(_settings_instance, name, value)

    def __repr__(self) -> str:
        return repr(_settings_instance)


settings = SettingsProxy()


def get_settings() -> AppSettings:
    return _settings_instance


def reload_settings() -> AppSettings:
    global _settings_instance
    _settings_instance = _build_settings()
    return _settings_instance


def save_runtime_config(data: dict[str, Any]) -> AppSettings:
    """Persist runtime config (git-ignored) and reload settings.
    If keitaro_api_key is omitted/empty in payload, keep existing key.
    """
    current = _load_runtime_config()
    merged: dict[str, Any] = {**current}
    for k in _RUNTIME_FIELDS:
        if k not in data:
            continue
        v = data.get(k)
        if k == "keitaro_api_key" and (v is None or (isinstance(v, str) and v.strip() == "")):
            # keep existing secret if not explicitly provided
            continue
        if v is None:
            merged[k] = None
        elif isinstance(v, str):
            merged[k] = v.strip()
        else:
            merged[k] = v

    # Normalize ints/empties for cleanliness
    for k in ("default_domain_id", "default_group_id", "default_traffic_source_id", "default_offer_id"):
        if k in merged:
            val = merged[k]
            if val in (None, ""):
                merged[k] = None
            else:
                try:
                    merged[k] = int(val)
                except Exception:
                    merged[k] = None

    RUNTIME_CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return reload_settings()
