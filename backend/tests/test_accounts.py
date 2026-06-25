from datetime import datetime
from app.auth import db as authdb
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
