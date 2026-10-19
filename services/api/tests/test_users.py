import json

import pytest

from src.core import users
from src.core.users import UserError


@pytest.fixture()
def store_path(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    monkeypatch.setattr(users, "_USERS_PATH", path)
    monkeypatch.setattr(users, "_DATA_DIR", tmp_path)
    return path


def test_register_login_session_roundtrip(store_path):
    user = users.create_user("张三", "secret123", "老张")
    assert user["username"] == "张三"
    assert user["display_name"] == "老张"

    authed = users.authenticate("张三", "secret123")
    assert authed["username"] == "张三"

    token = users.create_session("张三")
    resolved = users.resolve_session(token)
    assert resolved is not None and resolved["display_name"] == "老张"

    assert users.revoke_session(token) is True
    assert users.resolve_session(token) is None
    assert users.revoke_session(token) is False


def test_duplicate_username_rejected(store_path):
    users.create_user("alice", "secret123")
    with pytest.raises(UserError):
        users.create_user("alice", "other456")


def test_wrong_password_rejected(store_path):
    users.create_user("alice", "secret123")
    with pytest.raises(UserError):
        users.authenticate("alice", "wrongpass")
    with pytest.raises(UserError):
        users.authenticate("ghost", "secret123")


def test_credential_validation(store_path):
    with pytest.raises(UserError):
        users.create_user("a", "secret123")  # 用户名过短
    with pytest.raises(UserError):
        users.create_user("has space", "secret123")  # 非法字符
    with pytest.raises(UserError):
        users.create_user("bob", "12345")  # 密码过短


def test_password_hash_never_stores_plaintext(store_path):
    users.create_user("alice", "secret123")
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    stored = raw["users"]["alice"]["password_hash"]
    assert stored.startswith("scrypt$")
    assert "secret123" not in stored


def test_expired_session_not_resolved(store_path):
    users.create_user("alice", "secret123")
    token = users.create_session("alice")
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    raw["sessions"][token]["expires_at"] = 1
    store_path.write_text(json.dumps(raw), encoding="utf-8")
    assert users.resolve_session(token) is None
