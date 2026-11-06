# Flutter v1 — API surface (GameDayPicks)

Base URL (production): `https://gamedaypicks.pythonanywhere.com/api/v1/`  
Auth header: `Authorization: Bearer <access_token>`  
Content-Type: `application/json`  
All `/api/v1/` responses are `Cache-Control: no-store`.

Django remains the source of truth. The app must not call Tank01 or re-grade picks.

---

## v1 scope (build this first)

Ship the app against these endpoints only. Everything else can wait for v1.1.

| Priority | Endpoint | Method | Notes |
|----------|----------|--------|--------|
| Auth | `/auth/register/` | POST | username, email, password |
| Auth | `/auth/login/` | POST | username or email + password → access + refresh |
| Auth | `/auth/google/` | POST | Google **ID token** for server `GOOGLE_CLIENT_ID` |
| Auth | `/auth/refresh/` | POST | refresh → new access (rotation) |
| Auth | `/auth/logout/` | POST | blacklist refresh token |
| Me | `/me/` | GET, PATCH | profile; PATCH `favorite_team`, `active_title` |
| Games | `/games/?season=&week=` | GET | schedule + scores for a week |
| Picks | `/picks/?season=&week=` | GET | my picks |
| Picks | `/picks/` | POST | `{ "game_id", "side": "home\|away", "confidence": 1\|2\|3\|null }` |
| Leaderboard | `/leaderboard/?tab=weekly\|season&week=&filter=all\|friends` | GET | standings |
| Friends | `/friends/` | GET | accepted friends |
| Friends | `/friends/search/?q=` | GET | find players |
| Friends | `/friends/requests/` | GET, POST | list / send |
| Friends | `/friends/requests/<id>/respond/` | POST | accept / decline |
| Notifications | `/notifications/` | GET | alerts feed |

**Out of v1 (exist in code, defer in the app):** chat, devices/push, challenges, Crossfire, Relay Wars, squares, playoffs UI, live moments, history, compare, divisions.

---

## Auth flow (app)

1. Login or Google → store `access` + `refresh` in **secure storage**.
2. Call APIs with `Authorization: Bearer <access>`.
3. On 401, POST `/auth/refresh/` with refresh token; retry once.
4. If refresh fails → send user to login.
5. Logout → POST `/auth/logout/` then clear secure storage.

Google: request an **ID token** audience = server OAuth client ID (`GOOGLE_CLIENT_ID` in Django settings). Do not put client secrets in the app binary.

---

## Example calls

**Login**
```http
POST /api/v1/auth/login/
{"username": "player1", "password": "..."}
```
Response includes `access`, `refresh`, and a small user payload.

**Week games**
```http
GET /api/v1/games/?season=2026&week=9
Authorization: Bearer <access>
```

**Submit pick**
```http
POST /api/v1/picks/
Authorization: Bearer <access>
{"game_id": "20261109_NE@MIA", "side": "home", "confidence": 2}
```
Server enforces lock times. Trust the error body if the game is locked.

**Leaderboard**
```http
GET /api/v1/leaderboard/?tab=weekly&week=9&filter=friends
Authorization: Bearer <access>
```

---

## Website vs app

| Concern | Website | Flutter |
|---------|---------|---------|
| Auth | Session cookie | JWT access + refresh |
| Picks / grades | Same DB | Same API → same DB |
| Scores freshness | Cron sync | Same; polling cannot beat cron |
| Push | N/A | Device register exists; **send path not live yet** |
| Realtime | Poll / page load | Poll; no WebSockets |

---

## Server prerequisites before the app hits production

1. `mobileapi` package is on the server and in `INSTALLED_APPS`.
2. `pip install -r requirements.txt` includes DRF + simplejwt + google-auth.
3. `migrate` applied (mobileapi + token_blacklist).
4. `GOOGLE_CLIENT_ID` set for ID-token verification.
5. Smoke: register → login → games → pick → leaderboard.

Until then, point Flutter at a staging/dev host only.

See `STABLE_DEPLOY.md` for the ordered website deploy that keeps the site up.
