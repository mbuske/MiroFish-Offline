import pytest
from contextlib import contextmanager
from flask import Flask, g
from app.auth import ownership
from app.auth.models import ROLE_ADMIN, ROLE_USER


class _U:
    def __init__(self, uid, role):
        self.id, self.role = uid, role


@contextmanager
def _ctx(app, user):
    with app.test_request_context():
        g.current_user = user
        yield


def test_owner_can_access():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        assert ownership.can_access("u1") is True
        assert ownership.can_access("u2") is False


def test_admin_can_access_anything():
    app = Flask(__name__)
    with _ctx(app, _U("a", ROLE_ADMIN)):
        assert ownership.can_access("u2") is True
        assert ownership.can_access(None) is True


def test_require_raises_for_foreign():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        with pytest.raises(PermissionError):
            ownership.require_owner_or_admin("u2")


def test_nonadmin_denied_legacy_unowned():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        assert ownership.can_access(None) is False  # legacy/unowned → non-admin denied


def test_anonymous_user_denied():
    app = Flask(__name__)
    with _ctx(app, None):                       # no authenticated user
        assert ownership.can_access("u1") is False
        assert ownership.can_access(None) is False
        with pytest.raises(PermissionError):
            ownership.require_owner_or_admin("u1")
