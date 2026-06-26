"""Account (tenant) management service."""
import re
import unicodedata
import uuid
from datetime import datetime

from ..auth import db as authdb
from ..auth.models import Account, User
from ..auth import service as user_service


def slugify(name: str) -> str:
    """Convert a name to a URL-safe lowercase slug."""
    norm = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug or "account"


def _unique_slug(session, base: str) -> str:
    """Return a slug that does not yet exist in the accounts table."""
    slug, n = base, 1
    while session.query(Account).filter_by(slug=slug).first() is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


def get_account_by_slug(slug):
    """Return the Account with the given slug, or None."""
    with authdb.session_scope() as s:
        a = s.query(Account).filter_by(slug=slug).first()
        if a:
            s.expunge(a)
        return a


def create_account(name, created_by=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("account name required")
    aid = str(uuid.uuid4())
    with authdb.session_scope() as s:
        slug = _unique_slug(s, slugify(name))
        s.add(Account(id=aid, name=name, slug=slug, is_active=True,
                      created_at=datetime.utcnow(), created_by=created_by))
    return aid


def get_account(account_id):
    with authdb.session_scope() as s:
        a = s.query(Account).filter_by(id=account_id).first()
        if a:
            s.expunge(a)
        return a


def list_accounts():
    with authdb.session_scope() as s:
        out = []
        for a in s.query(Account).order_by(Account.created_at).all():
            count = s.query(User).filter_by(account_id=a.id).count()
            out.append({"id": a.id, "name": a.name, "slug": a.slug,
                        "is_active": a.is_active,
                        "created_at": a.created_at.isoformat(), "user_count": count})
        return out


def set_account_active(account_id, active):
    with authdb.session_scope() as s:
        a = s.query(Account).filter_by(id=account_id).first()
        if not a:
            raise ValueError("no such account")
        a.is_active = bool(active)
        member_ids = [u.id for u in s.query(User).filter_by(account_id=account_id).all()]
    if not active:
        for uid in member_ids:
            user_service.revoke_user_sessions(uid)
