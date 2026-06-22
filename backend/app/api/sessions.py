from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import APIRouter, Depends, HTTPException

from app.db.mongodb import get_db
from app.models.chat import ChatSessionResponse

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("", response_model=list[ChatSessionResponse])
async def list_sessions(
    tenant_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    query: dict = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    if status:
        query["status"] = status

    cursor = db.chat_sessions.find(query).sort("updated_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


@router.get("/{session_id}", response_model=ChatSessionResponse)
async def get_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    doc = await db.chat_sessions.find_one({"session_id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return ChatSessionResponse(**doc)
