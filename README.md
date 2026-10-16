# BookLeaf Author Support & Communication Portal

A web app with an **Author Portal** and an **Admin Support Desk**, with AI-assisted ticket triage and reply drafting grounded in the BookLeaf Knowledge Base.

- **Live demo:** https://bookleaf-support-portal-pi.vercel.app (Vercel, Python runtime)
  - Author: `priya.sharma@email.com` / `author123`
  - Admin: `admin@bookleafpub.com` / `admin123`
  - Demo limitation: the live demo currently uses SQLite in `/tmp` on Vercel, reseeded from the sample data on each cold start, so tickets created there are temporary (they last while the serverless instance is warm). Set `DATABASE_URL` / `POSTGRES_URL` (e.g. Neon via the Vercel Marketplace) and the app uses Postgres with persistent data, no code change needed. AI runs on the keyword/template fallback unless `OPENAI_API_KEY` is set.
- **Stack:** FastAPI (Python 3.12+) · SQLAlchemy 2 · SQLite (Postgres-ready via `DATABASE_URL`) · Vue 3 SPA (no build step) · OpenAI `gpt-4o-mini` (any OpenAI-compatible API)

## Test logins (seeded from `bookleaf_sample_data.json`)

| Role | Email | Password |
|---|---|---|
| Author | `priya.sharma@email.com` (any of the 10 author emails in the dataset) | `author123` |
| Author with books in production | `kavita.deshmukh@email.com`, `sneha.kulkarni@email.com` | `author123` |
| Admin | `admin@bookleafpub.com` | `admin123` |
| Admin (2nd agent, to test assignment) | `support@bookleafpub.com` | `admin123` |

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env          # optional: add OPENAI_API_KEY; without it the app uses the rules fallback
cd backend
set -a; [ -f ../.env ] && . ../.env; set +a
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 for the app, and http://localhost:8000/docs for the interactive OpenAPI (Swagger) docs. The database is created and seeded automatically on first start. Delete `backend/bookleaf.db` to reset it.

Tests: `cd backend && python -m pytest -q`. They cover auth, RBAC, validation, the full ticket lifecycle, internal-note privacy, AI fallback on 429/5xx, and KB scoping in prompts. No real AI calls are made.

Docker: `docker build -t bookleaf . && docker run -p 8000:8000 -e OPENAI_API_KEY=... -e JWT_SECRET=... bookleaf`. `render.yaml` deploys the same image to Render.

## Architecture

```
frontend/            Vue 3 SPA (index.html, app.js, styles.css), served by FastAPI at /
backend/app/
  main.py            app factory, routers, startup create+seed, static hosting
  config.py          all settings from env vars (API keys never in code or frontend)
  models.py          SQLAlchemy schema (users, authors, books, tickets, ticket_messages)
  schemas.py         Pydantic request/response models = validation + OpenAPI
  security.py        PBKDF2 password hashing, JWT, require_author / require_admin dependencies
  errors.py          uniform error envelope {"error": {code, message, details}}
  api/               thin route handlers: auth.py, author.py (/api/me/*), admin.py (/api/admin/*)
  services/tickets.py  ticket domain logic (create, triage, drafts, replies, filters, serializers)
  ai/                llm.py (provider client), prompts.py, knowledge_base.py (sectioned), rules.py (fallback), service.py (orchestration)
```

**Why these choices**
- **FastAPI:** typed request validation and free OpenAPI docs. Dependencies make auth and RBAC explicit on every route.
- **Schema:** `tickets.category_source` / `priority_source` are `ai | rules | admin`, so admins can see who set a value, and an admin override is never overwritten by a late AI result. Internal notes are `ticket_messages.is_internal=true`. They're filtered out in the author serializer, so they can't leak.
- **SQLite by default** for zero-setup review. Swap to Postgres with `DATABASE_URL` and no code changes.
- **Vue without a build step:** the reviewer runs one process. The SPA only talks to the REST API and holds no secrets.
- **Near-real-time via 4s polling:** simplest reliable option behind any host or proxy. It pauses when the tab is hidden. The author sees admin replies and status changes without refreshing. SSE/WebSockets are a drop-in upgrade (see Improvements).

## AI integration

**Flow**
1. **Ticket created:** keyword rules classify it instantly (so a ticket is never unclassified), the API returns 201 immediately, then a **background task** asks the LLM for `{category, priority, reason}` in JSON mode. The author never waits on the AI.
2. **Admin opens a ticket:** `GET /api/admin/tickets/{id}/draft` generates a reply draft, **caches it on the ticket**, and returns `source: ai|rules`. "Regenerate" forces a fresh one. The admin edits it and sends it, and it appears in the author's thread.

**Prompt strategy** (`ai/prompts.py`)
- Classification: a system prompt with category definitions and priority rubric taken from the brief's examples (e.g. "no royalty for 6 months" → Critical, "update bio" → Low), `temperature=0`, `max_tokens=80`, and JSON output. The output is **validated against the enum**, and invalid labels fall back to the rules.
- Drafting: the system prompt encodes BookLeaf's tone guidelines (acknowledge first, be specific with real numbers, own mistakes, concrete timelines, clear next step, no AI filler, sign-off). The user prompt has three tagged blocks: `<kb>` (only the relevant section), `<author_data>` (only this ticket's book: sold, earned, paid, pending, last payout, status, partner, platforms), and `<ticket>`. The model is told to use only these facts, which reduces hallucinated promises.

