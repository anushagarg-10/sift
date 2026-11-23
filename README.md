# Sift

**An AI data pipeline for customer feedback.** Upload a CSV, and Sift validates every row, stores it in PostgreSQL, uses an LLM to label each record with sentiment, category, urgency and a one-line summary, then shows the results in a dashboard. A built-in eval harness scores the model against a hand-labelled golden set, so prompt or model changes are measured instead of guessed.

`Next.js` · `TypeScript` · `Python` · `FastAPI` · `PostgreSQL` · `SQLAlchemy` · `Pydantic` · `Pytest` · `Docker` · `GitHub Actions` · `Claude API`

![Dataset view](docs/dataset.jpg)

## Highlights

- **Row-level CSV validation.** A bad line never sinks an upload. Missing fields, duplicate IDs, oversized text and malformed rows are rejected with a line number and a reason, and the clean rows go through.
- **Structured LLM output, validated twice.** The model is constrained to a JSON schema through Claude's structured outputs, then the result is checked again by a stricter Pydantic model (ranges, lengths, allowed labels). Output that fails is retried, and anything that still fails is stored as a failed record with a readable error, never silently dropped.
- **Pluggable providers.** `LLM_PROVIDER=anthropic` calls Claude. `LLM_PROVIDER=mock` runs a deterministic keyword classifier, so the whole app, the test suite and CI work offline with no API key. The mock also acts as a baseline the real model has to beat.
- **Evals as a quality gate.** `python -m app.evals` scores category accuracy, sentiment accuracy, urgency within one point, schema-valid rate, latency and token use. It exits non-zero when a metric drops below its threshold, and CI runs it on every push. Runs are also stored in Postgres and charted in the dashboard.
- **Telemetry per record.** Every enrichment stores the provider, model, attempts, input and output tokens and latency, so cost and speed are visible per dataset.
- **One command to run.** `docker compose up` starts Postgres, the API and the dashboard with health checks and startup ordering.

## Architecture

```
            ┌──────────────────────┐        ┌──────────────────────────┐
  CSV  ───▶ │  Next.js dashboard   │ ─────▶ │  FastAPI service          │
            │  (TypeScript)        │  REST  │                           │
            └──────────────────────┘        │  ingest.py   validate CSV │
                                            │  services.py enrich rows  │──▶ Claude API
                                            │  evals.py    score model  │    (structured JSON)
                                            └────────────┬─────────────┘
                                                         │ SQLAlchemy
                                                   ┌─────▼──────┐
                                                   │ PostgreSQL │ datasets, records,
                                                   └────────────┘ enrichments, eval_runs
```

Enrichment runs as a background task with a bounded thread pool, and the dashboard polls the dataset status until it finishes.

## Run it

**With Docker (recommended)**

```bash
docker compose up --build
```

Open http://localhost:3000, click **Use sample data**, then **Run enrichment**. API docs are at http://localhost:8000/docs.

To use Claude instead of the offline mock, copy `.env.example` to `.env`, add your `ANTHROPIC_API_KEY`, and restart:

```bash
cp .env.example .env
docker compose up --build
```

**Without Docker**

```bash
# backend (needs a Postgres, or set DATABASE_URL=sqlite:///./sift.db)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

## Tests and evals

```bash
cd backend
pytest                 # 35 tests: ingestion, validation and retry logic, Claude provider (offline), API, eval metrics
python -m app.evals --min-category 0.8 --min-sentiment 0.65
```

Tests use SQLite locally for speed. In CI they run against a real Postgres service container.

Current scores on the 24-case golden set:

| Provider | Category | Sentiment | Urgency ±1 | Schema valid |
| --- | --- | --- | --- | --- |
| `mock` keyword baseline | 88% | 71% | 92% | 100% |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/datasets` | Upload a CSV (multipart). Returns accepted and rejected rows. |
| `GET` | `/datasets` | List datasets |
| `GET` | `/datasets/{id}` | Dataset detail with aggregate stats |
| `GET` | `/datasets/{id}/records` | Records with filters: `sentiment`, `category`, `min_urgency`, `status`, `q`, paging |
| `POST` | `/datasets/{id}/enrich` | Start LLM enrichment in the background |
| `DELETE` | `/datasets/{id}` | Delete a dataset and its records |
| `POST` | `/evals/run` | Score the active provider on the golden set |
| `GET` | `/evals` | Eval run history |

## CSV format

| Column | Required | Notes |
| --- | --- | --- |
| `id` | yes | Unique within the file |
| `text` | yes | The feedback itself, up to 4,000 characters |
| `customer` | no | |
| `channel` | no | e.g. email, chat, phone |

## Project layout

```
backend/
  app/
    main.py          FastAPI routes
    ingest.py        CSV parsing and row validation
    services.py      enrichment pipeline, retries, stats
    evals.py         golden-set scoring and CLI gate
    llm/schema.py    model-facing and DB-facing Pydantic schemas
    llm/providers.py Claude and mock providers
    models.py        SQLAlchemy tables
  evals/golden.csv   hand-labelled eval cases
  tests/             Pytest suite
frontend/
  src/app/           dashboard pages (datasets, dataset detail, evals)
  src/lib/api.ts     typed API client
docker-compose.yml
.github/workflows/ci.yml
```
