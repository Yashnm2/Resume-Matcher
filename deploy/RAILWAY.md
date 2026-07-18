# Railway deployment

> Looking for a no-cost hobby deployment? Use the Hugging Face Docker Space
> configuration in the root `README.md`. CPU Basic currently supports the full
> container at no charge, but sleeps when idle and does not provide persistent
> local disk. Add `LLM_API_KEY` as a Space **Secret**, never a Variable.

For new accounts where Docker Spaces are not available on the free plan, use
the root `render.yaml`: it deploys a backend-only container on Render's free web
tier while the frontend remains on Vercel. The backend stores SQLite snapshots
in a private Hugging Face dataset via `HF_STATE_REPO_ID` and `HF_TOKEN`.

## Fastest usable deployment

For the regular Resume Matcher experience, deploy the repository as one Railway
service. Railway reads the root `railway.toml`, builds the root `Dockerfile`, and
runs the frontend and API in the same container. Add a volume mounted at
`/app/backend/data` so resumes and encrypted settings survive redeployments.

Set these service variables:

```env
LLM_PROVIDER=openai
LLM_API_KEY=your-provider-key
ENCRYPTION_SECRET=a-long-random-value
DEPLOYMENT_ENVIRONMENT=production
```

The key is read only by the backend. Browser requests use the same-origin `/api`
proxy, so the key is never included in frontend JavaScript. `AUTH_REQUIRED`
defaults to `false`; enable the multi-user Supabase setup below before sharing a
deployment with other people.

## Full scheduled Job Scout deployment

Create seven private services from the same repository and Dockerfile. Give all
services the variables in `scout.env.example`; expose only **frontend** and
**api** publicly. Use Railway private networking for `BACKEND_ORIGIN`.

| Service | Start command | Extra variable |
| --- | --- | --- |
| frontend | `sh /app/deploy/start-frontend.sh` | `BACKEND_ORIGIN=http://api.railway.internal:8000` |
| api | `sh /app/deploy/start-api.sh` | `PORT=8000` |
| discovery-worker | `sh /app/deploy/start-worker.sh` | `WORKER_QUEUE=discovery` |
| llm-worker | `sh /app/deploy/start-worker.sh` | `WORKER_QUEUE=llm` |
| render-worker | `sh /app/deploy/start-worker.sh` | `WORKER_QUEUE=render` |
| beat | `sh /app/deploy/start-beat.sh` | none |
| Redis | Railway Redis template | set its URL as `REDIS_URL` everywhere |

The API process runs Alembic before startup. Run exactly one Beat replica.
Keep the render worker at concurrency 1. Configure the private Supabase Storage
bucket named by `SUPABASE_STORAGE_BUCKET`; the service-role key belongs only on
backend and worker services, never the frontend.

Build arguments required by the frontend image:

- `NEXT_PUBLIC_API_URL=/`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
- `BACKEND_ORIGIN=http://api.railway.internal:8000`

After deployment, verify `/api/v1/health`, sign in, create one source, run one
manual scan, prepare one pack, and download both PDFs before enabling Beat.

## Backup and recovery drill

Supabase database backups or point-in-time recovery remain the primary recovery
layer. Also schedule `backup-postgres.sh` daily from a `postgres:17` maintenance
job, write the dump and checksum to encrypted object storage, and retain at least
30 daily copies. The script requires `DATABASE_URL` and a durable `BACKUP_DIR`.

Once per quarter, provision an isolated Supabase project, download a backup and
its checksum, then run `verify-restore.sh` with `RESTORE_DATABASE_URL` and
`BACKUP_FILE`. The verifier refuses to target `DATABASE_URL`, validates the
checksum, restores the database, and reads the migration, profile, posting, pack,
and audit tables. Record the duration and row counts in the operations log. Test
private Storage recovery separately by copying the bucket into an isolated test
bucket and opening one résumé and cover-letter PDF through a signed URL.
