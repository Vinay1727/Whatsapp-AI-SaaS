from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.mongodb import get_db
from app.models.message import MessageResponse

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])


@router.get("", response_model=list[MessageResponse])
async def list_messages(
    session_id: str = Query(..., description="Session ID to fetch messages for"),
    limit: int = Query(default=100, le=500, description="Max messages to return"),
    direction: str | None = Query(
        default=None, description="Filter by direction: incoming or outgoing",
    ),
    before_id: str | None = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    query: dict = {"session_id": session_id}
    if direction:
        query["direction"] = direction

    cursor = db.messages.find(query).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    docs.reverse()
    return [MessageResponse(**d) for d in docs]


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    doc = await db.messages.find_one({"message_id": message_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found")
    return MessageResponse(**doc)
