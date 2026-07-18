# Daily 20 job scout

The scout is a review-only production line for up to 20 application packs per day. It never applies, sends email, signs into LinkedIn/Indeed, bypasses blocks, or guesses contact details.

## Services

- Web: Next.js frontend (`/scout`, `/sources`, `/contacts`).
- API: FastAPI under `/api/v1` with optional Supabase JWT validation.
- Database: PostgreSQL in production; SQLite remains supported for local development. Run `uv run alembic upgrade head` before starting production services.
- Queue: Redis and Celery with separate `discovery`, `llm`, and `render` queues.
- Scheduler: Celery Beat scans every four hours and selects the daily queue at 06:00 in the configured timezone.
- Notification: Resend sends one completion email with the private review-inbox link when at least one pack is ready. Referral drafts are never sent.
- Storage: generated résumé, cover-letter, and supporting artifacts are written to a private Supabase Storage bucket and exposed only through authenticated server-side access.

## Railway process commands

Create the API, frontend, Beat scheduler, and three isolated worker services from the same repository:

```text
api:               sh /app/deploy/start-api.sh
discovery-worker:  WORKER_QUEUE=discovery sh /app/deploy/start-worker.sh
llm-worker:        WORKER_QUEUE=llm sh /app/deploy/start-worker.sh
render-worker:     WORKER_QUEUE=render sh /app/deploy/start-worker.sh
beat:              sh /app/deploy/start-beat.sh
frontend:          sh /app/deploy/start-frontend.sh
redis:             Railway managed Redis
```

Run migrations as the API service pre-deploy command. Give every service the same `DATABASE_URL`, `REDIS_URL`, encryption secret, and LLM settings. Only the frontend receives the public API origin.

## Supported discovery

Manual postings, Greenhouse, Lever, Ashby, SmartRecruiters, robots-aware career-page JSON-LD, and forwarded LinkedIn/Indeed alert metadata are supported. LinkedIn and Indeed partner adapters intentionally remain disabled without approved access.

## Daily run

1. Discovery adapters normalize and hash postings, preserving the original URL and description.
2. Hard exclusions run before scoring. The weighted score is persisted with its component explanation and gaps.
3. Daily selection enforces threshold, company cap, 20-pack limit, and ten-item reserve.
4. Pack preparation is idempotent. Tailoring uses the existing diff workflow and stores provenance separately from the untouched master resume.
5. Contacts come only from official LinkedIn exports. The top three company matches are explainable and no missing email is inferred.

## Operations

Back up PostgreSQL daily and Supabase Storage with object versioning. Test restore quarterly into a separate project. Alert on failed scout runs, stale sources, queued tasks older than 30 minutes, and repeated pack failures. `ScoutRun`, `AuditEvent`, pack state, source errors, and generation-cost fields provide the operational trail. Use `/api/v1/events` for authenticated live progress in the UI.
