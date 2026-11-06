# GameDayPicks — Flutter website readiness

## Goal

Prepare the existing Django website to serve a native Flutter client. Django remains the only source of truth for accounts, picks, scores, grading, standings, challenges, Crossfire, Relay Wars, playoffs, and all other competitive rules. The Flutter client must not reimplement those rules or connect directly to Tank01.

## What this change adds

- A separate, versioned API at `/api/v1/`; the existing HTML website routes remain in place.
- The existing `/api/sync/` cron endpoint remains at its current URL and keeps its `X-Sync-Token` contract.
- Django REST Framework JSON API support.
- JWT authentication with 10-minute access tokens, 30-day refresh tokens, refresh rotation, and refresh-token blacklist on logout.
- Username/email + password registration and login against the same Django `User` table used by the website.
- Google ID-token verification and linking to the same Django user by verified email / Google subject. Flutter must request an ID token for the server OAuth client ID configured as `GOOGLE_CLIENT_ID`.
- API throttling and `Cache-Control: no-store` for versioned API responses.
- APIs for games, picks, leaderboard, friends, reactions, notifications, chat, challenges, Crossfire, Relay Wars, history, player profiles/comparison, divisions, playoffs, squares, live moments, player feature summary, and device/push preference registration.
- Additive `Device` and `NotificationPreference` models. They store registration data and preferences; push delivery itself is not configured by this change.

## API routes

All routes below are prefixed with `/api/v1/`. Auth routes except logout are public. All other routes require `Authorization: Bearer <access_token>`.

| Method | Route | Purpose |
|---|---|---|
| POST | `auth/register/` | Create an account using the existing signup form validation |
| POST | `auth/login/` | Username/email + password login |
| POST | `auth/google/` | Verify Google ID token and issue JWTs |
| POST | `auth/refresh/` | Rotate refresh token and issue a new access token |
| POST | `auth/logout/` | Blacklist refresh token |
| GET / PATCH | `me/` | Read account / update favorite team or unlocked title |
| GET | `games/?season=&week=` | Game slate, lock state, score, own pick, community percentages |
| GET / POST | `picks/` | Read picks / create or change a pick before server-side lock |
| GET | `leaderboard/?tab=weekly\|season&mode=all\|friends&season=&week=` | Existing canonical standings |
| GET | `friends/` | Friends, incoming requests, outgoing requests |
| GET | `friends/search/?q=` | Search players |
| POST | `friends/requests/` | Send friend request (`user_id`) |
| POST | `friends/requests/{id}/respond/` | Accept or decline (`action`) |
| GET / POST | `notifications/` | Read in-app alerts / mark current alerts read |
| GET | `chat/status/` | Live chat status and whisper polling |
| GET / POST | `chat/games/{game_id}/` | Poll, start, or send a chat message |
| GET / POST / PATCH / DELETE | `devices/` | Register/unregister device and manage push preferences |
| POST | `games/{game_id}/reactions/` | React to a game |
| POST | `reactions/performance/` | React to a player's weekly performance |
| GET | `features/summary/?season=&week=` | Existing quests, achievements, playoff path, and weekly recap |
| GET | `history/?season=` | Signed-in player's pick history |
| GET | `players/{id}/` | Public player profile and record |
| GET | `players/{id}/compare/?season=&week=` | Side-by-side picks with existing friend/non-friend visibility rules |
| GET | `divisions/?division=` | Division standings and qualification status |
| GET | `playoffs/?season=` | Read-only qualification field and bracket preview |
| GET | `squares/?season=` | Read-only Super Bowl Squares board and quarter results |
| GET | `live-moments/?season=&week=` | Live-game reactions and confidence board |
| GET / POST | `challenges/` | List or create challenges |
| POST | `challenges/{id}/respond/` | Accept, decline, or cancel challenge |
| GET / POST | `crossfire/` | Read Crossfire board or fire a Crossfire; pass `game_id` on GET to retrieve eligible opposing-pick targets |
| DELETE | `crossfire/{id}/` | Cancel an unlocked Crossfire |
| GET / POST | `relaywars/` | Relay events, teams, queue, invite/join/leave actions |
| GET / POST | `relaywars/matches/{id}/` | Match state, available games, draft picks, skips, ability proposals and votes |

