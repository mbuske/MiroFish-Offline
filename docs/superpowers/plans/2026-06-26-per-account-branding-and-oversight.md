# Per-Account Branding (+ slug) & Superadmin Oversight — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make branding per-account (with a global-default fallback and a URL `slug` that brands the login screen), and surface superadmin oversight (slug column + read-only per-account users drill-down; suspend already exists).

**Architecture:** `Account` gains a unique `slug`. The singleton `Branding` row becomes account-keyed (`account_id` nullable; NULL = global default). Branding resolves per field as account → default → hardcoded. Public read endpoints take `?account=<slug>` so the login screen can render an account's branding before auth; after login the SPA re-resolves to the user's account. account_admins edit their own account's branding; superadmins edit any account + the default.

**Tech Stack:** Flask 3, Flask-SQLAlchemy, SQLite, Vue 3 + vue-i18n, axios.

## Global Constraints

- Python `>=3.11,<3.13`; no new dependencies. Backend tests from `backend/`: `cd backend && uv run pytest tests/` (~11 min full run — let it finish; must end green + pristine). Run from `backend/`.
- Roles: `superadmin` (account_id None), `account_admin`, `user`. Decorators: `@superadmin_required`, `@account_admin_required` (allows account_admin + superadmin), `@login_required`.
- Branding field resolution everywhere: **account value → global-default value → None** (frontend applies a hardcoded fallback e.g. `#FF4500`). Global default = the `Branding` row with `account_id IS NULL`.
- Slug: URL-safe (`^[a-z0-9]+(?:-[a-z0-9]+)*$`), unique, generated from the account name, collision-suffixed; superadmin-renameable.
- `/api/account/branding/*` requires a non-null `current_account_id()` → **400** "no account context" otherwise (so a superadmin uses the superadmin/default routes).
- Public branding reads stay allowlisted (path-based; the `?account=` query doesn't change the path): `/api/branding/config`, `/api/branding/logo`, `/api/branding/favicon`.
- Frontend: axios returns UNWRAPPED payloads (don't destructure `.data`); FormData uploads omit JSON content-type (already handled). Locale files `locales/en.json`/`de.json` at key parity (German Sie-form, real umlauts). Frontend verified by `cd frontend && npm run build` (no JS test runner).
- Fresh-start friendly: additive schema; convert the existing singleton branding row to the global default; backfill account slugs. A one-time `auth.db` wipe is also acceptable.

---

## File Structure

**Backend — modify:** `app/auth/models.py` (Account.slug; Branding.account_id), `app/accounts/service.py` (slug gen/rename), `app/accounts/routes.py` (slug in payload + rename route + per-account branding routes), `app/auth/routes.py` (`/me` + account_slug), `app/branding/service.py` (per-account + resolve + slug), `app/branding/routes.py` (public `?account=`), `app/branding/admin_routes.py` (→ global default), `app/__init__.py` (register account-branding blueprint). **Create:** `app/branding/account_routes.py` (`/api/account/branding/*`).
**Backend — test:** extend `tests/test_accounts.py`, `tests/test_branding.py`, `tests/test_auth_routes.py`.
**Frontend — modify:** `src/stores/branding.js` (slug), `src/views/BrandingSettings.vue` (account-scoped), `src/views/SuperadminAccounts.vue` (slug + users drill-down + per-account branding), `src/components/UserMenu.vue` (account_admin Appearance), `src/router/index.js` (if a per-account branding route is added), `locales/*.json`.

---

# PHASE 1 — Account slug

### Task 1: `Account.slug` + generation

**Files:** Modify `backend/app/auth/models.py`, `backend/app/accounts/service.py`; Test `backend/tests/test_accounts.py`.

**Interfaces:**
- Produces: `Account.slug` (str, unique, not null). `accounts.service.slugify(name) -> str`. `create_account(name, created_by=None) -> str` now also sets a unique slug. `get_account`/`list_accounts` expose `slug`. `get_account_by_slug(slug) -> Account|None`.

- [ ] **Step 1: Write failing test**
```python
from app.auth import db as authdb
from app.accounts import service as acct


def test_account_gets_unique_slug(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    a1 = acct.create_account("Acme Corp", created_by="su")
    a2 = acct.create_account("Acme Corp", created_by="su")  # same name → unique slug
    s1 = acct.get_account(a1).slug
    s2 = acct.get_account(a2).slug
    assert s1 == "acme-corp"
    assert s2 != s1 and s2.startswith("acme-corp")
    assert acct.get_account_by_slug("acme-corp").id == a1
    assert acct.slugify("Ünîç &   Test!") == "unic-test"
```

- [ ] **Step 2: Run test, verify it fails**
Run: `cd backend && uv run pytest tests/test_accounts.py::test_account_gets_unique_slug -v`
Expected: FAIL (`slug` attribute / `slugify` missing).

- [ ] **Step 3: Add `slug` to `Account`** in `models.py`: `slug = Column(String, unique=True, nullable=False, index=True)`.

- [ ] **Step 4: Implement in `accounts/service.py`**
```python
import re
import unicodedata

def slugify(name: str) -> str:
    norm = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    return slug or "account"

def _unique_slug(session, base: str) -> str:
    from ..auth.models import Account
    slug, n = base, 1
    while session.query(Account).filter_by(slug=slug).first() is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug

def get_account_by_slug(slug):
    with authdb.session_scope() as s:
        a = s.query(Account).filter_by(slug=slug).first()
        if a:
            s.expunge(a)
        return a
```
In `create_account`, after validating name, set `slug = _unique_slug(s, slugify(name))` inside the session and store it on the `Account`. In `get_account`/`list_accounts`, include `slug` (list dict gains `"slug": a.slug`).

- [ ] **Step 5: Run test, verify it passes**
Run: `cd backend && uv run pytest tests/test_accounts.py -v`
Expected: PASS.

- [ ] **Step 6: Run full suite, then commit**
Run: `cd backend && uv run pytest tests/ -q` (let it finish; migrate any account test asserting the old dict shape to include `slug`).
```bash
git add backend/app/auth/models.py backend/app/accounts/service.py backend/tests/test_accounts.py
git commit -m "feat(branding): add unique Account.slug + slug generation"
```

---

### Task 2: slug in accounts API + rename route + `/me` account_slug

**Files:** Modify `backend/app/accounts/routes.py`, `backend/app/auth/routes.py`; Test `backend/tests/test_accounts.py`, `tests/test_auth_routes.py`.

**Interfaces:**
- Consumes: `acct.get_account`, `acct.slugify`, `Account.slug`.
- Produces: `GET /api/superadmin/accounts` items include `slug`; `POST /api/superadmin/accounts/<id>/slug {slug}` (superadmin rename, validates URL-safe + unique → 400 on bad/dupe). `/api/auth/me` user dict gains `account_slug`.

- [ ] **Step 1: Write failing test** (append to `test_accounts.py`) — using the existing `su_client` fixture:
```python
def test_superadmin_rename_slug(su_client):
    aid = su_client.post("/api/superadmin/accounts", json={"name": "Acme"}).get_json()["account"]["id"]
    r = su_client.post(f"/api/superadmin/accounts/{aid}/slug", json={"slug": "acme-eu"})
    assert r.status_code == 200
    listed = su_client.get("/api/superadmin/accounts").get_json()["accounts"]
    assert any(a["id"] == aid and a["slug"] == "acme-eu" for a in listed)
    assert su_client.post(f"/api/superadmin/accounts/{aid}/slug", json={"slug": "Bad Slug!"}).status_code == 400
```

- [ ] **Step 2: Run, verify fail.** `cd backend && uv run pytest tests/test_accounts.py::test_superadmin_rename_slug -v` → FAIL.

- [ ] **Step 3: Implement**
- In `accounts/routes.py`: ensure `list_accounts` returns `slug` (already from `acct.list_accounts()` after Task 1). Add a `set_account_slug(account_id, slug)` to `accounts/service.py` (validate `re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)` else ValueError; ensure unique else ValueError) and the route:
```python
@superadmin_bp.route("/accounts/<account_id>/slug", methods=["POST"])
@superadmin_required
def set_slug(account_id):
    slug = (request.get_json(silent=True) or {}).get("slug", "")
    try:
        acct.set_account_slug(account_id, slug)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})
```
- In `auth/routes.py` `_user_dict`: add `account_slug` (look up via `get_account(user.account_id).slug` when account_id set, else None) — reuse the existing lazy `get_account` import already there.

- [ ] **Step 4: Add a `/me` test** (append to `test_auth_routes.py`): a member's `/me` returns `account_slug` matching their account's slug.

- [ ] **Step 5: Full suite + commit**
Run: `cd backend && uv run pytest tests/ -q`
```bash
git add backend/app/accounts/routes.py backend/app/accounts/service.py backend/app/auth/routes.py backend/tests/test_accounts.py backend/tests/test_auth_routes.py
git commit -m "feat(branding): expose account slug in API + rename route + /me account_slug"
```

---

# PHASE 2 — Branding: per-account model + service

### Task 3: `Branding` keyed by account_id (+ default) and singleton→default conversion

**Files:** Modify `backend/app/auth/models.py`; Test `backend/tests/test_branding.py`.

**Interfaces:**
- Produces: `Branding.account_id` (str, FK→accounts.id, nullable, unique — one row per account; NULL row = global default). The fixed `id="singleton"` is no longer used as the lookup key (rows are found by `account_id`). Keep `id` as the PK (UUID per row).

- [ ] **Step 1: Write failing test**
```python
from datetime import datetime
from app.auth import db as authdb
from app.auth.models import Branding


def test_branding_rows_keyed_by_account(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    with authdb.session_scope() as s:
        s.add(Branding(id="b-default", account_id=None, primary_color="#000000", updated_at=datetime.utcnow()))
        s.add(Branding(id="b-acc", account_id="accA", primary_color="#ff0000", updated_at=datetime.utcnow()))
    with authdb.session_scope() as s:
        assert s.query(Branding).filter_by(account_id=None).one().primary_color == "#000000"
        assert s.query(Branding).filter_by(account_id="accA").one().primary_color == "#ff0000"
```

- [ ] **Step 2: Run, verify fail.** `cd backend && uv run pytest tests/test_branding.py::test_branding_rows_keyed_by_account -v` → FAIL (no `account_id` column).

- [ ] **Step 3: Edit `Branding` in `models.py`** — keep `id` (String PK, now a UUID per row) and add `account_id = Column(String, ForeignKey("accounts.id"), nullable=True, unique=True, index=True)`.

- [ ] **Step 4: Run, verify pass.** `cd backend && uv run pytest tests/test_branding.py::test_branding_rows_keyed_by_account -v` → PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/app/auth/models.py backend/tests/test_branding.py
git commit -m "feat(branding): key Branding rows by account_id (NULL = global default)"
```

---

### Task 4: branding service rewrite (per-account + resolve + slug)

**Files:** Modify `backend/app/branding/service.py`; Test `backend/tests/test_branding.py`.

**Interfaces:**
- Consumes: `Branding`, `accounts.service.get_account_by_slug`.
- Produces (all account-scoped; `account_id=None` means the global default row):
  - `get_branding(account_id=None) -> dict` (that row's raw `{primary_color, accent_color, logo_filename, favicon_filename}` or Nones)
  - `resolve_branding(account_id=None) -> dict` — each field = account row value else default row value else None
  - `resolve_account_id_for_slug(slug) -> str|None` (via `get_account_by_slug`; None when slug missing/unknown)
  - `update_colors(account_id, primary_color, accent_color, updated_by)` (upsert that account's row; account_id None = default)
  - `save_asset(account_id, kind, file_storage, updated_by) -> str` (store under `uploads/branding/<account_id or 'default'>/<kind><ext>`)
  - `asset_path(account_id, kind) -> str|None` (that account's asset, NO fallback — the resolve layer handles fallback)

- [ ] **Step 1: Write failing test**
```python
from app.auth import db as authdb
from app.branding import service as br


def test_resolve_falls_back_to_default(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    br.update_colors(None, "#111111", "#222222", "su")          # global default
    br.update_colors("accA", "#ff0000", None, "admin")           # account overrides primary only
    res = br.resolve_branding("accA")
    assert res["primary_color"] == "#ff0000"   # account wins
    assert res["accent_color"] == "#222222"    # falls back to default
    res_default = br.resolve_branding(None)
    assert res_default["primary_color"] == "#111111"
    res_unknown = br.resolve_branding("nope")  # no row → all from default
    assert res_unknown["accent_color"] == "#222222"
```

- [ ] **Step 2: Run, verify fail.** `cd backend && uv run pytest tests/test_branding.py::test_resolve_falls_back_to_default -v` → FAIL.

- [ ] **Step 3: Rewrite `service.py`** — replace the singleton logic. Core:
```python
import os, uuid, re
from datetime import datetime
from ..auth import db as authdb
from ..auth.models import Branding

BRANDING_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "branding")
_ALLOWED_EXT = {"png", "jpg", "jpeg", "svg", "ico", "webp"}
_FIELDS = ("primary_color", "accent_color", "logo_filename", "favicon_filename")

def _dir_for(account_id):
    sub = account_id or "default"
    d = os.path.join(BRANDING_DIR, sub)
    os.makedirs(d, exist_ok=True)
    return d

def _row(session, account_id):
    return session.query(Branding).filter_by(account_id=account_id).first()

def get_branding(account_id=None):
    with authdb.session_scope() as s:
        r = _row(s, account_id)
        return {f: getattr(r, f) if r else None for f in _FIELDS}

def resolve_branding(account_id=None):
    with authdb.session_scope() as s:
        acc = _row(s, account_id) if account_id is not None else None
        default = _row(s, None)
        def pick(f):
            if acc is not None and getattr(acc, f) is not None:
                return getattr(acc, f)
            return getattr(default, f) if default is not None else None
        return {f: pick(f) for f in _FIELDS}

def resolve_account_id_for_slug(slug):
    if not slug:
        return None
    from ..accounts.service import get_account_by_slug
    a = get_account_by_slug(slug)
    return a.id if a else None

def _validate_color(value, name):
    if value in (None, ""):
        return
    if not re.fullmatch(r"#[0-9a-fA-F]{3,8}", value):
        raise ValueError(f"invalid {name}")

def update_colors(account_id, primary_color, accent_color, updated_by):
    _validate_color(primary_color, "primary_color")
    _validate_color(accent_color, "accent_color")
    with authdb.session_scope() as s:
        r = _row(s, account_id)
        if r is None:
            r = Branding(id=str(uuid.uuid4()), account_id=account_id)
            s.add(r)
        if primary_color is not None:
            r.primary_color = primary_color
        if accent_color is not None:
            r.accent_color = accent_color
        r.updated_at = datetime.utcnow()
        r.updated_by = updated_by

def save_asset(account_id, kind, file_storage, updated_by):
    if kind not in ("logo", "favicon"):
        raise ValueError("bad kind")
    ext = (file_storage.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXT:
        raise ValueError("unsupported file type")
    fname = f"{kind}.{ext}"
    file_storage.save(os.path.join(_dir_for(account_id), fname))
    with authdb.session_scope() as s:
        r = _row(s, account_id)
        if r is None:
            r = Branding(id=str(uuid.uuid4()), account_id=account_id)
            s.add(r)
        setattr(r, f"{kind}_filename", fname)
        r.updated_at = datetime.utcnow()
        r.updated_by = updated_by
    return fname

def asset_path(account_id, kind):
    with authdb.session_scope() as s:
        r = _row(s, account_id)
        fname = getattr(r, f"{kind}_filename", None) if r else None
    if not fname:
        return None
    p = os.path.join(_dir_for(account_id), fname)
    return p if os.path.exists(p) else None
```

- [ ] **Step 4: Run, verify pass.** `cd backend && uv run pytest tests/test_branding.py::test_resolve_falls_back_to_default -v` → PASS.

- [ ] **Step 5: Full suite + commit.** Run `cd backend && uv run pytest tests/ -q` (migrate existing branding service tests to the new account-scoped signatures).
```bash
git add backend/app/branding/service.py backend/tests/test_branding.py
git commit -m "feat(branding): per-account branding service with default fallback + slug resolve"
```

---

# PHASE 3 — Public read API with `?account=<slug>`

### Task 5: public config/logo/favicon take `?account=<slug>`

**Files:** Modify `backend/app/branding/routes.py`; Test `backend/tests/test_branding.py`.

**Interfaces:**
- Consumes: `service.resolve_branding`, `service.resolve_account_id_for_slug`, `service.asset_path`.
- Produces: `GET /api/branding/config?account=<slug>` → `{success, data:{primary_color, accent_color, logo_url, favicon_url}}` where urls = `/api/branding/logo?account=<slug>` (only when the resolved asset exists). `GET /api/branding/logo?account=<slug>` / `…/favicon?account=<slug>` serve the resolved asset (account's, else default's, else 404). No slug → global default.

- [ ] **Step 1: Write failing test** (build a Flask app with `branding_bp` + `register_auth`, no login — proves public):
```python
def test_public_config_by_slug_no_auth(tmp_path, monkeypatch):
    from flask import Flask
    from app.auth import db as authdb
    from app.accounts import service as acct
    from app.branding import service as br
    from app.branding.routes import branding_bp
    from app.security import register_auth
    from app.config import Config
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    aid = acct.create_account("Acme", "su"); slug = acct.get_account(aid).slug
    br.update_colors(None, "#111111", "#222222", "su")
    br.update_colors(aid, "#ff0000", None, "admin")
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(branding_bp); register_auth(app)
    c = app.test_client()
    r = c.get(f"/api/branding/config?account={slug}")     # no login
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert d["primary_color"] == "#ff0000" and d["accent_color"] == "#222222"
    assert c.get("/api/branding/config").get_json()["data"]["primary_color"] == "#111111"
```

- [ ] **Step 2: Run, verify fail.** `cd backend && uv run pytest tests/test_branding.py::test_public_config_by_slug_no_auth -v` → FAIL.

- [ ] **Step 3: Edit `routes.py`**
```python
from flask import Blueprint, jsonify, send_file, request
from . import service

@branding_bp.route("/config", methods=["GET"])
def get_config():
    slug = request.args.get("account")
    account_id = service.resolve_account_id_for_slug(slug)
    res = service.resolve_branding(account_id)
    q = f"?account={slug}" if slug else ""
    return jsonify({"success": True, "data": {
        "primary_color": res["primary_color"],
        "accent_color": res["accent_color"],
        "logo_url": f"/api/branding/logo{q}" if res["logo_filename"] else None,
        "favicon_url": f"/api/branding/favicon{q}" if res["favicon_filename"] else None,
    }})

def _serve(kind):
    slug = request.args.get("account")
    account_id = service.resolve_account_id_for_slug(slug)
    # try account asset, then default
    path = service.asset_path(account_id, kind) if account_id else None
    if path is None:
        path = service.asset_path(None, kind)
    if path is None:
        return jsonify({"success": False, "error": "not found"}), 404
    return send_file(path)

@branding_bp.route("/logo", methods=["GET"])
def get_logo():
    return _serve("logo")

@branding_bp.route("/favicon", methods=["GET"])
def get_favicon():
    return _serve("favicon")
```
(Note: `logo_url` should be non-null when EITHER the account or the default has a logo — adjust `res["logo_filename"]` to reflect the resolved value, which `resolve_branding` already merges, so it's the account's-or-default's filename. Good.)

- [ ] **Step 4: Run, verify pass.** `cd backend && uv run pytest tests/test_branding.py -v` → PASS.

- [ ] **Step 5: Full suite + commit.**
```bash
git add backend/app/branding/routes.py backend/tests/test_branding.py
git commit -m "feat(branding): public branding read by ?account=<slug> with default fallback"
```

---

# PHASE 4 — Write APIs (account-admin + superadmin + default)

### Task 6: account-admin branding API

**Files:** Create `backend/app/branding/account_routes.py`; Modify `backend/app/__init__.py`; Test `backend/tests/test_branding.py`.

**Interfaces:**
- Consumes: `@account_admin_required`, `current_account_id`, `service.update_colors/save_asset`.
- Produces: blueprint `branding_account_bp` (url_prefix `/api/account/branding`): `POST ""` `{primary_color, accent_color}`; `POST /logo`; `POST /favicon`. Each requires non-null `current_account_id()` → 400 otherwise; writes to that account.

- [ ] **Step 1: Write failing test** (account_admin edits own account; a superadmin (None account) gets 400):
```python
def test_account_admin_edits_own_branding(tmp_path, monkeypatch):
    from flask import Flask
    from app.auth import db as authdb, service as us
    from app.accounts import service as acct
    from app.branding import service as br
    from app.auth.routes import auth_bp
    from app.branding.account_routes import branding_account_bp
    from app.security import register_auth
    from app.config import Config
    from app.auth.models import ROLE_ACCOUNT_ADMIN
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    aid = acct.create_account("Acme", "su")
    us.create_user("adm@x.de", "pw12345", role=ROLE_ACCOUNT_ADMIN, account_id=aid)
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(branding_account_bp); register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "adm@x.de", "password": "pw12345"})
    assert c.post("/api/account/branding", json={"primary_color": "#abcdef"}).status_code == 200
    assert br.get_branding(aid)["primary_color"] == "#abcdef"
```

- [ ] **Step 2: Run, verify fail.** `cd backend && uv run pytest tests/test_branding.py::test_account_admin_edits_own_branding -v` → FAIL.

- [ ] **Step 3: Create `account_routes.py`**
```python
from flask import Blueprint, jsonify, request, g
from . import service
from ..auth.decorators import account_admin_required
from ..auth.accounts import current_account_id

branding_account_bp = Blueprint("branding_account", __name__, url_prefix="/api/account/branding")

def _acc_or_400():
    aid = current_account_id()
    return aid

@branding_account_bp.route("", methods=["POST"])
@account_admin_required
def update_colors():
    aid = current_account_id()
    if aid is None:
        return jsonify({"success": False, "error": "no account context"}), 400
    d = request.get_json(silent=True) or {}
    try:
        service.update_colors(aid, d.get("primary_color"), d.get("accent_color"), g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})

