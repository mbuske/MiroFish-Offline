import os
from app.auth import db as authdb


def test_init_db_creates_tables(tmp_path):
    path = str(tmp_path / "auth.db")
    authdb.init_db(path)
    assert os.path.exists(path)
    # Tables exist: opening a session and querying users must not raise.
    from app.auth.models import User
    with authdb.session_scope() as s:
        assert s.query(User).count() == 0
