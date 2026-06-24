# Design: Account Management & Login (Multi-User + Roles)

**Date:** 2026-06-24
**Status:** Approved (design) — pending implementation plan
**Scope:** Add multi-user authentication, role-based authorization (admin/user),
and per-user data isolation to MiroFish-Offline, which is currently fully
single-tenant (no user concept).

---

## 1. Goals & Decisions

| Decision | Choice |
|----------|--------|
| Core scope | Multi-user with roles (admin/user) + per-user data isolation |
| User provisioning | Admin creates users; **no open registration** |
| First admin | Idempotent **ENV auto-seed** at startup (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) |
| User/credential store | **SQLite via SQLAlchemy** (`backend/uploads/auth.db`) |
| Login identity | **Email address** (unique) + optional display `name` |
| Session mechanism | **Server-side sessions**, opaque token in an httpOnly cookie, revocable |
| Existing global data | **Migrated to the seed admin** (`owner_id` backfill) |
| Auth library strategy | Lightweight standard building blocks (Flask-SQLAlchemy + passlib/bcrypt + thin custom session layer); extends existing `app/security.py` |

**Non-goals (YAGNI):** open self-registration, email-based password reset /
verification, OAuth/SSO, JWT, per-user API tokens, fine-grained permissions
beyond admin/user, organizations/teams.

**Builds on prior work:** the CVE-fix branch already added `app/security.py`
(a `before_request` hook), a CORS allowlist (no wildcard), and input validation.
This design extends that hook into the central auth resolver and the ownership
checks close the documented residual cross-tenant risk.

---

## 2. Architecture & Components

New backend package `backend/app/auth/`:

| Module | Responsibility |
|--------|----------------|
| `models.py` | SQLAlchemy models `User`, `Session` |
| `db.py` | Engine/session factory; SQLite at `backend/uploads/auth.db`; `init_db()` + lightweight migrations |
| `service.py` | Pure logic: `create_user`, `verify_password`, `start_session`, `resolve_session`, `revoke_session`, `revoke_user_sessions`, `set_role`, `set_active`, `reset_password` (bcrypt via passlib) |
| `routes.py` | Blueprint `/api/auth/*`: `POST /login`, `POST /logout`, `GET /me` |
| `admin_routes.py` | Blueprint `/api/admin/users/*` (admin-only): list / create / set-role / set-active / reset-password |
| `decorators.py` | `@login_required`, `@admin_required` |
| `ownership.py` | `require_owner_or_admin(resource_owner_id)` helper |
| `seed.py` | Idempotent admin seeding from ENV |

**Extension of `app/security.py`:** the existing `before_request` hook becomes
the central auth resolver — reads the session cookie → `resolve_session` →
sets `g.current_user`. Deny-by-default for `/api/*` (allowlist: `/api/auth/login`,
`/health`, `OPTIONS`). The legacy static `API_TOKEN` remains as an **optional
machine/fallback access path** (scripts), not required for the web UI.

**Frontend:** `Login.vue` view, router `beforeEach` guard, an `auth` store,
axios `withCredentials` + 401 interceptor, and an admin `AdminUsers.vue` page;
header shows current user + logout next to the existing `LanguageSwitcher`.

### Component boundaries
- `service.py` is pure and unit-testable without Flask (takes a db session).
- Routes are thin: validate input → call service → shape JSON.
- The request resolver is the single place that maps cookie → user.
- Ownership enforcement is one helper used uniformly across resource endpoints.

---

## 3. Data Model (SQLite via SQLAlchemy)

### `users`
| Field | Type | Notes |
|-------|------|-------|
| `id` | str (UUID) PK | Owner reference for all resources |
| `email` | str, unique, not null | Login identity; validated format |
| `name` | str, nullable | Display name |
| `password_hash` | str | bcrypt (passlib), cost configurable (default 12) |
| `role` | str | `admin` \| `user` (default `user`) |
| `is_active` | bool | Default true; deactivation blocks login + kills sessions |
| `created_at` / `updated_at` | datetime | |
| `created_by` | str (UUID), nullable | Admin who created the account |

### `sessions`
| Field | Type | Notes |
|-------|------|-------|
| `id` | str (UUID) PK | |
| `token_hash` | str, unique, indexed | Cookie holds the plaintext token; DB stores only SHA-256(token) |
| `user_id` | str FK → users.id | |
| `created_at` | datetime | |
| `expires_at` | datetime | Absolute lifetime (default 7 days) |
| `last_used_at` | datetime | Updated on each authenticated request |
| `user_agent` / `ip` | str, nullable | For future "active sessions" display |

**Indexes:** `users.email` unique; `sessions.token_hash` unique.

### Ownership on existing resources (no new SQLite schema)
Add an `owner_id` field to the existing stores:
- `project.json` → `owner_id`
- Simulation `state.json` → `owner_id`
- Report store → `owner_id`
- Neo4j graph root object → `owner_id` (set on `create_graph`)

**Security note:** the cookie token is a 32-byte random opaque value; only its
hash is stored, so a DB leak yields no usable sessions.

---

## 4. Authentication Flow

