import os
import pytest
from datetime import datetime, timedelta
from app.auth import db as authdb
from app.auth import service
from app.auth.models import User, UserSession, ROLE_ADMIN, ROLE_USER


def test_init_db_creates_tables(tmp_path):
    path = str(tmp_path / "auth.db")
    authdb.init_db(path)
    assert os.path.exists(path)
    # Tables exist: opening a session and querying users must not raise.
    with authdb.session_scope() as s:
        assert s.query(User).count() == 0


def test_user_and_session_persist(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    with authdb.session_scope() as s:
        u = User(id="u1", email="a@b.de", name="A", password_hash="x",
                 role=ROLE_ADMIN, is_active=True,
                 created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        s.add(u)
        s.flush()
        s.add(UserSession(id="s1", token_hash="h", user_id="u1",
                          created_at=datetime.utcnow(),
                          expires_at=datetime.utcnow() + timedelta(days=7),
                          last_used_at=datetime.utcnow()))
    with authdb.session_scope() as s:
        assert s.query(User).filter_by(email="a@b.de").one().role == "admin"
        assert s.query(UserSession).filter_by(user_id="u1").count() == 1


def test_hash_and_verify_password():
    h = service.hash_password("s3cret")
    assert h != "s3cret"
    assert service.verify_password("s3cret", h) is True
    assert service.verify_password("wrong", h) is False


def test_create_user_and_duplicate(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    uid = service.create_user("x@y.de", "pw12345", name="X")
    assert isinstance(uid, str)
    fetched = service.get_user_by_email("x@y.de")
    assert fetched.id == uid and fetched.role == "user"
    with pytest.raises(ValueError):
        service.create_user("x@y.de", "other")


def test_create_user_rejects_empty(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    with pytest.raises(ValueError):
        service.create_user("", "pw")
    with pytest.raises(ValueError):
        service.create_user("a@b.de", "")


def _setup(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    return service.create_user("a@b.de", "pw")


def test_start_and_resolve_session(tmp_path):
    uid = _setup(tmp_path)
    token = service.start_session(uid)
    assert service.resolve_session(token).id == uid


def test_resolve_rejects_unknown(tmp_path):
    _setup(tmp_path)
    assert service.resolve_session("nope") is None


def test_revoke_session(tmp_path):
    uid = _setup(tmp_path)
    token = service.start_session(uid)
    service.revoke_session(token)
    assert service.resolve_session(token) is None


def test_revoke_user_sessions(tmp_path):
    uid = _setup(tmp_path)
    t1 = service.start_session(uid)
    t2 = service.start_session(uid)
    count = service.revoke_user_sessions(uid)
    assert count == 2
    assert service.resolve_session(t1) is None
    assert service.resolve_session(t2) is None


def test_expired_session_rejected(tmp_path):
    uid = _setup(tmp_path)
    token = service.start_session(uid)
    with authdb.session_scope() as s:
        row = s.query(UserSession).filter_by(
            token_hash=service._hash_token(token)).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    assert service.resolve_session(token) is None
