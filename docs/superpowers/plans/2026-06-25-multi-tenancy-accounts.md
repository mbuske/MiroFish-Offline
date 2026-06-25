# Multi-Tenancy (Accounts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Account (tenant) layer with three roles (superadmin / account_admin / user) and account-wide-shared resource isolation, replacing the prior per-user ownership model.

**Architecture:** Accounts live in the existing auth SQLite DB; every user has an `account_id` (null only for superadmin). Resources gain `account_id` (access dimension) and keep `owner_id` as a created-by audit field. Access is account-scoped: `superadmin OR resource.account_id == current_user.account_id`. Superadmin provisions accounts + each account's admin; account_admin manages users within their account. Fresh start — no data migration; `auth.db` is wiped once.

**Tech Stack:** Flask 3, Flask-SQLAlchemy, SQLite, bcrypt, Vue 3 + vue-i18n, axios.

## Global Constraints

- Python `>=3.11,<3.13`; no new dependencies.
- Backend tests run from `backend/`: `cd backend && uv run pytest tests/` (must stay green + pristine).
- Roles: `ROLE_SUPERADMIN = "superadmin"`, `ROLE_ACCOUNT_ADMIN = "account_admin"`, `ROLE_USER = "user"`. The old `ROLE_ADMIN = "admin"` is REMOVED (fresh start).
- Resource access rule (everywhere): `superadmin OR resource.account_id == current_user.account_id`; foreign/other-account access returns **404** (hide existence). List endpoints filter to the caller's account unless superadmin (sees all). Same 404 shape for missing and forbidden.
- A user/account_admin with `account_id is None` cannot create resources; superadmin (account_id None) administers only and does not create resources.
- Frontend: axios instance returns the UNWRAPPED payload (don't destructure `.data` off the promise); FormData uploads omit the JSON content-type (already handled). Locale files `locales/en.json`+`locales/de.json` stay at key parity (German Sie-form, real umlauts).
- TDD for backend; frontend verified by `cd frontend && npm run build` (no JS test runner).
- One account per user. Branding stays superadmin-only.

---

## File Structure

**Backend — create:**
- `backend/app/auth/accounts.py` — account-scope helpers (`current_account_id`, `is_superadmin`, `is_account_admin`, `can_access_account`, `require_account_access`)
- `backend/app/accounts/__init__.py`, `backend/app/accounts/service.py` — account CRUD service
- `backend/app/accounts/routes.py` — `/api/superadmin/*` blueprint
- tests: `backend/tests/test_accounts.py`, extend `test_rbac.py`, `test_admin_users.py`, `test_ownership.py`, `test_seed.py`

**Backend — modify:**
- `backend/app/auth/models.py` — `Account` model, role constants, `User.account_id`
- `backend/app/auth/decorators.py` — `superadmin_required`, `account_admin_required` (replace `admin_required`)
- `backend/app/auth/ownership.py` — account-scoped helpers (keep file; add account funcs; remove owner-based ones once call sites move)
- `backend/app/auth/service.py` — `create_user(..., account_id)`, `list_users(account_id=None)`, role validation for the new roles
- `backend/app/auth/seed.py` — seed superadmin
- `backend/app/auth/routes.py` — `/api/auth/me` returns `account_id`+`account_name`
- `backend/app/auth/admin_routes.py` — account-scope the `/api/admin/users*` endpoints
- `backend/app/auth/graph_access.py` — account-based graph access
- `backend/app/__init__.py` — register `superadmin` blueprint
- `backend/app/models/project.py`, `backend/app/services/simulation_manager.py`, `backend/app/services/report_agent.py`, `backend/app/storage/neo4j_storage.py` — add `account_id`
- `backend/app/api/graph.py`, `backend/app/api/simulation.py`, `backend/app/api/report.py` — switch access checks + list filters to account scope

**Frontend — create:** `frontend/src/views/SuperadminAccounts.vue`; **modify:** `UserMenu.vue`, `router/index.js`, `stores/auth.js` (expose account), header account name, `locales/*.json`.

---

# PHASE 1 — Roles, Account model, helpers, decorators

### Task 1: Role constants + Account model + users.account_id

**Files:**
- Modify: `backend/app/auth/models.py`
- Test: `backend/tests/test_accounts.py`

**Interfaces:**
- Produces: `ROLE_SUPERADMIN="superadmin"`, `ROLE_ACCOUNT_ADMIN="account_admin"`, `ROLE_USER="user"`; `Account(id, name, is_active, created_at, created_by)`; `User.account_id` (nullable str).

- [ ] **Step 1: Write failing test** in `backend/tests/test_accounts.py`

```python
from datetime import datetime
from app.auth import db as authdb
from app.auth.models import Account, User, ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER


def test_account_and_user_account_id_persist(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    with authdb.session_scope() as s:
        s.add(Account(id="acc1", name="Acme", is_active=True, created_at=datetime.utcnow(), created_by="su1"))
        s.flush()
        s.add(User(id="u1", email="a@b.de", password_hash="x", role=ROLE_USER, is_active=True,
                   account_id="acc1", created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
    with authdb.session_scope() as s:
        assert s.query(Account).one().name == "Acme"
        assert s.query(User).filter_by(email="a@b.de").one().account_id == "acc1"
    assert (ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER) == ("superadmin", "account_admin", "user")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_accounts.py::test_account_and_user_account_id_persist -v`
Expected: FAIL (`cannot import name 'Account'` / `ROLE_SUPERADMIN`).

- [ ] **Step 3: Edit `backend/app/auth/models.py`**
  - Replace role constants:
    ```python
    ROLE_SUPERADMIN = "superadmin"
    ROLE_ACCOUNT_ADMIN = "account_admin"
    ROLE_USER = "user"
    ```
    (Remove `ROLE_ADMIN`.)
  - Add to `User`: `account_id = Column(String, ForeignKey("accounts.id"), nullable=True, index=True)`.
  - Add the model:
    ```python
    class Account(Base):
        __tablename__ = "accounts"
        id = Column(String, primary_key=True)
        name = Column(String, nullable=False)
        is_active = Column(Boolean, nullable=False, default=True)
        created_at = Column(DateTime, nullable=False)
        created_by = Column(String, nullable=True)
    ```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_accounts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/models.py backend/tests/test_accounts.py
git commit -m "feat(accounts): add Account model, account_id, three-tier role constants"
```

---

### Task 2: Account-scope helpers

**Files:**
- Create: `backend/app/auth/accounts.py`
- Test: `backend/tests/test_ownership.py` (append)

**Interfaces:**
- Consumes: `g.current_user` (has `.role`, `.account_id`).
- Produces: `is_superadmin() -> bool`; `is_account_admin() -> bool`; `current_account_id() -> str|None`; `can_access_account(account_id) -> bool` (True if superadmin, or `account_id is not None and current_user.account_id == account_id`); `require_account_access(account_id)` (raises `PermissionError` if not allowed).

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_ownership.py`)

