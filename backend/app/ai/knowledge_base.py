"""BookLeaf Knowledge Base, split into sections so we only send what a ticket needs.

Cost control: a royalty ticket gets the Royalty section (+ company basics + tone),
not the whole KB. Sections are short, hand-condensed versions of the policy doc.
"""
from ..models import Category

COMPANY = (
    "BookLeaf Publishing is a self-publishing company in India and the US. Packages: Standard Free (no upfront cost) "
    "and Bestseller Breakthrough (paid, with marketing & distribution add-ons). BookLeaf handles cover design, "
    "typesetting, ISBN assignment, printing, distribution and royalty management. In-house printing facility and "
    "warehouse in Delhi; print partners Repro India and Epitome Books."
)

TONE = (
    "Tone: empathetic and professional; authors are partners. Acknowledge the concern before solutions. Be specific "
    "(real numbers, dates, statuses from the author's data). If BookLeaf is at fault (delayed royalty, ISBN error) own "
    "it directly, no corporate deflection. If escalation is needed give a clear timeline (e.g. 'within 48 hours'). "
    "Never blame the author, frame delays collaboratively. Always end with a clear next step."
)

SECTIONS: dict[str, str] = {
    Category.royalty.value: (
        "Royalty policy: 80/20 split, 80% of net profit per book to the author. Net profit = MRP minus printing cost, "
        "platform commission (Amazon/Flipkart) and shipping. Royalties are calculated quarterly and paid within 45 days "
        "of quarter end. Minimum payout threshold Rs 1,000; smaller balances roll over to the next quarter. Paid by bank "
        "transfer to the account linked in the author dashboard (ask them to confirm bank details are linked). The "
        "dashboard shows a per-platform royalty breakdown; offer a line-by-line breakdown when amounts are questioned. "
        "If a payment is genuinely overdue, escalate with a 48-hour resolution timeline."
    ),
    Category.isbn.value: (
        "ISBN policy: every book gets a unique ISBN assigned by BookLeaf, registered under BookLeaf's imprint. Authors "
        "wanting their own imprint must obtain an ISBN independently. ISBN errors (duplicate, wrong book linked, "
        "mismatch between platform and print) are HIGH priority: acknowledge it is serious, escalate to the production "
        "team immediately, 48-hour resolution timeline. Metadata updates (description etc.) can be submitted via the "
        "dashboard or by email and reflect on platforms in 3-5 business days."
    ),
    Category.printing.value: (
        "Printing & quality: most orders printed in-house; overflow/special formats go to Repro India or Epitome Books. "
        "Standard print turnaround 5-7 business days from order confirmation. For quality issues (misprints, binding "
        "defects, colour inconsistency) apologise sincerely, ask for photos of the defective copies, and confirm a free "
        "reprint once verified, with a 5-7 business day reprint timeline."
    ),
    Category.distribution.value: (
        "Distribution: books are listed on Amazon India, Flipkart, Amazon US, Amazon UK and the BookLeaf Store. New "
        "listings go live 7-10 business days after publication completes. 'Currently unavailable' usually means a stock "
        "sync issue; BookLeaf triggers a re-sync and it is live again within 24-48 hours."
    ),
    Category.production.value: (
        "Production stages: Manuscript Received -> Editing (if opted) -> Cover Design -> Typesetting -> Proofreading -> "
        "ISBN Assignment -> Printing -> Distribution Setup -> Published & Live. Authors get an email at each stage. "
        "Delays usually happen at Cover Design (awaiting author approval) and Proofreading (revision rounds). Check the "
        "book's actual status, be honest about the reason, give a specific updated timeline, frame it collaboratively."
    ),
    Category.general.value: (
        "General: metadata (e.g. book description) can be updated after going live via the dashboard or by emailing the "
        "BookLeaf team; changes reflect in 3-5 business days. Packages: Standard Free and Bestseller Breakthrough."
    ),
}


def context_for(category: str) -> str:
    """Return the minimal KB context for one category."""
    return f"{COMPANY}\n\n{SECTIONS.get(category, SECTIONS[Category.general.value])}\n\n{TONE}"
