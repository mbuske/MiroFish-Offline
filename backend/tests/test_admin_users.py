import pytest
from flask import Flask
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.auth.admin_routes import admin_bp
from app.auth.models import ROLE_ACCOUNT_ADMIN
from app.security import register_auth
from app.config import Config


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("admin@x.de", "adminpw", role=ROLE_ACCOUNT_ADMIN)
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(admin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "admin@x.de", "password": "adminpw"})
    return c


def test_admin_creates_and_lists_users(admin_client):
    r = admin_client.post("/api/admin/users",
                          json={"email": "new@x.de", "password": "pw12345", "name": "New"})
    assert r.status_code == 201
    users = admin_client.get("/api/admin/users").get_json()["users"]
    assert any(u["email"] == "new@x.de" for u in users)


def test_admin_deactivates_user(admin_client):
    uid = admin_client.post("/api/admin/users",
                            json={"email": "n@x.de", "password": "pw12345"}).get_json()["user"]["id"]
    assert admin_client.post(f"/api/admin/users/{uid}/active",
                             json={"active": False}).status_code == 200


def test_nonadmin_forbidden_on_admin_routes(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("user@x.de", "pw12345", role="user")
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(admin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "user@x.de", "password": "pw12345"})
    assert c.get("/api/admin/users").status_code == 403


def test_unauthenticated_blocked_on_admin_routes(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(admin_bp)
    register_auth(app)
    assert app.test_client().get("/api/admin/users").status_code in (401, 403)


def test_account_admin_scoped_to_own_account(tmp_path, monkeypatch):
    from app.accounts import service as acct_service
    from app.auth.models import ROLE_ACCOUNT_ADMIN, ROLE_USER
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    a = acct_service.create_account("A", "su"); b = acct_service.create_account("B", "su")
    service.create_user("admA@x.de", "pw12345", role=ROLE_ACCOUNT_ADMIN, account_id=a)
    other = service.create_user("ub@x.de", "pw12345", role=ROLE_USER, account_id=b)
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(admin_bp); register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "admA@x.de", "password": "pw12345"})
    # create -> lands in account A
    assert c.post("/api/admin/users", json={"email": "new@x.de", "password": "pw12345"}).status_code == 201
    emails = [u["email"] for u in c.get("/api/admin/users").get_json()["users"]]
    assert "new@x.de" in emails and "ub@x.de" not in emails
    # acting on account-B user -> 404
    assert c.post(f"/api/admin/users/{other}/active", json={"active": False}).status_code == 404
