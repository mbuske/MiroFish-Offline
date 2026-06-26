"""FIX 3: /api/graph/tasks blanket enumeration is gated to superadmin.

Tasks carry no account association, so listing them all would leak cross-account
simulation_id/graph_id/report_id metadata. The endpoint is a debug/admin listing
not used by normal frontend flows, so it is restricted to superadmin.
"""
from flask import Flask

from app.api import graph_bp, graph
from app.auth.routes import auth_bp
from app.security import register_auth
from app.config import Config
from app.auth import db as authdb, service
from app.auth.models import ROLE_SUPERADMIN, ROLE_USER


def _make_app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    # Avoid touching TaskManager/Neo4j inside the handler.
    monkeypatch.setattr(graph.TaskManager, "list_tasks", lambda self: [])
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    app.register_blueprint(graph_bp, url_prefix="/api/graph")
    register_auth(app)
    return app


def test_tasks_superadmin_allowed(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    service.create_user("root@x.de", "rootpw12", role=ROLE_SUPERADMIN, account_id=None)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "root@x.de", "password": "rootpw12"})
    r = c.get("/api/graph/tasks")
    assert r.status_code == 200
    assert r.get_json()["success"] is True


def test_tasks_non_superadmin_forbidden(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    service.create_user("u@x.de", "pw123456", role=ROLE_USER, account_id="accA")
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "u@x.de", "password": "pw123456"})
    r = c.get("/api/graph/tasks")
    assert r.status_code == 403


def test_tasks_anonymous_unauthorized(tmp_path, monkeypatch):
    app = _make_app(tmp_path, monkeypatch)
    c = app.test_client()
    r = c.get("/api/graph/tasks")
    assert r.status_code == 401
