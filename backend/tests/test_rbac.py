import pytest
from flask import Flask, Blueprint, jsonify, g
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.security import register_auth
from app.config import Config


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("a@b.de", "pw12345", account_id="accA")
    app = Flask(__name__)
    app.config.from_object(Config)
    bp = Blueprint("p", __name__)

    @bp.route("/secret")
    def secret():
        return jsonify({"who": g.current_user.email})

    app.register_blueprint(bp, url_prefix="/api/p")
    app.register_blueprint(auth_bp)
    register_auth(app)
    return app


def test_protected_route_blocks_anonymous(app):
    assert app.test_client().get("/api/p/secret").status_code == 401


def test_protected_route_after_login(app):
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "a@b.de", "password": "pw12345"})
    r = c.get("/api/p/secret")
    assert r.status_code == 200 and r.get_json()["who"] == "a@b.de"


def test_login_endpoint_is_public(app):
    assert app.test_client().post(
        "/api/auth/login", json={"email": "a@b.de", "password": "pw12345"}
    ).status_code == 200


def test_account_admin_required_blocks_non_admin(tmp_path, monkeypatch):
    from app.auth.decorators import account_admin_required
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("u@b.de", "pw12345", account_id="accA")  # role=user
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.route("/api/admin/ping")
    @account_admin_required
    def ping():
        return jsonify({"ok": True})

    app.register_blueprint(auth_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "u@b.de", "password": "pw12345"})
    assert c.get("/api/admin/ping").status_code == 403


def test_role_decorators(tmp_path, monkeypatch):
    from flask import Flask, g, jsonify
    from app.auth.decorators import superadmin_required, account_admin_required
    from app.auth.models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER

    class _U:
        def __init__(self, role):
            self.role = role

    app = Flask(__name__)

    @app.route("/su")
    @superadmin_required
    def su():
        return jsonify(ok=True)

    @app.route("/aa")
    @account_admin_required
    def aa():
        return jsonify(ok=True)

    def call(path, user):
        with app.test_request_context(path):
            g.current_user = user
            return app.view_functions[{"/su": "su", "/aa": "aa"}[path]]()

    # superadmin route
    with app.test_request_context("/su"):
        g.current_user = _U(ROLE_ACCOUNT_ADMIN)
        from app.auth.decorators import superadmin_required as _s  # ensure import
    c = app.test_client()
    # use real dispatch for status codes:
    @app.before_request
    def _noop():
        return None

    # account_admin route: user forbidden, account_admin ok
    with app.test_request_context("/aa"):
        g.current_user = _U(ROLE_USER)
        resp = aa()
        assert resp[1] == 403
    with app.test_request_context("/aa"):
        g.current_user = _U(ROLE_ACCOUNT_ADMIN)
        assert aa().json["ok"] is True
    # superadmin route: account_admin forbidden, superadmin ok
    with app.test_request_context("/su"):
        g.current_user = _U(ROLE_ACCOUNT_ADMIN)
        resp = su()
        assert resp[1] == 403
    with app.test_request_context("/su"):
        g.current_user = _U(ROLE_SUPERADMIN)
        assert su().json["ok"] is True
