"""Autenticazione admin — hashing password, JWT di sessione, dependency di protezione.

Singolo account admin configurato via .env (nessuna tabella utenti):
username/hash bcrypt della password confrontati in `verify_password`.
"""
import sys
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request

from app.config import settings

JWT_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def require_admin(request: Request) -> str:
    token = request.cookies.get("access_token")
    username = decode_access_token(token) if token else None
    if not username:
        raise HTTPException(status_code=401, detail="Login richiesto")
    return username


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python -m app.services.auth_service <password>")
        sys.exit(1)
    print(hash_password(sys.argv[1]))