### Pick payload

`POST /api/v1/picks/`

```json
{
  "game_id": "the-existing-game-id",
  "side": "home",
  "confidence": 2
}
```

`side` is `home` or `away`. `confidence` is `1`, `2`, `3`, or `null`. The server checks the existing `Game.has_started` rule. A locked pick returns HTTP 409. Repeating the same pick request updates the existing unique `(user, game)` pick rather than creating a duplicate.

For non-idempotent mutations (friend requests/responses, chat sends, reactions, challenges, Crossfire, Relay Wars, and device registration/preferences), send an `Idempotency-Key` header containing a fresh UUID per intended action. Reuse that exact key only for retries of the same request. The API stores a hash of the request and replays the matching response for 48 hours; reusing a key with a different payload is rejected. Picks use an upsert on the existing unique user/game row, and profile updates are naturally repeatable. Old records can be removed with `python manage.py cleanup_mobile_idempotency`.

### Authentication request bodies

- Register: `username`, `email`, `password1`, `password2` (the existing `SignUpForm` enforces the website's username/password rules).
- Password login: `identifier` (username or email) and `password`.
- Google login: `id_token` from Google Sign-In.
- Refresh/logout: `refresh` token.
- Favorite team: `PATCH me/` with `favorite_team` (NFL abbreviation). An `active_title` can also be supplied if it is already unlocked.

### Authentication headers

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

The Flutter app must keep refresh tokens in the platform secure storage/keychain. Never put Django, Google, Tank01, or sync secrets in the app binary.

## Existing behavior deliberately preserved

- Website HTML routes and session authentication are unchanged.
- The website and Flutter client use the same `User`, `Pick`, `Game`, `FriendRequest`, `Challenge`, chat, Crossfire, and Relay Wars records.
- Standings and feature summaries call the existing Python calculation modules. No second grading or leaderboard implementation is introduced.
- Pick locks are enforced on the server, not trusted to the client.
- Community pick percentages remain hidden until the requesting player has made that game's pick, matching the website.
- Chat keeps the existing visibility, whisper privacy, room timing, and rate-limit rules by calling `accounts.chat`.
- Relay Wars uses the existing `relaywars.services` functions and membership rules.
- Scores are read from the database populated by the existing cron/Tank01 sync. Mobile polling cannot make the score data fresher than the server sync cadence.
- No Channels/WebSocket, Celery, PostgreSQL, or Django upgrade is introduced.

## Deployment steps (after review)

1. Back up the live database and project before deploying.
2. Install updated requirements in the existing virtualenv:
   `pip install -r requirements.txt`
3. Run:
   `python manage.py migrate`
4. Run:
   `python manage.py check`
5. Run:
   `python manage.py test mobileapi accounts api relaywars main`
6. Run:
   `python manage.py collectstatic --noinput`
7. Reload the PythonAnywhere web app.
8. Schedule `python manage.py flushexpiredtokens` daily to clean expired refresh-token blacklist records.
9. Schedule `python manage.py cleanup_mobile_idempotency` daily to remove cached mutation responses older than 48 hours.

Do not deploy until the new dependencies install successfully and the test suite passes in the actual PythonAnywhere virtualenv.

## Not configured / next website-preparation work

- FCM/APNs delivery credentials and a server-side push sender. Device registration and preference storage are only the foundation.
- A formal OpenAPI schema / generated Flutter client contract.
- Full API test coverage for every permission boundary, chat whisper visibility, Relay Wars vote rules, and challenge/Crossfire edge cases.
- API coverage for remaining website surfaces such as share-card link generation and any staff-only playoff/cut operations. Player-facing profiles, pick comparisons/history, divisions, playoff preview, Squares, and confidence board are exposed read-only.
- Production database concurrency review. SQLite remains the current deployment database; a PostgreSQL move needs a separate approved migration and backup plan.

## Security / secrets

The uploaded ZIP included a `.env` and database file. Neither belongs in a mobile build or in the source archive shared for app development. The distributable source ZIP must omit `.env`, `db.sqlite3`, and `.git`. If the uploaded archive was shared outside a trusted environment, rotate the secrets listed in the project's production checklist.
