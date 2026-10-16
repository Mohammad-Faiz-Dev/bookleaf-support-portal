from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import Category, Priority, TicketStatus

StatusT = Literal["Open", "In Progress", "Resolved", "Closed"]
CategoryT = Literal[tuple(c.value for c in Category)]  # type: ignore[valid-type]
PriorityT = Literal[tuple(p.value for p in Priority)]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORM):
    id: int
    email: str
    name: str
    role: str
    author_id: str | None = None


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BookOut(ORM):
    book_id: str
    title: str
    isbn: str | None
    genre: str | None
    publication_date: str | None
    status: str
    mrp: int
    author_royalty_per_copy: int
    total_copies_sold: int
    total_royalty_earned: int
    royalty_paid: int
    royalty_pending: int
    last_royalty_payout_date: str | None
    print_partner: str | None
    available_on: list[str]


class TicketCreate(BaseModel):
    book_id: str | None = Field(default=None, description="null = General / Account Level")
    subject: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    attachment_name: str | None = Field(default=None, max_length=255)

    @field_validator("subject", "description")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def strip(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class MessageOut(ORM):
    id: int
    body: str
    is_internal: bool
    created_at: datetime
    sender_name: str
    sender_role: str


class TicketSummary(ORM):
    id: int
    subject: str
    status: str
    category: str
    priority: str
    book_id: str | None
    book_title: str | None
    created_at: datetime
    updated_at: datetime
    response_count: int


class AdminTicketSummary(TicketSummary):
    author_id: str
    author_name: str
    category_source: str
    priority_source: str
    assigned_to: str | None
    age_hours: float


class TicketDetail(TicketSummary):
    description: str
    attachment_name: str | None
    messages: list[MessageOut]


class AdminTicketDetail(AdminTicketSummary):
    description: str
    attachment_name: str | None
    ai_reason: str | None
    assigned_to_id: int | None
    author_email: str
    book: BookOut | None
    messages: list[MessageOut]


class TicketUpdate(BaseModel):
    status: StatusT | None = None
    category: CategoryT | None = None
    priority: PriorityT | None = None
    assign_to_me: bool | None = Field(default=None, description="true = assign to caller, false = unassign")


class DraftOut(BaseModel):
    draft: str
    source: Literal["ai", "rules"]
    cached: bool
