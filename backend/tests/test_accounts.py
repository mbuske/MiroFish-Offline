import pytest
from datetime import datetime
from flask import Flask
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.accounts.routes import superadmin_bp
from app.security import register_auth
from app.config import Config
from app.auth.models import Account, User, ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER
from app.accounts import service as acct_service
from app.auth import service as user_service


def test_account_and_user_account_id_persist(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    with authdb.session_scope() as s:
        s.add(Account(id="acc1", name="Acme", is_active=True, created_at=datetime.utcnow(), created_by="su1"))
        s.flush()
        s.add(User(id="u1", email="a@b.de", password_hash="x", role=ROLE_USER, is_active=True,
                   account_id="acc1", created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
    with authdb.session_scope() as s:
        assert s.query(Account).one().name == "Acme"
        assert s.query(User).filter_by(email="a@b.de").one().account_id == "acc1"
    assert (ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER) == ("superadmin", "account_admin", "user")


def test_account_service_crud_and_disable_revokes(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    aid = acct_service.create_account("Acme", created_by="su1")
    assert isinstance(aid, str)
    # a member with a live session
    uid = user_service.create_user("m@acme.de", "pw12345", role=ROLE_USER, account_id=aid)
    token = user_service.start_session(uid)
    listed = acct_service.list_accounts()
    row = [a for a in listed if a["id"] == aid][0]
    assert row["name"] == "Acme" and row["user_count"] == 1
    acct_service.set_account_active(aid, False)
    assert user_service.resolve_session(token) is None  # member session revoked


@pytest.fixture
def su_client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("root@x.de", "rootpw12", role=ROLE_SUPERADMIN, account_id=None)
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(superadmin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "root@x.de", "password": "rootpw12"})
    return c


def test_superadmin_creates_account_and_admin(su_client):
    r = su_client.post("/api/superadmin/accounts", json={"name": "Acme"})
    assert r.status_code == 201
    aid = r.get_json()["account"]["id"]
    r2 = su_client.post(f"/api/superadmin/accounts/{aid}/admin",
                        json={"email": "admin@acme.de", "password": "pw123456", "name": "A"})
    assert r2.status_code == 201
    users = su_client.get(f"/api/superadmin/accounts/{aid}/users").get_json()["users"]
    assert any(u["email"] == "admin@acme.de" and u["role"] == "account_admin" for u in users)


def test_superadmin_routes_forbidden_for_non_superadmin(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("u@x.de", "pw12345", role=ROLE_USER, account_id="accA")
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(superadmin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "u@x.de", "password": "pw12345"})
    assert c.get("/api/superadmin/accounts").status_code == 403
