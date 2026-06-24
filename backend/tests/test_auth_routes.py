import pytest
from flask import Flask
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.config import Config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("a@b.de", "pw12345", name="A")
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    return app.test_client()


def test_login_success_sets_cookie(client):
    r = client.post("/api/auth/login", json={"email": "a@b.de", "password": "pw12345"})
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "a@b.de"
    assert "mf_session" in r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in r.headers.get("Set-Cookie", "")


def test_login_bad_password_generic_401(client):
    r = client.post("/api/auth/login", json={"email": "a@b.de", "password": "wrong"})
    assert r.status_code == 401
    # Generic — must not reveal whether the user exists.
    assert "password" not in r.get_json().get("error", "").lower()


def test_login_unknown_user_same_401(client):
    r = client.post("/api/auth/login", json={"email": "no@b.de", "password": "x"})
    assert r.status_code == 401
