"""Pure auth logic: password hashing, user CRUD, sessions."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

import bcrypt

from . import db as authdb
from .models import User, UserSession, ROLE_ADMIN, ROLE_USER


def hash_password(plain, cost=12):
    """Hash a plain password using bcrypt."""
    if isinstance(plain, str):
        plain = plain.encode('utf-8')
    salt = bcrypt.gensalt(rounds=cost)
    return bcrypt.hashpw(plain, salt).decode('utf-8')


def verify_password(plain, hashed):
    """Verify a plain password against a bcrypt hash."""
    try:
        if isinstance(plain, str):
            plain = plain.encode('utf-8')
        if isinstance(hashed, str):
            hashed = hashed.encode('utf-8')
        return bcrypt.checkpw(plain, hashed)
    except ValueError:
        return False


def create_user(email, password, name=None, role=ROLE_USER, created_by=None):
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("invalid email")
    if not password:
        raise ValueError("password required")
    now = datetime.utcnow()
    uid = str(uuid.uuid4())
    with authdb.session_scope() as s:
        if s.query(User).filter_by(email=email).first():
            raise ValueError("email already exists")
        s.add(User(id=uid, email=email, name=name,
                   password_hash=hash_password(password),
                   role=role, is_active=True,
                   created_at=now, updated_at=now, created_by=created_by))
    return uid


def get_user_by_email(email):
    with authdb.session_scope() as s:
        u = s.query(User).filter_by(email=(email or "").strip().lower()).first()
        if u:
            s.expunge(u)
        return u


def get_user(user_id):
    with authdb.session_scope() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if u:
            s.expunge(u)
        return u