@branding_account_bp.route("/logo", methods=["POST"])
@account_admin_required
def upload_logo():
    aid = current_account_id()
    if aid is None:
        return jsonify({"success": False, "error": "no account context"}), 400
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "error": "no file"}), 400
    try:
        service.save_asset(aid, "logo", f, g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "logo_url": f"/api/branding/logo"})

@branding_account_bp.route("/favicon", methods=["POST"])
@account_admin_required
def upload_favicon():
    aid = current_account_id()
    if aid is None:
        return jsonify({"success": False, "error": "no account context"}), 400
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "error": "no file"}), 400
    try:
        service.save_asset(aid, "favicon", f, g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "favicon_url": f"/api/branding/favicon"})
```

- [ ] **Step 4: Register** in `__init__.py`: `from .branding.account_routes import branding_account_bp` + `app.register_blueprint(branding_account_bp)`.

- [ ] **Step 5: Full suite + commit.**
```bash
git add backend/app/branding/account_routes.py backend/app/__init__.py backend/tests/test_branding.py
git commit -m "feat(branding): account-admin branding API (own account)"
```

---

### Task 7: superadmin per-account branding + repoint default routes

**Files:** Modify `backend/app/accounts/routes.py` (per-account branding), `backend/app/branding/admin_routes.py` (→ global default); Test `backend/tests/test_branding.py`.

**Interfaces:**
- Produces: `POST /api/superadmin/accounts/<id>/branding` `{primary_color, accent_color}`, `POST …/branding/logo`, `POST …/branding/favicon` (`@superadmin_required`, write that account's branding). The existing `/api/admin/branding*` now writes the **global default** (`update_colors(None, …)` / `save_asset(None, …)`).

- [ ] **Step 1: Write failing test** (superadmin edits account A's branding and the global default):
```python
def test_superadmin_edits_account_and_default(su_client):
    aid = su_client.post("/api/superadmin/accounts", json={"name": "Acme"}).get_json()["account"]["id"]
    assert su_client.post(f"/api/superadmin/accounts/{aid}/branding", json={"primary_color": "#0a0a0a"}).status_code == 200
    assert su_client.post("/api/admin/branding", json={"primary_color": "#ffffff"}).status_code == 200
    from app.branding import service as br
    assert br.get_branding(aid)["primary_color"] == "#0a0a0a"
    assert br.get_branding(None)["primary_color"] == "#ffffff"
