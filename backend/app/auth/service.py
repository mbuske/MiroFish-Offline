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