```python
def test_account_access_helpers():
    from flask import Flask, g
    from app.auth import accounts
    from app.auth.models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER
    import pytest

    class _U:
        def __init__(self, role, account_id):
            self.role, self.account_id = role, account_id

    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = _U(ROLE_USER, "accA")
        assert accounts.can_access_account("accA") is True
        assert accounts.can_access_account("accB") is False
        assert accounts.can_access_account(None) is False
        with pytest.raises(PermissionError):
            accounts.require_account_access("accB")
    with app.test_request_context():
        g.current_user = _U(ROLE_SUPERADMIN, None)
        assert accounts.can_access_account("accB") is True
        assert accounts.is_superadmin() is True
    with app.test_request_context():
        g.current_user = None
        assert accounts.can_access_account("accA") is False
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_account_access_helpers -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.accounts`).

- [ ] **Step 3: Create `backend/app/auth/accounts.py`**

```python
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
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_ownership.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/accounts.py backend/tests/test_ownership.py
git commit -m "feat(accounts): add account-scope access helpers"
```

---

### Task 3: Role decorators (superadmin_required, account_admin_required)

**Files:**
- Modify: `backend/app/auth/decorators.py`
- Test: `backend/tests/test_rbac.py` (append)

**Interfaces:**
- Produces: `login_required` (unchanged), `superadmin_required` (401 no user / 403 not superadmin), `account_admin_required` (401 no user / 403 if role is `user`; allows `account_admin` and `superadmin`). `admin_required` is REMOVED — callers move to `account_admin_required`.

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_rbac.py`)

```python
def test_role_decorators(tmp_path, monkeypatch):
    from flask import Flask, g, jsonify
    from app.auth.decorators import superadmin_required, account_admin_required
    from app.auth.models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER

    class _U:
        def __init__(self, role):
            self.role = role

    app = Flask(__name__)

    @app.route("/su")
    @superadmin_required
    def su():
        return jsonify(ok=True)

    @app.route("/aa")
    @account_admin_required
    def aa():
        return jsonify(ok=True)

    def call(path, user):
        with app.test_request_context(path):
            g.current_user = user
            return app.view_functions[{"/su": "su", "/aa": "aa"}[path]]()

    # superadmin route
    with app.test_request_context("/su"):
        g.current_user = _U(ROLE_ACCOUNT_ADMIN)
        from app.auth.decorators import superadmin_required as _s  # ensure import
    c = app.test_client()
    # use real dispatch for status codes:
    @app.before_request
    def _noop():
        return None

    # account_admin route: user forbidden, account_admin ok
    with app.test_request_context("/aa"):
        g.current_user = _U(ROLE_USER)
        resp = aa()
        assert resp[1] == 403
    with app.test_request_context("/aa"):
        g.current_user = _U(ROLE_ACCOUNT_ADMIN)
        assert aa().json["ok"] is True
    # superadmin route: account_admin forbidden, superadmin ok
    with app.test_request_context("/su"):
        g.current_user = _U(ROLE_ACCOUNT_ADMIN)
        resp = su()
        assert resp[1] == 403
    with app.test_request_context("/su"):
        g.current_user = _U(ROLE_SUPERADMIN)
        assert su().json["ok"] is True
