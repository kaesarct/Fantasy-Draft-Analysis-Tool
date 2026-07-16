"""Router di autenticazione — login/logout admin via cookie httpOnly."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import settings
from app.services.auth_service import create_access_token, decode_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "access_token"


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    valid = (
        payload.username == settings.admin_username
        and verify_password(payload.password, settings.admin_password_hash)
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    token = create_access_token(payload.username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return {"ok": True, "username": payload.username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    username = decode_access_token(token) if token else None
    if not username:
        raise HTTPException(status_code=401, detail="Non autenticato")
    return {"authenticated": True, "username": username}
