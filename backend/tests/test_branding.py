"""Tests for the branding/appearance settings store."""
import io
import pytest
from datetime import datetime
from flask import Flask

from app.auth import db as authdb, service as auth_service
from app.auth.routes import auth_bp
from app.auth.admin_routes import admin_bp
from app.auth.models import ROLE_SUPERADMIN, Branding
from app.security import register_auth
from app.config import Config
import app.branding.service as branding_service
from app.branding.routes import branding_bp
from app.branding.admin_routes import branding_admin_bp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_branding_dir(tmp_path, monkeypatch):
    """Redirect BRANDING_DIR to a temp directory for every test."""
    branding_dir = str(tmp_path / "branding")
    monkeypatch.setattr(branding_service, "BRANDING_DIR", branding_dir)


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    """Set up an isolated auth DB and return its path."""
    db_path = str(tmp_path / "auth.db")
    monkeypatch.setattr(Config, "AUTH_DB_PATH", db_path)
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(db_path)
    return db_path


@pytest.fixture()
def public_client(auth_db):
    """Flask test client with only branding_bp + register_auth (no login)."""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(branding_bp)
    register_auth(app)
    return app.test_client()


@pytest.fixture()
def admin_client(auth_db):
    """Flask test client logged in as superadmin (branding writes require superadmin)."""
    auth_service.create_user("admin@x.de", "adminpw", role=ROLE_SUPERADMIN)
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(branding_admin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "admin@x.de", "password": "adminpw"})
    return c


@pytest.fixture()
def user_client(auth_db):
    """Flask test client logged in as a regular (non-admin) user."""
    auth_service.create_user("user@x.de", "userpw", role="user", account_id="accA")
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(branding_admin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "user@x.de", "password": "userpw"})
    return c


@pytest.fixture()
def anon_client(auth_db):
    """Unauthenticated test client with admin branding bp wired in."""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(branding_admin_bp)
    register_auth(app)
    return app.test_client()


# ---------------------------------------------------------------------------
# Model unit tests
# ---------------------------------------------------------------------------

def test_branding_rows_keyed_by_account(tmp_path):
    """Test that Branding rows can be keyed by account_id (NULL = global default)."""
    authdb.init_db(str(tmp_path / "auth.db"))
    with authdb.session_scope() as s:
        s.add(Branding(id="b-default", account_id=None, primary_color="#000000", updated_at=datetime.utcnow()))
        s.add(Branding(id="b-acc", account_id="accA", primary_color="#ff0000", updated_at=datetime.utcnow()))
    with authdb.session_scope() as s:
        assert s.query(Branding).filter_by(account_id=None).one().primary_color == "#000000"
        assert s.query(Branding).filter_by(account_id="accA").one().primary_color == "#ff0000"


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------

class TestGetBranding:
    def test_returns_nones_when_unset(self, auth_db):
        result = branding_service.get_branding()
        assert result == {
            "primary_color": None,
            "accent_color": None,
            "logo_filename": None,
            "favicon_filename": None,
        }


class TestUpdateColors:
    def test_persists_and_round_trips(self, auth_db):
        branding_service.update_colors("#ff0000", "#00ff00", updated_by="user-1")
        result = branding_service.get_branding()
        assert result["primary_color"] == "#ff0000"
        assert result["accent_color"] == "#00ff00"

    def test_invalid_primary_color_raises_value_error(self, auth_db):
        with pytest.raises(ValueError, match="primary_color"):
            branding_service.update_colors("red", None, updated_by=None)

    def test_invalid_accent_color_raises_value_error(self, auth_db):
        with pytest.raises(ValueError, match="accent_color"):
            branding_service.update_colors(None, "not-a-color", updated_by=None)

    def test_empty_string_color_is_accepted(self, auth_db):
        # empty string means "unset", should not raise
        branding_service.update_colors("", "", updated_by=None)
        result = branding_service.get_branding()
        assert result["primary_color"] is None
        assert result["accent_color"] is None

    def test_none_color_is_accepted(self, auth_db):
        branding_service.update_colors(None, None, updated_by=None)

    def test_three_char_hex_is_valid(self, auth_db):
        branding_service.update_colors("#abc", "#def", updated_by=None)
        result = branding_service.get_branding()
        assert result["primary_color"] == "#abc"

    def test_eight_char_hex_is_valid(self, auth_db):
        branding_service.update_colors("#aabbccdd", None, updated_by=None)
        result = branding_service.get_branding()
        assert result["primary_color"] == "#aabbccdd"

    def test_upsert_overwrites_previous_value(self, auth_db):
        branding_service.update_colors("#111111", None, updated_by=None)
        branding_service.update_colors("#222222", None, updated_by=None)
        result = branding_service.get_branding()
        assert result["primary_color"] == "#222222"


