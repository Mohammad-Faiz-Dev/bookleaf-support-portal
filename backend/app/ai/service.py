"""AI orchestration: classify + draft, with graceful fallback to rules.

Every function returns (result, source) where source is "ai" or "rules", so the UI can
show admins whether a value came from the model.
"""
import json
import logging

from . import knowledge_base, prompts, rules
from .llm import LLMClient, LLMUnavailable
from ..models import Book, Ticket

log = logging.getLogger("bookleaf.ai")


def _book_dict(book: Book | None) -> dict | None:
    if not book:
        return None
    return {k: getattr(book, k) for k in ("title", "isbn", "status", "publication_date", "mrp", "author_royalty_per_copy",
                                          "total_copies_sold", "total_royalty_earned", "royalty_paid", "royalty_pending",
                                          "last_royalty_payout_date", "print_partner", "available_on")}


def _author_facts(ticket: Ticket) -> str:
    """Only the fields relevant to this ticket's book (not the whole catalog) -> fewer tokens."""
    lines = [f"Author: {ticket.author.name} (joined {ticket.author.joined_date}, {ticket.author.city})"]
    b = _book_dict(ticket.book)
    if b:
        lines.append("Book: " + "; ".join(f"{k}={v}" for k, v in b.items() if v not in (None, [], "")))
    else:
        lines.append("Query is account-level. Books: " + ", ".join(f"{bk.title} [{bk.status}]" for bk in ticket.author.books))
    return "\n".join(lines)


def classify(ticket: Ticket, client: LLMClient | None = None) -> tuple[str, str, str | None, str]:
    """Returns (category, priority, reason, source)."""
    client = client or LLMClient()
    try:
        raw = client.chat(prompts.CLASSIFY_SYSTEM,
                          prompts.classify_user(ticket.subject, ticket.description, ticket.book.status if ticket.book else None),
                          max_tokens=80, temperature=0, json_mode=True)
        data = json.loads(raw)
        cat, pri = data.get("category"), data.get("priority")
        if cat not in prompts.CATEGORIES or pri not in prompts.PRIORITIES:
            raise ValueError(f"model returned invalid labels: {data}")
        return cat, pri, (data.get("reason") or "")[:300], "ai"
    except (LLMUnavailable, ValueError, json.JSONDecodeError) as e:
        log.info("classification fallback to rules: %s", e)
        cat, pri = rules.classify(ticket.subject, ticket.description)
        return cat, pri, None, "rules"


def draft_reply(ticket: Ticket, status: str | None = None, client: LLMClient | None = None) -> tuple[str, str]:
    client = client or LLMClient()
    first_name = ticket.author.name.split()[0]
    use_status = status or ticket.status or "Open"
    try:
        text = client.chat(prompts.DRAFT_SYSTEM,
                           prompts.draft_user(knowledge_base.context_for(ticket.category), _author_facts(ticket),
                                              ticket.category, ticket.subject, ticket.description, use_status),
                           max_tokens=450, temperature=0.4)
        if len(text) < 40:
            raise ValueError("draft too short")
        return text, "ai"
    except (LLMUnavailable, ValueError) as e:
        log.info("draft fallback to template: %s", e)
        return rules.draft(ticket.category, first_name, _book_dict(ticket.book)), "rules"


def professionalize(rough_text: str, status: str | None = None, author_first_name: str | None = None,
                    client: LLMClient | None = None) -> tuple[str, str]:
    """Rewrite rough user text into a professional reply. Returns (text, source)."""
    client = client or LLMClient()
    if not rough_text or len(rough_text.strip()) < 5:
        return rough_text.strip() or "Please provide some content to professionalize.", "rules"
    try:
        text = client.chat(prompts.PROFESSIONALIZE_SYSTEM,
                           prompts.professionalize_user(rough_text, status, author_first_name),
                           max_tokens=500, temperature=0.3)
        if len(text) < 20:
            raise ValueError("professionalized text too short")
        return text, "ai"
    except (LLMUnavailable, ValueError) as e:
        log.info("professionalize fallback: %s", e)
        # Simple fallback: just clean up whitespace and add a greeting if missing
        cleaned = rough_text.strip()
        if author_first_name and not cleaned.lower().startswith(("dear", "hi", "hello")):
            cleaned = f"Dear {author_first_name},\n\n{cleaned}"
        if "regards" not in cleaned.lower():
            cleaned += "\n\nWarm regards,\nBookLeaf Author Support"
        return cleaned, "rules"
