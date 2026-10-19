def test_login_errors(client):
    assert client.post("/api/auth/login", json={"email": "priya.sharma@email.com", "password": "nope"}).json()["error"]["code"] == "invalid_credentials"
    r = client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "email"


def test_routes_require_auth(client):
    for path in ["/api/me/books", "/api/me/tickets", "/api/admin/tickets"]:
        assert client.get(path).status_code == 401
    assert client.get("/api/me/books", headers={"Authorization": "Bearer junk"}).json()["error"]["code"] == "invalid_token"


def test_seeded_books_scoped_to_author(client, priya):
    books = client.get("/api/me/books", headers=priya).json()
    assert [b["book_id"] for b in books] == ["BK001", "BK002"]
    assert books[0]["royalty_pending"] == 3570


def test_book_in_production_has_zero_royalties(client):
    from tests.conftest import _login
    h = _login(client, "kavita.deshmukh@email.com", "author123")
    bk = {b["book_id"]: b for b in client.get("/api/me/books", headers=h).json()}
    assert bk["BK015"]["publication_date"] is None and bk["BK015"]["total_royalty_earned"] == 0


def test_role_based_access(client, priya, admin):
    assert client.get("/api/admin/tickets", headers=priya).status_code == 403
    assert client.get("/api/me/books", headers=admin).status_code == 403


def test_ticket_validation(client, priya):
    r = client.post("/api/me/tickets", headers=priya, json={"subject": "hi", "description": "short"})
    assert r.status_code == 422 and {d["field"] for d in r.json()["error"]["details"]} == {"subject", "description"}
    r = client.post("/api/me/tickets", headers=priya, json={"book_id": "BK003", "subject": "Not my book",
                                                           "description": "This belongs to someone else"})
    assert r.json()["error"]["code"] == "invalid_book"


def test_full_ticket_lifecycle(client, priya, rohit, admin):
    r = client.post("/api/me/tickets", headers=priya, json={
        "book_id": "BK001", "subject": "No royalty for 6 months",
        "description": "I haven't received any royalty for 6 months even though sales continue.",
        "attachment_name": "statement.pdf"})
    assert r.status_code == 201
    tid = r.json()["id"]

    # Other authors cannot see it
    assert client.get(f"/api/me/tickets/{tid}", headers=rohit).status_code == 404

    # Admin sees it classified (AI disabled in tests -> rules fallback), urgent first
    t = client.get(f"/api/admin/tickets/{tid}", headers=admin).json()
    assert t["category"] == "Royalty & Payments" and t["priority"] == "Critical" and t["category_source"] == "rules"
    queue = client.get("/api/admin/tickets?status=Open", headers=admin).json()
    assert queue[0]["priority"] == "Critical"

    # Draft works without AI, uses real data, is cached
    d = client.get(f"/api/admin/tickets/{tid}/draft", headers=admin).json()
    assert d["source"] == "rules" and "₹3,570" in d["draft"] and "Priya" in d["draft"]
    assert client.get(f"/api/admin/tickets/{tid}/draft", headers=admin).json()["cached"] is True

    # Override, assign, internal note, reply
    t = client.patch(f"/api/admin/tickets/{tid}", headers=admin,
                     json={"priority": "High", "assign_to_me": True}).json()
    assert t["priority"] == "High" and t["priority_source"] == "admin" and t["assigned_to"] == "Ops Admin"
    client.post(f"/api/admin/tickets/{tid}/notes", headers=admin, json={"body": "Check Q3 bank file"})
    t = client.post(f"/api/admin/tickets/{tid}/responses", headers=admin, json={"body": d["draft"]}).json()
    assert t["status"] == "In Progress"

    # Author sees the reply but not the internal note
    mine = client.get(f"/api/me/tickets/{tid}", headers=priya).json()
    assert len(mine["messages"]) == 1 and mine["messages"][0]["sender_role"] == "admin"
    assert "Check Q3" not in str(mine)

    # Invalid status rejected; resolve; author follow-up reopens
    assert client.patch(f"/api/admin/tickets/{tid}", headers=admin, json={"status": "Done"}).status_code == 422
    client.patch(f"/api/admin/tickets/{tid}", headers=admin, json={"status": "Resolved"})
    mine = client.post(f"/api/me/tickets/{tid}/messages", headers=priya, json={"body": "Still missing"}).json()
    assert mine["status"] == "Open"


def test_filters_and_404(client, admin):
    assert client.get("/api/admin/tickets?priority=Bogus", headers=admin).status_code == 422
    assert client.get("/api/admin/tickets?assigned=me", headers=admin).status_code == 200
    assert client.get("/api/admin/tickets/99999", headers=admin).json()["error"]["code"] == "ticket_not_found"


def test_resolved_ticket_with_messages_opens_for_author_and_admin(client, priya, admin):
    """Regression: ticket detail with messages returned 500 (MessageOut lacked sender_name/role)."""
    t = client.post("/api/me/tickets", headers=priya, json={
        "subject": "Last pages of every copy are blank", "description": "Readers say the last 5 pages are blank."}).json()
    assert client.post(f"/api/admin/tickets/{t['id']}/responses", headers=admin, json={"body": "We are reprinting."}).status_code == 201
    assert client.post(f"/api/admin/tickets/{t['id']}/notes", headers=admin, json={"body": "internal"}).status_code == 201
    assert client.patch(f"/api/admin/tickets/{t['id']}", headers=admin, json={"status": "Resolved"}).status_code == 200
    for _ in range(3):
        a = client.get(f"/api/me/tickets/{t['id']}", headers=priya)
        assert a.status_code == 200, a.text
        assert a.json()["status"] == "Resolved"
        assert [(m["sender_role"], m["is_internal"]) for m in a.json()["messages"]] == [("admin", False)]
        d = client.get(f"/api/admin/tickets/{t['id']}", headers=admin)
        assert d.status_code == 200, d.text
        assert {m["sender_name"] for m in d.json()["messages"]} == {"Ops Admin"}
