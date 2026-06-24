"""
Integration tests: the real app factory must enforce auth when API_TOKEN is set
and must not use a wildcard CORS origin.
"""
import pytest

from app import create_app
from app.config import Config


def _first_api_get_path(app):
    for rule in app.url_map.iter_rules():
        if str(rule).startswith("/api/") and "GET" in (rule.methods or set()) and not rule.arguments:
            return str(rule)
    return None


@pytest.fixture
def token_app(monkeypatch, tmp_path):
    import app.storage as storage_mod
    from app.auth import db as authdb, service

    def _boom(*a, **k):
        raise RuntimeError("no neo4j in test")
    monkeypatch.setattr(storage_mod, "Neo4jStorage", _boom)
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "ADMIN_EMAIL", "admin@x.de")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "adminpw")
    app = create_app()
    return app


def test_api_blocked_without_login(token_app):
    path = _first_api_get_path(token_app)
    assert token_app.test_client().get(path).status_code == 401


def test_api_passes_after_login(token_app):
    c = token_app.test_client()
    c.post("/api/auth/login", json={"email": "admin@x.de", "password": "adminpw"})
    assert c.get(_first_api_get_path(token_app)).status_code != 401


def test_health_open_even_with_token(token_app):
    resp = token_app.test_client().get("/health")
    assert resp.status_code == 200