```

(If the decorator returns a `(json, status)` tuple, `resp[1]` is the status. Adapt assertions to the actual return form — the contract is 403 for the disallowed role and the view result for allowed.)

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_rbac.py::test_role_decorators -v`
Expected: FAIL (`cannot import name 'superadmin_required'`).

- [ ] **Step 3: Replace `backend/app/auth/decorators.py`**

```python
"""Authorization decorators."""
from functools import wraps
from flask import g, jsonify
from .models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def superadmin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if user.role != ROLE_SUPERADMIN:
            return jsonify({"success": False, "error": "Forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


def account_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if user.role not in (ROLE_ACCOUNT_ADMIN, ROLE_SUPERADMIN):
            return jsonify({"success": False, "error": "Forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_rbac.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/decorators.py backend/tests/test_rbac.py
git commit -m "feat(accounts): superadmin_required + account_admin_required decorators"
```

---

# PHASE 2 — Account service + user-service changes

### Task 4: Account service (create / list / set_active / counts)

**Files:**
- Create: `backend/app/accounts/__init__.py`, `backend/app/accounts/service.py`
- Test: `backend/tests/test_accounts.py` (append)

**Interfaces:**
- Consumes: `app.auth.db.session_scope`, models `Account`, `User`; `app.auth.service.revoke_user_sessions`.
- Produces:
  - `create_account(name, created_by) -> str` (raises ValueError on empty name)
  - `list_accounts() -> list[dict]` each `{id, name, is_active, created_at, user_count}`
  - `get_account(account_id) -> Account | None`
  - `set_account_active(account_id, active)` (on disable, revokes sessions of all the account's users)

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_accounts.py`)

```python
from app.accounts import service as acct_service
from app.auth import service as user_service


def test_account_service_crud_and_disable_revokes(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    aid = acct_service.create_account("Acme", created_by="su1")
    assert isinstance(aid, str)
    # a member with a live session
    uid = user_service.create_user("m@acme.de", "pw12345", role=ROLE_USER, account_id=aid)
    token = user_service.start_session(uid)
    listed = acct_service.list_accounts()
    row = [a for a in listed if a["id"] == aid][0]
    assert row["name"] == "Acme" and row["user_count"] == 1
    acct_service.set_account_active(aid, False)
    assert user_service.resolve_session(token) is None  # member session revoked
```

(This test relies on Task 5's `create_user(..., account_id=...)`; if running strictly in order, implement Task 5's signature first or accept that this test is added after Task 5. Order: do Task 5 service signature, then this. The brief's interface block names the exact signature.)

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_accounts.py::test_account_service_crud_and_disable_revokes -v`
Expected: FAIL (`ModuleNotFoundError: app.accounts.service`).

- [ ] **Step 3: Create `backend/app/accounts/__init__.py`** (empty package marker) and `backend/app/accounts/service.py`

```python
"""Account (tenant) management service."""
import uuid
from datetime import datetime

from ..auth import db as authdb
from ..auth.models import Account, User
from ..auth import service as user_service


def create_account(name, created_by=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("account name required")
    aid = str(uuid.uuid4())
    with authdb.session_scope() as s:
        s.add(Account(id=aid, name=name, is_active=True,
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
            out.append({"id": a.id, "name": a.name, "is_active": a.is_active,
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
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_accounts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/accounts/ backend/tests/test_accounts.py
git commit -m "feat(accounts): account service (create/list/get/set_active)"
```

---

### Task 5: User service — account_id + account-filtered listing + role validation

**Files:**
- Modify: `backend/app/auth/service.py`
- Test: `backend/tests/test_auth_service.py` (append)

**Interfaces:**
- Produces:
  - `create_user(email, password, name=None, role=ROLE_USER, account_id=None, created_by=None) -> str` (validates role in the three new roles; keeps email/password validation)
  - `list_users(account_id=None) -> list[User]` (when `account_id` is given, filter to it; else all)
  - `count_account_admins(account_id) -> int` (active account_admins in an account; used by seeding/guards if needed)
  - `set_role` accepts the new roles.

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_auth_service.py`)

```python
import pytest
from app.auth import db as authdb, service
from app.auth.models import ROLE_ACCOUNT_ADMIN, ROLE_USER, ROLE_SUPERADMIN


def test_create_user_with_account_and_list_filter(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    service.create_user("a@x.de", "pw12345", role=ROLE_USER, account_id="accA")
    service.create_user("b@x.de", "pw12345", role=ROLE_ACCOUNT_ADMIN, account_id="accA")
    service.create_user("c@x.de", "pw12345", role=ROLE_USER, account_id="accB")
    assert {u.email for u in service.list_users(account_id="accA")} == {"a@x.de", "b@x.de"}
    assert len(service.list_users()) == 3
    with pytest.raises(ValueError):
        service.create_user("d@x.de", "pw12345", role="root", account_id="accA")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_service.py::test_create_user_with_account_and_list_filter -v`
Expected: FAIL (`create_user() got unexpected keyword 'account_id'` or role accepted).

- [ ] **Step 3: Edit `backend/app/auth/service.py`**
  - Update the roles import to the three new constants.
  - `create_user` signature → `(email, password, name=None, role=ROLE_USER, account_id=None, created_by=None)`; validate `role in (ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER)` (raise ValueError otherwise); set `account_id=account_id` on the `User`.
  - `list_users(account_id=None)`: if `account_id is not None`, `query(User).filter_by(account_id=account_id)`, else all; keep `expunge`.
  - `set_role(user_id, role)`: validate against the three roles.
  - Replace any remaining `ROLE_ADMIN` references with the new roles; `count_admins()` (used by seed) → rename/repurpose to `count_superadmins()` returning active superadmins.

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_auth_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/service.py backend/tests/test_auth_service.py
git commit -m "feat(accounts): user service account_id + account-filtered listing + role validation"
```

---

# PHASE 3 — Superadmin API + seeding + /me

### Task 6: Superadmin accounts API

**Files:**
- Create: `backend/app/accounts/routes.py`
- Modify: `backend/app/__init__.py` (register blueprint)
- Test: `backend/tests/test_accounts.py` (append)

**Interfaces:**
- Consumes: `@superadmin_required`, `acct_service`, `user_service.create_user`, `user_service.list_users`.
- Produces: Blueprint `superadmin_bp` (url_prefix `/api/superadmin`):
  - `GET /accounts` → `{success, accounts:[...]}`
  - `POST /accounts` `{name}` → 201 `{success, account:{id,name}}`
  - `POST /accounts/<id>/active` `{active}` → `{success}`
  - `POST /accounts/<id>/admin` `{email, password, name}` → 201 `{success, user:{...}}` (creates role=account_admin, account_id=<id>)
  - `GET /accounts/<id>/users` → `{success, users:[...]}`

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_accounts.py`)

```python
import pytest
from flask import Flask
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.accounts.routes import superadmin_bp
from app.security import register_auth
from app.config import Config
from app.auth.models import ROLE_SUPERADMIN, ROLE_USER


@pytest.fixture
def su_client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("root@x.de", "rootpw12", role=ROLE_SUPERADMIN, account_id=None)
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(superadmin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "root@x.de", "password": "rootpw12"})
    return c


def test_superadmin_creates_account_and_admin(su_client):
    r = su_client.post("/api/superadmin/accounts", json={"name": "Acme"})
    assert r.status_code == 201
    aid = r.get_json()["account"]["id"]
    r2 = su_client.post(f"/api/superadmin/accounts/{aid}/admin",
                        json={"email": "admin@acme.de", "password": "pw123456", "name": "A"})
    assert r2.status_code == 201
    users = su_client.get(f"/api/superadmin/accounts/{aid}/users").get_json()["users"]
    assert any(u["email"] == "admin@acme.de" and u["role"] == "account_admin" for u in users)


def test_superadmin_routes_forbidden_for_non_superadmin(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("u@x.de", "pw12345", role=ROLE_USER, account_id="accA")
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(superadmin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "u@x.de", "password": "pw12345"})
    assert c.get("/api/superadmin/accounts").status_code == 403
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && uv run pytest tests/test_accounts.py -k superadmin -v`
Expected: FAIL (`ModuleNotFoundError: app.accounts.routes`).

- [ ] **Step 3: Create `backend/app/accounts/routes.py`**

```python
"""/api/superadmin/* — account provisioning (superadmin only)."""
from flask import Blueprint, jsonify, request, g

from . import service as acct_service
from ..auth import service as user_service
from ..auth.decorators import superadmin_required
from ..auth.models import ROLE_ACCOUNT_ADMIN

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/api/superadmin")


def _u(u):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "account_id": u.account_id}


@superadmin_bp.route("/accounts", methods=["GET"])
@superadmin_required
def list_accounts():
    return jsonify({"success": True, "accounts": acct_service.list_accounts()})


@superadmin_bp.route("/accounts", methods=["POST"])
@superadmin_required
def create_account():
    name = (request.get_json(silent=True) or {}).get("name")
    try:
        aid = acct_service.create_account(name, created_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "account": {"id": aid, "name": name.strip()}}), 201


