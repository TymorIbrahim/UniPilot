# UniPilot AI — Risk Assessment

**Project:** UniPilot AI — AI-powered academic decision support platform
**Date:** 2026-08-27
**Authors:** UniPilot team
**Version:** ad826d5

## 1. Scoring Scale
- **Likelihood:** Low / Medium / High
- **Impact:** Low / Medium / High
- **Residual risk:** remaining risk after mitigation (Low / Medium / High)

## 2. Risk Register

### Security Risks
| ID | Risk | Likelihood | Impact | Mitigation (implemented/planned) | Residual |
|----|------|-----------|--------|----------------------------------|----------|
| S-1 | JWT secret leakage / weak secret | Low | High | Secret loaded from env only (`JWT_SECRET`, `services/api/app/config.py`); `require_jwt_secret()` refuses to boot without one; `validate_production_settings()` rejects the dev placeholder and enforces ≥32 chars when `ENVIRONMENT=production`. Access tokens are short-lived (`JWT_EXPIRES_IN`, default 1h); refresh tokens are stored server-side in Redis (`app/security/refresh_tokens.py`, prefix `rt:`, hashed with SHA-256 before storage — the raw token is never persisted) with TTL (24h session / 30d remember-me) and rotate-and-revoke on refresh. | Low |
| S-2 | Password compromise | Low | High | bcrypt hashing (`app/security/password.py`), salt rounds configurable via `BCRYPT_SALT_ROUNDS` (default 12, `resolved_bcrypt_salt_rounds()` floors any misconfiguration at 10). Passwords are never logged, returned in responses, or stored in plaintext. Pydantic schema enforces the bcrypt 72-byte input limit at validation time. | Low |
| S-3 | Broken access control (cross-account) | Low | High | Every user-owned resource (profile, completed courses, semester plans, academic risks, AI jobs) scopes every query by `userId` parsed from the JWT (`AuthContext.user_id`), never a client-supplied id — write schemas explicitly reject a client-sent `userId`/`_id` (`extra="forbid"`). Verified by dedicated cross-user security tests per resource (e.g. `tests/security/test_ai_jobs_security.py::test_cross_user_job_access_returns_404`). | Low |
| S-4 | Injection / malformed input | Low | Medium | Pydantic v2 strict validation at every write boundary (`extra="forbid"`, typed fields, custom validators for ObjectIds/semester codes/credit ranges); Motor/PyMongo parameterizes all queries (no raw string query construction), so classic NoSQL injection via string concatenation isn't possible. | Low |
| S-5 | Brute force / abuse | Low | Medium | Redis-backed rate limiting (`app/middleware/auth_rate_limiter.py`) on auth (`rl:auth:`, per-IP and per-email), `/academic-risks/analyze` (`rl:ai:`), `/graduation-progress*` (`rl:progress:`), and `/ai-jobs` (`rl:job:`) — fixed-window counters via `INCR`+`PEXPIRE`, with an in-memory fallback if Redis is unreachable (fail-open by design, see O-2). Production limits are capped and validated at startup (e.g. `AUTH_RATE_LIMIT_MAX ≤ 10`). | Medium |
| S-6 | Secret exposure in repo/images | Low | Medium | Only `.env.example` (placeholder values) is committed; `.env` is git-ignored. Every service (`api`, `web`, `worker`, `ai`, `data-engineering`) has its own `.dockerignore` excluding `.env`/`node_modules`/test artifacts from build context. `docs/operations/PRODUCTION_DEPLOYMENT.md` requires unique production secrets before deploy, and `Settings.validate_production_settings()` fails startup if the dev JWT/Mongo placeholders are still in place. | Low |
| S-7 | Internal service impersonation (worker↔ai) | Low | Medium | `worker`→`ai` calls carry `x-internal-service-token` (`INTERNAL_SERVICE_TOKEN`), checked by `ai`'s `requireInternalServiceToken` middleware; required ≥32 chars in production. **Known gap:** if the token env var is unset/empty, `ai` currently falls back to open access rather than refusing to start — acceptable in dev (internal-only network, no host port published) but should be hardened to fail closed before this pattern is reused for a client-facing internal API. | Medium |

