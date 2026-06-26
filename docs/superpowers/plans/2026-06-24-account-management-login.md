# Account Management & Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-user authentication, admin/user roles, and per-user data isolation to MiroFish-Offline (currently single-tenant).

**Architecture:** A new `backend/app/auth/` package holds a SQLite/SQLAlchemy user+session store and pure-logic service. The existing `app/security.py` `before_request` hook becomes the central resolver (cookie → server-side session → `g.current_user`) with deny-by-default over `/api/*`. Resource endpoints gain an `owner_id` and enforce owner-or-admin access. The Vue SPA gets a login page, router guard, cookie-credentialed axios, and an admin users page.

**Tech Stack:** Flask 3, Flask-SQLAlchemy, passlib[bcrypt], SQLite, Vue 3 + vue-i18n, axios.

## Global Constraints

- Python: `>=3.11,<3.13` (do not widen).
- New deps only: `Flask-SQLAlchemy`, `passlib[bcrypt]`. No rate-limit library (custom minimal).
- Tests run: `cd backend && uv run pytest tests/` (pytest already configured).
- Run tests from the `backend/` directory (uv resolves `app` package there).
- Login identity is **email** (unique); no username.
- Provisioning is **admin-only**; no open registration.
- Sessions are **server-side, revocable**; cookie holds an opaque token, DB stores only `sha256(token)`.
- Foreign-resource access returns **404** (not 403). Login failures return a **generic 401** (no user enumeration).
- CORS uses a concrete origin allowlist with credentials — never `*` (already set in `app/security.py`).
- New user-facing strings go in BOTH `locales/de.json` and `locales/en.json` with identical key trees.
- Default locale German; bcrypt cost default 12; session TTL default 7 days.

---

## File Structure

**Create (backend):**
- `backend/app/auth/__init__.py` — package marker + exports
- `backend/app/auth/db.py` — SQLAlchemy engine/session factory, `init_db()`
- `backend/app/auth/models.py` — `User`, `UserSession` ORM models
- `backend/app/auth/service.py` — pure auth logic
- `backend/app/auth/routes.py` — `/api/auth/*` blueprint
- `backend/app/auth/admin_routes.py` — `/api/admin/users/*` blueprint
- `backend/app/auth/decorators.py` — `login_required`, `admin_required`
- `backend/app/auth/ownership.py` — `require_owner_or_admin`, `is_admin`
- `backend/app/auth/seed.py` — `seed_admin_from_env`
- `backend/scripts/migrate_ownership.py` — backfill `owner_id`
- `backend/tests/test_auth_service.py`, `test_auth_routes.py`, `test_rbac.py`, `test_ownership.py`, `test_admin_users.py`, `test_seed.py`, `test_migration.py`

**Modify (backend):**
- `backend/pyproject.toml` — add deps
- `backend/app/config.py` — auth config
- `backend/app/security.py` — central session resolver + deny-by-default
- `backend/app/__init__.py` — init DB, register blueprints, seed, CORS credentials
- `backend/app/models/project.py` — `owner_id`
- `backend/app/api/graph.py` — owner on create/list/get/delete project
- `backend/app/api/simulation.py` — owner on simulations
- `backend/app/services/report_agent.py` (ReportManager) + `backend/app/api/report.py` — owner on reports
- `backend/app/storage/neo4j_storage.py` — `owner_id` on graph root
- `.env.example` — new vars

**Create/Modify (frontend):**
- `frontend/src/stores/auth.js` (create) — auth state
- `frontend/src/views/Login.vue` (create)
- `frontend/src/views/AdminUsers.vue` (create)
- `frontend/src/api/index.js` (modify) — `withCredentials`, 401 interceptor
- `frontend/src/router/index.js` (modify) — guard + routes
- `frontend/src/main.js` (modify) — bootstrap auth
- header component (modify) — user + logout
- `locales/de.json`, `locales/en.json` (modify) — keys

---

# PHASE 1 — Auth DB, Models & Service

### Task 1: Add dependencies & SQLAlchemy bootstrap

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/auth/__init__.py`, `backend/app/auth/db.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Produces: `auth.db.Base` (declarative base), `auth.db.get_engine(db_path: str)`, `auth.db.SessionLocal` (scoped factory), `auth.db.init_db(db_path: str) -> None`, `auth.db.session_scope()` (contextmanager yielding a `Session`).

- [ ] **Step 1: Add deps** to `backend/pyproject.toml` `dependencies` list:

```toml
    "Flask-SQLAlchemy>=3.1.0",
    "passlib[bcrypt]>=1.7.4",
```

- [ ] **Step 2: Sync deps**

Run: `cd backend && uv sync`
Expected: resolves and installs Flask-SQLAlchemy + passlib.

- [ ] **Step 3: Create `backend/app/auth/__init__.py`**

```python
"""Authentication, authorization and account-management package."""
```

- [ ] **Step 4: Write failing test** in `backend/tests/test_auth_service.py`

```python
import os
from app.auth import db as authdb


def test_init_db_creates_tables(tmp_path):
    path = str(tmp_path / "auth.db")
    authdb.init_db(path)
    assert os.path.exists(path)
    # Tables exist: opening a session and querying users must not raise.
    from app.auth.models import User
    with authdb.session_scope() as s:
        assert s.query(User).count() == 0
```

- [ ] **Step 5: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_service.py::test_init_db_creates_tables -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.db` / `app.auth.models`).

- [ ] **Step 6: Create `backend/app/auth/db.py`**

```python
"""SQLAlchemy engine/session factory for the auth store (SQLite)."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

_engine = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False)


def get_engine(db_path):
    global _engine
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal.configure(bind=_engine)
    return _engine


def init_db(db_path):
    """Create the engine and all tables. Idempotent."""
    engine = get_engine(db_path)
    # Import models so they register on Base before create_all.
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

(Models module is created in Task 2; this test will pass once Task 2 exists. Run order: do Task 2 Step "create models" before re-running. To keep this task self-contained, create a minimal `models.py` stub now and flesh it out in Task 2.)

- [ ] **Step 7: Create minimal `backend/app/auth/models.py` stub**

```python
"""ORM models for the auth store (expanded in Task 2)."""
from sqlalchemy import Column, String
from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
```

- [ ] **Step 8: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_auth_service.py::test_init_db_creates_tables -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/auth/ backend/tests/test_auth_service.py
git commit -m "feat(auth): add SQLAlchemy auth-store bootstrap (db.py, init_db)"
```

---

### Task 2: User & UserSession models

**Files:**
- Modify: `backend/app/auth/models.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Produces:
  - `User(id: str, email: str, name: str|None, password_hash: str, role: str, is_active: bool, created_at: datetime, updated_at: datetime, created_by: str|None)`
  - `UserSession(id: str, token_hash: str, user_id: str, created_at: datetime, expires_at: datetime, last_used_at: datetime, user_agent: str|None, ip: str|None)`
  - Roles: `ROLE_ADMIN = "admin"`, `ROLE_USER = "user"`.

- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timedelta
from app.auth import db as authdb
from app.auth.models import User, UserSession, ROLE_ADMIN


def test_user_and_session_persist(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    with authdb.session_scope() as s:
        u = User(id="u1", email="a@b.de", name="A", password_hash="x",
                 role=ROLE_ADMIN, is_active=True,
                 created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        s.add(u)
        s.flush()
        s.add(UserSession(id="s1", token_hash="h", user_id="u1",
                          created_at=datetime.utcnow(),
                          expires_at=datetime.utcnow() + timedelta(days=7),
                          last_used_at=datetime.utcnow()))
    with authdb.session_scope() as s:
        assert s.query(User).filter_by(email="a@b.de").one().role == "admin"
        assert s.query(UserSession).filter_by(user_id="u1").count() == 1
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_service.py::test_user_and_session_persist -v`
Expected: FAIL (`cannot import name 'UserSession'`).

- [ ] **Step 3: Replace `backend/app/auth/models.py` with full models**

```python
"""ORM models for the auth store."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from .db import Base

