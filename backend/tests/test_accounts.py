from datetime import datetime
from app.auth import db as authdb
from app.auth.models import Account, User, ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER


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