@superadmin_bp.route("/accounts/<account_id>/active", methods=["POST"])
@superadmin_required
def set_active(account_id):
    active = bool((request.get_json(silent=True) or {}).get("active"))
    try:
        acct_service.set_account_active(account_id, active)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@superadmin_bp.route("/accounts/<account_id>/admin", methods=["POST"])
@superadmin_required
def create_account_admin(account_id):
    if not acct_service.get_account(account_id):
        return jsonify({"success": False, "error": "account not found"}), 404
    d = request.get_json(silent=True) or {}
    try:
        uid = user_service.create_user(d.get("email", ""), d.get("password", ""),
                                       name=d.get("name"), role=ROLE_ACCOUNT_ADMIN,
                                       account_id=account_id, created_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "user": _u(user_service.get_user(uid))}), 201


@superadmin_bp.route("/accounts/<account_id>/users", methods=["GET"])
@superadmin_required
def account_users(account_id):
    return jsonify({"success": True, "users": [_u(u) for u in user_service.list_users(account_id=account_id)]})
```

- [ ] **Step 4: Register blueprint** in `backend/app/__init__.py` (next to the auth/admin/branding registrations): `from .accounts.routes import superadmin_bp` and `app.register_blueprint(superadmin_bp)`.

- [ ] **Step 5: Run tests + full suite**

Run: `cd backend && uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/accounts/routes.py backend/app/__init__.py backend/tests/test_accounts.py
git commit -m "feat(accounts): superadmin accounts API (+ register blueprint)"
```

---

### Task 7: Seed superadmin + /api/auth/me returns account info

**Files:**
- Modify: `backend/app/auth/seed.py`, `backend/app/auth/routes.py`
- Test: `backend/tests/test_seed.py` (modify), `backend/tests/test_auth_routes.py` (append)

**Interfaces:**
- Produces: `seed_admin_from_env()` creates a **superadmin** (role=ROLE_SUPERADMIN, account_id=None) when no superadmin exists; `/api/auth/me` (and login) `user` dict gains `account_id` and `account_name`.

- [ ] **Step 1: Write failing test** in `backend/tests/test_seed.py` (replace the admin-role assertion)

```python
def test_seed_creates_superadmin(tmp_path, monkeypatch):
    from app.auth import db as authdb, service
    from app.auth.seed import seed_admin_from_env
    from app.config import Config
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "ADMIN_EMAIL", "root@x.de")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "rootpw12")
    authdb.init_db(Config.AUTH_DB_PATH)
    assert seed_admin_from_env() is not None
    u = service.get_user_by_email("root@x.de")
    assert u.role == "superadmin" and u.account_id is None
    assert seed_admin_from_env() is None  # idempotent
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && uv run pytest tests/test_seed.py -v`
Expected: FAIL (role is `admin`, not `superadmin`).

- [ ] **Step 3: Edit `seed.py`** — create with `role=ROLE_SUPERADMIN`; guard on `service.count_superadmins() > 0` (the renamed counter from Task 5). Edit `routes.py` `_user_dict(user)` to include `account_id` and `account_name` (look up the account name via `app.accounts.service.get_account(user.account_id).name` when `account_id` is set, else None).

```python
# routes.py _user_dict
def _user_dict(user):
    account_name = None
    if user.account_id:
        from ..accounts.service import get_account
        acc = get_account(user.account_id)
        account_name = acc.name if acc else None
    return {"id": user.id, "email": user.email, "name": user.name,
            "role": user.role, "account_id": user.account_id, "account_name": account_name}
