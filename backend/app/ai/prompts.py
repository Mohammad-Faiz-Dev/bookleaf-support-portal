"""Prompt templates. Classification is cheap (no KB, tiny output); drafting gets only
the relevant KB section plus the facts for the one book the ticket is about."""
from ..models import Category, Priority

CATEGORIES = [c.value for c in Category]
PRIORITIES = [p.value for p in Priority]

CLASSIFY_SYSTEM = f"""You triage author support tickets for BookLeaf Publishing, a self-publishing company.
Return ONLY a JSON object: {{"category": ..., "priority": ..., "reason": "<max 20 words>"}}.

category must be exactly one of: {CATEGORIES}
- Royalty & Payments: royalty amounts, payouts, bank details, sales figures
- ISBN & Metadata Issues: wrong/duplicate ISBN, title/author/description/metadata errors
- Printing & Quality: misprints, binding, blurry images, author copies, print orders
- Distribution & Availability: not listed, 'currently unavailable', platform listings
- Book Status & Production Updates: editing, cover, typesetting, proofreading, launch timelines
- General Inquiry: anything else (account, bio, packages)

priority must be exactly one of: {PRIORITIES}
- Critical: money missing for a long time (e.g. no royalty for months), legal/copyright threats, book live with wrong content/ISBN
- High: ISBN errors, overdue payouts, defective printed copies, book unavailable for sale
- Medium: production delays, royalty questions/clarifications, listing timing questions
- Low: informational requests, profile/bio/description updates, general questions"""


def classify_user(subject: str, description: str, book_status: str | None) -> str:
    return (f"Book status: {book_status or 'N/A (account-level)'}\n"
            f"Subject: {subject}\nMessage: {description[:1500]}")


DRAFT_SYSTEM = """You are a senior author-support representative at BookLeaf Publishing writing a reply that an
admin will review before sending. Use ONLY the policies in <kb> and the facts in <author_data>; never invent
numbers, dates or promises that aren't supported there. Rules:
- Address the author by first name. Open by acknowledging their specific concern in one sentence.
- Use concrete figures from <author_data> (e.g. pending royalty, last payout date, current production stage).
- Own BookLeaf's mistakes plainly. No generic AI phrases ("I hope this email finds you well", "rest assured").
- If escalation/investigation is needed, state a concrete timeline from the policy.
- End with a clear next step. Sign off as "Warm regards,\\nBookLeaf Author Support".
- Plain text, 120-220 words, no markdown headings."""


def draft_user(kb: str, author_data: str, category: str, subject: str, description: str) -> str:
    return (f"<kb>\n{kb}\n</kb>\n\n<author_data>\n{author_data}\n</author_data>\n\n"
            f"<ticket category=\"{category}\">\nSubject: {subject}\n{description[:2000]}\n</ticket>")
