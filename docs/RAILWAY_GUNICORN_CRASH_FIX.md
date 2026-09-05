# Railway Gunicorn crash fix

The production entrypoint is now `wsgi:app` instead of relying on Gunicorn's
`--chdir backend` behavior. `wsgi.py` explicitly puts `backend/` on Python's
module path, so `app`, `ai_provider`, `feature_scout`, `edu_app`, and `security`
resolve consistently on Railway.

The PostgreSQL driver is also declared explicitly as both `psycopg` and
`psycopg-binary` at the same pinned version to avoid binary-driver installation
ambiguity during Nixpacks builds.

Railway start command:

`gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120 --graceful-timeout 30 --access-logfile - --error-logfile -`

Required production variables remain the same as the previous deployment,
including `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and
`GROQ_API_KEY` when the TSO AI engine is enabled.
