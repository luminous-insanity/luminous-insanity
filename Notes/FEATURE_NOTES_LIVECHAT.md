# Live game chat (Social drawer -> "Live chat")

Polling-based (no websockets, fine for PythonAnywhere). Replaces the old
"Live energy" accordion; reactions still write `GameReaction`, so the
"Recent reactions" list and the no-JS `react_to_game` fallback keep working.

## Pieces
- `accounts/models.py`  `LiveChatRoom` (one per game) + `LiveChatMessage` (`is_hidden` = soft delete for the future moderator).
- `accounts/chat.py`    all rules: live window, whisper privacy, rate limits, serialization.
- `accounts/chat_views.py` + `urls.py`  `chat/status/`, `chat/<game>/poll|start|send/` (JSON, 401 when logged out).
- `static/js/livechat.js`  drawer chat; polls every 1s only while the Social drawer + Live chat tab are open and the browser tab is visible; its timer is stopped entirely when inactive.
- `static/js/chat_live.js` + `base.html`  site-wide announcement: polls `chat/status/` every 10s on every signed-in page.
- `theme.css`  styles at the bottom ("LIVE CHAT").

## Behaviour
- A room goes live when someone starts it (game window button) or posts the first public line; it goes idle after 10 min of silence and goes live again (new announcement) on the next public line.
- Announcement: one toast per live room per browser (`localStorage gdp-chat-seen`), pulsing dot on Social / Live chat tab / Dashboard links.
- Whispers: `/w friend msg`, `/r msg`, or tap a friend's name. Only accepted friends; only sender + recipient are ever sent the row. Whispers never make a room "live".
- Commands: `/w /r /me /s /friends /clear /help`. Limits: 240 chars, 1 line/sec, 8 lines/15s.
- Colors: author team badge (favorite-team primary/on_primary), your accents use `--primary`; friends = gold bar + star; whispers = pink/violet; emotes = orange.

## Deploy
`python manage.py migrate` (adds 0020), `collectstatic`, reload. Run `python manage.py test accounts.test_chat`.
