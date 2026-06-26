# Design: Per-Account Branding (+ slug) & Superadmin Oversight

**Date:** 2026-06-26
**Status:** Approved (design) — pending implementation plan
**Builds on:** `2026-06-25-multi-tenancy-accounts-design.md` (accounts, roles, isolation) and the singleton branding system from the account-management work. Branch: `feat/account-management`.

---

## 1. Goals & Decisions

| Decision | Choice |
|----------|--------|
| Branding scope | **Per-account**, with a **global default** fallback. Each account has its own colors/logo/favicon. |
| Field resolution | For each field (primary_color, accent_color, logo, favicon): **account value → global-default value → hardcoded fallback**. |
| Who edits | **account_admin** edits their **own** account's branding; **superadmin** edits **any** account's branding **and** the global default. |
| Pre-login branding | Each account has a URL **slug**; `?account=<slug>` makes that account's branding load **before login** (login screen). No slug → global default. After login → the logged-in user's account branding. |
| Superadmin oversight | Already has accounts list + suspend/reactivate + an account-users API. ADD: `slug` shown, and a **read-only per-account users drill-down** in the UI. (No new oversight backend needed.) |
| Migration | The existing singleton row becomes the **global default** (`account_id` NULL); add `Account.slug` (backfilled). Additive schema; a one-time `auth.db` wipe also works (pre-production). |

**Non-goals (YAGNI):** per-account custom domains, theme marketplaces, superadmin browsing of an account's resources in the UI (superadmin already sees all via the API; no new resource-browse UI in this scope), slug history/redirects.

---

## 2. Data Model

### `Account` — add `slug`
- `slug` (str, unique, not null, URL-safe). Generated from `name` (lowercase, non-alphanumeric → `-`, collapsed, trimmed), uniquified with a numeric suffix on collision. Superadmin-editable.

### `Branding` — singleton → per-account + default
- Repurpose: drop the fixed `id="singleton"` semantics. Rows are keyed by **`account_id`** (FK→accounts.id, nullable). **`account_id` NULL = the global default** row.
- Keep fields: `primary_color`, `accent_color`, `logo_filename`, `favicon_filename`, `updated_at`, `updated_by`. Add `account_id` (nullable, unique — one branding row per account, one default).
- Asset files: `backend/uploads/branding/<account_id>/logo.<ext>` and `favicon.<ext>`; the global default under `backend/uploads/branding/default/`.

---

## 3. Branding Resolution

`resolve_branding(account_id_or_None) -> dict` returns each field as: account row's value if set, else the global-default row's value, else None (frontend applies a hardcoded fallback like `#FF4500`). Returns `{primary_color, accent_color, logo_url, favicon_url}` where the urls point at the public serve routes carrying the resolving `account` slug (or default when none).

Slug path: `resolve_by_slug(slug) -> account_id` (None if slug unknown → use global default).

---

## 4. APIs

### Public read (allowlisted — work pre-login)
- `GET /api/branding/config?account=<slug>` → merged-over-default branding for that account; **no/unknown slug → global default**.
- `GET /api/branding/logo?account=<slug>` and `GET /api/branding/favicon?account=<slug>` → serve the resolved asset (account's, else default's, else 404).

### Account-admin branding — `/api/account/branding/*` (`@account_admin_required`, scoped to caller's account)
- `POST /api/account/branding` `{primary_color, accent_color}` → upsert the caller's account branding row (`account_id = current_account_id()`).
- `POST /api/account/branding/logo` and `/favicon` (multipart `file`) → store under the caller's account.
- **Guard:** these routes require a non-null `current_account_id()` → a caller with no account (i.e. a superadmin) gets **400** ("no account context") and must use the superadmin per-account / default routes below. This keeps the account-admin path unambiguous.

### Superadmin branding
- Global default: the existing `/api/admin/branding*` routes are repurposed to edit the **global default** row (account_id NULL). (Stay `@superadmin_required`.)
- Per-account (any account): `POST /api/superadmin/accounts/<id>/branding` (+ `/logo`, `/favicon`) → edit that account's branding row.

### Accounts (additions)
- `create_account(name, ...)` also generates a unique `slug`. `list_accounts()` returns `slug`. `POST /api/superadmin/accounts/<id>/slug {slug}` → superadmin rename (validates uniqueness + URL-safety). Suspend/reactivate (`/active`) and the account-users endpoint already exist.

