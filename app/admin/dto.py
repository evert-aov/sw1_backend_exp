from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class AdminRolesDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[Literal["ATTENDEE", "HOST", "VENUE", "ADMIN"]] = Field(
        min_length=1, max_length=4
    )


class OverviewDTO(BaseModel):
    users: int
    active_users: int
    hosts: int
    attendees: int
    venues: int
    experiences: int
    paid_bookings: int
