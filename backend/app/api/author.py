"""Author-facing endpoints. Every query is scoped to the caller's author_id."""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_db
from ..models import Book, Ticket, User
from ..security import require_author
from ..services import tickets as svc

router = APIRouter(prefix="/api/me", tags=["author"])


@router.get("/books", response_model=list[schemas.BookOut])
def my_books(user: User = Depends(require_author), db: Session = Depends(get_db)):
    return list(db.scalars(select(Book).where(Book.author_id == user.author_id).order_by(Book.book_id)))


@router.get("/tickets", response_model=list[schemas.TicketSummary])
def my_tickets(user: User = Depends(require_author), db: Session = Depends(get_db)):
    rows = db.scalars(svc._q().where(Ticket.author_id == user.author_id).order_by(Ticket.updated_at.desc()))
    return [svc.author_summary(t) for t in rows]


@router.post("/tickets", response_model=schemas.TicketDetail, status_code=201)
def create(body: schemas.TicketCreate, bg: BackgroundTasks, user: User = Depends(require_author),
           db: Session = Depends(get_db)):
    t = svc.create_ticket(db, user.author_id, body)
    bg.add_task(svc.ai_classify_ticket, t.id)  # runs after the response; author never waits on the AI
    return svc.author_detail(t)


@router.get("/tickets/{ticket_id}", response_model=schemas.TicketDetail)
def detail(ticket_id: int, user: User = Depends(require_author), db: Session = Depends(get_db)):
    return svc.author_detail(svc.get_ticket(db, ticket_id, user.author_id))


@router.post("/tickets/{ticket_id}/messages", response_model=schemas.TicketDetail, status_code=201)
def follow_up(ticket_id: int, body: schemas.MessageIn, user: User = Depends(require_author),
              db: Session = Depends(get_db)):
    t = svc.get_ticket(db, ticket_id, user.author_id)
    return svc.author_detail(svc.add_message(db, t, user, body.body, internal=False))
