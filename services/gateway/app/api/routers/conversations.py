from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pymongo import ASCENDING

from services.gateway.app.api.dependencies.auth import verify_auth_token
from services.gateway.app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationResponse,
    MessageCreateRequest,
    MessageResponse,
)
from shared.database.mongodb import get_mongodb_database
from shared.exceptions.handlers import NotFoundException
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/conversations", tags=["Chat & Conversations"])


@router.post(
    "",
    response_model=SuccessResponse[ConversationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create New Conversation",
    description="Initializes a multi-turn chat conversation session with MongoDB persistence.",
    responses={
        201: {"model": SuccessResponse[ConversationResponse], "description": "Conversation created"},
    },
)
async def create_conversation(
    payload: ConversationCreateRequest | None = None,
    auth: dict = Depends(verify_auth_token),
) -> SuccessResponse[ConversationResponse]:
    db = get_mongodb_database()
    conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()
    user_id = auth.get("user_id", "user_dev")

    title = (payload.title if payload and payload.title else f"Conversation {conv_id[:8]}")
    project_id = payload.project_id if payload else None
    repository_id = payload.repository_id if payload else None

    doc = {
        "id": conv_id,
        "conversation_id": conv_id,
        "title": title,
        "project_id": project_id,
        "repository_id": repository_id,
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
    }

    await db["conversations"].insert_one(doc)

    return SuccessResponse(
        data=ConversationResponse(
            id=conv_id,
            title=title,
            project_id=project_id,
            repository_id=repository_id,
            user_id=user_id,
            created_at=now,
            updated_at=now,
            messages=[],
        ),
        message="Conversation created successfully",
    )


@router.get(
    "",
    response_model=SuccessResponse[list[ConversationResponse]],
    summary="List Conversations",
    description="Returns all conversation sessions for the authenticated user.",
)
async def list_conversations(
    auth: dict = Depends(verify_auth_token),
) -> SuccessResponse[list[ConversationResponse]]:
    db = get_mongodb_database()
    user_id = auth.get("user_id")

    query: dict[str, Any] = {}
    if user_id and auth.get("role") != "admin":
        query["user_id"] = user_id

    cursor = db["conversations"].find(query).sort("created_at", -1).limit(50)
    items = await cursor.to_list(length=50)

    result: list[ConversationResponse] = []
    for item in items:
        conv_id = item.get("id") or item.get("conversation_id")
        result.append(
            ConversationResponse(
                id=conv_id,
                title=item.get("title", "Untitled"),
                project_id=item.get("project_id"),
                repository_id=item.get("repository_id"),
                user_id=item.get("user_id"),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
                messages=[],
            )
        )

    return SuccessResponse(data=result, message="Conversations retrieved")


@router.get(
    "/{id}",
    response_model=SuccessResponse[ConversationResponse],
    summary="Get Conversation Details & Messages",
    description="Retrieves a conversation record and its historical message thread.",
    responses={
        200: {"model": SuccessResponse[ConversationResponse], "description": "Conversation found"},
        404: {"model": ErrorResponse, "description": "Conversation not found"},
    },
)
async def get_conversation(
    id: str,
    auth: dict = Depends(verify_auth_token),
) -> SuccessResponse[ConversationResponse]:
    db = get_mongodb_database()
    conv = await db["conversations"].find_one({"$or": [{"id": id}, {"conversation_id": id}]})
    if not conv:
        raise NotFoundException(message=f"Conversation '{id}' not found")

    conv_id = conv.get("id") or conv.get("conversation_id")

    # Fetch messages
    msg_cursor = db["messages"].find({"conversation_id": conv_id}).sort("created_at", ASCENDING)
    msg_docs = await msg_cursor.to_list(length=200)

    messages = [
        MessageResponse(
            id=m.get("id") or m.get("message_id", ""),
            conversation_id=conv_id,
            role=m.get("role", "user"),
            content=m.get("content", ""),
            created_at=m.get("created_at", ""),
        )
        for m in msg_docs
    ]

    return SuccessResponse(
        data=ConversationResponse(
            id=conv_id,
            title=conv.get("title", "Untitled"),
            project_id=conv.get("project_id"),
            repository_id=conv.get("repository_id"),
            user_id=conv.get("user_id"),
            created_at=conv.get("created_at", ""),
            updated_at=conv.get("updated_at", ""),
            messages=messages,
        ),
        message="Conversation retrieved",
    )


@router.post(
    "/{id}/messages",
    response_model=SuccessResponse[MessageResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Post Message to Conversation",
    description="Appends a message to the conversation thread and persists in MongoDB.",
    responses={
        201: {"model": SuccessResponse[MessageResponse], "description": "Message added"},
        404: {"model": ErrorResponse, "description": "Conversation not found"},
    },
)
async def add_message(
    id: str,
    payload: MessageCreateRequest,
    auth: dict = Depends(verify_auth_token),
) -> SuccessResponse[MessageResponse]:
    db = get_mongodb_database()
    conv = await db["conversations"].find_one({"$or": [{"id": id}, {"conversation_id": id}]})
    if not conv:
        raise NotFoundException(message=f"Conversation '{id}' not found")

    conv_id = conv.get("id") or conv.get("conversation_id")
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC).isoformat()

    msg_doc = {
        "id": msg_id,
        "message_id": msg_id,
        "conversation_id": conv_id,
        "role": payload.role,
        "content": payload.content,
        "created_at": now,
    }

    await db["messages"].insert_one(msg_doc)
    await db["conversations"].update_one(
        {"$or": [{"id": id}, {"conversation_id": id}]},
        {"$set": {"updated_at": now}},
    )

    return SuccessResponse(
        data=MessageResponse(
            id=msg_id,
            conversation_id=conv_id,
            role=payload.role,
            content=payload.content,
            created_at=now,
        ),
        message="Message created successfully",
    )
