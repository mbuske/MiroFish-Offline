import pytest
from flask import Flask
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.config import Config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("a@b.de", "pw12345", name="A", account_id="accA")
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    return app.test_client()


@pytest.fixture
def me_client(tmp_path, monkeypatch):
    """Client with security middleware registered so /me works via cookie."""
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    authdb.init_db(Config.AUTH_DB_PATH)
    from app.accounts import service as acct_service
    aid = acct_service.create_account("Acme Corp")
    service.create_user("member@b.de", "pw12345", name="Member", account_id=aid)
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    from app.security import register_auth
    register_auth(app)
    return app.test_client()


def test_login_success_sets_cookie(client):
    r = client.post("/api/auth/login", json={"email": "a@b.de", "password": "pw12345"})
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "a@b.de"
    assert "mf_session" in r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in r.headers.get("Set-Cookie", "")
    cookie = r.headers.get("Set-Cookie", "")
    assert "SameSite=Lax" in cookie
    assert "Max-Age=" in cookie


def test_login_bad_password_generic_401(client):
    r = client.post("/api/auth/login", json={"email": "a@b.de", "password": "wrong"})
    assert r.status_code == 401
    # Generic — must not reveal whether the user exists.
    assert "password" not in r.get_json().get("error", "").lower()


def test_login_unknown_user_same_401(client):
    r = client.post("/api/auth/login", json={"email": "no@b.de", "password": "x"})
    assert r.status_code == 401
    assert r.get_json().get("error") == "Invalid credentials"


def test_login_inactive_user_generic_401(client):
    uid = service.get_user_by_email("a@b.de").id
    service.set_active(uid, False)
    r = client.post("/api/auth/login", json={"email": "a@b.de", "password": "pw12345"})
    assert r.status_code == 401
    assert r.get_json().get("error") == "Invalid credentials"


def test_me_returns_account_id_and_name(me_client):
    """Login as an account member; /me must return account_id and account_name."""
    r = me_client.post("/api/auth/login", json={"email": "member@b.de", "password": "pw12345"})
    assert r.status_code == 200
    user = r.get_json()["user"]
    assert user["account_id"] is not None
    assert user["account_name"] == "Acme Corp"

    # Also verify /me endpoint returns the same fields.
    r2 = me_client.get("/api/auth/me")
    assert r2.status_code == 200
    me = r2.get_json()["user"]
    assert me["account_id"] == user["account_id"]
    assert me["account_name"] == "Acme Corp"


def test_me_returns_account_slug(me_client):
    """Login as an account member; /me must return account_slug matching the account's slug."""
    from app.accounts import service as acct_service
    r = me_client.post("/api/auth/login", json={"email": "member@b.de", "password": "pw12345"})
    assert r.status_code == 200
    user = r.get_json()["user"]
    assert "account_slug" in user
    aid = user["account_id"]
    expected_slug = acct_service.get_account(aid).slug
    assert user["account_slug"] == expected_slug

    r2 = me_client.get("/api/auth/me")
    assert r2.status_code == 200
    assert r2.get_json()["user"]["account_slug"] == expected_slug


def test_me_superadmin_has_null_account(me_client):
    """A superadmin (account_id=None) gets null account fields on /me."""
    from app.auth.models import ROLE_SUPERADMIN
    service.create_user("root@b.de", "rootpw12", role=ROLE_SUPERADMIN)
    r = me_client.post("/api/auth/login", json={"email": "root@b.de", "password": "rootpw12"})
    assert r.status_code == 200
    user = r.get_json()["user"]
    assert user["account_id"] is None
    assert user["account_name"] is None
