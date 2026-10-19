"""Ticket domain logic, kept out of the route handlers."""
import logging
from datetime import datetime, time
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..ai import service as ai
from ..ai.llm import LLMClient
from ..db import SessionLocal
from ..models import Author, Book, Ticket, TicketMessage, TicketStatus, User, utcnow
from ..security import hash_password

log = logging.getLogger("bookleaf.tickets")

# Open tickets first, then by priority rank, then oldest
_OPEN_FIRST = case({"Open": 0, "In Progress": 1, "Resolved": 2, "Closed": 3}, value=Ticket.status, else_=4)
_PRIORITY_RANK = case({"Critical": 0, "High": 1, "Medium": 2, "Low": 3}, value=Ticket.priority, else_=4)


def get_ticket(db: Session, ticket_id: int) -> Ticket:
    t = db.get(Ticket, ticket_id)
    if not t:
        from ..errors import NotFound
        raise NotFound("Ticket not found")
    return t


def list_author(db: Session, author_id: str) -> list[Ticket]:
    return list(db.scalars(
        select(Ticket).where(Ticket.author_id == author_id)
        .options(selectinload(Ticket.book), selectinload(Ticket.messages))
        .order_by(Ticket.updated_at.desc())
    ))


def list_admin(db: Session, *, status, category, priority, date_from, date_to, assigned, q, admin: User) -> list[Ticket]:
    stmt = select(Ticket).options(selectinload(Ticket.book), selectinload(Ticket.author), selectinload(Ticket.assignee))
    if status:
        stmt = stmt.where(Ticket.status == status)
    if category:
        stmt = stmt.where(Ticket.category == category)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if date_from:
        stmt = stmt.where(Ticket.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Ticket.created_at <= date_to)
    if assigned == "me":
        stmt = stmt.where(Ticket.assigned_to_id == admin.id)
    elif assigned == "unassigned":
        stmt = stmt.where(Ticket.assigned_to_id.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Ticket.subject.ilike(like), Ticket.description.ilike(like)))
    stmt = stmt.order_by(_OPEN_FIRST, _PRIORITY_RANK, Ticket.created_at)
    return list(db.scalars(stmt))


def ai_classify_ticket(ticket_id: int, client: LLMClient | None = None) -> None:
    """Background task: AI classification. Never overrides an admin's manual choice."""
    with SessionLocal() as db:
        t = get_ticket(db, ticket_id)
        cat, pri, reason, source = ai.classify(t, client)
        if t.category_source != "admin":
            t.category, t.category_source = cat, source
        if t.priority_source != "admin":
            t.priority, t.priority_source = pri, source
        t.ai_reason = reason
        db.commit()


def get_or_create_draft(db: Session, t: Ticket, regenerate: bool = False, status: str | None = None,
                        client: LLMClient | None = None) -> schemas.DraftOut:
    # Cache: a draft is generated once per ticket (or on explicit regenerate) to avoid paying per page view.
    if t.ai_draft and not regenerate and not status:
        return schemas.DraftOut(draft=t.ai_draft, source=t.ai_draft_source or "rules", cached=True)
    text, source = ai.draft_reply(t, status=status, client=client)
    t.ai_draft, t.ai_draft_source = text, source
    db.commit()
    return schemas.DraftOut(draft=text, source=source, cached=False)


def add_message(db: Session, t: Ticket, user: User, body: str, internal: bool) -> Ticket:
    db.add(TicketMessage(ticket_id=t.id, sender_id=user.id, body=body, is_internal=internal))
    if not internal and user.role == "admin" and t.status == TicketStatus.open.value:
        t.status = TicketStatus.in_progress.value
    if not internal and user.role == "author" and t.status in (TicketStatus.resolved.value, TicketStatus.closed.value):
        t.status = TicketStatus.open.value  # author follow-up re-opens the ticket
    t.updated_at = utcnow()
    db.commit()
    db.expire(t)
    return get_ticket(db, t.id)


def update_ticket(db: Session, t: Ticket, admin: User, data: schemas.TicketUpdate) -> Ticket:
    if data.status:
        t.status = data.status
    if data.category:
        t.category, t.category_source = data.category, "admin"
    if data.priority:
        t.priority, t.priority_source = data.priority, "admin"
    if data.assign_to_me is True:
        t.assigned_to_id = admin.id
    elif data.assign_to_me is False:
        t.assigned_to_id = None
    t.updated_at = utcnow()
    db.commit()
    db.expire(t)
    return get_ticket(db, t.id)


def admin_summary(t: Ticket) -> schemas.AdminTicketSummary:
    return schemas.AdminTicketSummary(
        id=t.id, subject=t.subject, status=t.status, category=t.category, priority=t.priority,
        category_source=t.category_source, priority_source=t.priority_source,
        author_name=t.author.name, author_email=t.author.email,
        book_title=t.book.title if t.book else None,
        assigned_to=t.assignee.name if t.assignee else None,
        response_count=sum(1 for m in t.messages if not m.is_internal),
        created_at=t.created_at, updated_at=t.updated_at,
        age_hours=(utcnow() - t.created_at).total_seconds() / 3600,
    )


def admin_detail(t: Ticket) -> schemas.AdminTicketDetail:
    return schemas.AdminTicketDetail(
        id=t.id, subject=t.subject, description=t.description, status=t.status,
        category=t.category, priority=t.priority,
        category_source=t.category_source, priority_source=t.priority_source,
        ai_reason=t.ai_reason, attachment_name=t.attachment_name,
        author_name=t.author.name, author_email=t.author.email, author_id=t.author_id,
        book=t.book, assigned_to=t.assignee.name if t.assignee else None, assigned_to_id=t.assigned_to_id,
        messages=[schemas.MessageOut.model_validate(m) for m in t.messages],
        created_at=t.created_at, updated_at=t.updated_at,
    )


def author_detail(t: Ticket) -> schemas.AuthorTicketDetail:
    return schemas.AuthorTicketDetail(
        id=t.id, subject=t.subject, description=t.description, status=t.status,
        book_title=t.book.title if t.book else None, attachment_name=t.attachment_name,
        messages=[schemas.MessageOut.model_validate(m) for m in t.messages if not m.is_internal],
        created_at=t.created_at, updated_at=t.updated_at,
    )


def author_summary(t: Ticket) -> schemas.AuthorTicketSummary:
    return schemas.AuthorTicketSummary(
        id=t.id, subject=t.subject, status=t.status,
        book_title=t.book.title if t.book else None,
        response_count=sum(1 for m in t.messages if not m.is_internal),
        created_at=t.created_at, updated_at=t.updated_at,
    )
