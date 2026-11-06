# Stable deploy path (GitHub → PythonAnywhere)

Goal: keep **https://gamedaypicks.pythonanywhere.com** up while shipping work in safe layers.

---

## Layer 0 — already on `main` (done)

- 504 fix: short team-records timeout, failure cache, safe confidence math  
  Commit: `Fix 504: resilient team records + safe confidence math`

After any pull of this layer: **reload only** (no pip, no migrate).

---

## Layer 1 — leaderboard UI (safe for `main` now)

**Files only (no new packages, no migrations):**

- `accounts/leaderboard.py`
- `main/views.py`
- `main/templates/main/leaderboard.html`

**Behavior:**

- Top tabs: Weekly | Season | Confidence  
- People filter: Everyone | Friends | Division (**not** on Confidence)  
- Division respects week (weekly tab) and season (season tab)  
- Centered controls  

**PythonAnywhere:**

```bash
cd ~/luminous-insanity   # your project path
git pull origin main
# Web tab → Reload
```

No `pip install`, no `migrate`.

---

## Layer 2 — Flutter API (`mobileapi`) — separate deploy

**Do not enable this until you can run the full sequence below without interruption.**

If `settings.py` lists `mobileapi` / `rest_framework` but packages are missing, **every page 500s**.

### On your machine

1. Commit `mobileapi/`, requirements extras, settings/urls/middleware changes, migrations together.
2. Prefer a branch (`flutter-api`) first; merge to `main` only when ready to run server steps immediately.

### On PythonAnywhere (order matters)

```bash
# 1) Pull code
cd ~/luminous-insanity
git pull origin main

# 2) Install deps INSIDE the site virtualenv BEFORE reload
source ~/.virtualenvs/pickem-venv/bin/activate   # your venv name
pip install -r requirements.txt

# 3) Migrate
python manage.py migrate

# 4) Static (if any new admin/static)
python manage.py collectstatic --noinput

# 5) Optional checks
python manage.py check
python manage.py test mobileapi -v1

# 6) THEN reload the web app in the Web tab
```

### Cron (after Layer 2 is live)

- Daily: `python manage.py flushexpiredtokens`
- Daily: `python manage.py cleanup_mobile_idempotency`

### Env

- `GOOGLE_CLIENT_ID` must match the OAuth client the Flutter app uses for ID tokens.

---

## Layer 3 — chat / auto-playoffs (hold)

- Live chat and auto playoff cuts stay off `main` until tested.
- Auto playoffs must stay **opt-in** (`AUTO_PLAYOFFS = True` only when intentional).
- Fix the “16 games every week” gate before enabling automation (bye weeks ≠ 16).

---

## If the site goes down after a pull

1. Check Error log on PythonAnywhere.  
2. Classic failure: `ModuleNotFoundError: rest_framework` → run `pip install -r requirements.txt` in the **same** venv the web app uses, then reload.  
3. Classic failure: missing migration → `python manage.py migrate`, then reload.  
4. Last resort: `git revert` the bad commit and reload.

---

## Recommended push order this week

1. **Now:** Layer 1 (leaderboard) → pull + reload.  
2. **When ready for Flutter against prod:** Layer 2 in one sitting (pip → migrate → reload).  
3. Point the Flutter app at `/api/v1/` using `FLUTTER_V1_API.md`.  
4. Chat / playoff automation later.
