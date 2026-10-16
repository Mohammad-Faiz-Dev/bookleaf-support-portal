import json

import httpx

from app.ai import rules, service
from app.ai.knowledge_base import context_for
from app.ai.llm import LLMClient
from app.config import Settings
from app.models import Author, Book, Ticket


def _ticket(subject, description, category="General Inquiry", book=True):
    a = Author(author_id="A1", name="Priya Sharma", email="p@x.com", city="Mumbai", joined_date="2023-01-01")
    b = Book(book_id="B1", title="Whispers", isbn="978", status="Published & Live", mrp=399, author_royalty_per_copy=35,
             total_copies_sold=342, total_royalty_earned=11970, royalty_paid=8400, royalty_pending=3570,
             last_royalty_payout_date="2025-10-15", print_partner="In-House", available_on=["Amazon India"])
    a.books = [b]
    return Ticket(subject=subject, description=description, category=category, author=a, book=b if book else None)


def _client(handler):
    s = Settings()
    s.ai_api_key = "test-key"
    return LLMClient(s, transport=httpx.MockTransport(handler))


def _ok(content):
    return lambda req: httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {}})


def test_rules_examples_from_brief():
    assert rules.classify("Royalty", "I haven't received any royalty for 6 months") == ("Royalty & Payments", "Critical")
    assert rules.classify("Bio", "Can I update my author bio?")[1] == "Low"
    assert rules.classify("ISBN wrong", "Amazon shows a different ISBN than the physical copy") == ("ISBN & Metadata Issues", "High")
    assert rules.classify("Unavailable", "Showing Currently Unavailable on Amazon")[0] == "Distribution & Availability"
    assert rules.classify("Print", "pages are misaligned and images blurry")[0] == "Printing & Quality"
    assert rules.classify("Typesetting", "It's been 3 weeks in typesetting")[0] == "Book Status & Production Updates"


def test_ai_classification_used_when_valid():
    c = _client(_ok(json.dumps({"category": "Printing & Quality", "priority": "High", "reason": "defect"})))
    assert service.classify(_ticket("x", "y"), c)[:2] + (service.classify(_ticket("x", "y"), c)[3],) == ("Printing & Quality", "High", "ai")


def test_ai_invalid_label_falls_back():
    c = _client(_ok(json.dumps({"category": "Spam", "priority": "Urgent!!"})))
    assert service.classify(_ticket("Royalty", "royalty missing"), c)[3] == "rules"


def test_rate_limit_and_outage_degrade_gracefully():
    for status in (429, 503):
        c = _client(lambda req, s=status: httpx.Response(s))
        text, src = service.draft_reply(_ticket("Royalty", "where is my royalty", "Royalty & Payments"), c)
        assert src == "rules" and "₹3,570" in text


def test_draft_prompt_sends_only_relevant_kb():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Dear Priya, " + "x" * 100}}]})

    text, src = service.draft_reply(_ticket("ISBN", "wrong isbn", "ISBN & Metadata Issues"), _client(handler))
    user_msg = seen["body"]["messages"][1]["content"]
    assert src == "ai" and "ISBN policy" in user_msg and "Royalty policy" not in user_msg and "Printing &" not in user_msg
    assert "royalty_pending=3570" in user_msg and seen["body"]["max_tokens"] <= 400


def test_kb_context_has_tone_for_every_category():
    for cat in ["Royalty & Payments", "General Inquiry", "unknown"]:
        assert "Tone:" in context_for(cat)


def test_gemini_provider_request_and_parse():
    seen = {}

    def handler(req):
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-goog-api-key")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"ok": 1}'}]}}]})

    s = Settings()
    s.ai_provider, s.ai_api_key, s.ai_model = "gemini", "g-key", "gemini-2.5-flash"
    s.ai_base_url = "https://generativelanguage.googleapis.com/v1beta"
    out = LLMClient(s, transport=httpx.MockTransport(handler)).chat("sys", "user", max_tokens=50, json_mode=True)
    assert out == '{"ok": 1}' and seen["key"] == "g-key" and seen["url"].endswith("gemini-2.5-flash:generateContent")
