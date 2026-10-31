# Feature Status

What is implemented vs partial vs future. Based on code audit, not planning notes.

## Fully implemented (code + UI + logic)

| Feature | Notes |
|---------|--------|
| User auth (username/email + Google) | allauth |
| Picks + confidence + lockout | Server-side lock |
| Derived standings & ranking | Ties share rank |
| Leaderboard (season / week / friends) | |
| Dashboard | Stats, alerts, quests, path to playoffs, etc. |
| Friends / friend requests | |
| Challenges (game / week) | |
| Achievements + trophy page | Persistent unlocks |
| Crossfire | Tokens, aim, fire |
| Confidence board | |
| Path to Playoffs card | |
| Week recap | |
| Live / game reactions | After kickoff |
| Division Wars page | |
| Super Bowl Squares | Board + quarter scores |
| Dynamic playoff qualification | Pure algo + shadow + lock path |
| Playoff open / weekly cuts | Management commands |
| Relay Wars | Teams, queue, draft, abilities, scoring |
| Privacy / Terms / Contact | |

## Implemented; needs live-season verification

- Full playoff field lock under a real completed 18-week season
- Relay Wars first live week (draft lock at first kickoff, ability expiry)
- Score-correction edge cases under production cron timing

## Partial / polish

- Empty states: present on major pages; not every secondary panel is equally polished
- Loading indicators: limited (mostly full-page renders)
- Email verification policy: allauth defaults (not forced mandatory)
- Password reset: allauth URLs available; depends on SMTP

## Not implemented (product opportunities, not bugs)

- Dedicated analytics / Sentry
- Automated DB backup job inside the app (host-level backups expected)
- Rate limiting beyond host + sync token
- Mobile app

## Historical planning docs

Older phase/feature notes live under `Notes/` and describe how features were built. Prefer this file and `ARCHITECTURE.md` for current truth.
