from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database import crud
from app.schemas.chat import (
    ChatOut,
    ChatCreate,
    MessageOut,
    SourceOut,
)

router = APIRouter(prefix="/api/chats", tags=["chats"])


def _chat_to_out(c) -> ChatOut:
    return ChatOut(
        id=str(c.id),
        title=c.title,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _message_to_out(m, sources) -> MessageOut:
    return MessageOut(
        id=str(m.id),
        role=m.role,
        content=m.content,
        created_at=m.created_at,
        sources=[
            SourceOut(
                title=s.title or "",
                url=s.url or "",
                snippet=s.snippet or "",
            )
            for s in sources
        ],
    )


@router.post("", response_model=ChatOut)
def create_chat(payload: ChatCreate, db: Session = Depends(get_db)):
    chat = crud.create_chat(db, payload.title)
    return _chat_to_out(chat)


@router.get("", response_model=list[ChatOut])
def list_chats(db: Session = Depends(get_db)):
    return [_chat_to_out(c) for c in crud.list_chats(db)]


@router.get("/{chat_id}", response_model=ChatOut)
def get_chat(chat_id: str, db: Session = Depends(get_db)):
    chat = crud.get_chat(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return _chat_to_out(chat)


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, db: Session = Depends(get_db)):
    ok = crud.delete_chat(db, chat_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"deleted": True}


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
def get_messages(chat_id: str, db: Session = Depends(get_db)):
    if not crud.get_chat(db, chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")

    messages = crud.get_messages(db, chat_id)
    out = []
    for m in messages:
        out.append(_message_to_out(m, m.sources))
    return out
