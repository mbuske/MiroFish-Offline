# Design: Multi-Tenancy (Accounts)

**Date:** 2026-06-25
**Status:** Approved (design) — pending implementation plan
**Builds on:** `2026-06-24-account-management-login-design.md` (auth, sessions, RBAC, per-user ownership). This spec **revises** that ownership/role model to add an account (tenant) layer.
**Branch:** continues on `feat/account-management` (the account-management work is unmerged and this reshapes it).

---

## 1. Goals & Decisions

| Decision | Choice |
|----------|--------|
| Tenant model | Introduce **Accounts** (organizations). Each account has many users. |
| Roles | Three tiers: **`superadmin`** (root, global) · **`account_admin`** (manages one account) · **`user`** |
| Resource visibility | **Account-wide shared** — every user in an account sees/works the same projects, simulations, reports, and graphs (team workspace). Isolation is at the **account** level. |
| Provisioning | **Superadmin** creates accounts and each account's first **account_admin**. The **account_admin** creates/manages users (and further account_admins) within **their own** account. |
| Existing data | **Fresh start** — accounts apply from now; no data migration. `backend/uploads/auth.db` is wiped once. |
| Single membership | One account per user (no multi-account membership). |
| Superadmin scope | Global administration only (account_id = null); administers accounts/users; does not own resources. Sees everything. |
| Branding | Stays **superadmin-only** (app-wide appearance). |

**Non-goals (YAGNI):** multi-account membership per user, account self-signup, billing/quotas, hard account deletion with cascade (v1 uses deactivate), cross-account resource sharing.

---

## 2. Data Model

### New `accounts` table (SQLite, same auth DB)
| Field | Type | Notes |
|-------|------|-------|
| `id` | str (UUID) PK | |
| `name` | str, not null | Display name (unique recommended) |
| `is_active` | bool | Default true; deactivation blocks the account's users from logging in |
| `created_at` | datetime | |
| `created_by` | str (UUID), nullable | Superadmin who created it |

### `users` changes
- Add `account_id` (str, FK→accounts.id, **nullable** — null only for `superadmin`).
- `role` values become: `superadmin` | `account_admin` | `user` (constants `ROLE_SUPERADMIN`, `ROLE_ACCOUNT_ADMIN`, `ROLE_USER`). The old `admin` role is removed (fresh start; no in-place migration).

### Resource changes (projects, simulations, reports, Neo4j graphs)
- Add **`account_id`** (the access dimension), stamped at creation = creator's `account_id`.
- **Keep the existing `owner_id`** as a "created_by" audit field (who created it). Access checks no longer use `owner_id`.

---

## 3. Access Model

Replaces the per-user `can_access`/`require_owner_or_admin` from the prior spec.

Helpers (in `app/auth/ownership.py` or a new `app/auth/accounts.py`):
- `is_superadmin()`, `is_account_admin()`, `current_account_id()`.
- `can_access_account(account_id) -> bool`: `is_superadmin() or (current user's account_id == account_id and account_id is not None)`.
- `require_account_access(resource_account_id)`: raises `PermissionError` if `not can_access_account(...)`.

