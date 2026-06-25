from app.auth import db as authdb, service
from app.auth.seed import seed_admin_from_env
from app.auth.models import ROLE_ACCOUNT_ADMIN
from app.config import Config


def test_seed_creates_admin_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "ADMIN_EMAIL", "admin@x.de")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "adminpw")
    authdb.init_db(Config.AUTH_DB_PATH)
    new_id = seed_admin_from_env()
    assert new_id is not None
    assert service.get_user_by_email("admin@x.de").role == ROLE_ACCOUNT_ADMIN
    # Idempotent: second call creates nothing.
    assert seed_admin_from_env() is None
