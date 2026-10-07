from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ChatCreate(BaseModel):
    title: Optional[str] = None


class ChatOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SourceOut(BaseModel):
    title: Optional[str] = ""
    url: Optional[str] = ""
    snippet: Optional[str] = ""


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    sources: List[SourceOut] = []


class ChatRequest(BaseModel):
    chat_id: Optional[str] = None
    message: str = Field(..., min_length=1)