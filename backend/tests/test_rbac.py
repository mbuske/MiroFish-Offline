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
    service.create_user("a@b.de", "pw12345")
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
