"""Unit tests for the route-level graph-access guard.

These exercise ``require_graph_account_access`` (the helper wired into every
graph_id-keyed route) with a pushed Flask request context, a ``g.current_user``,
and a fake Neo4j storage whose ``get_graph_account`` returns a known account_id.

The legacy ``require_graph_owner_or_admin`` function was removed in Task 13;
its tests have been removed accordingly.
"""
import pytest
from contextlib import contextmanager
from flask import Flask, g, current_app

from app.auth import graph_access
from app.auth.models import ROLE_USER, ROLE_SUPERADMIN


class _U:
    def __init__(self, uid, role, account_id=None):
        self.id, self.role = uid, role
        self.account_id = account_id


class _FakeStorage:
    def __init__(self, account=None):
        self._account = account

    def get_graph_account(self, graph_id):
        return self._account


@contextmanager
def _ctx(user, account=None):
    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = user
        current_app.extensions['neo4j_storage'] = _FakeStorage(account=account)
        yield


# ---------------------------------------------------------------------------
# require_graph_account_access (account-scoped — primary guard)
# ---------------------------------------------------------------------------

def test_account_member_passes():
    with _ctx(_U("u1", ROLE_USER, account_id="accA"), account="accA"):
        graph_access.require_graph_account_access("g1")  # must not raise


def test_foreign_account_raises():
    with _ctx(_U("u1", ROLE_USER, account_id="accA"), account="accB"):
        with pytest.raises(PermissionError):
            graph_access.require_graph_account_access("g1")


def test_legacy_none_account_non_superadmin_raises():
    with _ctx(_U("u1", ROLE_USER, account_id="accA"), account=None):
        with pytest.raises(PermissionError):
            graph_access.require_graph_account_access("g1")


def test_superadmin_passes_for_any_account():
    with _ctx(_U("sa", ROLE_SUPERADMIN, account_id=None), account="accB"):
        graph_access.require_graph_account_access("g1")  # must not raise


def test_superadmin_passes_for_none_account():
    with _ctx(_U("sa", ROLE_SUPERADMIN, account_id=None), account=None):
        graph_access.require_graph_account_access("g1")  # must not raise


def test_missing_storage_account_access_denied():
    """No storage extension → account is None → non-superadmin denied (fail closed)."""
    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = _U("u1", ROLE_USER, account_id="accA")
        # do not register neo4j_storage
        with pytest.raises(PermissionError):
            graph_access.require_graph_account_access("g1")
