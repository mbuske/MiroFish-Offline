"""Ownership / data-isolation helpers.

Only ``current_user_id`` is retained; the legacy owner-based access helpers
(is_admin, can_access, require_owner_or_admin) were removed in Task 13 —
callers now use account-scoped helpers from ``app.auth.accounts``.
"""
from flask import g


def _user():
    return getattr(g, "current_user", None)


def current_user_id():
    u = _user()
    return u.id if u else None
