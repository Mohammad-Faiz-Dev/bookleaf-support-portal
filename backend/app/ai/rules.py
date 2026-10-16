"""Deterministic fallbacks used when the LLM is unavailable (no key, outage, rate limit).

They are deliberately simple keyword rules + templated replies so tickets are always
classified and admins always have a sensible starting draft.
"""
import re

from ..models import Category, Priority

_KEYWORDS: list[tuple[str, list[str]]] = [
    (Category.isbn.value, ["isbn", "metadata", "wrong title", "wrong author", "barcode", "imprint"]),
    (Category.royalty.value, ["royalt", "payout", "payment", "paid", "bank", "earning", "money", "₹", "rs.", "inr"]),
    (Category.printing.value, ["print", "binding", "misprint", "blurry", "pages", "copies", "defect", "colour", "color"]),
    (Category.distribution.value, ["amazon", "flipkart", "unavailable", "listing", "listed", "out of stock", "distribution"]),
    (Category.production.value, ["typesetting", "cover design", "proofread", "editing", "production", "manuscript", "when will", "status"]),
]

_CRITICAL = [r"\b([4-9]|1[0-2]|six|seven|eight|nine|ten|twelve)\s+months?\b.*(royalt|pay)",
             r"(royalt|pay).*\b([4-9]|six|seven|eight|nine|ten)\s+months?\b",
             r"legal|lawyer|copyright|fraud|scam|never received any"]
_HIGH = [r"isbn", r"not received", "haven'?t received", "overdue", "defect", "misprint", "unavailable", "wrong", "urgent"]
_LOW = [r"\bbio\b", r"update (my|the) (description|bio|profile|photo)", r"\bhow (do|can) i\b", r"can i\b"]


def classify(subject: str, description: str) -> tuple[str, str]:
    text = f"{subject} {description}".lower()
    category = Category.general.value
    for cat, words in _KEYWORDS:
        if any(w in text for w in words):
            category = cat
            break
    if any(re.search(p, text) for p in _CRITICAL):
        priority = Priority.critical.value
    elif any(re.search(p, text) for p in _HIGH):
        priority = Priority.high.value
    elif any(re.search(p, text) for p in _LOW):
        priority = Priority.low.value
    else:
        priority = Priority.medium.value
    return category, priority


def draft(category: str, first_name: str, book: dict | None) -> str:
    title = f'"{book["title"]}"' if book else "your account"
    lines = [f"Dear {first_name},", ""]
    if category == Category.royalty.value:
        lines.append(f"Thank you for reaching out about the royalties for {title}, and I understand how important this is.")
        if book:
            lines.append(f"Our records show {book['total_copies_sold']} copies sold, ₹{book['total_royalty_earned']:,} earned, "
                         f"₹{book['royalty_paid']:,} paid and ₹{book['royalty_pending']:,} pending"
                         + (f" (last payout on {book['last_royalty_payout_date']})." if book.get("last_royalty_payout_date") else ", with no payout made yet."))
        lines.append("Royalties are calculated quarterly and paid within 45 days of the quarter ending, once the balance crosses ₹1,000. "
                     "Please confirm your bank details are linked in your dashboard. If anything is overdue, we will resolve it within 48 hours, "
                     "and I'm happy to share a line-by-line breakdown.")
    elif category == Category.isbn.value:
        lines.append(f"Thank you for flagging this ISBN issue with {title}. This is a serious data problem and it's on us to fix it.")
        lines.append("I have escalated it to our production team as a high-priority issue, and we will have it resolved within 48 hours.")
    elif category == Category.printing.value:
        lines.append(f"I'm truly sorry about the print quality of {title}; that's not the standard we hold ourselves to.")
        lines.append("Could you share a few photos of the defective copies? Once verified, we will arrange a free reprint, "
                     "which takes 5–7 business days.")
    elif category == Category.distribution.value:
        lines.append(f"Thank you for letting us know about the availability of {title}.")
        lines.append("This is usually a stock sync issue. I'm triggering a re-sync with our distribution team, and the listing should "
                     "be live again within 24–48 hours.")
    elif category == Category.production.value:
        status = book["status"] if book else "in production"
        lines.append(f"Thank you for checking in on {title}. I understand the wait is frustrating.")
        lines.append(f"It is currently at: {status}. Our team will confirm the exact next milestone and an updated timeline within 48 hours, "
                     "and if anything is needed from your side we'll work through it together.")
    else:
        lines.append("Thank you for reaching out to BookLeaf.")
        lines.append("Metadata updates can be submitted through your dashboard or by emailing our team; changes usually reflect "
                     "within 3–5 business days. We'll get back to you on the specifics within 48 hours.")
    lines += ["", "Please reply here if you have any other questions.", "", "Warm regards,", "BookLeaf Author Support"]
    return "\n".join(lines)