```

- [ ] **Step 4: Add `/me` payload test** (append to `backend/tests/test_auth_routes.py`): log in a user with an account, assert `/api/auth/me` returns `account_id` and `account_name`. (Build the fixture creating an account via `acct_service.create_account` + a member, mirroring existing fixtures.)

- [ ] **Step 5: Run full suite, verify pass**

Run: `cd backend && uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/seed.py backend/app/auth/routes.py backend/tests/test_seed.py backend/tests/test_auth_routes.py
git commit -m "feat(accounts): seed superadmin; /me returns account_id + account_name"
```

---

# PHASE 4 — Account-scope the user-management API

### Task 8: Account-scope `/api/admin/users*`

**Files:**
- Modify: `backend/app/auth/admin_routes.py`
- Test: `backend/tests/test_admin_users.py` (modify/append)

**Interfaces:**
- Consumes: `@account_admin_required`, `current_account_id`, `is_superadmin`, `user_service`.
- Produces: the existing `/api/admin/users*` endpoints, now account-scoped:
  - `GET /users` → users of the caller's account (`list_users(account_id=current_account_id())`); a superadmin may pass `?account_id=` (or sees all if none given).
  - `POST /users` → forces `account_id=current_account_id()` (superadmin must pass `account_id` in body); role limited to `user`/`account_admin`.
  - `POST /users/<id>/role|active|reset-password` → first load target user; if not superadmin and target's `account_id != current_account_id()` → **404**; role changes limited to `user`/`account_admin`.

- [ ] **Step 1: Write failing test** (append to `backend/tests/test_admin_users.py`): an account_admin of account A creating a user gets that user in account A; listing returns only account-A users; acting on an account-B user returns 404. (Build two accounts + an account_admin in A; mirror existing fixture style.)

```python
def test_account_admin_scoped_to_own_account(tmp_path, monkeypatch):
    from flask import Flask
    from app.auth import db as authdb, service
    from app.accounts import service as acct_service
    from app.auth.routes import auth_bp
    from app.auth.admin_routes import admin_bp
    from app.security import register_auth
    from app.config import Config
    from app.auth.models import ROLE_ACCOUNT_ADMIN, ROLE_USER
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    a = acct_service.create_account("A", "su"); b = acct_service.create_account("B", "su")
    service.create_user("admA@x.de", "pw12345", role=ROLE_ACCOUNT_ADMIN, account_id=a)
    other = service.create_user("ub@x.de", "pw12345", role=ROLE_USER, account_id=b)
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(admin_bp); register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "admA@x.de", "password": "pw12345"})
    # create -> lands in account A
    assert c.post("/api/admin/users", json={"email": "new@x.de", "password": "pw12345"}).status_code == 201
    emails = [u["email"] for u in c.get("/api/admin/users").get_json()["users"]]
    assert "new@x.de" in emails and "ub@x.de" not in emails
    # acting on account-B user -> 404
    assert c.post(f"/api/admin/users/{other}/active", json={"active": False}).status_code == 404
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && uv run pytest tests/test_admin_users.py::test_account_admin_scoped_to_own_account -v`
Expected: FAIL (currently not account-scoped).

- [ ] **Step 3: Edit `admin_routes.py`**
  - Swap `@admin_required` → `@account_admin_required` on all routes.
  - `list_users`: `account_id = request.args.get("account_id") if is_superadmin() else current_account_id()`; `service.list_users(account_id=account_id)`.
  - `create_user`: `account_id = body.get("account_id") if is_superadmin() else current_account_id()`; pass to `service.create_user(..., account_id=account_id)`; reject role not in `{user, account_admin}` → 400.
  - For `<id>/role|active|reset-password`: load `target = service.get_user(user_id)`; if `target is None` → 404; `if not is_superadmin() and target.account_id != current_account_id(): return 404`; then proceed (role limited to user/account_admin).
  - Import `current_account_id, is_superadmin` from `..auth.accounts`.

- [ ] **Step 4: Run full suite**

Run: `cd backend && uv run pytest tests/ -q`
Expected: PASS (update any prior admin tests that assumed the old `admin` role/global scope to the new roles/scoping).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/admin_routes.py backend/tests/test_admin_users.py
git commit -m "feat(accounts): account-scope user-management API"
```

