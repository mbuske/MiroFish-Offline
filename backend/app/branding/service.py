"""Branding/appearance settings service — per-account with global-default fallback."""
import os
import re
import uuid
from datetime import datetime, timezone

from app.auth import db as authdb
from app.auth.models import Branding

# Where branding assets are stored. Tests may monkeypatch this.
BRANDING_DIR = os.path.join(
    os.path.dirname(__file__), "../../uploads/branding"
)

_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "svg", "ico", "webp"}
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_FIELDS = ("primary_color", "accent_color", "logo_filename", "favicon_filename")


def _dir_for(account_id):
    """Return (and create) the asset directory for an account or 'default'."""
    sub = account_id if account_id is not None else "default"
    d = os.path.join(BRANDING_DIR, sub)
    os.makedirs(d, exist_ok=True)
    return d


def _row(session, account_id):
    """Fetch the Branding row for the given account_id (None = global default)."""
    return session.query(Branding).filter_by(account_id=account_id).first()


def get_branding(account_id=None) -> dict:
    """Return the raw branding settings for one account row (None values when unset)."""
    with authdb.session_scope() as s:
        r = _row(s, account_id)
        return {f: getattr(r, f) if r else None for f in _FIELDS}


def resolve_branding(account_id=None) -> dict:
    """
    Return merged branding: each field = account row value else default row value else None.
    When account_id is None, returns the default row directly.
    """
    with authdb.session_scope() as s:
        acc = _row(s, account_id) if account_id is not None else None
        default = _row(s, None)

        def pick(f):
            if acc is not None and getattr(acc, f) is not None:
                return getattr(acc, f)
            return getattr(default, f) if default is not None else None

        return {f: pick(f) for f in _FIELDS}


def resolve_account_id_for_slug(slug) -> str | None:
    """Return the account id for a slug, or None if not found."""
    if not slug:
        return None
    from app.accounts.service import get_account_by_slug
    a = get_account_by_slug(slug)
    return a.id if a else None


def _validate_color(value: str | None, name: str) -> None:
    """Raise ValueError if value is not a valid CSS hex color or empty/None."""
    if value is None or value == "":
        return
    if not _COLOR_RE.match(value):
        raise ValueError(
            f"{name} must be a CSS hex color (e.g. #fff or #1a2b3c), got: {value!r}"
        )


def update_colors(
    account_id,
    primary_color: str | None,
    accent_color: str | None,
    updated_by: str | None,
) -> None:
    """Upsert the branding row for account_id (None = global default)."""
    _validate_color(primary_color, "primary_color")
    _validate_color(accent_color, "accent_color")
    with authdb.session_scope() as s:
        r = _row(s, account_id)
        if r is None:
            r = Branding(id=str(uuid.uuid4()), account_id=account_id)
            s.add(r)
        if primary_color is not None:
            r.primary_color = primary_color or None
        if accent_color is not None:
            r.accent_color = accent_color or None
        r.updated_at = datetime.now(timezone.utc)
        r.updated_by = updated_by


def save_asset(account_id, kind: str, file_storage, updated_by: str | None) -> str:
    """
    Validate and save a logo or favicon asset for a given account.

    Parameters
    ----------
    account_id  : account id (None = global default)
    kind        : "logo" or "favicon"
    file_storage: werkzeug FileStorage object
    updated_by  : user id of the actor

    Returns
    -------
    The filename stored under the account's asset directory.

    Raises
    ------
    ValueError on bad kind or unsupported extension.
    """
    if kind not in ("logo", "favicon"):
        raise ValueError(f"kind must be 'logo' or 'favicon', got {kind!r}")

    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file extension {ext!r}. Allowed: {_ALLOWED_EXTENSIONS}"
        )

    dest_dir = _dir_for(account_id)
    dest_filename = f"{kind}.{ext}"
    dest_path = os.path.join(dest_dir, dest_filename)
    file_storage.save(dest_path)

    with authdb.session_scope() as s:
        r = _row(s, account_id)
        if r is None:
            r = Branding(id=str(uuid.uuid4()), account_id=account_id)
            s.add(r)
        setattr(r, f"{kind}_filename", dest_filename)
        r.updated_at = datetime.now(timezone.utc)
        r.updated_by = updated_by

    return dest_filename


def asset_path(account_id, kind: str) -> str | None:
    """
    Return the absolute path to the stored asset for account_id if it exists, else None.
    No fallback — the resolve layer handles fallback to default.
    """
    with authdb.session_scope() as s:
        r = _row(s, account_id)
        if r is None:
            return None
        fname = getattr(r, f"{kind}_filename", None) if r else None
        if not fname:
            return None
    sub = account_id if account_id is not None else "default"
    p = os.path.join(BRANDING_DIR, sub, fname)
    return p if os.path.isfile(p) else None
