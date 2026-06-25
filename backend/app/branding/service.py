"""Branding/appearance settings service."""
import os
import re
from datetime import datetime, timezone

from app.auth.db import session_scope
from app.auth.models import Branding

# Singleton row key
_SINGLETON_ID = "singleton"

# Where branding assets are stored. Tests may monkeypatch this.
BRANDING_DIR = os.path.join(
    os.path.dirname(__file__), "../../uploads/branding"
)

_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "svg", "ico", "webp"}
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _ensure_dir():
    os.makedirs(BRANDING_DIR, exist_ok=True)


def _get_row(session):
    return session.get(Branding, _SINGLETON_ID)


def _upsert_row(session) -> Branding:
    row = _get_row(session)
    if row is None:
        row = Branding(id=_SINGLETON_ID)
        session.add(row)
    return row


def get_branding() -> dict:
    """Return the current branding settings (None values when unset)."""
    with session_scope() as s:
        row = _get_row(s)
        if row is None:
            return {
                "primary_color": None,
                "accent_color": None,
                "logo_filename": None,
                "favicon_filename": None,
            }
        return {
            "primary_color": row.primary_color,
            "accent_color": row.accent_color,
            "logo_filename": row.logo_filename,
            "favicon_filename": row.favicon_filename,
        }


def _validate_color(value: str | None, name: str) -> None:
    """Raise ValueError if value is not a valid CSS hex color or empty/None."""
    if value is None or value == "":
        return
    if not _COLOR_RE.match(value):
        raise ValueError(
            f"{name} must be a CSS hex color (e.g. #fff or #1a2b3c), got: {value!r}"
        )


def update_colors(
    primary_color: str | None,
    accent_color: str | None,
    updated_by: str | None,
) -> None:
    """Upsert the singleton row's color settings."""
    _validate_color(primary_color, "primary_color")
    _validate_color(accent_color, "accent_color")
    with session_scope() as s:
        row = _upsert_row(s)
        row.primary_color = primary_color or None
        row.accent_color = accent_color or None
        row.updated_at = datetime.now(timezone.utc)
        row.updated_by = updated_by


def save_asset(kind: str, file_storage, updated_by: str | None) -> str:
    """
    Validate and save a logo or favicon asset.

    Parameters
    ----------
    kind        : "logo" or "favicon"
    file_storage: werkzeug FileStorage object
    updated_by  : user id of the actor

    Returns
    -------
    The filename stored under BRANDING_DIR.

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

    _ensure_dir()
    dest_filename = f"{kind}.{ext}"
    dest_path = os.path.join(BRANDING_DIR, dest_filename)
    file_storage.save(dest_path)

    with session_scope() as s:
        row = _upsert_row(s)
        if kind == "logo":
            row.logo_filename = dest_filename
        else:
            row.favicon_filename = dest_filename
        row.updated_at = datetime.now(timezone.utc)
        row.updated_by = updated_by

    return dest_filename


def asset_path(kind: str) -> str | None:
    """Return the absolute path to the stored asset if it exists, else None."""
    with session_scope() as s:
        row = _get_row(s)
        if row is None:
            return None
        filename = row.logo_filename if kind == "logo" else row.favicon_filename
        if not filename:
            return None
    path = os.path.join(BRANDING_DIR, filename)
    return path if os.path.isfile(path) else None
