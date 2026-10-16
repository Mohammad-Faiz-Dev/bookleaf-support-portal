import os
import tempfile

import pytest

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""  # tests never hit a real AI provider

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, email, pw):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def priya(client):
    return _login(client, "priya.sharma@email.com", "author123")


@pytest.fixture(scope="session")
def rohit(client):
    return _login(client, "rohit.kapoor@email.com", "author123")


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@bookleafpub.com", "admin123")