```
(Reuse `su_client` from `test_accounts.py`; if it isn't importable, build an equivalent superadmin fixture in `test_branding.py` registering `auth_bp`, `superadmin_bp`, `branding_admin_bp`, and the new routes.)

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement**
- In `accounts/routes.py` add three routes (`@superadmin_required`): each loads `acct.get_account(account_id)` → 404 if missing, then calls `service.update_colors(account_id, …, g.current_user.id)` / `service.save_asset(account_id, kind, request.files["file"], g.current_user.id)`.
- In `branding/admin_routes.py`: change the three handlers to operate on the **default** row — call `service.update_colors(None, …)` and `service.save_asset(None, kind, …)` (account_id None). Keep `@superadmin_required`.

- [ ] **Step 4: Full suite + commit.** (Migrate existing `test_branding.py` superadmin-write tests: they now write the default row — assert via `get_branding(None)`.)
```bash
git add backend/app/accounts/routes.py backend/app/branding/admin_routes.py backend/tests/test_branding.py
git commit -m "feat(branding): superadmin per-account branding + default-row admin routes"
```

---

# PHASE 5 — Frontend: slug-aware store + account-scoped Appearance

### Task 8: branding store reads `?account=<slug>` (pre-login) + re-resolves post-login

**Files:** Modify `frontend/src/stores/branding.js`, `frontend/src/stores/auth.js` (expose `accountSlug`).

- [ ] **Step 1:** In `auth.js` add `accountSlug: computed(() => state.user?.account_slug ?? null)`.
- [ ] **Step 2:** In `branding.js` `applyBranding(slug)`: accept an optional `slug`; if not passed, read it from the URL (`new URLSearchParams(window.location.search).get('account')`). Call `api.get('/api/branding/config' + (slug ? ('?account=' + encodeURIComponent(slug)) : ''))`, read `res.data`, set `--brand-primary`/`--brand-accent`, and set the favicon link href to `res.data.favicon_url` (already carries `?account=`). Expose `logoUrl` = `res.data.logo_url`.
- [ ] **Step 3:** Startup (in `main.js` or the existing bootstrap) calls `applyBranding()` (URL slug, pre-login). After a successful login / `fetchMe`, call `applyBranding(auth.accountSlug.value)` to switch to the user's account branding. (Wire this in the auth store's `login`/`fetchMe` or the router guard, after `state.user` is set.)
- [ ] **Step 4:** `cd frontend && npm run build` → 0 errors.
- [ ] **Step 5: Commit** `feat(branding): slug-aware branding load (pre-login URL + post-login account)`.

---

### Task 9: account-scoped Appearance page + me-menu

**Files:** Modify `frontend/src/views/BrandingSettings.vue`, `frontend/src/components/UserMenu.vue`.

- [ ] **Step 1:** `BrandingSettings.vue`: when used by an **account_admin**, post to `/api/account/branding` (+ `/logo`, `/favicon`); load current values from `/api/branding/config?account=<own slug>` (use `auth.accountSlug`). When used by a **superadmin** (global default), post to `/api/admin/branding*` and load from `/api/branding/config` (no slug = default). Decide which mode by `auth.isSuperadmin`/`isAccountAdmin`. After save, call `useBranding().applyBranding(auth.accountSlug.value)` (account_admin) or `applyBranding()` (superadmin default).
- [ ] **Step 2:** `UserMenu.vue`: add an **Appearance** entry (`$t('branding.menuTitle')`, route `/admin/branding`) for **account_admin** too (currently superadmin-only). Superadmin's Appearance entry stays (it edits the default).
- [ ] **Step 3:** `cd frontend && npm run build` → 0 errors.
- [ ] **Step 4: Commit** `feat(branding): account-scoped Appearance page + account_admin menu entry`.

---

# PHASE 6 — Superadmin Accounts oversight

### Task 10: slug column + read-only users drill-down + per-account branding entry

**Files:** Modify `frontend/src/views/SuperadminAccounts.vue` (+ router/route if a dedicated per-account branding editor view is added).

- [ ] **Step 1:** Add a **slug** column to the accounts table (`acc.slug`), with an inline rename control → `POST /api/superadmin/accounts/<id>/slug {slug}` (show error on 400), refresh after.
- [ ] **Step 2:** Add a **read-only users drill-down**: an expand control per row → `GET /api/superadmin/accounts/<id>/users` → render the users (email, name, role, active) read-only (no mutation controls). Cache per account; toggle expand.
- [ ] **Step 3:** Add a per-account **"Edit branding"** affordance: a small form/panel per row to set primary/accent (`POST /api/superadmin/accounts/<id>/branding`) and upload logo/favicon (`POST …/branding/logo`,`/favicon`). (Reuse a compact inline form; full reuse of `BrandingSettings.vue` is optional.) Show errors; no live re-apply needed (it's another account's branding).
- [ ] **Step 4:** `cd frontend && npm run build` → 0 errors.
- [ ] **Step 5: Commit** `feat(accounts): superadmin slug rename + read-only users drill-down + per-account branding`.

---

# PHASE 7 — i18n

### Task 11: DE/EN keys for the new UI

**Files:** Modify `locales/en.json`, `locales/de.json`.

- [ ] **Step 1:** Add the new keys referenced by Tasks 9–10 (grep `accounts.*` and `branding.*` usages added in those tasks to get the exact list — e.g. `accounts.slug`, `accounts.rename`, `accounts.viewUsers`, `accounts.editBranding`, `accounts.suspend`, `accounts.reactivate`, plus any new `branding.*`). Add ALL to BOTH files with German Sie-form + real umlauts.
- [ ] **Step 2:** Parity check: `cd backend && uv run python -c "import json;a=json.load(open('../locales/en.json'));b=json.load(open('../locales/de.json'));print(a.keys()==b.keys(), set(a['accounts'])==set(b['accounts']), set(a['branding'])==set(b['branding']))"` → all True.
- [ ] **Step 3:** `cd frontend && npm run build` → 0 errors.
- [ ] **Step 4: Commit** `feat(branding): DE/EN i18n for slug/branding/oversight UI`.

---

## Final Verification
- [ ] Full backend suite: `cd backend && uv run pytest tests/ -q` → green, pristine.
- [ ] Manual (Docker, fresh `auth.db`): superadmin sets a global default branding; creates account "Acme" (note its slug); sets Acme's branding (different primary). Visit `/?account=acme` logged-out → Acme branding on the login screen; visit `/` logged-out → default branding. Log in as Acme's account_admin → Appearance edits Acme only; the app shows Acme branding. Superadmin Accounts page: rename slug, expand read-only users, edit Acme branding. Suspend Acme → its users can't log in.
- [ ] Update docs: extend `docs/security.md`/`docs/README.md` with the per-account branding + slug behavior (note `?account=<slug>` pre-login branding).

## Self-Review Notes (spec coverage)
- Account.slug + generation + rename + /me slug → Tasks 1-2. ✓
- Branding per-account model + default + resolve + slug → Tasks 3-4. ✓
- Public read by ?account=slug → Task 5. ✓
- account-admin edits own (400 for no-account) + superadmin any + default → Tasks 6-7. ✓
- Frontend slug pre-login + post-login re-resolve → Task 8. ✓
- account-scoped Appearance + me-menu → Task 9. ✓
- Oversight: slug column + read-only users drill-down (+ per-account branding) → Task 10. ✓
- i18n parity → Task 11. ✓
- Field resolution account→default→fallback → Task 4 (+frontend hardcoded fallback). ✓
