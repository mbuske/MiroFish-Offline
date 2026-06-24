# Repo Consolidation — Merging Three Source Repositories

`mbuske/MiroFish-Offline` is not a single-lineage fork. It is a **consolidation**
of three upstream repositories, each contributing a different ingredient:
the local-stack base, current upstream maintenance, and German terminology.
This document explains what each source contributed and *how* it was combined —
including why one of them was used as a **reference** rather than merged.

---

## 1. The git remotes

```
origin       https://github.com/mbuske/MiroFish-Offline.git    # ← this repo (the consolidation)
upstream     https://github.com/666ghj/MiroFish.git            # ① original project
offline      https://github.com/nikmcfly/MiroFish-Offline.git  # ② local-stack fork (our base)
mirofish-de  https://github.com/BEKO2210/MiroFish-DE.git       # ③ German variant (reference only)
```

| # | Repo | Role | Stack / language | Integration |
|---|------|------|------------------|-------------|
| ① | `666ghj/MiroFish` (`upstream`) | The **original, canonical** project | Zep Cloud + DashScope (Alibaba Qwen API); Chinese UI | **Ported** (selected commits) + used as **i18n key reference** |
| ② | `nikmcfly/MiroFish-Offline` (`offline`) | The **base** this repo is built on | Neo4j CE + Ollama; English UI; rebranded "MiroFish Offline" | **Direct ancestor** (history continues from it) |
| ③ | `BEKO2210/MiroFish-DE` (`mirofish-de`) | A **German variant** | Zep-based + Obsidian memory provider; German (Sie-form) UI | **Reference only** (terminology mined, not merged) |

> The repo's commit history descends from ② (the offline fork). ① and ③ were
> brought in selectively — ① by porting commits, ③ purely as a translation
> reference — because a straight merge of either would have dragged in
> incompatible architecture (Zep instead of Neo4j) or Chinese strings.

---

## 2. Why not just `git merge` all three?

Each source had divergence that made a blind merge wrong:

- **① `666ghj/MiroFish`** is still on the **Zep Cloud + DashScope** architecture
  and a **Chinese** UI. Merging its `main` would reintroduce the very stack the
  offline fork removed. So only *individual, still-relevant* commits were ported
  (maintenance fixes that are architecture-agnostic), and its already-i18n'd
  files were used as a *structural reference* for key names.
- **③ `BEKO2210/MiroFish-DE`** is **also Zep-based** and diverged further by
  adding an Obsidian/MemoryFactory memory provider. Merging it would conflict
  with the Neo4j storage layer. Its value was its **native German wording**, so
  that wording was *harvested* into `locales/de.json` and the rest left behind.

The result: a clean Neo4j/Ollama base (②), brought up to date with upstream
maintenance (①), made bilingual using both ① and ③ as references.

---

## 3. What each source contributed

### ② `nikmcfly/MiroFish-Offline` — the base (inherited history)

Everything below `e748f35` in the history comes from here. Key inherited work:

- Full backend migration to **Neo4j CE + Ollama** behind a `GraphStorage`
  abstraction (replacing Zep Cloud + DashScope). See [`progress.md`](progress.md).
- Frontend translated **Chinese → English**, rebranded to "MiroFish Offline".
- Earlier offline-fork fixes (CSS rendering, homepage copy, Docker/pyproject
  tweaks via PR #2).

This is the trunk; the consolidation work is layered on top.

### ① `666ghj/MiroFish` — upstream sync (ported commits) + i18n key reference

**(a) Ported maintenance commits.** Three still-relevant upstream commits were
ported onto an `upstream-sync` branch and folded into the i18n work. They are
architecture-agnostic, so they apply cleanly to the offline fork:

| This repo | Upstream original | What |
|-----------|-------------------|------|
| `e748f35` | `daec4b6` | `refactor`: add type hints and `FileParser.is_supported()` helper |
| `e11520b` | `3f4d561` | `fix(backend)`: constrain Python to `>=3.11,<3.13` |
| `afc0075` | `223b283` | `fix(security)`: raise axios floor to `^1.14.0`, patch transitive deps |

Each ported commit's message records `Port of upstream 666ghj/MiroFish <sha>,
adapted to the offline fork's dependency tree`. The axios patch in particular
was **adapted** — the offline fork's dependency tree differs (e.g. it now has
`vue-i18n`), so the lockfile was regenerated rather than copied.

