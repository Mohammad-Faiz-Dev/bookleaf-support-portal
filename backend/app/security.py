"""Password hashing (PBKDF2, stdlib) and JWT auth dependencies with role checks."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .errors import ApiError
from .models import Role, User

_ITER = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    return hmac.compare_digest(calc.hex(), digest)


def create_token(user: User) -> str:
    s = get_settings()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=s.jwt_ttl_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "unauthenticated", "Missing bearer token.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "token_expired", "Your session has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise ApiError(401, "invalid_token", "Invalid authentication token.")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise ApiError(401, "invalid_token", "User no longer exists.")
    return user


def require_author(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.author.value or not user.author_id:
        raise ApiError(403, "forbidden", "This endpoint is for authors only.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.admin.value:
        raise ApiError(403, "forbidden", "Admin access required.")
    return user