ROLE_ADMIN = "admin"
ROLE_USER = "user"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default=ROLE_USER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=True)


class UserSession(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=False)
    user_agent = Column(String, nullable=True)
    ip = Column(String, nullable=True)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_auth_service.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/models.py backend/tests/test_auth_service.py
git commit -m "feat(auth): add User and UserSession models"
```

---

### Task 3: Password hashing

**Files:**
- Create: `backend/app/auth/service.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Produces: `service.hash_password(plain: str, cost: int = 12) -> str`, `service.verify_password(plain: str, hashed: str) -> bool`.

- [ ] **Step 1: Write failing test**

```python
from app.auth import service


def test_hash_and_verify_password():
    h = service.hash_password("s3cret")
    assert h != "s3cret"
    assert service.verify_password("s3cret", h) is True
    assert service.verify_password("wrong", h) is False
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_service.py::test_hash_and_verify_password -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.service`).

- [ ] **Step 3: Create `backend/app/auth/service.py`**

```python
"""Pure auth logic: password hashing, user CRUD, sessions."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from passlib.context import CryptContext

from . import db as authdb
from .models import User, UserSession, ROLE_ADMIN, ROLE_USER

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain, cost=12):
    return _pwd.using(rounds=cost).hash(plain)


def verify_password(plain, hashed):
    try:
        return _pwd.verify(plain, hashed)
    except ValueError:
        return False
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_auth_service.py::test_hash_and_verify_password -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/service.py backend/tests/test_auth_service.py
git commit -m "feat(auth): add bcrypt password hashing/verification"
```

---

### Task 4: User creation & lookup

**Files:**
- Modify: `backend/app/auth/service.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Produces:
  - `service.create_user(email, password, name=None, role=ROLE_USER, created_by=None) -> str` (returns user id; raises `ValueError` on duplicate email or empty email/password)
  - `service.get_user_by_email(email) -> User | None`
  - `service.get_user(user_id) -> User | None`

- [ ] **Step 1: Write failing test**

```python
import pytest
from app.auth import db as authdb, service


