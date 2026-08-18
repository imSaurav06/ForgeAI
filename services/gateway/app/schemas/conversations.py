from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, description="Conversation title")
    project_id: str | None = Field(default=None, description="Associated project ID")
    repository_id: str | None = Field(default=None, description="Associated repository ID")


class MessageCreateRequest(BaseModel):
    content: str = Field(..., description="Message text content")
    role: str = Field(default="user", description="Message role (user, assistant, system)")


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    project_id: str | None = None
    repository_id: str | None = None
    user_id: str | None = None
    created_at: str
    updated_at: str
    messages: list[MessageResponse] = Field(default_factory=list)
