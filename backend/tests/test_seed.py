from app.auth import db as authdb, service
from app.auth.seed import seed_admin_from_env
from app.config import Config


def test_seed_creates_superadmin(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "ADMIN_EMAIL", "root@x.de")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "rootpw12")
    authdb.init_db(Config.AUTH_DB_PATH)
    assert seed_admin_from_env() is not None
    u = service.get_user_by_email("root@x.de")
    assert u.role == "superadmin" and u.account_id is None
    assert seed_admin_from_env() is None  # idempotent