def test_create_user_and_duplicate(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    uid = service.create_user("x@y.de", "pw12345", name="X")
    assert isinstance(uid, str)
    fetched = service.get_user_by_email("x@y.de")
    assert fetched.id == uid and fetched.role == "user"
    with pytest.raises(ValueError):
        service.create_user("x@y.de", "other")


def test_create_user_rejects_empty(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    with pytest.raises(ValueError):
        service.create_user("", "pw")
    with pytest.raises(ValueError):
        service.create_user("a@b.de", "")
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_auth_service.py::test_create_user_and_duplicate -v`
Expected: FAIL (`AttributeError: ... create_user`).

- [ ] **Step 3: Append to `service.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_auth_service.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/service.py backend/tests/test_auth_service.py
git commit -m "feat(auth): add create_user / get_user lookups"
```

---

### Task 5: Sessions (start, resolve, expiry, revoke)

**Files:**
- Modify: `backend/app/auth/service.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Produces:
  - `service.start_session(user_id, ttl_days=7, user_agent=None, ip=None) -> str` (returns plaintext token; stores `sha256` hash)
  - `service.resolve_session(token) -> User | None` (None if missing/expired/inactive; bumps `last_used_at`)
  - `service.revoke_session(token) -> None`
  - `service.revoke_user_sessions(user_id) -> int`
  - `service._hash_token(token) -> str` (sha256 hex)

- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timedelta
from app.auth import db as authdb, service
from app.auth.models import UserSession


def _setup(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    return service.create_user("a@b.de", "pw")


def test_start_and_resolve_session(tmp_path):
    uid = _setup(tmp_path)
    token = service.start_session(uid)
    assert service.resolve_session(token).id == uid


def test_resolve_rejects_unknown(tmp_path):
    _setup(tmp_path)
    assert service.resolve_session("nope") is None


def test_revoke_session(tmp_path):
    uid = _setup(tmp_path)
    token = service.start_session(uid)
    service.revoke_session(token)
    assert service.resolve_session(token) is None


def test_expired_session_rejected(tmp_path):
    uid = _setup(tmp_path)
    token = service.start_session(uid)
    with authdb.session_scope() as s:
        row = s.query(UserSession).filter_by(
            token_hash=service._hash_token(token)).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    assert service.resolve_session(token) is None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && uv run pytest tests/test_auth_service.py -k session -v`
Expected: FAIL (`AttributeError: start_session`).

- [ ] **Step 3: Append to `service.py`**

```python
def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(user_id, ttl_days=7, user_agent=None, ip=None):
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    with authdb.session_scope() as s:
        s.add(UserSession(id=str(uuid.uuid4()), token_hash=_hash_token(token),
                          user_id=user_id, created_at=now,
                          expires_at=now + timedelta(days=ttl_days),
                          last_used_at=now, user_agent=user_agent, ip=ip))
    return token


def resolve_session(token):
    if not token:
        return None
    now = datetime.utcnow()
    with authdb.session_scope() as s:
        row = s.query(UserSession).filter_by(token_hash=_hash_token(token)).first()
        if not row or row.expires_at < now:
            return None
        user = s.query(User).filter_by(id=row.user_id).first()
        if not user or not user.is_active:
            return None
        row.last_used_at = now
        s.expunge(user)
        return user


def revoke_session(token):
    with authdb.session_scope() as s:
        s.query(UserSession).filter_by(token_hash=_hash_token(token)).delete()


def revoke_user_sessions(user_id):
    with authdb.session_scope() as s:
        return s.query(UserSession).filter_by(user_id=user_id).delete()
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_auth_service.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/service.py backend/tests/test_auth_service.py
git commit -m "feat(auth): add server-side session start/resolve/revoke"
```

---

### Task 6: Admin user-management service ops

**Files:**
- Modify: `backend/app/auth/service.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Produces:
  - `service.set_role(user_id, role) -> None` (raises `ValueError` for bad role)
  - `service.set_active(user_id, active: bool) -> None` (deactivation also revokes sessions)
  - `service.reset_password(user_id, new_password) -> None`
  - `service.list_users() -> list[User]`
  - `service.count_admins() -> int`

- [ ] **Step 1: Write failing test**

```python
import pytest
from app.auth import db as authdb, service
from app.auth.models import ROLE_ADMIN


def test_deactivate_revokes_sessions(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    uid = service.create_user("a@b.de", "pw")
    token = service.start_session(uid)
    service.set_active(uid, False)
    assert service.resolve_session(token) is None


def test_set_role_and_reset_password(tmp_path):
    authdb.init_db(str(tmp_path / "auth.db"))
    uid = service.create_user("a@b.de", "pw")
    service.set_role(uid, ROLE_ADMIN)
    assert service.get_user(uid).role == "admin"
    service.reset_password(uid, "newpw99")
    assert service.verify_password("newpw99", service.get_user(uid).password_hash)
    with pytest.raises(ValueError):
        service.set_role(uid, "superuser")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && uv run pytest tests/test_auth_service.py -k "deactivate or set_role" -v`
Expected: FAIL.

- [ ] **Step 3: Append to `service.py`**

```python
def set_role(user_id, role):
    if role not in (ROLE_ADMIN, ROLE_USER):
        raise ValueError("invalid role")
    with authdb.session_scope() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise ValueError("no such user")
        u.role = role
        u.updated_at = datetime.utcnow()


def set_active(user_id, active):
    with authdb.session_scope() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise ValueError("no such user")
        u.is_active = bool(active)
        u.updated_at = datetime.utcnow()
    if not active:
        revoke_user_sessions(user_id)


def reset_password(user_id, new_password):
    if not new_password:
        raise ValueError("password required")
    with authdb.session_scope() as s:
        u = s.query(User).filter_by(id=user_id).first()
        if not u:
            raise ValueError("no such user")
        u.password_hash = hash_password(new_password)
        u.updated_at = datetime.utcnow()


def list_users():
    with authdb.session_scope() as s:
        users = s.query(User).order_by(User.created_at).all()
        for u in users:
            s.expunge(u)
        return users


def count_admins():
    with authdb.session_scope() as s:
        return s.query(User).filter_by(role=ROLE_ADMIN, is_active=True).count()
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_auth_service.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/service.py backend/tests/test_auth_service.py
git commit -m "feat(auth): add set_role/set_active/reset_password/list_users"
```

---

# PHASE 2 — Config, Login Routes & Central Resolver

### Task 7: Auth configuration

**Files:**
- Modify: `backend/app/config.py`, `.env.example`
- Test: `backend/tests/test_security.py`

**Interfaces:**
- Produces: `Config.AUTH_DB_PATH`, `Config.SESSION_TTL_DAYS` (int), `Config.BCRYPT_COST` (int), `Config.ADMIN_EMAIL`, `Config.ADMIN_PASSWORD`, `Config.SESSION_COOKIE_NAME = "mf_session"`.

- [ ] **Step 1: Write failing test** in `backend/tests/test_security.py`

```python
def test_auth_config_defaults():
    from app.config import Config
    assert Config.SESSION_COOKIE_NAME == "mf_session"
    assert isinstance(Config.SESSION_TTL_DAYS, int)
    assert isinstance(Config.BCRYPT_COST, int)
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_security.py::test_auth_config_defaults -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Add to `Config` in `backend/app/config.py`** (after the existing security block)

```python
    # ===== Auth / account management =====
    AUTH_DB_PATH = os.environ.get(
        'AUTH_DB_PATH',
        os.path.join(os.path.dirname(__file__), '../uploads/auth.db'))
    SESSION_COOKIE_NAME = "mf_session"
    SESSION_TTL_DAYS = int(os.environ.get('SESSION_TTL_DAYS', '7'))
    BCRYPT_COST = int(os.environ.get('BCRYPT_COST', '12'))
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
```

- [ ] **Step 4: Add to `.env.example`** under the Security section

```bash
# Seed admin (created idempotently at startup if no admin exists yet)
ADMIN_EMAIL=
ADMIN_PASSWORD=
# Session lifetime (days) and bcrypt cost
SESSION_TTL_DAYS=7
BCRYPT_COST=12
```

- [ ] **Step 5: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_security.py::test_auth_config_defaults -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py .env.example backend/tests/test_security.py
git commit -m "feat(auth): add auth configuration (session, bcrypt, admin seed)"
```

---

### Task 8: Auth routes (login / logout / me)

**Files:**
- Create: `backend/app/auth/routes.py`
- Test: `backend/tests/test_auth_routes.py`

**Interfaces:**
- Consumes: `service.get_user_by_email`, `verify_password`, `start_session`, `revoke_session`; `Config.SESSION_COOKIE_NAME`, `SESSION_TTL_DAYS`.
- Produces: Blueprint `auth_bp` (url_prefix `/api/auth`) with `POST /login`, `POST /logout`, `GET /me`. Sets/clears the `mf_session` httpOnly cookie. `_user_dict(user) -> dict` shape `{id,email,name,role}`.

- [ ] **Step 1: Write failing test** in `backend/tests/test_auth_routes.py`

```python
import pytest
from flask import Flask
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.config import Config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("a@b.de", "pw12345", name="A")
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(auth_bp)
    return app.test_client()


def test_login_success_sets_cookie(client):
    r = client.post("/api/auth/login", json={"email": "a@b.de", "password": "pw12345"})
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "a@b.de"
    assert "mf_session" in r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in r.headers.get("Set-Cookie", "")


def test_login_bad_password_generic_401(client):
    r = client.post("/api/auth/login", json={"email": "a@b.de", "password": "wrong"})
    assert r.status_code == 401
    # Generic — must not reveal whether the user exists.
    assert "password" not in r.get_json().get("error", "").lower()


def test_login_unknown_user_same_401(client):
    r = client.post("/api/auth/login", json={"email": "no@b.de", "password": "x"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && uv run pytest tests/test_auth_routes.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.routes`).

- [ ] **Step 3: Create `backend/app/auth/routes.py`**

```python
"""/api/auth/* — login, logout, current user."""
from flask import Blueprint, current_app, g, jsonify, request

from . import service
from ..config import Config

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _user_dict(user):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


def _set_cookie(resp, token):
    resp.set_cookie(
        Config.SESSION_COOKIE_NAME, token,
        max_age=Config.SESSION_TTL_DAYS * 86400,
        httponly=True, samesite="Lax",
        secure=not current_app.config.get("DEBUG", False),
        path="/",
    )


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    password = data.get("password", "")
    user = service.get_user_by_email(email)
    if not user or not user.is_active or not service.verify_password(password, user.password_hash):
        return jsonify({"success": False, "error": "Invalid credentials"}), 401
    token = service.start_session(
        user.id, ttl_days=Config.SESSION_TTL_DAYS,
        user_agent=request.headers.get("User-Agent"),
        ip=request.remote_addr)
    resp = jsonify({"success": True, "user": _user_dict(user)})
    _set_cookie(resp, token)
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    token = request.cookies.get(Config.SESSION_COOKIE_NAME)
    if token:
        service.revoke_session(token)
    resp = jsonify({"success": True})
    resp.delete_cookie(Config.SESSION_COOKIE_NAME, path="/")
    return resp


@auth_bp.route("/me", methods=["GET"])
def me():
    user = getattr(g, "current_user", None)
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return jsonify({"success": True, "user": _user_dict(user)})
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_auth_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/routes.py backend/tests/test_auth_routes.py
git commit -m "feat(auth): add login/logout/me routes with httpOnly cookie"
```

---

### Task 9: Central session resolver + deny-by-default

**Files:**
- Modify: `backend/app/security.py`
- Test: `backend/tests/test_rbac.py`

**Interfaces:**
- Consumes: `service.resolve_session`, `Config.SESSION_COOKIE_NAME`.
- Produces: updated `register_auth(app)` that (1) resolves the session cookie into `g.current_user` on every request, and (2) returns 401 for `/api/*` when no authenticated user, EXCEPT allowlist `{"/api/auth/login", "/health"}` and `OPTIONS`. Keeps the existing static `API_TOKEN` path as an accepted alternative when configured.

- [ ] **Step 1: Write failing test** in `backend/tests/test_rbac.py`

```python
import pytest
from flask import Flask, Blueprint, jsonify, g
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.security import register_auth
from app.config import Config


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("a@b.de", "pw12345")
    app = Flask(__name__)
    app.config.from_object(Config)
    bp = Blueprint("p", __name__)

    @bp.route("/secret")
    def secret():
        return jsonify({"who": g.current_user.email})

    app.register_blueprint(bp, url_prefix="/api/p")
    app.register_blueprint(auth_bp)
    register_auth(app)
    return app


def test_protected_route_blocks_anonymous(app):
    assert app.test_client().get("/api/p/secret").status_code == 401


def test_protected_route_after_login(app):
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "a@b.de", "password": "pw12345"})
    r = c.get("/api/p/secret")
    assert r.status_code == 200 and r.get_json()["who"] == "a@b.de"


def test_login_endpoint_is_public(app):
    assert app.test_client().post(
        "/api/auth/login", json={"email": "a@b.de", "password": "pw12345"}
    ).status_code == 200
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && uv run pytest tests/test_rbac.py -v`
Expected: FAIL (anonymous gets 200, because current resolver only checks API_TOKEN).

- [ ] **Step 3: Replace the body of `register_auth` in `backend/app/security.py`**

```python
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
```

(Keep the existing `_extract_token`, `get_cors_origins`, `_AUTH_EXEMPT_PATHS` helpers in the module.)

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_rbac.py tests/test_security.py -v`
Expected: PASS. (Note: `test_security.py::test_no_token_configured_allows_request_but_open` from the prior CVE work asserted open-when-no-token using a bare app without the auth DB. Update that test to register `auth_bp` and expect 401, since deny-by-default now applies; adjust its assertion to `== 401`.)

- [ ] **Step 5: Adjust the obsolete CVE-era test** in `backend/tests/test_security.py`

Replace `test_no_token_configured_allows_request_but_open` with:

```python
    def test_no_token_configured_now_requires_login(self):
        # After account-management, deny-by-default applies even without API_TOKEN.
        app = _make_app("")
        register_auth(app)
        resp = app.test_client().get("/api/t/ping")
        assert resp.status_code == 401
```

(The `_make_app` helper has no auth DB; `g.current_user` stays None → 401. Add `from app.security import register_auth` already imported.)

- [ ] **Step 6: Run full suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/security.py backend/tests/test_rbac.py backend/tests/test_security.py
git commit -m "feat(auth): central session resolver + deny-by-default on /api/*"
```

---

### Task 10: Wire DB init, blueprints, CORS credentials & seeding into app factory

**Files:**
- Modify: `backend/app/__init__.py`
- Create: `backend/app/auth/seed.py`
- Test: `backend/tests/test_app_integration.py`, `backend/tests/test_seed.py`

**Interfaces:**
- Consumes: `authdb.init_db`, `seed.seed_admin_from_env`, `auth_bp`, `admin_bp` (Task 12), `service`.
- Produces: `create_app()` now calls `init_db(Config.AUTH_DB_PATH)`, registers `auth_bp`, sets CORS `supports_credentials=True`, and seeds the admin. `seed.seed_admin_from_env() -> str | None` (creates admin if none exists; returns new admin id or None).

- [ ] **Step 1: Write failing test** in `backend/tests/test_seed.py`

```python
from app.auth import db as authdb, service
from app.auth.seed import seed_admin_from_env
from app.config import Config


def test_seed_creates_admin_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "ADMIN_EMAIL", "admin@x.de")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "adminpw")
    authdb.init_db(Config.AUTH_DB_PATH)
    new_id = seed_admin_from_env()
    assert new_id is not None
    assert service.get_user_by_email("admin@x.de").role == "admin"
    # Idempotent: second call creates nothing.
    assert seed_admin_from_env() is None
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_seed.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.seed`).

- [ ] **Step 3: Create `backend/app/auth/seed.py`**

```python
"""Idempotent first-admin seeding from environment."""
from . import service
from .models import ROLE_ADMIN
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.auth")


def seed_admin_from_env():
    if service.count_admins() > 0:
        return None
    if not Config.ADMIN_EMAIL or not Config.ADMIN_PASSWORD:
        logger.warning(
            "No admin exists and ADMIN_EMAIL/ADMIN_PASSWORD are unset — "
            "create an admin before using the app.")
        return None
    uid = service.create_user(Config.ADMIN_EMAIL, Config.ADMIN_PASSWORD,
                              role=ROLE_ADMIN)
    logger.info("Seeded initial admin %s", Config.ADMIN_EMAIL)
    return uid
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_seed.py -v`
Expected: PASS.

- [ ] **Step 5: Modify `backend/app/__init__.py`** — after the CORS block, replace/extend:

```python
    # Enable CORS — restricted to configured origins, WITH credentials (cookies)
    from .security import get_cors_origins, register_auth
    cors_origins = get_cors_origins(Config.CORS_ORIGINS)
    CORS(app, resources={r"/api/*": {"origins": cors_origins}},
         supports_credentials=True)

    # --- Auth store: init DB, seed admin, register auth blueprints ---
    from .auth.db import init_db
    from .auth.seed import seed_admin_from_env
    from .auth.routes import auth_bp
    from .auth.admin_routes import admin_bp
    init_db(Config.AUTH_DB_PATH)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    try:
        seed_admin_from_env()
    except Exception as e:
        logger.error("Admin seeding failed: %s", e)

    register_auth(app)
```

(Remove the old `register_auth(app)` call/CORS line replaced above. `admin_bp` comes from Task 12 — implement Task 12 before running the app, or temporarily comment its import/registration until then.)

- [ ] **Step 6: Update `backend/tests/test_app_integration.py`** — the fixture must seed a user and authenticate. Replace the `token_app` fixture body with:

```python
@pytest.fixture
def token_app(monkeypatch, tmp_path):
    import app.storage as storage_mod
    from app.auth import db as authdb, service

    def _boom(*a, **k):
        raise RuntimeError("no neo4j in test")
    monkeypatch.setattr(storage_mod, "Neo4jStorage", _boom)
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "ADMIN_EMAIL", "admin@x.de")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "adminpw")
    app = create_app()
    return app
```

Replace the two auth assertions:

```python
def test_api_blocked_without_login(token_app):
    path = _first_api_get_path(token_app)
    assert token_app.test_client().get(path).status_code == 401


def test_api_passes_after_login(token_app):
    c = token_app.test_client()
    c.post("/api/auth/login", json={"email": "admin@x.de", "password": "adminpw"})
    assert c.get(_first_api_get_path(token_app)).status_code != 401
```

- [ ] **Step 7: Run full suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS (after Task 12 exists; if running now, temporarily skip admin_bp import).

- [ ] **Step 8: Commit**

```bash
git add backend/app/__init__.py backend/app/auth/seed.py backend/tests/test_seed.py backend/tests/test_app_integration.py
git commit -m "feat(auth): wire DB init, seeding, blueprints, CORS credentials into app factory"
```

---

# PHASE 3 — RBAC & Admin API

### Task 11: Authorization decorators

**Files:**
- Create: `backend/app/auth/decorators.py`
- Test: `backend/tests/test_rbac.py`

**Interfaces:**
- Consumes: `g.current_user`.
- Produces: `@login_required` (401 if no user), `@admin_required` (401 if none, 403 if not admin).

- [ ] **Step 1: Write failing test** (append to `test_rbac.py`)

```python
def test_admin_required_blocks_non_admin(tmp_path, monkeypatch):
    from flask import Flask, jsonify
    from app.auth.decorators import admin_required
    from app.auth import db as authdb, service
    from app.auth.routes import auth_bp
    from app.security import register_auth
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("u@b.de", "pw12345")  # role=user
    app = Flask(__name__); app.config.from_object(Config)

    @app.route("/api/admin/ping")
    @admin_required
    def ping():
        return jsonify({"ok": True})

    app.register_blueprint(auth_bp); register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "u@b.de", "password": "pw12345"})
    assert c.get("/api/admin/ping").status_code == 403
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_rbac.py::test_admin_required_blocks_non_admin -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.decorators`).

