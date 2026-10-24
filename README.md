# BizSproutAI Brain

A small, standalone **FastAPI** service that turns a founder's business idea into structured, region-aware guidance using OpenAI. It is one of the three BizSproutAI repositories and is deployed and scaled independently of the app frontend and the Supabase backend.

> A repository, branch, deployment, and configured API integration are different things. This service only produces advisory output; founder review is still required, and a readiness score is not proof of demand or a guarantee of revenue.

## What it does

The service exposes three JSON endpoints that each call an OpenAI chat model with a purpose-built system prompt and return parsed JSON:

| Method & path | Purpose |
|---|---|
| `POST /api/validate` | Scores and critiques a business idea (demand, economics, distribution, moat) and returns a GO/FIX/STOP status with fixes. |
| `POST /api/generate_roadmap` | Produces a region-specific "build plan" (legal, infrastructure, launch) for a validated idea. |
| `POST /api/generate_report` | Produces a due-diligence report; if no roadmap is supplied it generates one internally first. |
| `GET /` | Health check — returns `{ "status": "BizSproutAI Brain is Online" }`. |

All model output is requested as JSON (`response_format={"type": "json_object"}`) and parsed before returning.

## How requests are shaped and bounded

- **Input validation:** request bodies are Pydantic models with length bounds (e.g. `idea` must be 5–1000 characters). Malformed input is rejected with a 422 before any model call.
- **Prompt-injection defense:** user text is wrapped in `<user_idea>…</user_idea>` tags, and the system prompts instruct the model never to follow instructions contained in that user text.
- **Rate limiting:** a per-IP sliding window (default **10 requests / 60 seconds**) guards every `/api/*` endpoint. The client IP is derived from `cf-connecting-ip` → `true-client-ip` → the last hop of `x-forwarded-for` → the socket peer.
  - **Caveat:** this limiter is **in-process and in-memory**. It does not coordinate across multiple instances/workers, so horizontal scaling weakens it. For multi-instance abuse protection, put a shared limiter (gateway/CDN or a shared store) in front of the service.
- **CORS:** origins come from the `ALLOWED_ORIGINS` env var (comma-separated). The default includes localhost dev origins plus the production site; **set `ALLOWED_ORIGINS` explicitly in production and exclude localhost.**

## Configuration

Secrets are read from the environment only; nothing is committed. Copy a local `.env` (git-ignored) for development.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | **yes** | — | Server-side only. Never expose it to a browser. |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | Override the chat model. |
| `OPENAI_TIMEOUT_SECONDS` | no | `45.0` | Per-request timeout to OpenAI. |
| `ALLOWED_ORIGINS` | no (prod: **yes**) | localhost + `https://bizsproutai.com`, `https://www.bizsproutai.com` | Comma-separated CORS allowlist. |

## Run locally

Requires **Python 3.11**.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # or put it in a git-ignored .env
uvicorn main:app --reload --port 8000
```

Then:

```bash
curl -s localhost:8000/                      # health check
curl -s -X POST localhost:8000/api/validate \
  -H 'content-type: application/json' \
  -d '{"idea":"A meal-prep service for busy nurses in Miami"}'
```

Interactive docs are available at `http://localhost:8000/docs` (FastAPI/Swagger UI).

## Deployment

Deployed as a Render web service (`render.yaml`): Python runtime, `pip install -r requirements.txt`, started with `uvicorn main:app --host 0.0.0.0 --port $PORT`. `OPENAI_API_KEY` is set in the environment (`sync: false`), `PYTHON_VERSION` is pinned to 3.11.

> The service name in `render.yaml` is historical; this repository is the Brain service. Confirm the actual deployed service and environment before promotion.

## CI

`.github/workflows/python-ci.yml` runs on pushes to `main`/`staging` and PRs to `main`: it installs dependencies, runs `python -m py_compile main.py` (syntax), and smoke-tests that the FastAPI app imports (`from main import app`) with a mock key.

## Repository responsibilities

| Repository | Responsibility |
|---|---|
| [bizsproutai-frontend](https://github.com/kreyolthrive/bizsproutai-frontend) | React/Vite browser application and UI |
| [bizsproutai-backend](https://github.com/kreyolthrive/bizsproutai-backend) | Supabase migrations, Edge Functions, authorization, persistence |
| **bizsproutai-brain** | This FastAPI/OpenAI advisory service |

## Security notes

- Keep `OPENAI_API_KEY` server-side; never place it in client code or a `VITE_*` variable.
- The in-memory rate limiter does not establish multi-instance abuse protection (see above).
- Set a tight `ALLOWED_ORIGINS` in production.
