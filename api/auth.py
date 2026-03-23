from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from database.connection import get_session
from database.models import ApiKey
from auth.jwt import create_access_token, decode_access_token

from sqlalchemy.future import select

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    api_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
async def token(req: TokenRequest):
    async with get_session() as session:
        q = await session.execute(select(ApiKey).where(ApiKey.key == req.api_key, ApiKey.active == True))
        api_key = q.scalars().first()
        if not api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        token = create_access_token(subject=api_key.name)
        return {"access_token": token}


async def get_current_subject(token: str):
    try:
        payload = decode_access_token(token)
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
