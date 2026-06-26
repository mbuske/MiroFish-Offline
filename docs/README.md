# MiroFish-Offline — Documentation

This `docs/` directory holds the engineering documentation for the offline fork.

## Contents

| Document | What it covers |
|----------|----------------|
| [`repo-consolidation.md`](repo-consolidation.md) | **How the three source repos were merged** — the local-stack base (`nikmcfly/MiroFish-Offline`), ported upstream maintenance + i18n key reference (`666ghj/MiroFish`), and German terminology reference (`BEKO2210/MiroFish-DE`); branch flow into PR #1; and why two sources were referenced rather than merged. |
| [`progress.md`](progress.md) | The **Zep Cloud → Neo4j + Ollama migration** — the storage/LLM abstraction layers (`LLMClient`, `EmbeddingService`, `GraphStorage`/`Neo4jStorage`), phase-by-phase task log, and file create/modify/delete inventory. |
| [`i18n.md`](i18n.md) | The **bilingual German/English internationalization system** — shared `locales/`, vue-i18n frontend, custom backend resolver, the background-thread locale pattern, and LLM language steering. |
| [`security.md`](security.md) | **Disclosed MiroFish CVEs & hardening** — verification + fixes for the Werkzeug debugger RCE, CVE-2026-7041 (PIN info-disclosure), CVE-2026-7059 (path traversal), IPC command injection, and CVE-2026-7042 (missing API auth); new `API_TOKEN`/`CORS_ORIGINS`/`FLASK_DEBUG`/`FLASK_HOST` settings. |
| [`llm-configuration.md`](llm-configuration.md) | **LLM & embedding configuration** — local / remote / hybrid deployment modes, the three model-config consumers, the embedding-service caveat, and the ontology-generation **500-error troubleshooting** guide. |
| [`accounts-and-branding.md`](accounts-and-branding.md) | **Accounts, roles & per-account branding** — the multi-tenant account model (superadmin / account_admin / user), revocable sessions + RBAC, account-scoped resource isolation, superadmin oversight, URL-safe account slugs, and the per-account branding system with `?account=<slug>` pre-login branding and a global-default fallback. |

## Change log of recent fork work

This repo is a **consolidation of three source repositories** — the
`nikmcfly/MiroFish-Offline` local-stack base, selected maintenance + i18n key
references from the original `666ghj/MiroFish`, and German terminology from
`BEKO2210/MiroFish-DE`. See [`repo-consolidation.md`](repo-consolidation.md) for
the full breakdown. Beyond the major features documented above, recent
maintenance changes:

### Bilingual EN/DE i18n (PR #1, merged `f357a40`)
Full German default + English fallback across UI, API responses, and
LLM-generated content. See [`i18n.md`](i18n.md).

### Zep → Neo4j refactor
Replaced the Zep Cloud knowledge-graph backend with local Neo4j CE + Ollama
behind a `GraphStorage` abstraction. See [`progress.md`](progress.md).

### Accounts, RBAC & per-account branding (`feat/account-management`)
Added multi-user authentication with revocable server-side sessions, a
three-tier role model (superadmin / account_admin / user), account-level
multi-tenancy with per-account resource isolation, superadmin oversight
(read-only user drill-down + account suspend/reactivate), URL-safe account
slugs, and per-account branding (colors/logo/favicon) with `?account=<slug>`
pre-login branding over a global default. See
[`accounts-and-branding.md`](accounts-and-branding.md). Requires a one-time
`backend/uploads/auth.db` wipe (fresh-start schema; no data migration).

### Security & dependency maintenance (upstream ports)
- **`afc0075`** `fix(security)` — raised the axios floor to `^1.14.0` and ran a
  non-breaking `npm audit fix`, patching rollup, picomatch, form-data, postcss
  and vite. Reduced `npm audit` from 5 vulnerabilities (4 high, 1 moderate) to
  1 low (esbuild dev-server, Windows-only, needs a breaking change — left out).
  Port of upstream `666ghj/MiroFish 223b283`, adapted to the offline fork's
  dependency tree.
- **`e11520b`** `fix(backend)` — constrained `requires-python` to `>=3.11,<3.13`
  in `backend/pyproject.toml` to avoid unsupported interpreter versions. Port of
  upstream `3f4d561`.
- **`e748f35`** `refactor` — added type hints and a `FileParser.is_supported()`
  helper.

### Known gap — dynamic web configuration (not yet ported)
`mirofish-de` ships a **"Dynamische Konfiguration"** feature (edit/test LLM,
memory and API settings live from the web dashboard via `/system/status`,
`/system/config`, `/system/test-llm`). It is **not present** in this repo —
neither implemented nor merged. Full breakdown and an adaptation plan for the
Neo4j/Ollama stack are in
[`repo-consolidation.md` §3a](repo-consolidation.md#3a-not-yet-ported-from--mirofish-de--dynamic-web-configuration).

### Report-agent fixes
- **`313fe64`** — forced English-only output in the report agent by removing a
  hardcoded Chinese language fallback and examples. (Superseded by the i18n
  `llmInstruction` mechanism — see [`i18n.md` §6](i18n.md#6-llm-language-steering).)
- **`f2e8e20`** — inject `GraphToolsService` into `ReportAgent` *before* the
  background thread starts (DI ordering fix).
- **`b372c40`** — pinned Neo4j to `>=5.18` for relationship vector search
  support.