**Cost awareness**
- The KB is **split into sections** (`knowledge_base.py`), and each draft call sends company basics, one category section and tone (~250 tokens) instead of the whole document.
- Only the relevant book's fields are sent, not the author's whole catalogue or ticket history. Descriptions are truncated (1.5k chars for classification, 2k for drafting).
- Classification uses no KB and ~80 output tokens. Drafts are capped at 400 tokens and **cached** (no re-billing on every page view).
- Token usage is logged per call (`bookleaf.ai` logger), for monitoring.

**Graceful degradation**
- No key, timeout, HTTP 429 or 5xx gives one retry with backoff, then `LLMUnavailable`. Tickets still get created and classified by the keyword rules, and admins get a **template draft filled with the author's real figures**, labelled "Template draft (AI unavailable)". They can always write manually.

**Key security:** the key is read from `OPENAI_API_KEY` on the server only (`config.py`). It's never sent to the browser and never committed (`.env` is git-ignored, and `.env.example` has no secrets). `/api/health` only reports `ai_enabled: true/false`.

**Model choice:** `gpt-4o-mini` is cheap (fractions of a paisa per ticket), fast, reliable at JSON-mode classification, and good at short, empathetic business writing, which is exactly this workload. The client targets the OpenAI-compatible Chat Completions API, so Claude Haiku (via a compatible gateway), Groq or a self-hosted model is a config change (`AI_BASE_URL`, `AI_MODEL`).

## API reference

All routes except login, health and meta need `Authorization: Bearer <token>`. Errors always look like `{"error": {"code": "...", "message": "...", "details": [{"field","message"}] | null}}` with proper status codes (401 unauthenticated, 403 wrong role, 404 not found, 422 validation). Full schemas are at `/docs` (OpenAPI JSON at `/openapi.json`).

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/api/auth/login` | public | `{email, password}` → `{access_token, user}` |
| GET | `/api/auth/me` | any | Current user |
| GET | `/api/health` / `/api/meta` | public | Health + AI enabled flag / enum values (statuses, categories, priorities) |
| GET | `/api/me/books` | author | Own books with sales and royalty figures |
| GET | `/api/me/tickets` | author | Own tickets (latest activity first) |
| POST | `/api/me/tickets` | author | Create `{book_id \| null, subject (5–200), description (10–5000), attachment_name?}`. The book must belong to the author |
| GET | `/api/me/tickets/{id}` | author | Own ticket with public messages only (404 for others' tickets) |
| POST | `/api/me/tickets/{id}/messages` | author | Follow-up `{body}`. Reopens Resolved/Closed tickets |
| GET | `/api/admin/tickets` | admin | Queue. Filters: `status, category, priority, date_from, date_to (YYYY-MM-DD), assigned=me\|unassigned, q`. Sorted unresolved → priority → oldest |
| GET | `/api/admin/stats` | admin | Counts by status, and open tickets by priority |
| GET | `/api/admin/tickets/{id}` | admin | Full ticket, book context, messages incl. internal notes |
| PATCH | `/api/admin/tickets/{id}` | admin | `{status?, category?, priority?, assign_to_me?}`. Category/priority changes are marked `admin` |
| GET | `/api/admin/tickets/{id}/draft?regenerate=false` | admin | AI (or template) draft `{draft, source, cached}` |
| POST | `/api/admin/tickets/{id}/responses` | admin | Send reply `{body}`. Visible to the author. Open → In Progress |
| POST | `/api/admin/tickets/{id}/notes` | admin | Internal note `{body}`. Never visible to authors |

## Product touches
- The queue highlights Critical/High tickets and puts a red edge on unresolved tickets older than 48h. KPI tiles show open tickets by priority.
- Badges (`ai` / `rules` / `admin`) show who set each category and priority, and the AI's one-line reason is shown.
- The admin sees the book's royalty and status context next to the draft, so they can verify numbers before sending.
- Edge cases: books in production show "Sales and royalties appear once your book is live". Zero royalties, no payout yet, and empty states are handled. "Ask about this book" pre-fills the form.

## Assumptions
- The dataset has no passwords, so all authors share a seeded demo password (`author123`, configurable via env). Admin users are seeded too.
- Attachments are UI-only (only the file name is stored), as the brief allows.
- Timestamps are stored in UTC and shown in the browser's local time.
- "Assign to themselves" is implemented as assign/unassign self. Reassigning to other agents is a small extension.

## Known limitations / what I'd improve
- Replace polling with SSE or WebSockets plus a pub/sub (Redis) for multi-instance deployments.
- Move AI work to a real queue (RQ/Celery) with retries and dead-lettering. FastAPI background tasks are in-process.
- Postgres + Alembic migrations, real file uploads to S3, password reset, rate limiting on login.
- Evaluate classification on a labelled set of real tickets, and track override rate as a quality metric. Feed admin edits back as few-shot examples.
- Retrieval over the full help-centre (embeddings) once the KB grows beyond a few sections. Response caching for near-duplicate queries.
- Email notifications to authors when a reply is sent.

Screenshots of both portals are in `docs/screenshots/`, and the short write-up is in `WRITEUP.md`.