class TestSaveAsset:
    def _make_file(self, name: str, content: bytes = b"data"):
        from werkzeug.datastructures import FileStorage
        return FileStorage(stream=io.BytesIO(content), filename=name)

    def test_rejects_bad_extension(self, auth_db):
        f = self._make_file("logo.exe")
        with pytest.raises(ValueError, match="extension"):
            branding_service.save_asset("logo", f, updated_by=None)

    def test_rejects_bad_kind(self, auth_db):
        f = self._make_file("logo.png")
        with pytest.raises(ValueError, match="kind"):
            branding_service.save_asset("banner", f, updated_by=None)

    def test_saves_logo_and_sets_filename(self, auth_db, tmp_path):
        f = self._make_file("mylogo.png", b"\x89PNG\r\n")
        filename = branding_service.save_asset("logo", f, updated_by="user-1")
        assert filename == "logo.png"
        import os
        assert os.path.isfile(os.path.join(branding_service.BRANDING_DIR, "logo.png"))
        result = branding_service.get_branding()
        assert result["logo_filename"] == "logo.png"

    def test_saves_favicon_and_sets_filename(self, auth_db):
        f = self._make_file("fav.ico", b"ICO")
        filename = branding_service.save_asset("favicon", f, updated_by="user-1")
        assert filename == "favicon.ico"
        result = branding_service.get_branding()
        assert result["favicon_filename"] == "favicon.ico"

    def test_overwrite_keeps_latest(self, auth_db):
        f1 = self._make_file("logo1.png", b"old")
        branding_service.save_asset("logo", f1, updated_by=None)
        f2 = self._make_file("logo2.png", b"new")
        branding_service.save_asset("logo", f2, updated_by=None)
        import os
        path = os.path.join(branding_service.BRANDING_DIR, "logo.png")
        assert open(path, "rb").read() == b"new"


class TestAssetPath:
    def _make_file(self, name: str, content: bytes = b"data"):
        from werkzeug.datastructures import FileStorage
        return FileStorage(stream=io.BytesIO(content), filename=name)

    def test_returns_none_when_no_row(self, auth_db):
        assert branding_service.asset_path("logo") is None

    def test_returns_none_when_file_missing(self, auth_db):
        branding_service.save_asset("logo", self._make_file("l.png"), updated_by=None)
        import os
        os.remove(os.path.join(branding_service.BRANDING_DIR, "logo.png"))
        assert branding_service.asset_path("logo") is None

    def test_returns_path_when_file_exists(self, auth_db):
        branding_service.save_asset("logo", self._make_file("l.svg", b"<svg/>"), updated_by=None)
        path = branding_service.asset_path("logo")
        import os
        assert path is not None and os.path.isfile(path)


# ---------------------------------------------------------------------------
# Public route tests (no auth required)
# ---------------------------------------------------------------------------

class TestPublicRoutes:
    def test_config_accessible_without_auth(self, public_client):
        """GET /api/branding/config must return 200 with no cookie/auth."""
        r = public_client.get("/api/branding/config")
        assert r.status_code == 200
        data = r.get_json()
        assert data["success"] is True
        assert "data" in data

    def test_config_returns_nones_when_unset(self, public_client):
        r = public_client.get("/api/branding/config")
        d = r.get_json()["data"]
        assert d["primary_color"] is None
        assert d["accent_color"] is None
        assert d["logo_url"] is None
        assert d["favicon_url"] is None

    def test_logo_404_when_no_logo(self, public_client):
        r = public_client.get("/api/branding/logo")
        assert r.status_code == 404

    def test_favicon_404_when_no_favicon(self, public_client):
        r = public_client.get("/api/branding/favicon")
        assert r.status_code == 404

    def test_logo_200_when_set(self, auth_db, tmp_path):
        """After saving a logo, GET /api/branding/logo returns 200."""
        from werkzeug.datastructures import FileStorage
        f = FileStorage(stream=io.BytesIO(b"\x89PNG"), filename="l.png")
        branding_service.save_asset("logo", f, updated_by=None)

        # Build a client that includes the branding_bp
        app = Flask(__name__)
        app.config.from_object(Config)
        app.register_blueprint(branding_bp)
        register_auth(app)
        r = app.test_client().get("/api/branding/logo")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Admin write route tests
# ---------------------------------------------------------------------------

class TestAdminRoutes:
    def test_unauthenticated_returns_401(self, anon_client):
        r = anon_client.post("/api/admin/branding", json={})
        assert r.status_code == 401

    def test_nonadmin_returns_403(self, user_client):
        r = user_client.post("/api/admin/branding", json={})
        assert r.status_code == 403

    def test_admin_update_colors_returns_200_and_persists(self, admin_client):
        r = admin_client.post(
            "/api/admin/branding",
            json={"primary_color": "#123456", "accent_color": "#abcdef"},
        )
        assert r.status_code == 200
        assert r.get_json()["success"] is True
        result = branding_service.get_branding()
        assert result["primary_color"] == "#123456"
        assert result["accent_color"] == "#abcdef"

    def test_admin_invalid_color_returns_400(self, admin_client):
        r = admin_client.post(
            "/api/admin/branding",
            json={"primary_color": "bad-color"},
        )
        assert r.status_code == 400

    def test_admin_upload_logo_missing_file_returns_400(self, admin_client):
        r = admin_client.post("/api/admin/branding/logo")
        assert r.status_code == 400

    def test_admin_upload_logo_bad_extension_returns_400(self, admin_client):
        data = {"file": (io.BytesIO(b"data"), "logo.exe")}
        r = admin_client.post(
            "/api/admin/branding/logo",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 400

    def test_admin_upload_logo_success(self, admin_client):
        data = {"file": (io.BytesIO(b"\x89PNG"), "logo.png")}
        r = admin_client.post(
            "/api/admin/branding/logo",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        j = r.get_json()
        assert j["success"] is True
        assert j["logo_url"] == "/api/branding/logo"

    def test_admin_upload_favicon_success(self, admin_client):
        data = {"file": (io.BytesIO(b"ICO"), "fav.ico")}
        r = admin_client.post(
            "/api/admin/branding/favicon",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        j = r.get_json()
        assert j["success"] is True
        assert j["favicon_url"] == "/api/branding/favicon"
