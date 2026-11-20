"""Bandeja autenticada para lectura y recuperación de avisos de quórum."""

from datetime import datetime
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.notifications.service import NotificationService
from app.notifications.user_push_device import (
    register_user_push_device,
    remove_user_push_device,
)

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


class UserPushDeviceRegisterDTO(BaseModel):
    fcm_token: str = Field(..., min_length=20, max_length=512)
    platform: Literal["android", "ios", "web"] = "android"


@notification_router.post("/push-device", status_code=status.HTTP_200_OK)
def register_push_device(
    dto: UserPushDeviceRegisterDTO,
    user: Annotated[User, Depends(get_current_active_user)],
):
    push_enabled = register_user_push_device(str(user.id), dto.fcm_token, dto.platform)
    return {"registered": True, "push_enabled": push_enabled}


@notification_router.delete("/push-device", status_code=status.HTTP_204_NO_CONTENT)
def unregister_push_device(
    dto: UserPushDeviceRegisterDTO,
    user: Annotated[User, Depends(get_current_active_user)],
):
    remove_user_push_device(str(user.id), dto.fcm_token)
