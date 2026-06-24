"""Ownership / data-isolation helpers."""
from flask import g
from .models import ROLE_ADMIN


def _user():
    return getattr(g, "current_user", None)


def is_admin():
    u = _user()
    return bool(u and u.role == ROLE_ADMIN)


def current_user_id():
    u = _user()
    return u.id if u else None


def can_access(owner_id):
    if is_admin():
        return True
    uid = current_user_id()
    return uid is not None and owner_id == uid


def require_owner_or_admin(owner_id):
    if not can_access(owner_id):
        raise PermissionError("not owner")
