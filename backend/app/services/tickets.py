"""Ticket domain logic, kept out of the route handlers."""
import logging
from datetime import datetime

from sqlalchemy import case, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..ai import service as ai
from ..ai.llm import LLMClient
from ..db import SessionLocal
from ..errors import ApiError
from ..models import Book, Ticket, TicketMessage, TicketStatus, User, utcnow

log = logging.getLogger("bookleaf.tickets")

_PRIORITY_ORDER = case({"Critical": 0, "High": 1, "Medium": 2, "Low": 3}, value=Ticket.priority, else_=4)
_OPEN_FIRST = case({"Open": 0, "In Progress": 1, "Resolved": 2, "Closed": 3}, value=Ticket.status, else_=4)


def _q():
    return select(Ticket).options(selectinload(Ticket.messages).selectinload(TicketMessage.sender),
                                  selectinload(Ticket.book), selectinload(Ticket.author), selectinload(Ticket.assigned_to))


def get_ticket(db: Session, ticket_id: int, author_id: str | None = None) -> Ticket:
    t = db.scalar(_q().where(Ticket.id == ticket_id))
    # Authors get 404 (not 403) for others' tickets so IDs can't be probed.
    if not t or (author_id and t.author_id != author_id):
        raise ApiError(404, "ticket_not_found", f"Ticket {ticket_id} not found.")
    return t


def create_ticket(db: Session, author_id: str, data: schemas.TicketCreate) -> Ticket:
    if data.book_id:
        book = db.get(Book, data.book_id)
        if not book or book.author_id != author_id:
            raise ApiError(422, "invalid_book", "Selected book does not belong to your account.",
                           [{"field": "book_id", "message": "unknown book"}])
    t = Ticket(author_id=author_id, book_id=data.book_id, subject=data.subject,
               description=data.description, attachment_name=data.attachment_name)
    # Instant rules-based triage so the ticket is never unclassified; AI refines it in the background.
    from ..ai import rules
    t.category, t.priority = rules.classify(data.subject, data.description)
    db.add(t)
    db.commit()
    return get_ticket(db, t.id)


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


def list_admin(db: Session, *, status=None, category=None, priority=None, date_from: datetime | None = None,
               date_to: datetime | None = None, assigned: str | None = None, q: str | None = None,
               admin: User | None = None) -> list[Ticket]:
    stmt = _q()
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
    if assigned == "me" and admin:
        stmt = stmt.where(Ticket.assigned_to_id == admin.id)
    elif assigned == "unassigned":
        stmt = stmt.where(Ticket.assigned_to_id.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Ticket.subject.ilike(like) | Ticket.description.ilike(like))
    # Open first, then by priority, then oldest
    stmt = stmt.order_by(_OPEN_FIRST, _PRIORITY_ORDER, Ticket.created_at)
    return list(db.scalars(stmt))


def _messages(t: Ticket, include_internal: bool) -> list[schemas.MessageOut]:
    return [schemas.MessageOut.model_validate(m) for m in t.messages
            if include_internal or not m.is_internal]


def _base(t: Ticket) -> dict:
    return dict(id=t.id, subject=t.subject, status=t.status, category=t.category, priority=t.priority,
                book_id=t.book_id, book_title=t.book.title if t.book else None, created_at=t.created_at,
                updated_at=t.updated_at,
                response_count=sum(1 for m in t.messages if not m.is_internal and m.sender.role == "admin"))


def author_summary(t):
    return schemas.TicketSummary(**_base(t))


def author_detail(t):
    return schemas.TicketDetail(**_base(t), description=t.description, attachment_name=t.attachment_name,
                                messages=_messages(t, False))


def _admin_base(t):
    return dict(**_base(t), author_id=t.author_id, author_name=t.author.name, category_source=t.category_source,
                priority_source=t.priority_source, assigned_to=t.assigned_to.name if t.assigned_to else None,
                age_hours=round((utcnow() - t.created_at).total_seconds() / 3600, 1))


def admin_summary(t):
    return schemas.AdminTicketSummary(**_admin_base(t))


def admin_detail(t):
    return schemas.AdminTicketDetail(**_admin_base(t), description=t.description, attachment_name=t.attachment_name,
                                     ai_reason=t.ai_reason, assigned_to_id=t.assigned_to_id, author_email=t.author.email,
                                     book=schemas.BookOut.model_validate(t.book) if t.book else None,
                                     messages=_messages(t, True))
