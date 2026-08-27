# UniPilot AI — Architecture

Last updated: 2026-06-20

UniPilot AI is an AI-powered academic decision support platform. It helps students make academic decisions (course/path planning, recommendations, what-if analysis) backed by deterministic planners and a deterministic async AI job pipeline.

## Design Principles

- **Backend-first.** Graded primarily on backend quality.
- **First-run Docker reliability.** One command brings the system up.
- **Least exposure.** Only the API container is reachable by clients.
- **Async by default for AI.** Long AI requests do not block the API — enqueued via Redis, processed by `worker`.
- **Persistence in MongoDB.** All durable state lives in MongoDB.

## Containers

| Container | Role | Client-facing | Notes |
|-----------|------|---------------|-------|
| `api` | FastAPI HTTP API | **Yes (only this one)** | Auth, validation, rate limiting, catalog, planners, AI job enqueue/status |
| `data-engineering` | Catalog ingestion CLI | No | Staging import, quality gates, guarded production promotion |
| `worker` | Background job processor | No | Redis `BLPOP` consumer; writes job status transitions to MongoDB |
| `ai` | Internal AI/inference service | No | Deterministic per-jobType compute registry (`/infer`); no real model call yet |
| `mongo` | MongoDB database | No | Persistent data; named volume `mongo_data` |
| `redis` | Queue + rate-limit store | No | Auth/AI/progress/job rate limits; `ai_jobs` job queue |

Minimum requirement: **at least two backend containers**. Current layout: `api` + `worker` + `ai` + `data-engineering`.

## Request Flows

### Synchronous (implemented)

```
Client → api (FastAPI) → MongoDB
              ↑
       JWT + Pydantic validation + rate limit
```

Covers auth, student profile, catalog reads, completed courses, graduation progress, semester plans, and academic risk analysis.

### Asynchronous (implemented — `POST /ai-jobs`)

```
Client → api  (validate, auth, rate limit)
          │  persist job (status=pending) + enqueue job id
          ▼
        redis (list: WORKER_QUEUE_NAME, default "ai_jobs")
          │
          ▼
        worker → ai service (/infer, deterministic compute) 
          │
          ▼
        MongoDB (job: pending → processing → completed/failed)

Client polls:  api → MongoDB → job status / result  (GET /ai-jobs/:id)
```

MVP job type: `academic_risk_narrative` — given an existing, user-owned academic-risk analysis, produces a deterministic narrative + stats summary. `ai` never touches Mongo/Redis directly; it is a stateless compute step called synchronously by `worker` with a full input snapshot. See `docs/API_SPEC.md` for the endpoint contract.

## Cross-Cutting Concerns

### Authentication & Authorization
- JWT issued at login/register; verified on protected routes.
- Student-owned resources enforce ownership (`token.sub` == resource `userId`).

### Passwords
- bcrypt hashing (cost ≥ 10). Never stored or returned in plaintext.

### Validation
- Pydantic schema validation at every boundary. `worker` validates the shape of every `ai` `/infer` result (`validateInferResponse`) before persisting it as a completed job — an untrusted/malformed result is treated as a job failure, never written back as-is.

### Rate Limiting
- Redis-backed limits on auth endpoints (`rl:auth:`), `POST /academic-risks/analyze` (`rl:ai:`), progress endpoints (`rl:progress:`), and `POST /ai-jobs` (`rl:job:`).

### Secrets & Config
- All secrets via environment variables; `.env.example` committed. Required secrets validated at startup.

### Networking
- Internal Docker network (`unipilot-internal`) for service-to-service calls by name.
- Only `api` publishes a host port (`API_PORT` → container `8000`).

## Data Stores

- **MongoDB** (`MONGO_DB`, default `unipilot_python`): users, profiles, completed courses, semester plans, academic risks, and promoted Technion DDS catalog collections (`courses`, `course_offerings`, `degree_programs`, `degree_requirements`, `catalog_rules`).
- **Redis**: rate-limiting counters and the `ai_jobs` job queue (list, consumed via `BLPOP`). Not a source of truth — MongoDB is authoritative for job state; the queue carries only job-id pointers.

## Component Diagram

```
                 ┌─────────────┐
   Client  ───▶  │  api (API)  │  (only exposed container)
                 └──────┬──────┘
            enqueue     │ read/write
                 ┌──────▼──────┐        ┌──────────────┐
                 │    redis    │◀──────▶│    worker    │
                 └─────────────┘ BLPOP  └──────┬───────┘
                                        POST /infer │ (deterministic compute)
                 ┌─────────────┐        ┌──────▼───────┐
                 │   mongo     │◀──────▶│  ai service  │
                 └─────────────┘ status └──────────────┘
                        ▲
                        │ promote (CLI)
                 ┌──────┴──────────────┐
                 │  data-engineering   │  (internal)
                 └─────────────────────┘
```

## Related Documents

- Index: `docs/README.md`
- Status: `docs/PROJECT_CONTEXT.md`
- API: `docs/API_SPEC.md`
- Phases: `docs/planning/IMPLEMENTATION_PHASES.md`
- Backlog: `docs/planning/FEATURE_BACKLOG.md`
- Ingestion: `docs/DATA_INGESTION_ARCHITECTURE.md`
- Promotion CLI: `services/data-engineering/README.md`
