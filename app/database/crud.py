from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.database.models import (
    Chat,
    Message,
    ResearchSource,
    ResearchRun,
)


# ---------------- CHATS ----------------

def create_chat(db: Session, title: Optional[str] = None) -> Chat:
    chat = Chat(title=(title or "New Research")[:255])
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def list_chats(db: Session):
    return db.query(Chat).order_by(Chat.updated_at.desc()).all()


def get_chat(db: Session, chat_id: str) -> Optional[Chat]:
    return db.query(Chat).filter(Chat.id == chat_id).first()


def delete_chat(db: Session, chat_id: str) -> bool:
    chat = get_chat(db, chat_id)
    if not chat:
        return False
    db.delete(chat)
    db.commit()
    return True


def touch_chat(db: Session, chat_id: str) -> None:
    chat = get_chat(db, chat_id)
    if chat:
        chat.updated_at = datetime.utcnow()
        db.commit()


def update_chat_title(db: Session, chat_id: str, title: str) -> None:
    chat = get_chat(db, chat_id)
    if chat:
        chat.title = title[:255]
        chat.updated_at = datetime.utcnow()
        db.commit()


# ---------------- MESSAGES ----------------

def add_message(
    db: Session, chat_id: str, role: str, content: str
) -> Message:
    msg = Message(chat_id=chat_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_messages(db: Session, chat_id: str):
    return (
        db.query(Message)
        .options(selectinload(Message.sources))
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
        .all()
    )


# ---------------- SOURCES ----------------

def add_sources(db: Session, message_id: str, sources: list) -> None:
    for s in sources:
        db.add(
            ResearchSource(
                message_id=message_id,
                title=(s.get("title") or "")[:2000],
                url=(s.get("url") or "")[:2000],
                snippet=(s.get("snippet") or "")[:4000],
            )
        )
    db.commit()


def get_sources(db: Session, message_id: str):
    return (
        db.query(ResearchSource)
        .filter(ResearchSource.message_id == message_id)
        .all()
    )


# ---------------- RUNS ----------------

def start_run(db: Session, chat_id: str) -> ResearchRun:
    run = ResearchRun(chat_id=chat_id, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_run(
    db: Session, run_id: str, status: str, message_id: str = None
):
    run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    if run:
        run.status = status
        run.completed_at = datetime.utcnow()
        if message_id:
            run.message_id = message_id
        db.commit()
