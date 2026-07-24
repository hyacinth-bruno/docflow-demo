# DocFlow — async document processing demo

A small, working slice of the pipeline pattern described in NotarNow's job posting:
**upload → object storage → async queue → extraction worker → DB → real-time
progress → search.** Built to be honest about what's simulated vs. real — see
the mapping table below.

Live locally in a few minutes:

```bash
# backend — needs a MongoDB instance. Easiest: a free Atlas cluster
# (see "Running against real MongoDB" below), or a local mongod.
cd backend
cp .env.example .env   # fill in MONGODB_URI
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000, drop in a PDF, and watch it move through
`queued → processing → done` in real time, with the extracted fields and a
search box over everything you've uploaded.

## Why this shape

The JD calls out an end-to-end pipeline (uploads → S3 → async processing →
DB → semantic search), event-driven processing (SQS → Lambda, idempotency,
retries, DLQs), real-time UX (WebSocket/SSE), and typed extraction into
Pydantic models. Rather than write a slide about those concepts, this is a
runnable example of the same shapes, small enough to read end to end in one
sitting.

## What's real vs. simulated

| Piece | In this demo | In production (NotarNow) |
|---|---|---|
| Object storage | Local disk (`backend/app/uploads/`) | S3 |
| Queue + worker | `asyncio.Queue` + in-process worker (`queue_sim.py`) | SQS + Lambda |
| Retry / backoff / DLQ | Implemented for real — exponential backoff, max attempts, DLQ list (`admin/dlq`) | Same logic, backed by SQS redrive policy |
| Idempotency | Content-hash based dedup, enforced with a unique Mongo index | Same pattern, via SQS message dedup ID or an idempotency table |
| **Database** | **REAL: MongoDB via [Odmantic](https://art049.github.io/odmantic/)'s `AIOEngine`** (Motor underneath) — same library the JD names ("MongoDB (engine)"). Repository layer in `repository.py` isolates all query logic from the routes. Point `MONGODB_URI` at an Atlas cluster and this is exactly what runs in prod | MongoDB Atlas |
| Real-time updates | Server-Sent Events (`/documents/{id}/events`) | SSE or WebSocket, same event contract |
| Field extraction | Heuristic/regex by default. If `ANTHROPIC_API_KEY` is set, calls the real Claude API and parses JSON straight into the same Pydantic model (`extraction.py`) | Azure Document Intelligence / Textract / multimodal LLM, same typed-output contract |
| Search | Naive term-overlap scoring (`search.py`), querying real Mongo documents via the repository | **Upgrade path**: MongoDB Atlas Vector Search — embed `extracted.summary` at write time (e.g. Voyage AI, which MongoDB now owns, or OpenAI embeddings), store the vector alongside the document, replace `score_documents()` with a `$vectorSearch` aggregation stage. The repository/route layers wouldn't change, only what's inside `search.py` |

The point of the table: every "simulated" piece was built behind the same
interface its production counterpart would have, so swapping one for the
real service wouldn't touch the callers around it — MongoDB is the proof
of that, since it went from simulated to real without changing a single
route signature.

### Testing

`backend/tests/` runs a real integration suite (upload → queue → extract →
persist → search → idempotency → 404s) against the actual FastAPI app and
repository layer. Since a live Atlas cluster isn't reachable from every dev
environment, tests substitute `mongomock-motor` for the Mongo client —
same repository code, same Odmantic models, fake in-memory backend. One
documented shim works around a known mongomock/Odmantic session
incompatibility ([mongomock#700](https://github.com/mongomock/mongomock/issues/700));
it's isolated to `tests/conftest.py` and never touches the production path.

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

### Running against real MongoDB

1. Create a free Atlas cluster at mongodb.com/atlas
2. Copy `backend/.env.example` to `backend/.env`, fill in `MONGODB_URI`
3. `pip install -r requirements.txt && uvicorn app.main:app --reload`

## What's intentionally *not* in this demo

- **Stripe billing** — I didn't want to fake a subscription lifecycle I
  haven't actually built. See [`docs/BILLING_DESIGN.md`](docs/BILLING_DESIGN.md)
  for how I'd approach schedules/proration/webhooks instead, based on how
  I've handled similarly stateful async flows.
- **Auth** — out of scope for a demo this size; NextAuth/Cognito is a known,
  well-documented pattern, not the part worth spending the few hours on.

## Stack

Backend: FastAPI (async), Pydantic v2, pypdf, httpx.
Frontend: Next.js 15 (App Router), TypeScript, native `EventSource` for SSE
(no extra library — this is the same primitive a WebSocket-based real-time
feature would sit next to).

## About me

Built by Bruno Mbachu — [linkedin.com/in/bruno-mbachu](https://linkedin.com/in/bruno-mbachu/) ·
[github.com/hyacinth-bruno](https://github.com/hyacinth-bruno)

Currently a Web Accessibility Engineer at Redcare Pharmacy, where I also
built a full-stack Jira roadmap tool (Koa.js, Redis dual-layer caching,
RabbitMQ, Elastic APM) — the closest prior work to this pipeline's shape.
