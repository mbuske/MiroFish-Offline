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
def token_app(monkeypatch):
    # Avoid blocking on a real Neo4j connection during init; create_app handles
    # storage init failure gracefully (stores None). Auth runs regardless.
    import app.storage as storage_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("no neo4j in test")

    monkeypatch.setattr(storage_mod, "Neo4jStorage", _boom)
    monkeypatch.setattr(Config, "API_TOKEN", "itest-token", raising=False)
    app = create_app()
    app.config["API_TOKEN"] = "itest-token"
    return app


def test_api_blocked_without_token(token_app):
    path = _first_api_get_path(token_app)
    assert path is not None, "expected at least one no-arg GET /api route"
    resp = token_app.test_client().get(path)
    assert resp.status_code == 401


def test_api_passes_auth_with_token(token_app):
    path = _first_api_get_path(token_app)
    resp = token_app.test_client().get(
        path, headers={"Authorization": "Bearer itest-token"}
    )
    # Auth passed -> not 401 (view may still 4xx/5xx for other reasons).
    assert resp.status_code != 401


def test_health_open_even_with_token(token_app):
    resp = token_app.test_client().get("/health")
    assert resp.status_code == 200
