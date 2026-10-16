"""Database schema.

users     - login identities (role = author | admin). Authors link 1:1 to an Author row.
authors   - author profile from the BookLeaf dataset.
books     - each book belongs to an author; royalty figures stored as integers (INR).
tickets   - support queries. category/priority carry a *_source column (ai | rules | admin)
            so we always know whether a value came from the model, the fallback, or a human.
ticket_messages - the conversation. is_internal=True rows are admin-only notes.
"""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(str, Enum):
    author = "author"
    admin = "admin"


class TicketStatus(str, Enum):
    open = "Open"
    in_progress = "In Progress"
    resolved = "Resolved"
    closed = "Closed"


class Category(str, Enum):
    royalty = "Royalty & Payments"
    isbn = "ISBN & Metadata Issues"
    printing = "Printing & Quality"
    distribution = "Distribution & Availability"
    production = "Book Status & Production Updates"
    general = "General Inquiry"


class Priority(str, Enum):
    critical = "Critical"
    high = "High"
    medium = "Medium"
    low = "Low"


PRIORITY_RANK = {Priority.critical.value: 0, Priority.high.value: 1, Priority.medium.value: 2, Priority.low.value: 3}


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[str | None] = mapped_column(ForeignKey("authors.author_id"), nullable=True)


class Author(Base):
    __tablename__ = "authors"
    author_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(64))
    joined_date: Mapped[str | None] = mapped_column(String(10))
    books: Mapped[list["Book"]] = relationship(back_populates="author", order_by="Book.book_id")


class Book(Base):
    __tablename__ = "books"
    book_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("authors.author_id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    isbn: Mapped[str | None] = mapped_column(String(32))
    genre: Mapped[str | None] = mapped_column(String(128))
    publication_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(64))
    mrp: Mapped[int] = mapped_column(Integer, default=0)
    author_royalty_per_copy: Mapped[int] = mapped_column(Integer, default=0)
    total_copies_sold: Mapped[int] = mapped_column(Integer, default=0)
    total_royalty_earned: Mapped[int] = mapped_column(Integer, default=0)
    royalty_paid: Mapped[int] = mapped_column(Integer, default=0)
    royalty_pending: Mapped[int] = mapped_column(Integer, default=0)
    last_royalty_payout_date: Mapped[str | None] = mapped_column(String(10))
    print_partner: Mapped[str | None] = mapped_column(String(64))
    available_on: Mapped[list] = mapped_column(JSON, default=list)
    author: Mapped[Author] = relationship(back_populates="books")


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("authors.author_id"), index=True)
    book_id: Mapped[str | None] = mapped_column(ForeignKey("books.book_id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    attachment_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=TicketStatus.open.value, index=True)
    category: Mapped[str] = mapped_column(String(64), default=Category.general.value, index=True)
    category_source: Mapped[str] = mapped_column(String(8), default="rules")
    priority: Mapped[str] = mapped_column(String(16), default=Priority.medium.value, index=True)
    priority_source: Mapped[str] = mapped_column(String(8), default="rules")
    ai_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ai_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_draft_source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    author: Mapped[Author] = relationship()
    book: Mapped[Book | None] = relationship()
    assigned_to: Mapped[User | None] = relationship()
    messages: Mapped[list["TicketMessage"]] = relationship(
        back_populates="ticket", order_by="TicketMessage.id", cascade="all, delete-orphan"
    )


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ticket: Mapped[Ticket] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship()
