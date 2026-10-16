"""Idempotent seeding from the provided BookLeaf JSON dataset (+ two admin users)."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Author, Book, Role, User
from .security import hash_password

ADMINS = [("admin@bookleafpub.com", "Ops Admin"), ("support@bookleafpub.com", "Support Agent")]


def seed(db: Session) -> None:
    s = get_settings()
    if db.scalar(select(User).limit(1)):
        return
    data = json.loads(s.seed_file.read_text(encoding="utf-8"))
    author_pw = hash_password(s.default_author_password)
    for a in data["authors"]:
        author = Author(**{k: a.get(k) for k in ("author_id", "name", "email", "phone", "city", "joined_date")})
        db.add(author)
        for b in a.get("books", []):
            fields = {k: v for k, v in b.items() if hasattr(Book, k)}
            fields["available_on"] = fields.get("available_on") or []
            db.add(Book(author_id=a["author_id"], **fields))
        db.add(User(email=a["email"].lower(), name=a["name"], password_hash=author_pw,
                    role=Role.author.value, author_id=a["author_id"]))
    admin_pw = hash_password(s.default_admin_password)
    for email, name in ADMINS:
        db.add(User(email=email, name=name, password_hash=admin_pw, role=Role.admin.value))
    db.commit()
