# Railway crash fix

## Root cause
Gunicorn was failing during startup at:

`from security.shield import Shield`

The project package name `security` can collide with another installed/module namespace on Railway/Python, causing `security.shield` to resolve to the wrong module and produce:

`ImportError: cannot import name 'Shield' from 'security.shield' (unknown location)`

## Fix
The project-local package was renamed from `backend/security/` to `backend/tso_security/`, and the two imports in `backend/app.py` were changed to:

- `from tso_security.qr_encoder import encode_qr_svg`
- `from tso_security.shield import Shield`

This makes the import unambiguous on Railway's Linux/Python environment.

## Deploy
Push the contents of this ZIP to GitHub, then redeploy the Railway service. Railway should rebuild the service rather than reuse a stale deployment.

The existing `wsgi.py` and Gunicorn entrypoint are retained.
