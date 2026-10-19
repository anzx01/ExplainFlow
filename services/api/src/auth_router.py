"""Auth API: local accounts with bearer-token sessions (see core/users.py)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.core import users
from src.core.users import UserError

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _user_error(exc: UserError, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


@router.post("/auth/register")
async def register(req: RegisterRequest) -> dict:
    try:
        user = users.create_user(req.username, req.password, req.display_name or "")
    except UserError as exc:
        raise _user_error(exc, 409) from exc
    token = users.create_session(user["username"])
    return {"token": token, "user": user}


@router.post("/auth/login")
async def login(req: LoginRequest) -> dict:
    try:
        user = users.authenticate(req.username, req.password)
    except UserError as exc:
        raise _user_error(exc, 401) from exc
    token = users.create_session(user["username"])
    return {"token": token, "user": user}


@router.post("/auth/logout")
async def logout(request: Request) -> dict:
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    users.revoke_session(token)
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request) -> dict:
    token = _bearer_token(request)
    user = users.resolve_session(token or "")
    if user is None:
        raise HTTPException(status_code=401, detail="not logged in")
    return {"user": user}