### Allowlist
Add the three public `?account=` branding read routes to the security allowlist (they already are, by path — confirm `/config`, `/logo`, `/favicon` stay public; the `account` query param doesn't change the path).

---

## 5. Superadmin Oversight (mostly existing)

- Accounts list (exists) → add `slug` to the payload/column.
- Suspend/reactivate (exists: `/accounts/<id>/active`, + the login/session block) — surface as "Suspend"/"Reactivate".
- **Read-only users drill-down** (frontend): expand an account row → `GET /api/superadmin/accounts/<id>/users` → render the users read-only (email, name, role, active). No mutation controls here (management happens via the account's own admin).

---

## 6. Frontend

- **Branding store**: on startup, read `?account=<slug>` from `window.location` → `GET /api/branding/config?account=<slug>` → apply (CSS vars `--brand-primary`/`--brand-accent`, favicon link, logo url). Build the logo/favicon `<img>`/link URLs with the same `?account=<slug>`. After login, re-resolve to the logged-in user's account (call config again with the user's account slug, available from `/me` — add `account_slug` to the `/me` payload).
- **Appearance page** (`BrandingSettings.vue`): account-scoped — account_admin edits their own account via `/api/account/branding/*`; reachable from the "me" menu for account_admins. Color pickers + logo/favicon upload + live re-apply.
- **Superadmin**: keeps a **global-default** Appearance editor (existing page → points at `/api/admin/branding*` = default), and can edit a **specific account's** branding from the Accounts page ("Edit branding" per row → `/api/superadmin/accounts/<id>/branding*`).
- **"me" menu**: account_admin gains **Appearance** (own account); superadmin keeps Appearance (= global default) + per-account branding via Accounts.
- **Accounts page**: add `slug` column + the read-only users drill-down.
- `/me` payload: add `account_slug` (so the SPA can request the right post-login branding).

---

## 7. Migration & Testing

- **Schema**: add `Account.slug` and `Branding.account_id`. Convert the existing singleton branding row to the **global default** (`account_id` NULL). Backfill `slug` for any existing accounts (from name). Additive; a one-time `auth.db` wipe is also acceptable pre-production.
- **TDD (backend):**
  - slug generation (from name), uniqueness/collision suffix, URL-safety; superadmin rename validates.
  - `resolve_branding`: account value wins; falls back to default; falls back to None; `resolve_by_slug` maps slug→account (unknown→default).
  - public `GET /config?account=<slug>` returns account branding WITHOUT auth (pre-login); unknown/missing slug → default.
  - account-admin edits only own account (cross-account branding write impossible — routes use `current_account_id()`); superadmin edits any account + the default.
  - per-account asset storage/serve (`?account=<slug>` returns that account's logo, else default).
  - oversight: superadmin reads an account's users (read-only); account-admin cannot read another account's users (already covered; confirm).
- **Frontend**: `npm run build` clean; manual: visit `/?account=<slug>` pre-login → account branding on the login screen; account_admin Appearance edits own; superadmin edits a chosen account + default; Accounts page shows slug + read-only users drill-down.

---

## 8. Impact on existing code
- `Branding` model + `branding/service.py` (singleton → per-account + default + resolve/slug).
- `branding/routes.py` (public read takes `?account=`), `branding/admin_routes.py` (→ global default), new account-admin branding routes, new superadmin per-account branding routes.
- `accounts/models` (slug), `accounts/service` (slug gen + rename), `accounts/routes` (slug in payload, rename route).
- `auth/routes.py` `/me` (+ `account_slug`).
- Frontend: branding store (slug), `BrandingSettings.vue` (account-scoped), `SuperadminAccounts.vue` (slug column + users drill-down + per-account branding entry), router/me-menu, locales.

## 9. Implementation Phases (for the plan)
1. `Account.slug` (model + generation + uniqueness) + slug in accounts API + rename route + `/me` account_slug.
2. `Branding` per-account model + service (`resolve_branding`, `resolve_by_slug`, per-account upsert, default).
3. Public read API with `?account=<slug>` (config/logo/favicon) + allowlist confirm.
4. Account-admin branding API (`/api/account/branding/*`) + superadmin per-account branding API + repoint `/api/admin/branding*` to the global default.
5. Frontend branding store (slug pre-login + post-login re-resolve) + account-scoped Appearance page + me-menu.
6. Superadmin Accounts page: slug column + read-only users drill-down + per-account "edit branding".
7. i18n (DE/EN parity) for new strings.
