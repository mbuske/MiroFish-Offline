# Security — Disclosed MiroFish CVEs & Hardening in this Fork

Several vulnerabilities were disclosed against upstream **MiroFish ≤ 0.1.2**
(`666ghj/MiroFish`). Because this repo descends from that codebase, each was
**verified against the current code** and then **remediated** on branch
`fix/security-cves`. This document records the verification evidence, the fix,
and the residual risk for each.

> **TL;DR:** all five issues were present (inherited from upstream, untouched by
> the Neo4j/i18n work). They are now mitigated by: debug OFF by default,
> loopback binding, non-wildcard CORS, opt-in API token auth, and strict
> validation/confinement of `simulation_id` and `platform`.

---

## Summary table

| # | Issue | CVE | CWE | Pre-fix status | Fix |
|---|-------|-----|-----|----------------|-----|
| 1 | Werkzeug debugger RCE | — | CWE-94 / CWE-215 | 🔴 Present | `DEBUG` default `False`; bind loopback |
| 2 | Werkzeug PIN info-disclosure | CVE-2026-7041 | CWE-200 | 🔴 Present | same as #1 + restricted CORS |
| 3 | Path traversal (`platform`/`simulation_id`) | CVE-2026-7059 | CWE-22 | 🔴 Present | validate + `safe_join` confinement |
| 4 | IPC command injection (unvalidated `simulation_id`) | — | CWE-74 / CWE-22 | 🔴 Present | validate `simulation_id` at runner chokepoint |
| 5 | Missing authentication on REST API | CVE-2026-7042 | CWE-287 / CWE-306 | 🔴 Present | opt-in bearer-token gate over `/api/*` |

---

## 1 & 2 — Werkzeug debugger: RCE + PIN info-disclosure (CVE-2026-7041)

**What it is.** Running Flask with `debug=True` enables the Werkzeug interactive
debugger. If the server is network-reachable, an attacker who triggers an
exception can reach the debugger console and, by defeating/abusing the PIN
handler, achieve **remote code execution** and **information disclosure**.

**Verification (pre-fix).**
- `backend/app/config.py` — `DEBUG = os.environ.get('FLASK_DEBUG', 'True')` →
  **defaulted to True**.
- `backend/run.py` — `host = os.environ.get('FLASK_HOST', '0.0.0.0')` (all
  interfaces) + `app.run(..., debug=debug)`.
- `Dockerfile` — `CMD ["npm", "run", "dev"]` (dev mode).
- `backend/app/__init__.py` — `CORS(app, resources={r"/api/*": {"origins": "*"}})`.

→ A network-reachable instance exposed the debugger on all interfaces.

**Fix.**
- `config.py`: `DEBUG` now defaults to **`False`** (must opt in via `FLASK_DEBUG=true`).
- `run.py`: `FLASK_HOST` now defaults to **`127.0.0.1`** (loopback). Exposing on
  a network is an explicit opt-in.
