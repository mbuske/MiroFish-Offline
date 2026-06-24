"""
API security layer.

Addresses CVE-2026-7042 (missing authentication for critical functions) by
adding an opt-in bearer-token gate over the REST API, and provides CORS origin
hardening to replace the wildcard `*` origin.

The token is opt-in (enabled by setting API_TOKEN) so the default localhost,
single-user experience is preserved; when set, every /api/* route requires it.
"""
import hmac
import os

from flask import request, jsonify

# Routes that must never require auth (liveness probe + CORS preflight handled
# separately by method).
_AUTH_EXEMPT_PATHS = frozenset({"/health"})

_DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def get_cors_origins(raw: str | None = None) -> list[str]:
    """
    Return the list of allowed CORS origins.

    Reads CORS_ORIGINS (comma-separated) from the environment when `raw` is not
    provided. Never returns a wildcard.
    """
    if raw is None:
        raw = os.environ.get("CORS_ORIGINS", "")
    if not raw.strip():
        raw = _DEFAULT_CORS_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]


def _extract_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer ") :].strip()
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    return None


def register_auth(app) -> None:
    """Resolve the session cookie into g.current_user and enforce auth on /api/*."""
    from flask import g
    from .auth import service
    from .config import Config

    @app.before_request
    def _auth():
        g.current_user = None
        # 1) Resolve a server-side session from the cookie (if any).
        token = request.cookies.get(Config.SESSION_COOKIE_NAME)
        if token:
            g.current_user = service.resolve_session(token)

        if request.method == "OPTIONS":
            return None
        if not request.path.startswith("/api/"):
            return None
        if request.path in _AUTH_EXEMPT_PATHS or request.path == "/api/auth/login":
            return None

        # 2) Accept the optional static machine token as an alternative.
        configured = app.config.get("API_TOKEN") or ""
        if configured and _extract_token() and hmac.compare_digest(_extract_token(), configured):
            return None

        # 3) Otherwise require an authenticated user.
        if g.current_user is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return None
