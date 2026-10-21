import pytest

import app as goatlifts

INVITE = "test-invite"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test client backed by a fresh, throwaway SQLite database."""
    monkeypatch.setattr(goatlifts, "DB_PATH", str(tmp_path / "test.db"))
    goatlifts.init_db()
    goatlifts.app.config.update(TESTING=True, INVITE_CODE=INVITE)
    with goatlifts.app.test_client() as client:
        yield client


def csrf(client):
    """This session's CSRF token (creating one if the session has none yet)."""
    with client.session_transaction() as session:
        session.setdefault("csrf_token", "test-csrf-token")
        return session["csrf_token"]


@pytest.fixture
def post(client):
    """POST with a valid CSRF token added automatically."""
    def _post(path, **data):
        data.setdefault("csrf_token", csrf(client))
        return client.post(path, data=data)
    return _post


@pytest.fixture
def register(post):
    def _register(username="vance", display_name="Vance Penny", password="squat-bench-dead",
                  invite_code=INVITE, confirm=None):
        return post("/register", username=username, display_name=display_name, password=password,
                    confirm=password if confirm is None else confirm, invite_code=invite_code)
    return _register


@pytest.fixture
def log(post):
    """Post a session to /log; any field can be overridden."""
    def _log(**overrides):
        data = {"date": "2026-10-01", "squat": "150", "bench": "100", "deadlift": "190"}
        data.update(overrides)
        return post("/log", **data)
    return _log


def query(sql, *args):
    with goatlifts.closing(goatlifts.get_db()) as conn:
        return conn.execute(sql, args).fetchall()
