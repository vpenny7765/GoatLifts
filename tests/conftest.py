import pytest

import app as goatlifts


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test client backed by a fresh, throwaway SQLite database."""
    monkeypatch.setattr(goatlifts, "DB_PATH", str(tmp_path / "test.db"))
    goatlifts.init_db()
    goatlifts.app.config["TESTING"] = True
    with goatlifts.app.test_client() as client:
        yield client


@pytest.fixture
def log(client):
    """Post a session to /log; any field can be overridden."""
    def _log(**overrides):
        data = {"name": "Vance Penny", "date": "2026-10-01",
                "squat": "150", "bench": "100", "deadlift": "190"}
        data.update(overrides)
        return client.post("/log", data=data)
    return _log


def rows():
    with goatlifts.closing(goatlifts.get_db()) as conn:
        return conn.execute("SELECT * FROM entries ORDER BY id").fetchall()
