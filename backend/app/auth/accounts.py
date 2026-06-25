"""Account-scope (tenant) access helpers."""
from flask import g
from .models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN


def _user():
    return getattr(g, "current_user", None)


def is_superadmin():
    u = _user()
    return bool(u and u.role == ROLE_SUPERADMIN)


def is_account_admin():
    u = _user()
    return bool(u and u.role == ROLE_ACCOUNT_ADMIN)


def current_account_id():
    u = _user()
    return u.account_id if u else None


def can_access_account(account_id):
    if is_superadmin():
        return True
    u = _user()
    return bool(u and account_id is not None and u.account_id == account_id)


def require_account_access(account_id):
    if not can_access_account(account_id):
        raise PermissionError("no account access")
