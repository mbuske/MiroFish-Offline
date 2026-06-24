# LLM & Embedding Configuration

MiroFish-Offline talks to language models through an **OpenAI-compatible API**.
By default that endpoint is a local [Ollama](https://ollama.com) server, but the
same configuration accepts **any OpenAI-compatible provider** (OpenAI,
OpenRouter, Together, Groq, Mistral, Azure OpenAI, vLLM, LM-Studio, or a hosted
"modal"/remote model behind a Bearer token).

This document covers the three deployment modes (fully local, fully remote,
hybrid), the environment variables involved, and the embedding-service caveat.

---

## 1. The three consumers of model config

There are **three** distinct places the app reaches out to a model, and they do
**not** all read the same variables:

| Consumer | What it does | Reads |
|----------|--------------|-------|
| **LLM text generation** | Ontology generation, report agent, profile/simulation-config generation | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_NAME` |
| **OASIS / CAMEL-AI simulation** (Step 3) | Multi-agent social simulation | `OPENAI_API_KEY`, `OPENAI_API_BASE_URL` |
| **Embeddings** | Vector embeddings for hybrid graph search | `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL` |

> The OASIS simulator (CAMEL-AI) only understands the `OPENAI_*` variable names,
> which is why `.env` sets both `LLM_*` and `OPENAI_*` — usually to the same
> endpoint.

---

## 2. Environment variables

From `.env.example`:

```bash
# ===== LLM Configuration (OpenAI-compatible) =====
LLM_API_KEY=ollama                       # becomes the "Authorization: Bearer <key>" header
LLM_BASE_URL=http://localhost:11434/v1   # OpenAI-compatible base URL
LLM_MODEL_NAME=qwen2.5:32b               # model id at that endpoint

# ===== Neo4j =====
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=mirofish

# ===== Embeddings =====
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434 # NOTE: no /v1 — see §5

# ===== OASIS / CAMEL-AI =====
OPENAI_API_KEY=ollama
OPENAI_API_BASE_URL=http://localhost:11434/v1
```

- `LLM_API_KEY` is passed straight through as the OpenAI client's `api_key`,
  which the SDK sends as `Authorization: Bearer <value>`. For local Ollama any
  non-empty string works (`ollama`); for a real provider it's your secret key.
- `LLM_BASE_URL` must include the OpenAI route prefix (`/v1`).

---

## 3. Mode A — Fully local (default)

All three consumers point at a local Ollama instance. This is the out-of-the-box
configuration and needs no cloud access.

```bash
LLM_BASE_URL=http://localhost:11434/v1
OPENAI_API_BASE_URL=http://localhost:11434/v1
EMBEDDING_BASE_URL=http://localhost:11434
```

### Docker overrides

When the backend runs **inside** Docker alongside `ollama` and `neo4j`
containers, `localhost` is wrong — use the **service names**. `.env.example`
ships these as commented overrides:

```bash
LLM_BASE_URL=http://ollama:11434/v1
NEO4J_URI=bolt://neo4j:7687
EMBEDDING_BASE_URL=http://ollama:11434
OPENAI_API_BASE_URL=http://ollama:11434/v1
```

> ⚠️ **A common 500 cause** is a container trying to reach `localhost:11434` —
> inside a container that resolves to the container itself, not the Ollama
> service. Always switch to service names in Docker mode.

---

## 4. Mode B — Remote / hosted model (Bearer token)

LLM **text generation** fully supports a remote OpenAI-compatible endpoint via
`.env` alone — no code change. Point the LLM (and OASIS) variables at the
provider and supply the real key:

```bash
# Remote LLM for all text generation
LLM_API_KEY=sk-...your-real-key...
LLM_BASE_URL=https://your-endpoint.example.com/v1
LLM_MODEL_NAME=qwen2.5-72b-instruct      # whatever the provider exposes

# OASIS simulation against the same remote endpoint
OPENAI_API_KEY=sk-...your-real-key...
OPENAI_API_BASE_URL=https://your-endpoint.example.com/v1
```

This works with OpenAI, OpenRouter, Together, Groq, Mistral, Azure OpenAI,
vLLM, LM-Studio, and any other OpenAI-compatible API. The key becomes the
`Authorization: Bearer` header automatically.

---

## 5. Mode C — Hybrid (remote LLM + local embeddings)

A common and recommended setup: use a **strong hosted model for text
generation** but keep **embeddings local** (they're cheap and the embedding
service has a different protocol — see below).

```bash
# Remote LLM
LLM_API_KEY=sk-...
LLM_BASE_URL=https://your-endpoint.example.com/v1
LLM_MODEL_NAME=qwen2.5-72b-instruct
OPENAI_API_KEY=sk-...
OPENAI_API_BASE_URL=https://your-endpoint.example.com/v1

# Local embeddings (still via Ollama)
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434
```

### ⚠️ Embedding-service caveat

The `EmbeddingService` does **not** go through the OpenAI SDK. It makes a
**direct HTTP request to Ollama's `/api/embed` endpoint** and **does not send a
Bearer token**. Consequences:

- `EMBEDDING_BASE_URL` is an Ollama-style base (no `/v1`).
- You **cannot** simply repoint embeddings at a Bearer-authenticated OpenAI
  `/v1/embeddings` endpoint by editing `.env` — the auth header and URL shape
  won't match.
- To fully eliminate the local Ollama dependency you'd need a small code patch
  extending `EmbeddingService` to support the OpenAI-compatible
  `/v1/embeddings` route with Bearer auth. (Tracked as a possible enhancement.)

So in hybrid mode, **keep a local Ollama running for embeddings only**, even if
all text generation is remote.

---

## 6. Troubleshooting: HTTP 500 on `/api/graph/ontology/generate`

A 500 from ontology generation almost always originates in the LLM call, not the
endpoint logic. The request path:

```
POST /api/graph/ontology/generate
  → backend/app/api/graph.py   (validates input, extracts document text)
  → OntologyGenerator.generate()
  → self.llm_client.chat_json(...)   ← 500 surfaces here
```

`LLMClient` requires `LLM_API_KEY` from `Config` to initialize; a missing/blank
value or an unreachable `LLM_BASE_URL` fails here.

### Diagnostic checklist

1. **Network reachability** — from the backend container/host, can it reach
   `LLM_BASE_URL`? In Docker, confirm you used the **service name**, not
   `localhost` (§3).
2. **Credentials** — `LLM_API_KEY` non-empty; for remote providers, valid.
3. **Model availability** — `LLM_MODEL_NAME` is actually pulled/served at the
   endpoint (`ollama list`, or the provider's model id).
4. **JSON mode compatibility** — ontology generation calls `chat_json()`, which
   requests structured/`json_object` output. Small local models (e.g.
   `qwen2.5:7b`) can **fail JSON-mode validation**, producing a 500 even when the
   server is reachable. **Fixes:** use a larger local model (`qwen2.5:32b`) or a
   hosted model that reliably honors JSON mode (Mode B/C).
5. **Logging** — exception handlers historically returned raw tracebacks without
   structured logging, making diagnosis harder; check container logs
   (`docker compose logs backend`) for the underlying exception from
   `chat_json()`.

> **Most frequent root causes observed:** (a) `localhost` vs Docker service-name
> mismatch, and (b) a small local model failing `json_object` mode. Switching to
> a hosted model (Mode B) resolves both.

---

## 7. Quick reference

| Goal | Set |
|------|-----|
| Run everything locally | `LLM_*`, `OPENAI_*`, `EMBEDDING_*` → `localhost` Ollama |
| Same, inside Docker | swap `localhost` → service names (`ollama`, `neo4j`) |
| Use a hosted LLM | `LLM_API_KEY`=real key, `LLM_BASE_URL`/`OPENAI_API_BASE_URL`=provider `/v1`, `LLM_MODEL_NAME`=provider model |
| Remote LLM + local embeddings | Mode B vars + keep `EMBEDDING_BASE_URL` on local Ollama |
| Fix ontology 500 | check reachability → creds → model pulled → JSON-mode capable model |

See also: [`progress.md`](progress.md) for the Zep→Neo4j migration that
introduced `LLMClient` and `EmbeddingService`, and [`i18n.md`](i18n.md) for how
the selected UI language steers LLM-generated content.
