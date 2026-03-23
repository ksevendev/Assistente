"""Helpers JWT e validação de ApiKey"""
import os
import datetime
from typing import Optional

from jose import jwt, JWTError

JWT_SECRET = os.getenv("JWT_SECRET", "please-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXP_MINUTES = int(os.getenv("JWT_EXP_MINUTES", "60"))


def create_access_token(subject: str, expires_delta: Optional[datetime.timedelta] = None) -> str:
    now = datetime.datetime.utcnow()
    if expires_delta is None:
        expires_delta = datetime.timedelta(minutes=JWT_EXP_MINUTES)
    payload = {"sub": subject, "iat": now, "exp": now + expires_delta}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise
