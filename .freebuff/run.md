# Run doc — OnlineRetailPOS (Django 4.1)

Workspace = main checkout, so there are NO artifacts to copy from elsewhere.
`.env` is already present in the repo root (sqlite database, settings module
`onlineretailpos.settings.devlopement`, `NAME_OF_DATABASE=sqlite`).

**Branch note (feat/saas-multi-tenancy):** the app is now multi-tenant (stores
app, per-store row scoping). New users must sign up at `/signup/` (creates the
store + owner + seeded tax/deposit/department). Pre-existing users were given
memberships to the bootstrap store "ONLINE RETAIL". Database backup from before
the SaaS migration: `.freebuff/db.backup-pre-saas.sqlite3`.

## Reproduce the artifacts

1. Virtualenv: use the checked-in `venv/` (Python 3.10, Django 4.1.13).
   If missing, recreate with:
   `python3.10 -m venv venv && venv/bin/pip install -r requirements.txt`
2. Sanity check: `venv/bin/python manage.py check` → expect "no issues".
3. Static files (required: `DEBUG=False` and `onlineretailpos/urls.py` serves
   `/static/` from `STATIC_ROOT` via `django.views.static.serve`):
   `venv/bin/python manage.py collectstatic --noinput`
   → ~2000 files into `static/`.
4. Database is file-based (`db.sqlite3`) — no external service needed.
   If login credentials are needed: `venv/bin/python manage.py createsuperuser`.

## Run the server

1. Port: default 8000 is frequently occupied by the user's own
   `manage.py runserver` (check `ss -tlnp | grep 8000` first). This preview
   uses **8080**; adapt if taken.
2. Detached start — run it as a transient **systemd user unit** so it lives
   outside the command runner's process tree. (History: plain `nohup` used to
   work, then the runner began reaping every spawned child — `setsid` included
   — when the command finishes. `systemd-run --user` is the reliable method;
   BACKGROUND process mode is not available.)

   ```
   systemd-run --user --unit=freebuff-preview-pos \
     --property=WorkingDirectory="$PWD" \
     --property="StandardOutput=append:$PWD/.freebuff/preview-<thread-id>.log" \
     --property="StandardError=append:$PWD/.freebuff/preview-<thread-id>.log" \
     "$PWD/venv/bin/python" manage.py runserver 127.0.0.1:8080 --noreload
   ```

   (Quote paths containing spaces; `--noreload` because auto-reload spawns a
   child the MainPID check would miss.)
3. Verify: `systemctl --user is-active freebuff-preview-pos.service` →
   `active` and `systemctl --user show freebuff-preview-pos.service
   -p MainPID --value` gives the pid; then
   `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/`
   → expect **302** (root redirects to `/user/login/?next=/`), while a
   logged-in browser session lands on the Sales Dashboard directly.
4. Stop it when no longer needed:
   `systemctl --user stop freebuff-preview-pos.service`
5. Most routes require login; the login page itself must return 200 and load
   its CSS/fonts from `/static/` (a plotly.js deprecation warning in the
   console is pre-existing and harmless).

## Tests

After changing `theme.js` or the sale/receipt flow, re-run:

1. Static checks: `venv/bin/python manage.py check`
2. Python contract (sale persistence, payment types, underpaid boundary,
   receipt change amount/badge, tenancy isolation, signup, per-store
   uniqueness): `venv/bin/python manage.py test transaction stores`
3. JS contract for the loading-overlay link guard (Node ≥18):
   `node --test onlineretailpos/static/js/theme.test.js`
   (pass the file, not the directory — Node treats a bare directory path as a
   module and fails to resolve it.)

Remember `venv/bin/python manage.py collectstatic --noinput` after editing
anything under `onlineretailpos/static/`, since `/static/` is served from
`STATIC_ROOT` while `DEBUG=False`.