**(b) i18n key reference.** Upstream had already converted its Vue components
from Chinese to `vue-i18n` (`$t('key')`) calls. Because the offline fork's
English literals sit at the **same structural positions** as upstream's
`$t()` calls, upstream was used as the **canonical source of key names**: an
agent compared each offline English string against upstream's already-converted
file and adopted the exact key, rather than inventing keys. Offline-specific
strings with no upstream match were left as-is and reported. This guaranteed
key-name correctness without guesswork.

### ③ `BEKO2210/MiroFish-DE` — German terminology reference

`locales/de.json` was **not** machine-translated from scratch. Instead, an agent
mined the **hardcoded German UI strings** from `mirofish-de` (its Views,
Components, and backend APIs) to reuse native, established German phrasing —
ensuring the German UI reads naturally and consistently.

Adaptations applied during the mining:

- The reference fork is **Zep-based**, so its terminology was **adapted to
  Neo4j** to match `en.json`'s intent (e.g. Zep wording → Neo4j wording).
- Constraints enforced: **Sie-form** (formal German), preserved technical nouns
  (`Neo4j`, `Ollama`, `LLM`, `GraphRAG`, `Reddit`, `Twitter`, `MBTI`), real
  umlauts (ä ö ü ß), all `{placeholder}` tokens preserved, and **exact key
  parity** with `en.json`.

See [`i18n.md`](i18n.md) for the resulting i18n system.

