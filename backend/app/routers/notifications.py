"""Endpoint delle notifiche: lista con conteggio non lette e segna-come-letto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import notifications
from ..database import get_db
from .auth import session_from_token

router = APIRouter(prefix="/notifications", tags=["notifications"])


class MarkRead(BaseModel):
    ids: list[int] | None = None  # None = tutte


@router.get("")
def my_notifications(
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    user_id = session_from_token(db, x_auth_token).user_id
    return notifications.list_for(db, user_id)


@router.post("/read")
def read_notifications(
    payload: MarkRead,
    x_auth_token: str = Header(default="", alias="X-Auth-Token"),
    db: Session = Depends(get_db),
):
    user_id = session_from_token(db, x_auth_token).user_id
    return {"marked": notifications.mark_read(db, user_id, payload.ids)}
