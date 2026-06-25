"""Unit tests for the route-level graph-access guard.

These exercise ``require_graph_owner_or_admin`` (the helper wired into every
graph_id-keyed route) with a pushed Flask request context, a ``g.current_user``,
and a fake Neo4j storage whose ``get_graph_owner`` returns a known owner. They
would have caught an unwired/misbehaving guard.
"""
import pytest
from contextlib import contextmanager
from flask import Flask, g, current_app

from app.auth import graph_access
from app.auth.models import ROLE_ADMIN, ROLE_USER


class _U:
    def __init__(self, uid, role):
        self.id, self.role = uid, role


class _FakeStorage:
    def __init__(self, owner):
        self._owner = owner

    def get_graph_owner(self, graph_id):
        return self._owner


@contextmanager
def _ctx(user, owner):
    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = user
        current_app.extensions['neo4j_storage'] = _FakeStorage(owner)
        yield


def test_owner_passes():
    with _ctx(_U("u1", ROLE_USER), owner="u1"):
        graph_access.require_graph_owner_or_admin("g1")  # must not raise


def test_foreign_non_owner_raises():
    with _ctx(_U("u1", ROLE_USER), owner="u2"):
        with pytest.raises(PermissionError):
            graph_access.require_graph_owner_or_admin("g1")


def test_legacy_none_owner_non_admin_raises():
    with _ctx(_U("u1", ROLE_USER), owner=None):
        with pytest.raises(PermissionError):
            graph_access.require_graph_owner_or_admin("g1")


def test_admin_passes_for_foreign_owner():
    with _ctx(_U("admin", ROLE_ADMIN), owner="u2"):
        graph_access.require_graph_owner_or_admin("g1")  # must not raise


def test_admin_passes_for_none_owner():
    with _ctx(_U("admin", ROLE_ADMIN), owner=None):
        graph_access.require_graph_owner_or_admin("g1")  # must not raise


def test_missing_storage_treats_owner_as_none():
    """No storage extension → owner is None → non-admin denied (fail closed)."""
    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = _U("u1", ROLE_USER)
        # do not register neo4j_storage
        with pytest.raises(PermissionError):
            graph_access.require_graph_owner_or_admin("g1")