- [ ] **Step 3: Create `backend/app/auth/decorators.py`**

```python
"""Authorization decorators."""
from functools import wraps
from flask import g, jsonify
from .models import ROLE_ADMIN


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if user.role != ROLE_ADMIN:
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
git commit -m "feat(auth): add login_required/admin_required decorators"
```

---

### Task 12: Admin user-management API

**Files:**
- Create: `backend/app/auth/admin_routes.py`
- Test: `backend/tests/test_admin_users.py`

**Interfaces:**
- Consumes: `service.list_users/create_user/set_role/set_active/reset_password`, `@admin_required`.
- Produces: Blueprint `admin_bp` (url_prefix `/api/admin`):
  - `GET /users` → `{users: [{id,email,name,role,is_active,created_at}]}`
  - `POST /users` `{email,password,name?,role?}` → 201 `{user}`
  - `POST /users/<id>/role` `{role}` → `{success}`
  - `POST /users/<id>/active` `{active}` → `{success}`
  - `POST /users/<id>/reset-password` `{password}` → `{success}`

- [ ] **Step 1: Write failing test** in `backend/tests/test_admin_users.py`

```python
import pytest
from flask import Flask
from app.auth import db as authdb, service
from app.auth.routes import auth_bp
from app.auth.admin_routes import admin_bp
from app.security import register_auth
from app.config import Config


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(Config, "API_TOKEN", "")
    authdb.init_db(Config.AUTH_DB_PATH)
    service.create_user("admin@x.de", "adminpw", role="admin")
    app = Flask(__name__); app.config.from_object(Config)
    app.register_blueprint(auth_bp); app.register_blueprint(admin_bp)
    register_auth(app)
    c = app.test_client()
    c.post("/api/auth/login", json={"email": "admin@x.de", "password": "adminpw"})
    return c


def test_admin_creates_and_lists_users(admin_client):
    r = admin_client.post("/api/admin/users",
                          json={"email": "new@x.de", "password": "pw12345", "name": "New"})
    assert r.status_code == 201
    users = admin_client.get("/api/admin/users").get_json()["users"]
    assert any(u["email"] == "new@x.de" for u in users)


def test_admin_deactivates_user(admin_client):
    uid = admin_client.post("/api/admin/users",
                            json={"email": "n@x.de", "password": "pw12345"}).get_json()["user"]["id"]
    assert admin_client.post(f"/api/admin/users/{uid}/active",
                             json={"active": False}).status_code == 200
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && uv run pytest tests/test_admin_users.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.admin_routes`).