---

# PHASE 5 — Account-scope the resources

> Pattern for ALL resource access changes: replace the per-user check
> `require_owner_or_admin(x.owner_id)` (→ 404 on PermissionError) with the
> account check `require_account_access(x.account_id)` (→ 404 on PermissionError),
> and replace list filters `owner_id=current_user_id(), include_all=is_admin()`
> with `account_id=current_account_id(), include_all=is_superadmin()`.
> Creation stamps `account_id=current_account_id()` (keep `owner_id=current_user_id()` as audit).
> Import from `..auth.accounts` (`current_account_id`, `is_superadmin`, `require_account_access`).

### Task 9: Projects — account_id field + account-scoped access

**Files:**
- Modify: `backend/app/models/project.py`, `backend/app/api/graph.py`
- Test: `backend/tests/test_ownership.py` (append)

**Interfaces:**
- Produces: `Project.account_id` (persisted in `to_dict`/loader, default None); `ProjectManager.create_project(name, owner_id=None, account_id=None)`; `ProjectManager.list_projects(limit=50, account_id=None, include_all=False)` filters by `account_id` unless `include_all`.

- [ ] **Step 1: Write failing test** (append)

```python
def test_list_projects_filters_by_account(tmp_path, monkeypatch):
    from app.models import project as pj
    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", str(tmp_path), raising=False)
    p1 = pj.ProjectManager.create_project("P1", account_id="accA")
    pj.ProjectManager.create_project("P2", account_id="accB")
    mine = pj.ProjectManager.list_projects(account_id="accA")
    assert {p.project_id for p in mine} == {p1.project_id}
    assert len(pj.ProjectManager.list_projects(include_all=True)) >= 2
```