- `__init__.py`: CORS origins restricted to a configured allowlist (see #5),
  never `*`.

**Residual risk.** If an operator deliberately sets `FLASK_DEBUG=true` **and**
`FLASK_HOST=0.0.0.0`, the debugger is exposed again. `.env.example` warns
against this; production should run under `gunicorn`/`uwsgi`, not `npm run dev`.

---

## 3 — Path traversal via `platform` / `simulation_id` (CVE-2026-7059)

**What it is.** Unsanitized request parameters were used to build filesystem
paths, letting an attacker read/write outside the simulation data directory.

**Verification (pre-fix).**
- `backend/app/api/simulation.py` — `platform = request.args.get('platform','reddit')`
  used directly in `os.path.join(sim_dir, f"{platform}_profiles.json")`
  (`simulation_manager.py:get_profiles`).
- `simulation_id` flowed unsanitized into
  `os.path.join(OASIS_SIMULATION_DATA_DIR, simulation_id)` and
  `os.makedirs(..., exist_ok=True)` — traversal **and** arbitrary directory
  creation. Three direct-join sites in `simulation.py` (`_check_simulation_prepared`,
  profiles endpoint, config endpoint).

**Fix.** New module `backend/app/utils/validation.py`:
- `validate_simulation_id()` — allowlist regex `^sim_[A-Za-z0-9_-]{1,64}$`.
- `validate_platform()` — allowlist `{reddit, twitter}`.
- `safe_join(base, *parts)` — resolves the path and raises `ValueError` if it
  escapes `base` (defense in depth against `..`, absolute components, etc.).

Applied at every chokepoint:
- `SimulationManager._get_simulation_dir()` — validates + `safe_join` (covers
  state files, profiles, **and** the IPC dirs that live underneath).
- `SimulationManager.get_profiles()` — `validate_platform()` before any FS access.
- `simulation.py` — a new `_resolve_simulation_dir()` helper validates +
  confines at the three direct-join sites; invalid ids return **HTTP 400**.
- `SimulationManager.list_simulations()` — skips disk dirs whose names are not
  valid ids (so a stray directory cannot crash listing).

---

## 4 — IPC command injection via unvalidated `simulation_id`

**What it is.** Inter-process communication with running simulations is
**file-based**: commands are written to `<sim_dir>/ipc_commands/<id>.json` and
responses read from `<sim_dir>/ipc_responses/<id>.json`
(`backend/app/services/simulation_ipc.py`). The `<sim_dir>` is derived solely
from `simulation_id`, with no validation and no ownership check. An attacker
supplying an arbitrary `simulation_id` could target **another** simulation's IPC
channel — injecting interview/prompt commands cross-tenant or sending
`close_env` to remotely shut a simulation down.

**Verification (pre-fix).** `simulation_runner.py` built the IPC base via
`os.path.join(cls.RUN_STATE_DIR, simulation_id)` at ~14 sites, all feeding
`SimulationIPCClient(sim_dir)`.

**Fix.** New chokepoint `SimulationRunner._sim_state_dir(simulation_id)`
(validates + `safe_join`), and **all** `os.path.join(RUN_STATE_DIR, simulation_id)`
sites were routed through it. A traversal/garbage id now raises before any IPC
file is touched.

**Residual risk.** Within the *valid* `sim_*` namespace there is still no
per-user ownership model — this fork is **single-user/local** by design, so
cross-tenant isolation is provided by **authentication (#5)**, not an internal
tenant boundary. A multi-tenant deployment would need an ownership check
(simulation → owner) added on top.

---

## 5 — Missing authentication on the REST API (CVE-2026-7042)

**What it is.** `create_app()` registered every `/api/*` blueprint with **no
authentication** (CWE-287/306) and wide-open CORS — any network client could
drive graph building, simulations, and report generation.

**Verification (pre-fix).** `backend/app/__init__.py` had no auth hook; CORS
origins `*`; only a `/health` route and request logging.

**Fix.** New module `backend/app/security.py`:
- `register_auth(app)` installs a `before_request` hook. When `API_TOKEN` is
  configured, every `/api/*` request must present it via
  `Authorization: Bearer <token>` or `X-API-Key: <token>`; otherwise **HTTP 401**.
  Comparison uses `hmac.compare_digest` (constant-time). `OPTIONS` preflight and
  `/health` are exempt.
- `get_cors_origins()` parses `CORS_ORIGINS` (comma-separated), defaulting to
  localhost dev origins — **never** a wildcard.

**Opt-in by design.** With **no** `API_TOKEN` set, the API stays open and the
app logs a prominent startup **warning** — this preserves the zero-config local
single-user experience. Set `API_TOKEN` before exposing the service. Combined
with the loopback bind default (#1), the out-of-the-box posture is "local only".

**Residual risk.** A single shared static token (no per-user accounts, no
rotation/expiry). Adequate for a personal/local deployment; a shared multi-user
deployment should put it behind a real auth proxy.

---

## 6 — Multi-tenant access control & per-account branding

Beyond the CVE fixes, the `feat/account-management` branch added the
authentication, RBAC, and tenant-isolation model that now governs the API.
Security-relevant properties:

- **Deny-by-default API** — `/api/*` is rejected without a valid server-side
  session unless the path is on the public allowlist (login + the public
  branding reads). Sessions are revocable (logout, password reset, account
  suspension).
- **Tenant isolation** — resources carry an `account_id`; access requires
  `superadmin OR resource.account_id == current_user.account_id`, and a mismatch
  returns **404** (existence is hidden). List endpoints filter to the caller's
  account.
- **Account suspension** revokes the account's sessions and blocks login +
  session-resolution for its users.
- **Branding write isolation** — account admins write only their own account's
  branding (routes use the session's account id, never client input); superadmin
  routes are `@superadmin_required`; a plain user cannot write branding.
- **Public branding reads** (`/api/branding/config|logo|favicon?account=<slug>`)
  are intentionally public (pre-login branding) and expose only branding fields;
  asset paths are keyed by the resolved account id and filenames are normalized
  server-side (`<kind>.<ext>`, extension allowlisted) — no path traversal via
  slug or uploaded filename.

Full model and endpoint list: [`accounts-and-branding.md`](accounts-and-branding.md).

---

## Configuration reference (new security settings)

All in `.env` (see [`.env.example`](../.env.example)):

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_TOKEN` | _(empty)_ | When set, required on all `/api/*` requests. **Set before network exposure.** |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Allowed CORS origins (no wildcard). |
| `FLASK_DEBUG` | `False` | Werkzeug debugger. Local dev only — never on a network. |
| `FLASK_HOST` | `127.0.0.1` | Bind address. `0.0.0.0` only with `API_TOKEN` set + debug off. |

### Recommended posture
- **Local single-user (default):** no token needed; loopback + debug-off is safe.
- **Network-exposed:** set `API_TOKEN` to a strong random value, keep
  `FLASK_DEBUG=False`, set `CORS_ORIGINS` to your real frontend origin, and run
  behind `gunicorn`/`uwsgi` + a TLS-terminating reverse proxy. Update the Docker
  `CMD` away from `npm run dev` for production.

---

## Tests

Regression tests live in `backend/tests/` (run: `cd backend && uv run pytest tests/`):

| File | Covers |
|------|--------|
| `test_validation.py` | `validate_simulation_id`, `validate_platform`, `safe_join` (#3/#4) |
| `test_security.py` | token auth hook + CORS origins (#5, #2) |
| `test_app_integration.py` | `create_app` enforces auth, `/health` open (#5) |
| `test_simulation_paths.py` | `_get_simulation_dir` / `get_profiles` guards (#3/#4) |
| `test_api_path_resolver.py` | API-layer `_resolve_simulation_dir` (#3) |
| `test_runner_paths.py` | `SimulationRunner._sim_state_dir` IPC confinement (#4) |
| `test_list_simulations.py` | listing skips stray dir names (regression) |

All fixes were developed test-first (TDD): a failing test demonstrating the
vector/guard, then the minimal fix to pass it.

---

## CVE references
- CVE-2026-7041 — Werkzeug debugger PIN handler information disclosure.
- CVE-2026-7042 — Missing authentication for critical REST API functions.
- CVE-2026-7059 — Path traversal via unsanitized parameters in
  `backend/app/api/simulation.py`.
- (No CVE assigned) Werkzeug debugger RCE; IPC command injection.
