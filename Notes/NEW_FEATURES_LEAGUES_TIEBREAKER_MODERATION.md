# New features: leagues, tiebreaker, moderation, insights, odds/injuries, Sentry, rate limits

## Install steps
1. `pip install -r requirements.txt`   (adds `sentry-sdk`)
2. `python manage.py migrate`          (accounts 0021, api 0016; SQLite stays as is)
3. `python manage.py test accounts api mobileapi main`   (new tests were written without being run; see "Not verified")
4. Optional `.env` entries (all have safe defaults):
   - `SENTRY_DSN=`  turn Sentry on, then `python manage.py sentry_test`
   - `CHAT_BLOCKED_TERMS=term1,term2`  extra words that block a chat line
   - `CHAT_PROFANITY_EXTRA=word1,word2`  extra words that get starred out
   - `LEAGUE_MAX_MEMBERS=50`, `LEAGUE_MAX_OWNED=5`, `LEAGUE_MAX_JOINED=15`
   - `RATELIMIT_ENABLED=False`  switch web-form rate limits off

## What was added
| Feature | Where | Notes |
|---|---|---|
| Private leagues | `accounts/leagues.py`, `league_views.py`, templates `leagues.html`, `league_detail.html`, `league_join.html` | Invite code + link, owner tools (rename, close joining, new code, remove, transfer, delete). Standings are computed from picks, never stored. Nav: profile menu > Private leagues. |
| The Score is Right | `accounts/tiebreaker.py`, `tiebreaker_rules.py`, `tiebreaker_views.py` | Guess the combined final score of the week's last game (or the game set in admin > Tiebreaker games). Closest without going over breaks ties on WEEKLY boards only; over-guesses rank below all under-guesses; no guess ranks last. No guesses = old behavior (shared rank). |
| Chat moderation | `accounts/moderation.py`, `moderation_rules.py` | Word filter, link/phone/email block, spam, duplicate lines, timeouts, /mute /block /unmute /unblock /blocked, report button on lines, auto-hide at 3 reporters, auto 15 min timeout after 3 hidden lines in 24h. Admin: Chat reports (review queue with actions), Chat sanctions, Chat blocks. |
| AI moderator hook | `CHAT_AI_MODERATOR` setting | Dotted path to `check(text, user)` returning `None`, `'block'` or `{'action': 'block', 'reason': '...'}`. Errors fail open. |
| My insights | `accounts/insights.py`, page `/accounts/insights/` | Home/road, favorite/underdog, confidence, with/against crowd, by team, by week, plain-English takeaways. |
| Site analytics (staff) | `accounts/analytics.py`, page `/accounts/staff/analytics/` | Active/new players, drop-off funnel, sign-ups per week, players per week + retention, chat/safety, leagues. Built from existing data; no tracking added. |
| Vegas odds + injuries | `api/models.py` (`GameOdds`, `InjuryReport`), `api/matchups.py`, admin, picks page | Display and insights only; never affects scoring. Load with admin or `python manage.py import_matchups file.json [--replace-injuries]` (format in the command's docstring). |
| Sentry | `GDP/settings.py` | Off until `SENTRY_DSN` is set. No user data sent. |
| Rate limiting | `accounts/ratelimit.py` | Signup, login (per IP and per account), friend search/requests, picks, chat send/report/block, leagues, tiebreaker, contact form. Mobile API uses DRF throttle scopes. Counters live in `.ratelimit_cache/`. |
| DB backup | `python manage.py backup_db [--keep N] [--dir PATH]` | Consistent SQLite copy + pruning. Schedule it daily. |

## Mobile API additions (`/api/v1/`)
- `leagues/` GET list, POST `{name}`; `leagues/join/` POST `{code}`; `leagues/<id>/` GET (`tab`, `season`, `week`), DELETE `{confirm}`; `leagues/<id>/action/` POST `{action: leave|rename|toggle_open|new_code|remove|transfer, ...}`
- `tiebreaker/` GET (`season`, `week`), POST `{game_id, total_points}`
- `insights/` GET (`season`)
- `matchups/` GET (`season`, `week`); `games/<game_id>/matchup/`; `games/` now includes `odds`
- `chat/report/` POST `{message_id, reason, details?}` (reasons: harassment, hate, threat, sexual, spam, other)
- `chat/blocks/` GET list, POST `{username, action: mute|block|unmute|unblock}`
- Existing chat endpoints now enforce the filters, timeouts and blocks automatically.

## Deliberately not included
Reminders/notifications/push, weekly digest email, email verification and password-reset email (need a site email), Postgres move, hosting changes, season wrapped, the user feed (the odds/injury tables are ready for it).

## Not verified
No Django in the build environment, so migrations, templates and the new tests were checked statically only (compile, import resolution, template tag balance, URL names) plus pure-logic runs of the tiebreaker, moderation text rules, rate counter and insights helpers. Run `python manage.py makemigrations --check` (should report no changes) and the test suite before deploying.