- [ ] **Step 3: Create `backend/app/auth/admin_routes.py`**

```python
"""/api/admin/users/* — admin-only account management."""
from flask import Blueprint, jsonify, request, g

from . import service
from .decorators import admin_required
from .models import ROLE_USER

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _u(u):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "created_at": u.created_at.isoformat()}


@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    return jsonify({"success": True, "users": [_u(u) for u in service.list_users()]})


@admin_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    d = request.get_json(silent=True) or {}
    try:
        uid = service.create_user(d.get("email", ""), d.get("password", ""),
                                  name=d.get("name"), role=d.get("role", ROLE_USER),
                                  created_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "user": _u(service.get_user(uid))}), 201


@admin_bp.route("/users/<user_id>/role", methods=["POST"])
@admin_required
def set_role(user_id):
    try:
        service.set_role(user_id, (request.get_json(silent=True) or {}).get("role"))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@admin_bp.route("/users/<user_id>/active", methods=["POST"])
@admin_required
def set_active(user_id):
    active = bool((request.get_json(silent=True) or {}).get("active"))
    service.set_active(user_id, active)
    return jsonify({"success": True})


@admin_bp.route("/users/<user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    pw = (request.get_json(silent=True) or {}).get("password")
    try:
        service.reset_password(user_id, pw)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_admin_users.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite** (admin_bp now exists; un-comment its import in `__init__.py` from Task 10 if you stubbed it)

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/admin_routes.py backend/tests/test_admin_users.py backend/app/__init__.py
git commit -m "feat(auth): add admin user-management API"
```

---

# PHASE 4 — Ownership & Data Isolation

### Task 13: Ownership helper

**Files:**
- Create: `backend/app/auth/ownership.py`
- Test: `backend/tests/test_ownership.py`

**Interfaces:**
- Consumes: `g.current_user`, `ROLE_ADMIN`.
- Produces:
  - `is_admin() -> bool`
  - `current_user_id() -> str | None`
  - `can_access(owner_id: str | None) -> bool` (True if admin, or owner matches; legacy `None` owner → admin-only)
  - `require_owner_or_admin(owner_id)` — raises `PermissionError` if not allowed.

- [ ] **Step 1: Write failing test** in `backend/tests/test_ownership.py`

```python
import pytest
from flask import Flask, g
from app.auth import ownership
from app.auth.models import ROLE_ADMIN, ROLE_USER


class _U:
    def __init__(self, uid, role):
        self.id, self.role = uid, role


def _ctx(app, user):
    ctx = app.test_request_context()
    ctx.push()
    g.current_user = user
    return ctx


def test_owner_can_access():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        assert ownership.can_access("u1") is True
        assert ownership.can_access("u2") is False


def test_admin_can_access_anything():
    app = Flask(__name__)
    with _ctx(app, _U("a", ROLE_ADMIN)):
        assert ownership.can_access("u2") is True
        assert ownership.can_access(None) is True


def test_require_raises_for_foreign():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        with pytest.raises(PermissionError):
            ownership.require_owner_or_admin("u2")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd backend && uv run pytest tests/test_ownership.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.ownership`).

- [ ] **Step 3: Create `backend/app/auth/ownership.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd backend && uv run pytest tests/test_ownership.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/ownership.py backend/tests/test_ownership.py
git commit -m "feat(auth): add ownership helper (can_access/require_owner_or_admin)"
```

---

### Task 14: Project ownership (model + create + list filter + access checks)

**Files:**
- Modify: `backend/app/models/project.py`, `backend/app/api/graph.py`
- Test: `backend/tests/test_ownership.py`

