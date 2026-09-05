# TSO Edu Speed Upgrade

This upgrade focuses on fast tab navigation and higher concurrent traffic without changing the product workflow.

## Included
- Browser-side GET caching with short, endpoint-specific TTLs.
- In-flight request deduplication so two components/tabs do not request the same resource at the same time.
- Targeted cache invalidation after jobs/credit/task mutations.
- Immediate UI shell support via content-visibility and loading skeleton utilities.
- Short-lived server-side hot-cache for the public job list.
- PostgreSQL connection pooling through `psycopg-pool` (configurable per Gunicorn worker).
- Gunicorn gthread configuration with configurable worker/thread counts.
- Existing Supabase, Credit, Edu, authentication and email integrations preserved.

## Recommended environment
For an 8 GB / 4 vCPU VPS:

WEB_CONCURRENCY=3
WEB_THREADS=4
DB_POOL_MIN_SIZE=1
DB_POOL_MAX_SIZE=10
DB_POOL_TIMEOUT=10

For a smaller 1–2 vCPU server, start with WEB_CONCURRENCY=1–2 and WEB_THREADS=2–4.

## Important
The short-lived in-memory cache is per Gunicorn worker. This is intentional for a zero-dependency fast path. When the service is scaled across multiple machines, use Redis for shared caching and background queues.

Heavy AI operations should still be moved to background workers for sustained 1,000-user traffic; this upgrade does not pretend that CPU-bound AI generation can be made instant by caching alone.