### Data Risks
| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|----|------|-----------|--------|-----------|----------|
| D-1 | Data loss on volume removal | Medium | High | MongoDB persists to a named volume (`mongo_data`); `docker compose down` (without `-v`) preserves it. **No automated backup pipeline exists** — `docs/operations/PRODUCTION_DEPLOYMENT.md`'s rollback guidance is a manual volume-snapshot restore, not a scheduled job. This is a genuine gap, not just a documentation shortcut. | Medium |
| D-2 | Student PII handling | Low | Medium | Stored PII is minimal: email (auth), transcript records (course/grade/credits), and profile fields (institution, program, semester) — no payment, government-ID, or contact-address data. Access is JWT-gated and ownership-scoped (see S-3). Redis-cached data (rate-limit counters, refresh tokens) contains no PII beyond a SHA-256 token hash. | Low |
| D-3 | Inconsistent/corrupt writes | Low | Medium | Pydantic validation before every write; Mongo unique/compound indexes enforce invariants at the DB layer (e.g. `(userId, courseId, attempt)` on completed courses, `(userId, createdAt)` on jobs/analyses); catalog promotion (`data-engineering`) is idempotent by stable key and gated behind a dry-run + explicit `--i-confirm-dangerous-production-write` flag, with a `promotion_runs` audit collection and a matching rollback command. | Low |

### AI Risks
| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|----|------|-----------|--------|-----------|----------|
| A-1 | AI provider outage/timeout | Medium | Low | `worker` calls `ai` with a bounded timeout (`WORKER_INFER_TIMEOUT_MS`, default 5s via `AbortSignal.timeout`) and exactly one retry on transient failures (network error, timeout, 5xx) — permanent failures (4xx) are never retried. Exhausted retries mark the job `failed` with a structured `error.code`/`message` rather than hanging; verified live (stopped `ai`, confirmed one retry then a terminal `failed` write). Impact is low today because `ai` is deterministic, not a real model call — this risk grows once a real provider is wired in (see Known Limitations). | Low (today) |
| A-2 | Cost/abuse via AI endpoints | Low | Medium | `POST /ai-jobs` is JWT-protected and rate-limited (`rl:job:`, independent budget from the deterministic risk analyzer's own limit) so a single user can't flood the queue. No per-provider spend cap exists yet — moot today (no billed provider), but must be added before a real LLM is wired in. | Medium (once real AI lands) |
| A-3 | Unsafe/hallucinated output | Low | Low | `worker` validates every `ai` result's shape (`validateInferResponse`) before persisting it as `completed` — a malformed or missing result is treated as a job failure, never silently stored or shown to the user. Not applicable today since `ai`'s compute is deterministic template logic, not a generative model; this validation layer is exactly the seam a real model would plug into. | Low (today) |
| A-4 | Blocking API on long calls | Low | Low | The whole point of the pipeline: `POST /ai-jobs` returns `202` immediately with a persisted `pending` job; real work happens in `worker`, decoupled from the request/response cycle; the client polls `GET /ai-jobs/:id`. Verified end-to-end against live containers. | Low |

### Availability / Operational Risks
| ID | Risk | Likelihood | Impact | Mitigation | Residual |
|----|------|-----------|--------|-----------|----------|
| O-1 | Startup ordering failures | Low | Medium | Every service has a Docker healthcheck; `depends_on` conditions gate startup on `service_healthy` (e.g. `api` waits on `mongo`+`redis`; `worker` waits on `mongo`+`redis`+`ai`). `worker`'s healthcheck actually pings Redis and Mongo (not just "is Express alive") — added specifically so a consumer that's up but can't reach its dependencies reports unhealthy rather than falsely healthy. | Low |
| O-2 | Dependency outage (Mongo/Redis/AI) | Medium | Medium | Redis outage: rate limiters and the AI job queue fail open to an in-memory store (`resolve_rate_limit_store`/`resolve_ai_job_queue_store`) rather than hard-failing requests — trades strict rate-limit correctness for availability, a deliberate but real trade-off. Mongo outage: requests fail with a clear error rather than hanging (`serverSelectionTimeoutMS=2000`). `ai` outage: covered under A-1. | Medium |
| O-3 | Queue backlog under load | Medium | Medium | Single `worker` replica consumes the `ai_jobs` Redis list via blocking `BLPOP`; no dead-letter queue, no max-queue-depth/backpressure, and no horizontal worker scaling configured. Under sustained load, jobs would queue indefinitely rather than shed load — acceptable for course-project traffic, a real gap for production scale. | Medium |
| O-4 | Scaling limits | Medium | Low | `api` is stateless (JWT, no server-side sessions) and horizontally scalable behind a load balancer in principle, sharing Mongo/Redis. `worker` is not — it's a single long-running process with no leader-election or partitioning if run as >1 replica (duplicate delivery is guarded against via the `status==="pending"` check in `processJob`, so it's safe but not throughput-scaling). Not exercised under real load. | Medium |