Rules:
- **superadmin** → all accounts, all resources; account/user administration.
- **account_admin** → manages their account's users; full access to their account's resources.
- **user** → full access to their account's resources (shared team workspace).
- Resource endpoints: load resource → `require_account_access(resource.account_id)` → **404** on `PermissionError` (hide existence). List endpoints filter to `current_account_id()` unless superadmin (superadmin sees all).
- Creation stamps `account_id = current_account_id()` (and `owner_id = current_user.id`). A `user`/`account_admin` with `account_id is None` cannot create resources (only superadmin lacks an account, and superadmin doesn't create resources) → guarded.

---

## 4. APIs

### Superadmin — `/api/superadmin/*` (`@superadmin_required`)
- `GET /accounts` → list all accounts (with user counts).
- `POST /accounts` `{name}` → create account (201).
- `POST /accounts/<id>/active` `{active}` → enable/disable account (disabling revokes its users' sessions).
- `POST /accounts/<id>/admin` `{email, password, name}` → create the account's account_admin (user with role=account_admin, account_id=<id>).
- `GET /accounts/<id>/users` → list a given account's users.

### Account-admin — existing `/api/admin/users/*`, now **account-scoped** (`@account_admin_required`)
- `GET /users` → users of the caller's account only (superadmin may pass `?account_id=` to view any).
- `POST /users` `{email, password, name, role}` → create a user in the caller's account; `account_id` forced to caller's; `role` limited to `user`|`account_admin`.
- `POST /users/<id>/role|active|reset-password` → only for users in the caller's account (else 404).

### Decorators
- `@superadmin_required` (401 no user / 403 not superadmin).
- `@account_admin_required` (allows `account_admin` and `superadmin`; 403 for `user`).
- Existing deny-by-default `before_request` unchanged; allowlist unchanged.

---

## 5. Seeding (fresh start)

- ENV `ADMIN_EMAIL` / `ADMIN_PASSWORD` seed a **superadmin** (role=superadmin, account_id=null) when no superadmin exists.
- No default account is created. The superadmin logs in and creates the first account + its account_admin.
- One-time: wipe `backend/uploads/auth.db` so the schema (with `accounts` + `users.account_id`) is created fresh. (Document this in the run notes.)

---

## 6. Frontend

- **Role-aware "me" menu** entries:
  - superadmin → **Accounts** page (`/superadmin/accounts`) + Appearance (branding).
  - account_admin → **Users** page (`/admin/users`, scoped to their account).
  - user → no admin entries.
- **Accounts page** (superadmin): list accounts (name, active, user count), create account, create/assign account_admin, enable/disable.
- **Users page** (account_admin): unchanged UI, now implicitly account-scoped; header shows the account name.
- **Header/account context:** show the current account name (from `/api/auth/me`, which now returns `{id,email,name,role,account_id,account_name}`).
- Branding stays superadmin-only.

---

## 7. Impact on the prior (account-management) work

- `role` constants/usages: `admin` → split into `superadmin`/`account_admin`. Update decorators (`admin_required` → `account_admin_required` + new `superadmin_required`) and all call sites.
- Ownership layer: per-user `require_owner_or_admin(owner_id)` → account-scoped `require_account_access(resource.account_id)` across projects (`graph.py`), simulations (`simulation.py`, all guarded routes + the report sim-id routes), reports (`report.py`), and graphs (`neo4j_storage.py` `get_graph_owner` → add/keep `account_id`; new `get_graph_account`). List filters switch from `owner_id` to `account_id`.
- Seeding: superadmin instead of admin.
- `/api/auth/me` payload adds `account_id` + `account_name`.

---

## 8. Testing (TDD)

- **Account model/service:** create account, list, deactivate (revokes member sessions), user counts.
- **Roles/decorators:** `superadmin_required` blocks account_admin/user; `account_admin_required` allows account_admin+superadmin, blocks user.
- **Account-scoped resource access:** same-account user sees a resource; other-account user → 404; superadmin sees all; list filtered to account; creation stamps account_id.
- **Account-admin user-scoping:** account_admin lists/creates only within own account; cannot touch another account's user (404); role choices limited.
- **Superadmin provisioning:** create account, create its account_admin, deactivate account blocks login.
- **Seeding:** superadmin seeded from ENV; no default account.

---

## 9. New Configuration / Ops
- `ADMIN_EMAIL`/`ADMIN_PASSWORD` now seed the **superadmin** (semantics change; same vars).
- One-time `auth.db` wipe on upgrade (fresh start) — documented in run notes.
- No new dependencies.

---

## 10. Implementation Phases (for the plan)
1. Data model: `Account` model + `users.account_id` + role constants (superadmin/account_admin/user).
2. Account service (create/list/set_active/user-counts) + account-scoped ownership helpers + decorators (`superadmin_required`, `account_admin_required`).
3. Superadmin API (`/api/superadmin/accounts*`).
4. Account-scope the existing user-management API (`/api/admin/users*`).
5. Switch resource access (projects, simulations, reports, graphs) from owner-based to account-based; add `account_id` to resources; account-filter lists.
6. Seeding → superadmin; `/api/auth/me` returns account info.
7. Frontend: Accounts page (superadmin), account-scoped Users page, role-aware me-menu, account-name in header.
