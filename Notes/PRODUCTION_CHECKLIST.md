# Production Deployment Checklist

Use this before and after deploying to PythonAnywhere (or any host).

## Environment

- [ ] `.env` present on the server (never in git)
- [ ] `DEBUG=False`
- [ ] Strong unique `SECRET_KEY`
- [ ] `ALLOWED_HOSTS` includes the real domain(s)
- [ ] `CSRF_TRUSTED_ORIGINS` includes `https://your-domain` (required for HTTPS forms)
- [ ] `SYNC_TOKEN` is a long random value; same value configured in the cron job header
- [ ] NFL / Google / email credentials are current (not the old free-tier samples)

## HTTPS & cookies

- [ ] Site is served over HTTPS
- [ ] After HTTPS is confirmed, HSTS can be left at the default 1 year
  (or set `SECURE_HSTS_SECONDS` lower while testing)
- [ ] `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` activate automatically when `DEBUG=False`

## Static & media

- [ ] Run `python manage.py collectstatic --noinput`
- [ ] Web server maps `/static/` to `STATIC_ROOT` (and `/media/` if used)

## Database

- [ ] Backup strategy in place (PythonAnywhere: scheduled download of `db.sqlite3`, or host backups)
- [ ] After deploy: `python manage.py migrate --check` (or run migrate if new migrations)

## Scheduled sync

- [ ] Cron (or cron-job.org) hits `POST/GET https://your-domain/api/sync/` every ~15–30 min
- [ ] Request header: `X-Sync-Token: <same as SYNC_TOKEN>`
- [ ] Monitor for non-200 / 502 responses (API trouble)

## Auth & email

- [ ] Google OAuth redirect URIs match the live domain
- [ ] SMTP credentials work (test password-reset or a contact form)
- [ ] allauth email verification behaviour matches what you want (default is fine for most cases)

## Smoke test after deploy

- [ ] Home page loads
- [ ] Login / signup
- [ ] Make a pick on an unlocked game; confirm lock message on a started game
- [ ] Dashboard / leaderboard render
- [ ] Admin loads for staff
- [ ] Sync endpoint returns 403 without token and 200/502 with correct token

## Do not

- Commit `.env` or real secrets
- Run destructive management commands (`manage_playoffs open/cut`, `shadow_playoffs --write`) against production without a backup and a clear reason