## 3. Known Limitations

- **No automated Mongo backups.** Only a manual volume-snapshot restore procedure is documented (D-1). Acceptable for a course project; would block real production use.
- **`ai`'s compute is deterministic, not a real model.** The async pipeline (queue, worker, retries, result validation, rate limiting) is fully built and tested, but only one `jobType` exists (`academic_risk_narrative`) and it's template-based, not LLM-backed. A-2/A-3 residual risk changes materially once a real provider is wired in — cost caps and stronger output validation should be revisited at that point.
- **Worker doesn't fail closed on a missing internal service token** (S-7) — relies on the internal-only Docker network as a compensating control, not on the auth check itself.
- **No horizontal scaling or backpressure for the job queue** (O-3, O-4) — a single `worker` replica, unbounded queue depth.
- **RisksPage frontend had a real client/server contract mismatch** (found and fixed during development: the frontend type for `academicRiskAnalysis.summary` assumed a string, the API returns a structured object, and rendering the mismatch crashed the page with no error boundary). No React error boundary exists anywhere in the app, so a similar unhandled type mismatch elsewhere would still blank the whole page rather than degrading gracefully — worth adding as a follow-up hardening item.
- **E2E suite depends on `AUTO_SEED_CATALOG=true` against a fresh Mongo volume** (per CI config) — running it locally against a Mongo instance with the full promoted real catalog instead of the lean seed fixture causes unrelated timing/content mismatches in existing specs (observed independently of any change in this work).
- **Full Technion catalog ingestion automation** beyond the currently promoted DDS + generic-faculty subset is not complete.
- **Simulation features** (`docs/planning/FEATURE_BACKLOG.md`) are not implemented.

## 4. Top Risks Summary
1. **Queue backlog / no backpressure (O-3)** — highest realistic residual risk today: sustained load has no shedding mechanism beyond "the queue grows." Straightforward to mitigate (bounded queue + reject/backoff) before any real traffic.
2. **No automated backups (D-1)** — low likelihood day-to-day, but high impact if it materializes (full data loss between manual snapshots), and it's a process gap, not a code gap, so it's easy to defer indefinitely without a forcing function.
3. **AI cost/abuse controls are not yet proven under a real provider (A-2)** — today's rate limiting is a reasonable placeholder, but per-provider spend caps and stronger abuse detection need dedicated design before `ai` calls anything billed.

## 5. References
- Architecture: `docs/architecture/ARCHITECTURE.md`
- API contract: `docs/API_SPEC.md` (see §4.9 for the async AI job pipeline)
- Rules: `.cursor/rules/unipilot-security.mdc`, `unipilot-docker.mdc`, `unipilot-ai.mdc`, `unipilot-database.mdc`
- Production runbook: `docs/operations/PRODUCTION_DEPLOYMENT.md`
- Test report: `docs/reports/TEST_REPORT.md`
