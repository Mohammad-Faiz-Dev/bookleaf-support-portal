"""Admin-facing endpoints (role=admin required on every route via router dependency)."""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import Ticket, User
from ..security import require_admin
from ..services import tickets as svc
from ..ai import service as ai

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/tickets", response_model=list[schemas.AdminTicketSummary])
def queue(status: schemas.StatusT | None = None, category: schemas.CategoryT | None = None,
          priority: schemas.PriorityT | None = None, date_from: date | None = None, date_to: date | None = None,
          assigned: str | None = Query(None, pattern="^(me|unassigned)$"), q: str | None = Query(None, max_length=100),
          admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = svc.list_admin(db, status=status, category=category, priority=priority,
                          date_from=datetime.combine(date_from, time.min) if date_from else None,
                          date_to=datetime.combine(date_to, time.max) if date_to else None,
                          assigned=assigned, q=q, admin=admin)
    return [svc.admin_summary(t) for t in rows]


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Ticket.status, func.count()).group_by(Ticket.status)).all())
    open_by_priority = dict(db.execute(select(Ticket.priority, func.count())
                                       .where(Ticket.status.in_(["Open", "In Progress"])).group_by(Ticket.priority)).all())
    return {"by_status": by_status, "open_by_priority": open_by_priority}


@router.get("/tickets/{ticket_id}", response_model=schemas.AdminTicketDetail)
def detail(ticket_id: int, db: Session = Depends(get_db)):
    return svc.admin_detail(svc.get_ticket(db, ticket_id))


@router.patch("/tickets/{ticket_id}", response_model=schemas.AdminTicketDetail)
def update(ticket_id: int, body: schemas.TicketUpdate, admin: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    return svc.admin_detail(svc.update_ticket(db, svc.get_ticket(db, ticket_id), admin, body))


@router.get("/tickets/{ticket_id}/draft", response_model=schemas.DraftOut)
def draft(ticket_id: int, regenerate: bool = False, status: str | None = Query(None), db: Session = Depends(get_db)):
    return svc.get_or_create_draft(db, svc.get_ticket(db, ticket_id), regenerate, status=status)


class ProfessionalizeIn(schemas.BaseModel):
    text: str
    status: str | None = None


@router.post("/tickets/{ticket_id}/professionalize", response_model=schemas.DraftOut)
def professionalize(ticket_id: int, body: ProfessionalizeIn, db: Session = Depends(get_db)):
    t = svc.get_ticket(db, ticket_id)
    first = t.author.name.split()[0] if t.author else None
    text, source = ai.professionalize(body.text, status=body.status or t.status, author_first_name=first)
    return schemas.DraftOut(draft=text, source=source, cached=False)


@router.post("/tickets/{ticket_id}/responses", response_model=schemas.AdminTicketDetail, status_code=201)
def respond(ticket_id: int, body: schemas.MessageIn, admin: User = Depends(require_admin),
            db: Session = Depends(get_db)):
    """Send a (possibly AI-drafted, admin-edited) reply visible to the author."""
    return svc.admin_detail(svc.add_message(db, svc.get_ticket(db, ticket_id), admin, body.body, internal=False))


@router.post("/tickets/{ticket_id}/notes", response_model=schemas.AdminTicketDetail, status_code=201)
def note(ticket_id: int, body: schemas.MessageIn, admin: User = Depends(require_admin),
         db: Session = Depends(get_db)):
    """Internal note, never returned by author endpoints."""
    return svc.admin_detail(svc.add_message(db, svc.get_ticket(db, ticket_id), admin, body.body, internal=True))
