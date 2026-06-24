import os
from datetime import datetime, timedelta
from app.auth import db as authdb
from app.auth.models import User, UserSession, ROLE_ADMIN


def test_init_db_creates_tables(tmp_path):
    path = str(tmp_path / "auth.db")
    authdb.init_db(path)
    assert os.path.exists(path)
    # Tables exist: opening a session and querying users must not raise.
    from app.auth.models import User
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
