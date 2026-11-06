/* Site-wide "a chat just went live" announcement (every signed-in page).
 *
 * Polls /accounts/chat/status/ every 10s (paused while the tab is hidden):
 *   - toasts once per live room ("Chat is live: DAL @ PHI  [Join chat]")
 *   - toasts when a friend whispers you and you're not already in the chat
 *   - lights a pulsing dot on the Social button, its Live chat tab and the
 *     Dashboard links while any chat is live
 * The 1-second message polling itself lives in livechat.js (dashboard only).
 */
(function () {
    'use strict';

    var cfg = document.getElementById('gdpChatLive');
    var box = document.getElementById('chatToasts');
    if (!cfg || !box) return;

    var INTERVAL_MS = 10000;
    var MAX_BACKOFF_MS = 60000;
    var TOAST_MS = 14000;
    var SEEN_KEY = 'gdp-chat-seen';
    var WHISPER_KEY = 'gdp-whisper-after';

    var timer = null;
    var fails = 0;
    var dead = false;
    var whisperAfter = readWhisperCursor();

    /* ---- small storage helpers (storage can be blocked) --------------- */
    function readSeen() {
        try { return JSON.parse(localStorage.getItem(SEEN_KEY) || '[]'); } catch (e) { return []; }
    }
    function writeSeen(list) {
        try { localStorage.setItem(SEEN_KEY, JSON.stringify(list.slice(-40))); } catch (e) { /* ignore */ }
    }
    function readWhisperCursor() {
        try {
            var v = sessionStorage.getItem(WHISPER_KEY);
            return v === null ? null : parseInt(v, 10);
        } catch (e) { return null; }
    }
    function writeWhisperCursor(n) {
        try { sessionStorage.setItem(WHISPER_KEY, String(n)); } catch (e) { /* ignore */ }
    }

    /* ---- toasts -------------------------------------------------------- */
    function openChat(gameId) {
        if (window.GDPChat) {
            document.dispatchEvent(new CustomEvent('gdp:open-chat', { detail: { gameId: gameId } }));
        } else {
            window.location.href = cfg.dataset.dashboardUrl + '?chat=' + encodeURIComponent(gameId);
        }
    }

    function toast(opts) {
        while (box.children.length >= 3) box.removeChild(box.firstChild);
        var node = document.createElement('div');
        node.className = 'chat-toast' + (opts.whisper ? ' is-whisper' : '');
        node.setAttribute('role', 'status');

        var body = document.createElement('div');
        body.className = 'chat-toast-body';
        var title = document.createElement('strong');
        title.textContent = opts.title;
        body.appendChild(title);
        if (opts.detail) {
            var detail = document.createElement('span');
            detail.textContent = opts.detail;
            body.appendChild(detail);
        }
        node.appendChild(body);

        function dismiss() { if (node.parentNode) node.parentNode.removeChild(node); }

        var join = document.createElement('button');
        join.type = 'button';
        join.className = 'btn btn-red btn-sm';
        join.textContent = opts.action;
        join.addEventListener('click', function () { dismiss(); openChat(opts.gameId); });
        node.appendChild(join);

        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'chat-toast-close';
        close.setAttribute('aria-label', 'Dismiss');
        close.textContent = '\u00d7';
        close.addEventListener('click', dismiss);
        node.appendChild(close);

        box.appendChild(node);
        setTimeout(dismiss, TOAST_MS);
    }

    /* ---- live indicators ------------------------------------------------ */
    function setDots(on) {
        var targets = [];
        var t = document.getElementById('friendsToggle');
        if (t) targets.push(t);
        var n = document.getElementById('socialNavLive');
        if (n) targets.push(n);
        Array.prototype.forEach.call(document.querySelectorAll('[data-chat-dot]'), function (a) {
            targets.push(a);
        });
        targets.forEach(function (node) { node.classList.toggle('has-live-chat', on); });
    }

    function handle(data) {
        var rooms = data.live || [];
        window.GDPLiveRooms = rooms;
        setDots(rooms.length > 0);
        document.dispatchEvent(new CustomEvent('gdp:live-rooms', { detail: { rooms: rooms } }));

        var inChat = !!(window.GDPChat && window.GDPChat.isActive());
        var seen = readSeen();
        var changed = false;
        rooms.forEach(function (room) {
            if (seen.indexOf(room.key) !== -1) return;
            seen.push(room.key);
            changed = true;
            if (room.mine || inChat) return;
            toast({
                title: '\uD83D\uDCAC Chat is live: ' + room.label,
                detail: room.started_by ? room.started_by + ' started it.' : '',
                action: 'Join chat',
                gameId: room.game_id
            });
        });
        if (changed) writeSeen(seen);

        // First response only sets the cursor so old whispers never pop up.
        if (whisperAfter !== null && !inChat) {
            (data.whispers || []).forEach(function (w) {
                toast({
                    title: '\uD83D\uDC8C ' + w.from + ' whispers you',
                    detail: w.preview,
                    action: 'Reply',
                    gameId: w.game_id,
                    whisper: true
                });
            });
        }
        whisperAfter = Math.max(whisperAfter === null ? 0 : whisperAfter, data.whisper_cursor || 0);
        writeWhisperCursor(whisperAfter);
    }

    /* ---- polling -------------------------------------------------------- */
    function schedule(ms) {
        clearTimeout(timer);
        timer = setTimeout(tick, ms);
    }

    function tick() {
        if (dead) return;
        if (document.hidden) { schedule(INTERVAL_MS); return; }
        var q = whisperAfter === null ? '' : '?whisper_after=' + whisperAfter;
        fetch(cfg.dataset.statusUrl + q, {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { 'Accept': 'application/json' }
        }).then(function (resp) {
            if (resp.status === 401) { dead = true; throw new Error('auth'); }
            if (!resp.ok) throw new Error('http ' + resp.status);
            return resp.json();
        }).then(function (data) {
            fails = 0;
            handle(data);
            schedule(INTERVAL_MS);
        }).catch(function () {
            if (dead) return;
            fails += 1;
            schedule(Math.min(INTERVAL_MS * Math.pow(2, fails), MAX_BACKOFF_MS));
        });
    }

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && !dead) schedule(0);
    });

    schedule(1500);
})();