**Interfaces:**
- Consumes: `ownership.current_user_id`, `is_admin`, `require_owner_or_admin`.
- Produces: `Project.owner_id: str | None` (persisted in `to_dict`/`from_dict`); `ProjectManager.create_project(name, owner_id=None)`; `ProjectManager.list_projects(limit=50, owner_id=None, include_all=False)` filters by owner unless `include_all`.

- [ ] **Step 1: Write failing test** (append to `test_ownership.py`)

```python
def test_list_projects_filters_by_owner(tmp_path, monkeypatch):
    from app.models import project as pj
    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", str(tmp_path), raising=False)
    # create two projects with different owners
    p1 = pj.ProjectManager.create_project("P1", owner_id="u1")
    p2 = pj.ProjectManager.create_project("P2", owner_id="u2")
    mine = pj.ProjectManager.list_projects(owner_id="u1")
    assert {p.project_id for p in mine} == {p1.project_id}
    everything = pj.ProjectManager.list_projects(include_all=True)
    assert {p.project_id for p in everything} >= {p1.project_id, p2.project_id}
```

(If `PROJECTS_DIR` isn't the attribute name, inspect `ProjectManager` and patch the actual class constant used by `_get_project_dir`.)

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_list_projects_filters_by_owner -v`
Expected: FAIL (`create_project() got unexpected kwarg owner_id`).

- [ ] **Step 3: Add `owner_id` to `Project`** in `backend/app/models/project.py`:
  - add field `owner_id: Optional[str] = None` in the dataclass (near `error`);
  - add `"owner_id": self.owner_id` to `to_dict()`;
  - ensure `from_dict`/loader reads `data.get("owner_id")`.

- [ ] **Step 4: Update `ProjectManager`** in the same file:

```python
    @classmethod
    def create_project(cls, name: str = "Unnamed Project", owner_id: str = None) -> "Project":
        # ... existing body that builds `project` ...
        project.owner_id = owner_id
        # ... existing save + return ...

    @classmethod
    def list_projects(cls, limit: int = 50, owner_id: str = None,
                      include_all: bool = False) -> "List[Project]":
        projects = cls._load_all_projects()  # existing loading logic
        if not include_all and owner_id is not None:
            projects = [p for p in projects if p.owner_id == owner_id]
        return projects[:limit]
```

(Adapt to the existing loading code; the key change is the post-filter.)

- [ ] **Step 5: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_list_projects_filters_by_owner -v`
Expected: PASS.

- [ ] **Step 6: Wire ownership into `backend/app/api/graph.py`:**
  - In `create_project` call sites (e.g. `generate_ontology`): pass `owner_id=current_user_id()`.
  - In `list_projects` route: `ProjectManager.list_projects(limit=limit, owner_id=current_user_id(), include_all=is_admin())`.
  - In `get_project`, `delete_project`, `reset_project`, `build_graph`: after loading the project, call `require_owner_or_admin(project.owner_id)`; on `PermissionError` return 404.

```python
from ..auth.ownership import current_user_id, is_admin, require_owner_or_admin
# ... in get_project:
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": t('api.projectNotFound')}), 404
    try:
        require_owner_or_admin(project.owner_id)
    except PermissionError:
        return jsonify({"success": False, "error": t('api.projectNotFound')}), 404
```

- [ ] **Step 7: Run full suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/project.py backend/app/api/graph.py backend/tests/test_ownership.py
git commit -m "feat(auth): scope projects to owner (create/list/access)"
```

---

### Task 15: Simulation ownership

**Files:**
- Modify: `backend/app/services/simulation_manager.py`, `backend/app/api/simulation.py`
- Test: `backend/tests/test_ownership.py`

**Interfaces:**
- Produces: simulation `state.json` carries `owner_id`; `SimulationManager` stores/loads it; `list_simulations(project_id=None, owner_id=None, include_all=False)` filters by owner.

- [ ] **Step 1: Write failing test** (append to `test_ownership.py`)

```python
def test_list_simulations_filters_by_owner(tmp_path, monkeypatch):
    from app.services.simulation_manager import SimulationManager
    m = SimulationManager(); m.SIMULATION_DATA_DIR = str(tmp_path)
    s1 = m.create_simulation(project_id="p1", owner_id="u1")  # adapt to real signature
    m.create_simulation(project_id="p2", owner_id="u2")
    mine = m.list_simulations(owner_id="u1")
    assert all(s.owner_id == "u1" for s in mine)
```

(Inspect the real `create_simulation`/state-construction signature and adapt; the assertion on owner filtering is the contract.)

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_list_simulations_filters_by_owner -v`
Expected: FAIL.

- [ ] **Step 3: Add `owner_id`** to the `SimulationState` dataclass + its `to_dict`/loader in `simulation_manager.py`; thread `owner_id` through the creation path; add the owner filter to `list_simulations` (mirroring Task 14 Step 4).

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_list_simulations_filters_by_owner -v`
Expected: PASS.

- [ ] **Step 5: Wire `backend/app/api/simulation.py`:** set `owner_id=current_user_id()` on creation; filter list endpoints with `owner_id=current_user_id(), include_all=is_admin()`; on detail/prepare/run/profiles/config endpoints, after loading state call `require_owner_or_admin(state.owner_id)` → 404 on `PermissionError`. (Combine with the existing `_resolve_simulation_dir` validation.)

- [ ] **Step 6: Run full suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/simulation_manager.py backend/app/api/simulation.py backend/tests/test_ownership.py
git commit -m "feat(auth): scope simulations to owner"
```

---

### Task 16: Report ownership

**Files:**
- Modify: `backend/app/services/report_agent.py` (ReportManager + Report), `backend/app/api/report.py`
- Test: `backend/tests/test_ownership.py`

**Interfaces:**
- Produces: `Report.owner_id`; `ReportManager.save_report` persists it; `ReportManager.list_reports(simulation_id=None, limit=50, owner_id=None, include_all=False)` filters.

- [ ] **Step 1: Write failing test** (append to `test_ownership.py`)

```python
def test_list_reports_filters_by_owner(tmp_path, monkeypatch):
    from app.services.report_agent import ReportManager, Report
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path), raising=False)
    r = Report(report_id="r1", simulation_id="s1")  # adapt to real ctor
    r.owner_id = "u1"
    ReportManager.save_report(r)
    assert all(x.owner_id == "u1" for x in ReportManager.list_reports(owner_id="u1"))
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_list_reports_filters_by_owner -v`
Expected: FAIL.

- [ ] **Step 3: Add `owner_id`** to `Report` + serialization in `report_agent.py`; add owner filter to `list_reports`. Set owner when the report is created (report-generation entry point in `api/report.py`/service).

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_list_reports_filters_by_owner -v`
Expected: PASS.

- [ ] **Step 5: Wire `backend/app/api/report.py`:** `get_report`, `get_report_by_simulation`, `get_report_progress`, `get_report_sections` → after load, `require_owner_or_admin(report.owner_id)` → 404; `list_reports` → owner filter; set owner on creation.

- [ ] **Step 6: Run full suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/report_agent.py backend/app/api/report.py backend/tests/test_ownership.py
git commit -m "feat(auth): scope reports to owner"
```

---

### Task 17: Graph ownership (Neo4j root)

**Files:**
- Modify: `backend/app/storage/neo4j_storage.py`
- Test: `backend/tests/test_ownership.py` (logic-level)

**Interfaces:**
- Produces: `Neo4jStorage.create_graph(name, owner_id=None)` sets `owner_id` on the graph root node; `get_graph_owner(graph_id) -> str | None`.

- [ ] **Step 1: Write failing test** (append to `test_ownership.py`) — pure-string check of the Cypher builder, avoiding a live DB:

```python
def test_create_graph_includes_owner_param(monkeypatch):
    import app.storage.neo4j_storage as ns
    captured = {}

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def run(self, query, **params):
            captured["query"] = query
            captured["params"] = params
            class R:  # minimal
                def single(self_inner): return {"graph_id": "g1"}
            return R()

    class FakeDriver:
        def session(self): return FakeSession()

    st = ns.Neo4jStorage.__new__(ns.Neo4jStorage)
    st._driver = FakeDriver()
    st.create_graph("G", owner_id="u1")
    assert captured["params"].get("owner_id") == "u1"
    assert "owner_id" in captured["query"]
```

(Adapt the fake to the real `create_graph` internals; the contract is that `owner_id` reaches the query params.)

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_create_graph_includes_owner_param -v`
Expected: FAIL (`create_graph() got unexpected kwarg owner_id`).

- [ ] **Step 3: Modify `create_graph`** in `neo4j_storage.py` to accept `owner_id=None`, include `owner_id: $owner_id` in the node-creation Cypher and pass `owner_id=owner_id`. Add `get_graph_owner(graph_id)` returning the root node's `owner_id`.

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_ownership.py::test_create_graph_includes_owner_param -v`
Expected: PASS.

- [ ] **Step 5: Wire** graph creation in `api/graph.py` `build_graph` to pass `owner_id=current_user_id()` (the project already enforces ownership, so this is defense-in-depth for direct graph access).

- [ ] **Step 6: Run full suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/storage/neo4j_storage.py backend/app/api/graph.py backend/tests/test_ownership.py
git commit -m "feat(auth): tag Neo4j graphs with owner_id"
```

---

# PHASE 5 — Migration

### Task 18: Ownership backfill migration script

**Files:**
- Create: `backend/scripts/migrate_ownership.py`
- Test: `backend/tests/test_migration.py`

**Interfaces:**
- Consumes: `service.count_admins`, `service.list_users`, `ProjectManager`, `SimulationManager`, `ReportManager`.
- Produces: `migrate_ownership.backfill(admin_id) -> dict` (counts per resource type); idempotent (skips objects that already have `owner_id`). A `__main__` block resolves the seed admin and runs `backfill`.

- [ ] **Step 1: Write failing test** in `backend/tests/test_migration.py`

```python
def test_backfill_assigns_admin_and_is_idempotent(tmp_path, monkeypatch):
    from app.models import project as pj
    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", str(tmp_path / "proj"), raising=False)
    p = pj.ProjectManager.create_project("legacy")  # owner_id None
    from backend.scripts import migrate_ownership  # adjust import path as needed
    counts = migrate_ownership.backfill("admin-id")
    assert pj.ProjectManager.get_project(p.project_id).owner_id == "admin-id"
    assert counts["projects"] >= 1
    # idempotent: second run changes nothing
    counts2 = migrate_ownership.backfill("admin-id")
    assert counts2["projects"] == 0
```

(Adjust the import to however scripts are importable; if needed add `backend/scripts/__init__.py` or import by path.)

- [ ] **Step 2: Run test, verify it fails**

Run: `cd backend && uv run pytest tests/test_migration.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Create `backend/scripts/migrate_ownership.py`**

```python
"""Backfill owner_id on pre-multi-user data, assigning it to the seed admin.

Usage: cd backend && uv run python scripts/migrate_ownership.py
Idempotent: objects that already have an owner are left untouched.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.project import ProjectManager


def backfill(admin_id):
    counts = {"projects": 0, "simulations": 0, "reports": 0}
    for p in ProjectManager.list_projects(limit=10_000, include_all=True):
        if getattr(p, "owner_id", None) is None:
            p.owner_id = admin_id
            ProjectManager.save_project(p)
            counts["projects"] += 1
    # Simulations
    from app.services.simulation_manager import SimulationManager
    sm = SimulationManager()
    for s in sm.list_simulations(include_all=True):
        if getattr(s, "owner_id", None) is None:
            s.owner_id = admin_id
            sm._save_simulation_state(s)
            counts["simulations"] += 1
    # Reports
    from app.services.report_agent import ReportManager
    for r in ReportManager.list_reports(limit=10_000, include_all=True):
        if getattr(r, "owner_id", None) is None:
            r.owner_id = admin_id
            ReportManager.save_report(r)
            counts["reports"] += 1
    return counts


def _resolve_admin_id():
    from app.auth.db import init_db
    from app.auth import service
    from app.config import Config
    init_db(Config.AUTH_DB_PATH)
    admins = [u for u in service.list_users() if u.role == "admin"]
    if not admins:
        raise SystemExit("No admin user exists; seed an admin first.")
    return admins[0].id


if __name__ == "__main__":
    admin_id = _resolve_admin_id()
    print("Backfilled:", backfill(admin_id))
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd backend && uv run pytest tests/test_migration.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: PASS (all phases green).

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/migrate_ownership.py backend/tests/test_migration.py
git commit -m "feat(auth): add idempotent ownership-backfill migration"
```

---

# PHASE 6 — Frontend

> Frontend has no test runner configured; verify each task manually in the browser (`npm run dev` in `frontend/`, backend running with a seeded admin). Keep changes small and committed per task.

### Task 19: Auth store + axios credentials + 401 interceptor

**Files:**
- Create: `frontend/src/stores/auth.js`
- Modify: `frontend/src/api/index.js`

**Interfaces:**
- Produces: `useAuth()` (or a reactive singleton) exposing `user`, `isAuthenticated`, `isAdmin`, `fetchMe()`, `login(email,password)`, `logout()`.

- [ ] **Step 1: Create `frontend/src/stores/auth.js`**

```javascript
import { reactive, computed } from 'vue'
import api from '@/api'

const state = reactive({ user: null, ready: false })

export function useAuth() {
  return {
    user: computed(() => state.user),
    ready: computed(() => state.ready),
    isAuthenticated: computed(() => !!state.user),
    isAdmin: computed(() => state.user?.role === 'admin'),
    async fetchMe() {
      try {
        const { data } = await api.get('/api/auth/me')
        state.user = data.user
      } catch { state.user = null }
      finally { state.ready = true }
    },
    async login(email, password) {
      const { data } = await api.post('/api/auth/login', { email, password })
      state.user = data.user
      return data.user
    },
    async logout() {
      try { await api.post('/api/auth/logout') } finally { state.user = null }
    },
  }
}
```

- [ ] **Step 2: Modify `frontend/src/api/index.js`** — add credentials + 401 handling:
  - set `withCredentials: true` on the axios instance;
  - in the response-error interceptor, on `error.response?.status === 401` redirect to `/login` (guard against redirect loop when already on `/login`).

```javascript
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})
// in the response error interceptor:
if (error.response && error.response.status === 401 &&
    window.location.pathname !== '/login') {
  window.location.href = '/login'
}
```

- [ ] **Step 3: Verify manually**

Run backend + `npm run dev`. In devtools, confirm requests send the cookie and that hitting an API route while logged out triggers a redirect to `/login`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/auth.js frontend/src/api/index.js
git commit -m "feat(auth): frontend auth store + cookie credentials + 401 redirect"
```

---

### Task 20: Login view + router guard

**Files:**
- Create: `frontend/src/views/Login.vue`
- Modify: `frontend/src/router/index.js`, `frontend/src/main.js`

- [ ] **Step 1: Create `frontend/src/views/Login.vue`** — email+password form calling `useAuth().login`, error display via `$t`, redirect to `route.query.redirect || '/'` on success.

```vue
<template>
  <form class="login" @submit.prevent="submit">
    <h1>{{ $t('auth.loginTitle') }}</h1>
    <input v-model="email" type="email" :placeholder="$t('auth.email')" required />
    <input v-model="password" type="password" :placeholder="$t('auth.password')" required />
    <p v-if="error" class="err">{{ $t('auth.invalidCredentials') }}</p>
    <button :disabled="busy">{{ $t('auth.login') }}</button>
  </form>
</template>
<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '@/stores/auth'
const email = ref(''); const password = ref(''); const error = ref(false); const busy = ref(false)
const route = useRoute(); const router = useRouter(); const auth = useAuth()
async function submit() {
  busy.value = true; error.value = false
  try { await auth.login(email.value, password.value); router.replace(route.query.redirect || '/') }
  catch { error.value = true } finally { busy.value = false }
}
</script>
```

- [ ] **Step 2: Add route + guard** in `frontend/src/router/index.js`:
  - add `{ path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { public: true } }`;
  - add `router.beforeEach`:

```javascript
import { useAuth } from '@/stores/auth'
router.beforeEach(async (to) => {
  const auth = useAuth()
  if (!auth.ready.value) await auth.fetchMe()
  if (to.meta.public) return true
  if (!auth.isAuthenticated.value) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !auth.isAdmin.value) return { path: '/' }
  return true
})
```

- [ ] **Step 3: Bootstrap** in `main.js`: nothing required beyond the guard (it lazily calls `fetchMe`). Ensure router is installed before mount.

- [ ] **Step 4: Verify manually** — logged out → any route redirects to `/login`; correct login → lands on target; wrong password → error message.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Login.vue frontend/src/router/index.js frontend/src/main.js
git commit -m "feat(auth): login view + router auth guard"
```

