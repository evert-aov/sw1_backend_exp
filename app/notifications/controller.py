"""Bandeja autenticada para lectura y recuperación de avisos de quórum."""

from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.notifications.service import NotificationService

notification_router = APIRouter(prefix="/notifications", tags=["Avisos de quórum (CU-06)"])


class NotificationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    experience_id: str
    kind: str
    message: str
    created_at: datetime
    read_at: datetime | None


@notification_router.get("", response_model=list[NotificationDTO])
def list_notifications(
    db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(get_current_active_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0,
):
    return NotificationService(db).list_own(user.id, limit, offset)


@notification_router.patch("/{notification_id}/read", response_model=NotificationDTO)
def mark_read(notification_id: str, db: Annotated[Session, Depends(get_db)], user: Annotated[User, Depends(get_current_active_user)]):
    return NotificationService(db).mark_read(notification_id, user.id)
