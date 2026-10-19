"""Local user accounts and bearer-token sessions persisted to disk.

Same pattern as runtime_settings: JSON file under data/, lock-guarded,
atomic replace. Passwords use stdlib scrypt; sessions are opaque random
tokens with a 30-day expiry. No external auth dependencies on purpose —
this stays a local-first single-machine deployment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_USERS_PATH = _DATA_DIR / "users.json"

_LOCK = threading.RLock()

SESSION_TTL_S = 30 * 24 * 3600
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32

MIN_USERNAME_LEN = 2
MAX_USERNAME_LEN = 32
MIN_PASSWORD_LEN = 6
_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fff.-]+$", re.UNICODE)


class UserError(ValueError):
    """Validation or credential failure with a user-facing message."""


def _empty() -> dict[str, Any]:
    return {"users": {}, "sessions": {}}


def _load_raw() -> dict[str, Any]:
    try:
        data = json.loads(_USERS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("users", {})
    data.setdefault("sessions", {})
    if not isinstance(data["users"], dict) or not isinstance(data["sessions"], dict):
        return _empty()
    return data


def _save_raw(data: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _USERS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_USERS_PATH)


def _prune_sessions(data: dict[str, Any], now: float) -> None:
    data["sessions"] = {
        token: sess
        for token, sess in data["sessions"].items()
        if isinstance(sess, dict) and isinstance(sess.get("expires_at"), (int, float)) and sess["expires_at"] > now
    }


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _public_user(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": record.get("username"),
        "display_name": record.get("display_name") or record.get("username"),
        "created_at": record.get("created_at"),
    }


def _validate_username(username: str) -> str:
    username = (username or "").strip()
    if not (MIN_USERNAME_LEN <= len(username) <= MAX_USERNAME_LEN):
        raise UserError(f"用户名长度需在 {MIN_USERNAME_LEN}-{MAX_USERNAME_LEN} 个字符之间")
    if not _USERNAME_RE.match(username):
        raise UserError("用户名只能包含中文、字母、数字、点、横线或下划线")
    return username


def _validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        raise UserError(f"密码至少 {MIN_PASSWORD_LEN} 个字符")
    return password


def create_user(username: str, password: str, display_name: str = "") -> dict[str, Any]:
    username = _validate_username(username)
    password = _validate_password(password)
    display_name = (display_name or "").strip()[:32]
    with _LOCK:
        data = _load_raw()
        if username in data["users"]:
            raise UserError("用户名已被注册")
        record = {
            "username": username,
            "display_name": display_name or username,
            "password_hash": _hash_password(password),
            "created_at": int(time.time()),
        }
        data["users"][username] = record
        _save_raw(data)
        return _public_user(record)


def authenticate(username: str, password: str) -> dict[str, Any]:
    with _LOCK:
        record = _load_raw()["users"].get((username or "").strip())
    if not isinstance(record, dict) or not _verify_password(password or "", record.get("password_hash", "")):
        raise UserError("用户名或密码不正确")
    return _public_user(record)


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _LOCK:
        data = _load_raw()
        _prune_sessions(data, now)
        data["sessions"][token] = {"username": username, "created_at": int(now), "expires_at": int(now + SESSION_TTL_S)}
        _save_raw(data)
    return token


def resolve_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    with _LOCK:
        data = _load_raw()
        _prune_sessions(data, time.time())
        sess = data["sessions"].get(token)
        if not isinstance(sess, dict):
            return None
        record = data["users"].get(sess.get("username"))
        if not isinstance(record, dict):
            return None
        return _public_user(record)


def revoke_session(token: str) -> bool:
    with _LOCK:
        data = _load_raw()
        existed = token in data["sessions"]
        data["sessions"].pop(token, None)
        if existed:
            _save_raw(data)
    return existed
