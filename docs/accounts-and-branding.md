# Accounts, Roles & Per-Account Branding

This document covers the multi-tenant account system, authentication/RBAC, and
the per-account branding system added on the `feat/account-management` branch.
These features build on each other and were delivered as three design→plan→build
cycles (account management → multi-tenancy → per-account branding & oversight).

---

## 1. Authentication & sessions

- User store: SQLite via Flask-SQLAlchemy at `backend/uploads/auth.db` (the same
  DB also holds accounts and branding).
- Passwords are hashed with **bcrypt**.
- Sessions are **server-side and revocable**: login issues an httpOnly cookie
  `mf_session`; the session row can be revoked (logout, account suspension,
  password reset), which immediately invalidates the cookie.
- API surface is **deny-by-default**: a `before_request` hook rejects any
  `/api/*` route not on the public allowlist unless the request carries a valid
  session. The public allowlist includes login and the public branding reads
  (see §4).
- Role decorators: `@login_required`, `@account_admin_required` (admits
  `account_admin` **and** `superadmin`), `@superadmin_required`.

## 2. Multi-tenancy (accounts)

Three roles:

| Role | `account_id` | Scope |
|------|--------------|-------|
| `superadmin` | `NULL` | Global. Manages accounts and each account's first admin. Sees everything. Owns no resources. |
| `account_admin` | an account | Manages users **within their own account**; full access to that account's resources. |
| `user` | an account | Full access to **their account's** resources (shared team workspace). |

- Resources (projects, simulations, reports, Neo4j graphs) carry an
  `account_id`, stamped at creation = creator's account. `owner_id` is retained
  as a "created-by" audit field only — access checks use `account_id`.
- Access rule: `superadmin OR resource.account_id == current_user.account_id`;
  a mismatch returns **404** (existence is hidden, not 403). List endpoints
  filter to the caller's account (superadmin sees all).
- Provisioning: superadmin creates an account + its first `account_admin`; the
  account_admin creates further users/admins within that account.
- **Suspension**: `POST /api/superadmin/accounts/<id>/active {active}` toggles an
  account. Suspending revokes the account's users' sessions, and login +
  session-resolution reject users of an inactive account.

### Superadmin oversight

- `GET /api/superadmin/accounts` — all accounts (with slug + user counts).
- `GET /api/superadmin/accounts/<id>/users` — an account's users, surfaced in the
  UI as a **read-only** drill-down (no mutation controls; management stays with
  the account's own admin).
- Suspend / reactivate as above.

## 3. Account slugs

- `Account.slug` is **unique, NOT NULL, URL-safe**. It is the public identifier
  used in branding URLs (§4) and the Accounts UI.
- Generated from the account name (`slugify`: NFKD→ASCII, lowercase,
  non-alphanumeric → `-`, collapsed/trimmed; empty → `account`), with a numeric
  collision suffix (`-2`, `-3`, …).
- Superadmin rename: `POST /api/superadmin/accounts/<id>/slug {slug}` — validates
  format `^[a-z0-9]+(?:-[a-z0-9]+)*$` and uniqueness (400 on invalid/duplicate).
- `/api/auth/me` returns `account_slug` so the SPA can request the right
  post-login branding.

## 4. Per-account branding

Each account has its own colors, logo, and favicon, with a **global default**
fallback.

### Data model
- `Branding.account_id` (FK→accounts.id, nullable, unique): one row per account;
  `account_id = NULL` is the **global default** row.
- Fields: `primary_color`, `accent_color`, `logo_filename`, `favicon_filename`,
  `updated_at`, `updated_by`.
- Assets: `backend/uploads/branding/<account_id>/{logo,favicon}.<ext>`; the
  default lives under `backend/uploads/branding/default/`. The stored filename is
  normalized server-side to `<kind>.<ext>` (extension allowlist-checked) — the
  uploaded filename is never used as a path.

### Resolution
`resolve_branding(account_id)` returns each field as **account value → default
value → None** (the frontend applies a hardcoded fallback such as `#FF4500`).
`resolve_account_id_for_slug(slug)` maps a slug to an account id; an unknown slug
resolves to `None` → the global default. No account's asset can be served for
another account — the asset path is keyed by the resolved account id, never by
client input.

### Who edits what
- **account_admin** → their own account, via `/api/account/branding`
  (+ `/logo`, `/favicon`). These routes use `current_account_id()` and never a
  client-supplied id. A caller with no account (a superadmin) gets **400**
  ("no account context") and must use the routes below.
- **superadmin** → any account, via
  `/api/superadmin/accounts/<id>/branding` (+ `/logo`, `/favicon`); and the
  **global default** via `/api/admin/branding` (+ `/logo`, `/favicon`).
- A plain `user` cannot write branding.

### Public read & pre-login branding
The reads are allowlisted (work before login):
- `GET /api/branding/config?account=<slug>` → branding merged over the default;
  no/unknown slug → global default.
- `GET /api/branding/logo?account=<slug>` and `…/favicon?account=<slug>` → the
  account's asset, else the default's, else 404.

The frontend branding store applies branding in three modes:
- `applyBranding()` (no arg) — reads `?account=<slug>` from the URL. Used at app
  startup so an account's branding shows **on the login screen** when the user
  visits `/?account=<slug>`.
- `applyBranding(null)` — loads the global default, ignoring the URL.
- `applyBranding(<slug>)` — loads that account's branding.

After login (`login()` / `fetchMe()`), the store re-resolves to the logged-in
user's account (`applyBranding(account_slug ?? null)`), overriding any stale URL
parameter. Branding is applied via CSS variables (`--brand-primary`,
`--brand-accent`), the favicon `<link>`, and the logo URL.

### UI
- **Appearance** page (`/admin/branding`): account-scoped — an account_admin
  edits their own account; a superadmin edits the global default. Reachable from
  the user menu for both roles.
- **Accounts** page (superadmin): slug column + inline rename, read-only users
  drill-down, and a per-account "Edit branding" panel.

## 5. Seeding & operations

- `ADMIN_EMAIL` / `ADMIN_PASSWORD` seed the **superadmin** (role=superadmin,
  `account_id=NULL`) when none exists. No default account is created — the
  superadmin logs in and creates the first account + its admin.
- **One-time `auth.db` wipe** is required when adopting these features (the
  schema adds `accounts`, `users.account_id`, `Account.slug`, and
  `Branding.account_id`). This is a fresh start — no data migration.
- No new third-party dependencies were introduced.

## 6. i18n

All new UI strings exist in both `locales/en.json` and `locales/de.json` (German
Sie-form). User-facing error messages prefer the backend's structured error and
fall back to a localized string. See [`i18n.md`](i18n.md) for the shared-locale
architecture.