---

### Task 21: Header — current user + logout

**Files:**
- Modify: the header/nav component that hosts `LanguageSwitcher` (locate via `grep -rl LanguageSwitcher frontend/src`)

- [ ] **Step 1: Add** next to `<LanguageSwitcher/>`: show `auth.user.email` and a logout button calling `await auth.logout(); router.replace('/login')`. Show an "Admin" link (to `/admin/users`) when `auth.isAdmin`.

- [ ] **Step 2: Verify manually** — email + logout visible when logged in; logout returns to login; admin link only for admins.

- [ ] **Step 3: Commit**

```bash
git add frontend/src
git commit -m "feat(auth): header shows current user, logout, admin link"
```

---

### Task 22: Admin users page

**Files:**
- Create: `frontend/src/views/AdminUsers.vue`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: Create `AdminUsers.vue`** — fetch `GET /api/admin/users`; table with email/name/role/active; a create form (email, name, role, initial password) → `POST /api/admin/users`; per-row actions: toggle active (`/active`), change role (`/role`), reset password (`/reset-password`). Use `$t` for labels.

- [ ] **Step 2: Add route** `{ path: '/admin/users', name: 'AdminUsers', component: () => import('@/views/AdminUsers.vue'), meta: { admin: true } }`.

- [ ] **Step 3: Verify manually** — as admin: list/create/deactivate/reset works; as normal user: route redirects away and the API returns 403.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/AdminUsers.vue frontend/src/router/index.js
git commit -m "feat(auth): admin users management page"
```

---

# PHASE 7 — i18n

### Task 23: Add DE/EN auth strings

**Files:**
- Modify: `locales/de.json`, `locales/en.json`

**Interfaces:**
- Produces: an `auth` key group used by the frontend tasks: `loginTitle`, `email`, `password`, `login`, `logout`, `invalidCredentials`, plus `admin.users.*` labels (title, create, role, active, resetPassword, etc.).

- [ ] **Step 1: Add to `locales/en.json`**

```json
"auth": {
  "loginTitle": "Sign in",
  "email": "Email",
  "password": "Password",
  "login": "Sign in",
  "logout": "Sign out",
  "invalidCredentials": "Invalid email or password.",
  "admin": {
    "usersTitle": "User management",
    "create": "Create user",
    "name": "Name",
    "role": "Role",
    "active": "Active",
    "resetPassword": "Reset password",
    "deactivate": "Deactivate",
    "activate": "Activate"
  }
}
```

- [ ] **Step 2: Add the same keys to `locales/de.json`** (German values, Sie-form):

```json
"auth": {
  "loginTitle": "Anmelden",
  "email": "E-Mail",
  "password": "Passwort",
  "login": "Anmelden",
  "logout": "Abmelden",
  "invalidCredentials": "Ungültige E-Mail oder Passwort.",
  "admin": {
    "usersTitle": "Benutzerverwaltung",
    "create": "Benutzer anlegen",
    "name": "Name",
    "role": "Rolle",
    "active": "Aktiv",
    "resetPassword": "Passwort zurücksetzen",
    "deactivate": "Deaktivieren",
    "activate": "Aktivieren"
  }
}
```

- [ ] **Step 3: Verify key parity**

Run: `cd backend && uv run python -c "import json; a=json.load(open('../locales/en.json')); b=json.load(open('../locales/de.json')); print('auth' in a and 'auth' in b)"`
Expected: `True`. Confirm in the UI that login/admin labels render in both languages.

- [ ] **Step 4: Commit**

```bash
git add locales/de.json locales/en.json
git commit -m "feat(auth): add DE/EN i18n strings for login and admin"
```

---

## Final Verification

- [ ] **Run the full backend suite**

Run: `cd backend && uv run pytest tests/ -v`
Expected: all green (auth service/routes, rbac, ownership, admin, seed, migration, plus the prior security/validation tests).

- [ ] **Manual end-to-end**: start backend (with `ADMIN_EMAIL`/`ADMIN_PASSWORD` set) + frontend; log in as admin; create a normal user; as that user confirm only own projects/simulations/reports are visible and foreign IDs return 404; deactivate the user and confirm immediate lockout.

- [ ] **Run migration** on existing data: `cd backend && uv run python scripts/migrate_ownership.py` → confirm counts and that legacy data is now owned by the admin.

- [ ] **Update docs**: add a short "Authentication & accounts" section to `docs/security.md` (or a new `docs/auth.md`) describing login, roles, seeding, and the migration step; link it from `docs/README.md`.

---

## Self-Review Notes (spec coverage)

- Scope (multi-user+roles) → Phases 1-7. ✓
- Admin-only provisioning → Task 12 (no registration route). ✓
- ENV-seeded first admin → Task 10/seed.py. ✓
- SQLite/SQLAlchemy store → Tasks 1-2. ✓
- Email login → Tasks 4, 8. ✓
- Server-side revocable sessions (httpOnly) → Tasks 5, 8, 9. ✓
- Existing data → admin migration → Task 18. ✓
- Ownership + admin-sees-all + 404 on foreign → Tasks 13-17. ✓
- Frontend login/guard/admin UI → Tasks 19-22. ✓
- DE/EN parity → Task 23. ✓