**`POST /api/auth/login`** `{email, password}`
1. Load user by email; check `is_active`; `verify_password` (bcrypt).
2. On success: generate 32-byte token → insert `sessions` row with
   `token_hash` and `expires_at`.
3. `Set-Cookie: mf_session=<token>; HttpOnly; SameSite=Lax; Path=/;
   Secure (when HTTPS); Max-Age=…`.
4. Body: `{ user: {id, email, name, role} }` — never hash/token in the body.
5. Failure → **401** with a generic message (no user-enumeration). Minimal
   rate-limit/lockout after N failures (small custom delay/temp-block; no extra
   dependency).

**Request resolution** (central `before_request`):
- Read cookie → hash token → `sessions` lookup → not expired & user active →
  set `g.current_user`, bump `last_used_at`.
- Otherwise, for `/api/*` (outside allowlist) → **401**. Frontend interceptor
  redirects to `/login`.

**`POST /api/auth/logout`** → delete session row + expire cookie.
**`GET /api/auth/me`** → current user (frontend bootstrap/guard).
**Revocation:** deactivating a user deletes all their sessions → immediate lockout.

---

## 5. Authorization (RBAC) & Data Isolation

- **Deny-by-default:** every `/api/*` route requires a valid session
  (allowlist: `/api/auth/login`, `/health`, `OPTIONS`).
- `@admin_required` guards `/api/admin/**` (user management).
- **Ownership enforcement** on resource endpoints (projects, simulations,
  reports, graphs):
  - **List**: filter to `owner_id == current_user.id`; **admin sees all**.
  - **Detail / mutation / delete**: `require_owner_or_admin(resource.owner_id)`;
    otherwise **404** (hide existence, not 403).
  - **Create**: `owner_id = current_user.id` set automatically.
- This ownership check also closes the documented residual cross-tenant risk
  (a user can no longer target another user's `simulation_id` / `project_id`).

---

## 6. Frontend

- **`auth` store** (small reactive module): holds `user`
  (`{id,email,name,role}`), `isAuthenticated`, `isAdmin`; bootstraps via
  `GET /api/auth/me` on app start.
- **`Login.vue`** — email/password form (i18n DE/EN), error display, redirect to
  the originally requested route after login.
- **Router guard** (`beforeEach`): routes protected by default
  (`meta.public` only for `/login`); unauthenticated → redirect
  `/login?redirect=…`; admin routes add `meta.admin`.
- **Axios** (`api/index.js`): `withCredentials = true`; response interceptor on
  **401** → clear store → redirect `/login`. Existing `Accept-Language`
  interceptor unchanged.
- **`AdminUsers.vue`** (admin-only): user table with create (email, name, role,
  initial password), change role, deactivate/activate, reset password. Reached
  from an admin entry in the header.
- **Header:** current user + logout button next to the `LanguageSwitcher`.
- All new strings added to `locales/de.json` + `locales/en.json` with key parity.

---

## 7. Seeding & Migration

**First-admin seeding (idempotent, at startup):** ENV `ADMIN_EMAIL` +
`ADMIN_PASSWORD` create the admin if no admin exists yet. A prominent warning is
logged if no admin is configured.

**Existing-data migration** — idempotent script
`backend/scripts/migrate_ownership.py`:
- Sets `owner_id = <seed-admin>` on every existing `project.json`, simulation
  `state.json`, report, and Neo4j graph root object where `owner_id` is missing.
- Logs the count of migrated objects; safe to run repeatedly.

---

## 8. Testing Strategy (TDD)

Continue the existing `backend/tests/` setup (`cd backend && uv run pytest tests/`):

| Area | Cases |
|------|-------|
| `auth/service` | hash/verify; session start/resolve/expiry/revoke; deactivation kills sessions |
| `auth/routes` | login success/failure (generic message); logout; `/me`; cookie attributes (HttpOnly/SameSite) |
| `rbac` | deny-by-default; `@admin_required` blocks non-admins; allowlist open |
| `ownership` | list filtered to owner; foreign access → 404; admin sees all; create sets owner |
| `migration` | global object → admin owner; idempotency |

All work developed test-first (RED → GREEN), consistent with the security-fix branch.

---

## 9. New Dependencies
- `Flask-SQLAlchemy`
- `passlib[bcrypt]`

(Rate-limiting kept minimal/custom — no extra dependency.)

## 10. New Configuration (.env)
| Variable | Purpose |
|----------|---------|
| `ADMIN_EMAIL` | Seed-admin email (idempotent auto-seed at startup) |
| `ADMIN_PASSWORD` | Seed-admin initial password |
| `SESSION_TTL_DAYS` | Optional; session absolute lifetime (default 7) |
| `BCRYPT_COST` | Optional; bcrypt cost factor (default 12) |

`SECRET_KEY` (already present) must be set to a strong value in production
(used for cookie signing / SameSite protections).

## 11. Implementation Phases (for the plan)
1. Auth DB + models + service (pure logic, TDD)
2. Login/logout/me routes + central session resolver in `security.py`
3. RBAC decorators + admin user-management API
4. Ownership fields + filtering/checks across projects/simulations/reports/graphs
5. Seeding (ENV) + data migration script
6. Frontend: login, router guard, auth store, axios, admin UI
7. i18n keys (DE/EN parity)
