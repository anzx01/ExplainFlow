"""Runtime-overridable settings persisted to disk.

The .env file stays the bootstrap default; anything saved through the
settings UI lands in data/runtime_settings.json and takes precedence at
call time, so provider/model switching works without a service restart.

Only an allow-listed set of keys is accepted from the client. API keys are
never returned in full — GET responses report presence and a short tail.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_SETTINGS_PATH = _DATA_DIR / "runtime_settings.json"

_LOCK = threading.Lock()

# key -> (type, is_secret); empty string clears an override
ALLOWED: dict[str, tuple[type, bool]] = {
    "llm_base_url": (str, False),
    "llm_api_key": (str, True),
    "llm_model": (str, False),
    "coder_model": (str, False),
    "imagegen_provider": (str, False),
    "ark_api_key": (str, True),
    "imagegen_base_url": (str, False),
    "imagegen_model": (str, False),
    "cloud_text2video_base_url": (str, False),
    "cloud_text2video_model": (str, False),
    "cloud_text2video_api_key": (str, True),
    "local_text2video_base_url": (str, False),
    "local_text2video_model": (str, False),
    "local_text2video_api_key": (str, True),
}

VALID_IMAGEGEN_PROVIDERS = {"local", "local_then_ark", "ark", "comfyui", "comfy"}


def _load_raw() -> dict[str, Any]:
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_raw(data: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_SETTINGS_PATH)


def get_overrides() -> dict[str, str]:
    with _LOCK:
        raw = _load_raw()
    return {k: v for k, v in raw.items() if isinstance(v, str) and v != ""}


def get_override(key: str) -> str | None:
    value = get_overrides().get(key)
    return value if value else None


def update_overrides(patch: dict[str, Any]) -> dict[str, str]:
    """Validate and merge a client patch; returns applied overrides."""
    errors: list[str] = []
    clean: dict[str, str] = {}
    for key, value in (patch or {}).items():
        if key not in ALLOWED:
            errors.append(f"unknown key: {key}")
            continue
        if value is None:
            value = ""
        if not isinstance(value, str):
            errors.append(f"{key} must be a string")
            continue
        if key == "imagegen_provider" and value and value not in VALID_IMAGEGEN_PROVIDERS:
            errors.append(f"imagegen_provider must be one of {sorted(VALID_IMAGEGEN_PROVIDERS)}")
            continue
        clean[key] = value
    if errors:
        raise ValueError("; ".join(errors))
    with _LOCK:
        raw = _load_raw()
        raw.update(clean)
        raw = {k: v for k, v in raw.items() if v != ""}
        _save_raw(raw)
    return {k: v for k, v in raw.items()}


def masked_snapshot() -> dict[str, Any]:
    """Client-safe view: secrets become has/tail markers."""
    out: dict[str, Any] = {}
    for key, value in get_overrides().items():
        _, is_secret = ALLOWED[key]
        if is_secret:
            out[key] = {"set": True, "tail": value[-4:]} if len(value) > 4 else {"set": True}
        else:
            out[key] = value
    return out
