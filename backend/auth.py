"""
Authentication helpers: password hashing + JSON Web Tokens.

Why these two pieces:

* bcrypt  - turns a password into a salted, deliberately-slow hash. We store
            ONLY the hash. Even if sessions.db leaks, the passwords don't.
* PyJWT   - after a successful login we hand the browser a signed token. Every
            later request carries that token in the `Authorization` header;
            we verify the signature instead of looking the session up in a
            table. That's "stateless" auth - the token itself is the proof.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt  # the PyJWT package imports as `jwt`
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

# In production this MUST come from the environment. The fallback only exists
# so the project still runs if someone forgets to set it in .env.
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 24 * 7  # a login lasts a week

# bcrypt refuses passwords longer than 72 bytes - clip defensively.
_BCRYPT_MAX_BYTES = 72


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except ValueError:
        return False  # malformed hash in the DB


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),          # standard "subject" claim = who this is
        "email": email,
        "iat": now,                    # issued-at
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),  # expiry
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError if the token is invalid, tampered, or expired."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# --------------------------------------------------------------------------
# FastAPI dependency: pull the current user id off the request
# --------------------------------------------------------------------------
# HTTPBearer reads the `Authorization: Bearer <token>` header for us.
_bearer_scheme = HTTPBearer(auto_error=True)
_bearer_optional = HTTPBearer(auto_error=False)  # doesn't 401 when the header is absent


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> int:
    """Use as `user_id: int = Depends(get_current_user_id)` on any protected route."""
    try:
        payload = decode_access_token(credentials.credentials)
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
) -> int | None:
    """Like get_current_user_id but returns None instead of raising when there's
    no (or a bad) token. Lets an endpoint work for guests AND remember the plan
    for logged-in users."""
    if credentials is None:
        return None
    try:
        return int(decode_access_token(credentials.credentials)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
