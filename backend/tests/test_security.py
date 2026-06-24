"""
Tests for the API authentication layer (CVE-2026-7042: missing authentication
for critical functions) and CORS hardening (CVE-2026-7041 related exposure).
"""
import pytest
from flask import Flask, Blueprint, jsonify

from app.security import register_auth, get_cors_origins


def _make_app(token):
    """Minimal app with a protected /api route and the auth hook installed."""
    app = Flask(__name__)
    app.config["API_TOKEN"] = token

    bp = Blueprint("t", __name__)

    @bp.route("/ping")
    def ping():
        return jsonify({"ok": True})

    app.register_blueprint(bp, url_prefix="/api/t")

    @app.route("/health")
    def health():
        return {"status": "ok"}

    register_auth(app)
    return app


class TestApiAuth:
    def test_api_rejected_without_token_when_token_configured(self):
        app = _make_app("s3cret")
        client = app.test_client()
        resp = client.get("/api/t/ping")
        assert resp.status_code == 401

    def test_api_allowed_with_correct_bearer_token(self):
        app = _make_app("s3cret")
        client = app.test_client()
        resp = client.get("/api/t/ping", headers={"Authorization": "Bearer s3cret"})
        assert resp.status_code == 200

    def test_api_allowed_with_x_api_key(self):
        app = _make_app("s3cret")
        client = app.test_client()
        resp = client.get("/api/t/ping", headers={"X-API-Key": "s3cret"})
        assert resp.status_code == 200

    def test_api_rejected_with_wrong_token(self):
        app = _make_app("s3cret")
        client = app.test_client()
        resp = client.get("/api/t/ping", headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 401

    def test_health_always_accessible(self):
        app = _make_app("s3cret")
        client = app.test_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_options_preflight_not_blocked(self):
        app = _make_app("s3cret")
        client = app.test_client()
        resp = client.open("/api/t/ping", method="OPTIONS")
        assert resp.status_code != 401

    def test_no_token_configured_now_requires_login(self):
        # After account-management, deny-by-default applies even without API_TOKEN.
        app = _make_app("")
        register_auth(app)
        resp = app.test_client().get("/api/t/ping")
        assert resp.status_code == 401


class TestCorsOrigins:
    def test_default_is_not_wildcard(self):
        origins = get_cors_origins("")
        assert origins != "*"
        assert "*" not in origins

    def test_parses_comma_separated_env(self):
        origins = get_cors_origins("http://localhost:3000, https://app.example.com")
        assert "http://localhost:3000" in origins
        assert "https://app.example.com" in origins


def test_auth_config_defaults():
    from app.config import Config
    assert Config.SESSION_COOKIE_NAME == "mf_session"
    assert isinstance(Config.SESSION_TTL_DAYS, int)
    assert isinstance(Config.BCRYPT_COST, int)