- [ ] **Step 2: Run, verify fail**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_list_projects_filters_by_account -v`
Expected: FAIL.

- [ ] **Step 3: Edit `project.py`** — add `account_id: Optional[str] = None` to `Project`; include in `to_dict()` and loader (`data.get("account_id")`); `create_project(name, owner_id=None, account_id=None)` sets both; `list_projects(limit=50, account_id=None, include_all=False)` → filter `p.account_id == account_id` unless `include_all`.

- [ ] **Step 4: Edit `graph.py`** — `import from ..auth.accounts import current_account_id, is_superadmin, require_account_access`. In `generate_ontology` create call: `account_id=current_account_id()` (also keep `owner_id=current_user_id()`). `list_projects` route: `account_id=current_account_id(), include_all=is_superadmin()`. In `get_project`/`delete_project`/`reset_project`/`build_graph`: replace `require_owner_or_admin(project.owner_id)` with `require_account_access(project.account_id)` → 404 on PermissionError.

- [ ] **Step 5: Run full suite**

Run: `cd backend && uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/project.py backend/app/api/graph.py backend/tests/test_ownership.py
git commit -m "feat(accounts): scope projects to account"
```

---

### Task 10: Simulations — account_id + account-scoped access

**Files:**
- Modify: `backend/app/services/simulation_manager.py`, `backend/app/api/simulation.py`
- Test: `backend/tests/test_ownership.py` (append)

**Interfaces:**
- Produces: `SimulationState.account_id` (persisted); `list_simulations(project_id=None, account_id=None, include_all=False)` filters by account.

- [ ] **Step 1: Write failing test** (append) — mirror Task 9's list-filter test for `SimulationManager` (adapt to its real creation API; assert account filtering).

- [ ] **Step 2: Run, verify fail.** `cd backend && uv run pytest tests/test_ownership.py -k simulations_filters_by_account -v`

- [ ] **Step 3: Edit `simulation_manager.py`** — add `account_id` to `SimulationState` + `to_dict`/loader; thread through creation; `list_simulations(..., account_id=None, include_all=False)` account filter; `list_simulations` skips stray dirs as before.

- [ ] **Step 4: Edit `simulation.py`** — apply the Phase-5 pattern at every guarded route (the ~17 routes that did `require_owner_or_admin(state.owner_id)` and the report-area sim routes): switch to `require_account_access(state.account_id)` using the loaded state's `account_id`; creation stamps `account_id=current_account_id()`; list/history filter `account_id=current_account_id(), include_all=is_superadmin()`. Keep the existing `_resolve_simulation_dir`/`validate_simulation_id` guards.

- [ ] **Step 5: Run full suite.** `cd backend && uv run pytest tests/ -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/simulation_manager.py backend/app/api/simulation.py backend/tests/test_ownership.py
git commit -m "feat(accounts): scope simulations to account"
```

---

### Task 11: Reports — account_id + account-scoped access

**Files:**
- Modify: `backend/app/services/report_agent.py` (Report + ReportManager), `backend/app/api/report.py`
- Test: `backend/tests/test_ownership.py` (append)

**Interfaces:**
- Produces: `Report.account_id` (persisted); `ReportManager.list_reports(simulation_id=None, limit=50, account_id=None, include_all=False)` account filter.

- [ ] **Step 1: Write failing test** (append) — report list filtered by account.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Edit `report_agent.py`** — add `account_id` to `Report` + serialization; `list_reports(..., account_id=None, include_all=False)`; set `account_id` when a report is created (creator's account).
- [ ] **Step 4: Edit `report.py`** — apply the Phase-5 pattern to all 12 report-id routes AND the three sim-id routes (chat/check/generate-status): use `require_account_access(<resource>.account_id)` (report's account for report-id routes; the simulation's account for the sim-id routes) → 404 / silent-hide as today; list filter by account; creation stamps account.
- [ ] **Step 5: Run full suite** → PASS.
- [ ] **Step 6: Commit**

```bash
git add backend/app/services/report_agent.py backend/app/api/report.py backend/tests/test_ownership.py
git commit -m "feat(accounts): scope reports to account"
```

---

### Task 12: Graphs — account on root + account-scoped graph access

**Files:**
- Modify: `backend/app/storage/neo4j_storage.py`, `backend/app/auth/graph_access.py`, `backend/app/api/graph.py`
- Test: `backend/tests/test_ownership.py` (append, fake-session)

**Interfaces:**
- Produces: `Neo4jStorage.create_graph(name, owner_id=None, account_id=None)` sets `account_id` on the root node; `get_graph_account(graph_id) -> str|None`; `require_graph_owner_or_admin` → renamed/repurposed to `require_graph_account_access(graph_id)` (resolves via `get_graph_account` then `require_account_access`).

- [ ] **Step 1: Write failing test** (append, fake-session) — `create_graph(..., account_id="accA")` includes `account_id` in the Cypher params; `require_graph_account_access` raises for a foreign account.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Edit `neo4j_storage.py`** — `create_graph(name, owner_id=None, account_id=None)` includes `account_id: $account_id` in the root-node Cypher; add `get_graph_account(graph_id)`.
- [ ] **Step 4: Edit `graph_access.py`** — `require_graph_account_access(graph_id)`: `account = storage.get_graph_account(graph_id)`; `require_account_access(account)`. Update the 8 graph_id route call sites (simulation.py entity routes + generate_profiles, graph.py get_graph_data + delete_graph, report.py /tools/search + /tools/statistics) to call it. `build_graph` passes `account_id=current_account_id()` to `create_graph`.
- [ ] **Step 5: Run full suite** → PASS.
- [ ] **Step 6: Commit**

```bash
git add backend/app/storage/neo4j_storage.py backend/app/auth/graph_access.py backend/app/api/graph.py backend/app/api/simulation.py backend/app/api/report.py backend/tests/test_ownership.py
git commit -m "feat(accounts): scope Neo4j graphs to account"
```

---

### Task 13: Remove the obsolete owner-based helpers

**Files:**
- Modify: `backend/app/auth/ownership.py`
- Test: full suite

**Interfaces:**
- Produces: `ownership.py` no longer exports `can_access`/`require_owner_or_admin`/`is_admin` (replaced by account helpers). `current_user_id()` stays (used for the `owner_id` audit stamp).

- [ ] **Step 1:** Grep for remaining references: `cd backend && grep -rn "require_owner_or_admin\|can_access\|is_admin\b" app/` — expect none in api/services after Phases 4-5 (only definitions left).
- [ ] **Step 2:** Remove `is_admin`, `can_access`, `require_owner_or_admin` from `ownership.py` (keep `current_user_id`). Run `cd backend && uv run pytest tests/ -q`.
- [ ] **Step 3:** If any test/file still imports the removed names, update it to the account equivalents. Re-run until green + pristine.
- [ ] **Step 4: Commit**

```bash
git add backend/app/auth/ownership.py
git commit -m "refactor(accounts): drop obsolete owner-based access helpers"
```

---

# PHASE 6 — Frontend

> No JS test runner — verify each task with `cd frontend && npm run build` (0 errors) + code review. The axios instance returns unwrapped payloads.

### Task 14: Auth store exposes account; role-aware me-menu

**Files:**
- Modify: `frontend/src/stores/auth.js`, `frontend/src/components/UserMenu.vue`

- [ ] **Step 1:** In `auth.js`, expose `accountName` (computed from `state.user?.account_name`), `isSuperadmin` (`role==='superadmin'`), `isAccountAdmin` (`role==='account_admin'`). (`login`/`fetchMe` already store the user object, which now includes `account_id`/`account_name`.)
- [ ] **Step 2:** In `UserMenu.vue` dropdown, show entries by role: superadmin → link to `/superadmin/accounts` (`$t('accounts.menuTitle')`) + Appearance (`/admin/branding`); account_admin → link to `/admin/users`; all → show `accountName` (when set) in the identity header; logout for all.
- [ ] **Step 3:** `cd frontend && npm run build` → 0 errors.
- [ ] **Step 4: Commit** `feat(accounts): role-aware me-menu + account context in auth store`.

---

### Task 15: Superadmin Accounts page

**Files:**
- Create: `frontend/src/views/SuperadminAccounts.vue`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1:** Create `SuperadminAccounts.vue` (full header like other admin views): list accounts (`GET /api/superadmin/accounts` → `res.accounts`: name, active, user_count); create account form (`POST /api/superadmin/accounts {name}`); per-row "create admin" (email/password/name → `POST /api/superadmin/accounts/<id>/admin`) and enable/disable (`POST /api/superadmin/accounts/<id>/active {active}`); refresh after mutations; show errors; `$t` labels.
- [ ] **Step 2:** Add route `{ path: '/superadmin/accounts', name: 'SuperadminAccounts', component: () => import('@/views/SuperadminAccounts.vue'), meta: { superadmin: true } }`. Extend the router guard: a `meta.superadmin` route requires `auth.isSuperadmin.value` (else redirect `/`); keep `meta.admin` for account_admin pages (allow account_admin OR superadmin).
- [ ] **Step 3:** `cd frontend && npm run build` → 0 errors.
- [ ] **Step 4: Commit** `feat(accounts): superadmin Accounts management page + route guard`.

---

### Task 16: i18n keys (DE/EN parity)

**Files:**
- Modify: `locales/en.json`, `locales/de.json`

- [ ] **Step 1:** Add an `accounts` block used by Tasks 14-15: `menuTitle` (EN "Accounts"/DE "Accounts"), `title` (EN "Account management"/DE "Account-Verwaltung"), `name` (EN "Account name"/DE "Account-Name"), `create` (EN "Create account"/DE "Account anlegen"), `active` (EN "Active"/DE "Aktiv"), `users` (EN "Users"/DE "Benutzer"), `createAdmin` (EN "Create admin"/DE "Admin anlegen"), `disable` (EN "Disable"/DE "Deaktivieren"), `enable` (EN "Enable"/DE "Aktivieren"). Add `auth.menu`/identity keys if new ones were introduced in Task 14.
- [ ] **Step 2:** Verify parity: `cd backend && uv run python -c "import json;a=json.load(open('../locales/en.json'));b=json.load(open('../locales/de.json'));print('accounts parity', set(a['accounts'])==set(b['accounts']))"` → True.
- [ ] **Step 3:** `cd frontend && npm run build` → 0 errors.
- [ ] **Step 4: Commit** `feat(accounts): DE/EN i18n for accounts UI`.

---

## Final Verification

- [ ] **Full backend suite:** `cd backend && uv run pytest tests/ -q` → all green, pristine.
- [ ] **Fresh-start note:** document that `backend/uploads/auth.db` must be deleted once on upgrade so the new schema (accounts + users.account_id) is created; the superadmin re-seeds from `ADMIN_EMAIL`/`ADMIN_PASSWORD`, then creates the first account + its admin in the UI.
- [ ] **Manual end-to-end (Docker):** wipe `auth.db`; log in as superadmin; create Account "Acme" + its admin; log in as that admin; create a user; as the user, create a project/sim and confirm the account-admin and other account members see it, while a user in another account gets 404; confirm a non-superadmin cannot reach `/superadmin/accounts`.
- [ ] **Update docs:** add an "Accounts / multi-tenancy" section to `docs/security.md` (roles, account scoping, seeding, fresh-start) and link from `docs/README.md`.

---

## Self-Review Notes (spec coverage)

- Accounts table + users.account_id + 3 roles → Task 1. ✓
- Account-scope access model → Tasks 2, 9-12. ✓
- superadmin/account_admin decorators → Task 3. ✓
- Account service → Task 4; user-service account changes → Task 5. ✓
- Superadmin provisioning API → Task 6; seed superadmin + /me account info → Task 7. ✓
- Account-scoped user-management → Task 8. ✓
- Resource account-scoping (projects/sims/reports/graphs) → Tasks 9-12; cleanup → 13. ✓
- Frontend (accounts page, role-aware menu, account context) → Tasks 14-15; i18n → 16. ✓
- Fresh start (no migration) → seeding (Task 7) + final-verification wipe note. ✓
- Branding superadmin-only → Task 14 (Appearance under superadmin entry). ✓