> **Not ported (known gap):** beyond its German wording, `mirofish-de` also added
> a **dynamic web-based configuration** feature ("Dynamische Konfiguration") that
> is **not** present in this repo. It is documented as a candidate enhancement in
> [§3a below](#3a-not-yet-ported-from--mirofish-de--dynamic-web-configuration).

---

## 3a. Not yet ported from ③ `mirofish-de` — dynamic web configuration

`mirofish-de` advertises a **"Dynamische Konfiguration"** as a headline feature:

> *"Memory-Provider, LLM-Provider und API-Einstellungen können nun direkt über
> das Web-Dashboard geändert und getestet werden."*

**Status in this repo: ABSENT.** It is neither implemented nor previously
documented. Verification (`mirofish-de/main` vs current `main`):

- ❌ No `backend/app/api/system.py` (this repo has only `graph.py`, `report.py`,
  `simulation.py`).
- ❌ `backend/app/config.py` is **read-only** — static `os.environ.get(...)`
  with no `save()`, and no `LLM_PROVIDER` / `LOCAL_LLM_*` / `MEMORY_PROVIDER`
  vars, `get_llm_config()`, `is_local_llm()`, or `mask_key()`.
- ❌ No settings panel in the frontend.

### What the feature consists of (in `mirofish-de`)

A collapsible **"⚙️ LLM-Konfiguration" panel** in `frontend/src/views/Home.vue`
(+331 lines) plus **three backend endpoints**, letting a user view, edit, test,
and persist configuration at runtime — no hand-editing `.env`, no restart.

**Frontend panel fields:**
- **Memory Provider** dropdown — `zep` / `obsidian` / `hybrid`
- **LLM Provider** dropdown — `openai` / `lmstudio` / `ollama`
- Conditional inputs: *Cloud* (API key, base URL, model) vs *Local* (base URL,
  model, optional key)
- Buttons: **Speichern** (save) and **Verbindung testen** (test connection)

**Backend endpoints (`system.py`, registered on `graph_bp`):**

| Endpoint | Purpose |
|----------|---------|
| `GET /system/status` | Return current config — **API keys masked** via `mask_key()` |
| `POST /system/config` | Persist settings: rewrite `.env` in place **and** update `os.environ` live |
| `POST /system/test-llm` | Connection test — sends a `"Say 'OK'"` prompt via `LLMClient.test_connection()`, returns provider/model/base_url/response |

**Config additions (`config.py`):** `LLM_PROVIDER`, `LOCAL_LLM_BASE_URL/MODEL_NAME/API_KEY`,
`MEMORY_PROVIDER`; helpers `get_llm_config()` (returns the active provider's
triple), `is_local_llm()` (`lmstudio`/`ollama`/`local`), and `Config.save(data)`
(in-place `.env` rewrite with auto-correction that appends `/v1` to local URLs).

**Security logic (worth keeping if ported):**
- `mask_key()` masks keys in responses (`abcd...****wxyz`).
- `save()` **skips masked values** (`***` / `...****`) so a masked display value
  can never overwrite the real key in `.env`.
- `validate()` **warns** (does not block startup) when a key is masked.

### Adaptation needed before porting to the offline fork

`mirofish-de` is **Zep-based** with a **dual-provider** model (cloud LLM vs.
separate `LOCAL_LLM_*`; memory `zep`/`obsidian`/`hybrid`). The offline fork
already unifies "local vs. cloud" behind a **single OpenAI-compatible `LLM_*`**
config (any endpoint via `LLM_BASE_URL`) and uses **Neo4j as the only memory
backend**. So a port would need:

- **Drop the Memory-Provider dropdown** (Neo4j is the only backend) — or repurpose
  it to expose **Neo4j connection fields** (`NEO4J_URI/USER/PASSWORD`).
- **Drop the `LOCAL_LLM_*` split** — one `LLM_*` set plus `EMBEDDING_*` covers
  both local and remote (see [`llm-configuration.md`](llm-configuration.md)).
- **Reuse directly:** the `test-llm` endpoint and `mask_key()` masking logic.
- Add an `EmbeddingService` connection test alongside `test-llm`, since
  embeddings use a separate endpoint/protocol (see
  [`llm-configuration.md` §5](llm-configuration.md#5-mode-c--hybrid-remote-llm--local-embeddings)).

---

## 4. How it was assembled (branch flow)

```
② nikmcfly/MiroFish-Offline (base history)
        │
        │  (313fe64) force English-only report output — remove Chinese fallback
        ▼
   ┌─────────────── upstream-sync branch ───────────────┐
   │  port ① 666ghj/MiroFish maintenance commits:       │
   │   e748f35 type hints · e11520b py constraint ·      │
   │   afc0075 axios security                            │
   └───────────────────────┬────────────────────────────┘
                           │  (continues on)
   ┌──────────────── feat/i18n-de branch ───────────────┐
   │  defb78b  vue-i18n infra (German default, EN fallback)
   │  9a1711b  de.json  ← ③ BEKO2210/MiroFish-DE terminology
   │           en.json  ← aligned to offline branding
   │  721ba94  convert Vue components ← ① 666ghj key reference
   │  46f41ac  backend locale.py + LLM language injection
   │  b8a2b4b  close remaining frontend string gap
   └───────────────────────┬────────────────────────────┘
                           │
                           ▼
        PR #1 → merge into main  (f357a40)
```

So all three sources converge in **PR #1** (`feat/i18n-de` → `main`, merged at
`f357a40`):
- **②** is the trunk it branches from,
- **①** supplies the ported maintenance commits *and* the i18n key names,
- **③** supplies the German wording in `de.json`.

---

## 5. Reproducing / maintaining the setup

To re-establish the remotes for future syncs:

```bash
git remote add upstream    https://github.com/666ghj/MiroFish.git
git remote add offline     https://github.com/nikmcfly/MiroFish-Offline.git
git remote add mirofish-de https://github.com/BEKO2210/MiroFish-DE.git
git fetch --all
```

Guidance for future syncs, consistent with how this consolidation was done:

- **From `upstream` (①):** cherry-pick/port *individual* architecture-agnostic
  commits (security, type hints, version pins). Do **not** merge `upstream/main`
  wholesale — it would reintroduce Zep + Chinese. Record `Port of upstream
  666ghj/MiroFish <sha>` in the commit message and re-run `npm audit fix` if it
  touches `package.json`.
- **For new languages / German updates (③):** treat `mirofish-de` as a
  **terminology reference**, not a merge source (it is Zep-based). Mine wording,
  adapt Zep→Neo4j terms, keep key parity with `en.json`. See
  [`i18n.md` §8](i18n.md#8-how-to-add-a-new-language).

---

## 6. Summary

| Question | Answer |
|----------|--------|
| What is the base? | ② `nikmcfly/MiroFish-Offline` (Neo4j + Ollama, English) — direct history |
| What came from the original? | ① `666ghj/MiroFish` — 3 ported maintenance commits + i18n key names |
| What came from the German fork? | ③ `BEKO2210/MiroFish-DE` — German terminology for `de.json` |
| Why references instead of merges for ① and ③? | Both are Zep-based / Chinese; a full merge would conflict with the Neo4j stack and reintroduce removed code |
| Where did they converge? | PR #1 → `main` (`f357a40`) |
| What is NOT yet ported? | ③'s **dynamic web configuration** (`/system/*` endpoints + settings panel) — absent here; see [§3a](#3a-not-yet-ported-from--mirofish-de--dynamic-web-configuration) |
