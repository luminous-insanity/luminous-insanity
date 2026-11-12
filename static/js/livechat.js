/* Live game chat for the Social drawer (polls once a second).
 *
 * Markup lives in accounts/dashboard.html (#gameChat). Endpoints are in
 * accounts/chat_views.py. World-of-Warcraft-vanilla flavoured:
 *   /w name msg   whisper a friend (only they see it)     /r msg   reply
 *   /me waves     emote                                   /s msg   say
 *   /friends      list your friends                       /help    commands
 * Click a friend's name to start whispering them.
 */
(function () {
    'use strict';

    var root = document.getElementById('gameChat');
    if (!root) return;

    var drawer = document.getElementById('friendsDrawer');
    var section = document.getElementById('socialSectionLive');
    var panel = document.getElementById('gchatPanel');
    var log = document.getElementById('gchatLog');
    var titleEl = document.getElementById('gchatTitle');
    var stateEl = document.getElementById('gchatState');
    var startBox = document.getElementById('gchatStart');
    var startBtn = document.getElementById('gchatStartBtn');
    var emotes = document.getElementById('gchatEmotes');
    var form = document.getElementById('gchatForm');
    var input = document.getElementById('gchatInput');
    var sendBtn = document.getElementById('gchatSend');
    var targetBox = document.getElementById('gchatTarget');
    var targetName = document.getElementById('gchatTargetName');
    var targetClear = document.getElementById('gchatTargetClear');
    var rows = Array.prototype.slice.call(root.querySelectorAll('[data-live-game]'));

    var POLL_MS = 1000;
    var MAX_BACKOFF_MS = 10000;
    var MAX_LINES = 300;

    var state = {
        gameId: null,
        cursor: null,        // null = first load (server sends the backlog)
        seen: {},            // message ids already drawn
        friends: [],         // [{id, name}] from the first load
        replyTo: '',         // last friend who whispered you (for /r)
        whisperTo: '',       // active whisper target, '' = say to the room
        open: true,          // chat window open for this game?
        live: false,
        room: false,
        timer: null,
        fails: 0,
        dead: false,         // session expired: stop polling
        token: 0,            // bumps when switching games to drop stale replies
        sending: false
    };

    /* ------------------------------------------------------------------ */
    /* helpers                                                             */
    /* ------------------------------------------------------------------ */
    function url(template, gameId) {
        return template.replace('__GAME__', encodeURIComponent(gameId));
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    function clock(ts) {
        var d = new Date(ts * 1000);
        var h = d.getHours() % 12 || 12;
        var m = d.getMinutes();
        return h + ':' + (m < 10 ? '0' : '') + m;
    }

    function nearBottom() {
        return log.scrollHeight - log.scrollTop - log.clientHeight < 48;
    }

    function trimLog() {
        while (log.childNodes.length > MAX_LINES) log.removeChild(log.firstChild);
    }

    function isActive() {
        return !document.hidden && !state.dead && !!state.gameId &&
            drawer && drawer.classList.contains('is-open') &&
            section && !section.hidden;
    }

    /* ------------------------------------------------------------------ */
    /* drawing the log                                                     */
    /* ------------------------------------------------------------------ */
    function teamBadge(author) {
        if (!author.team) return null;
        var badge = el('span', 'gchat-team', author.team);
        badge.style.background = author.primary;
        badge.style.color = author.on_primary || '#fff';
        badge.title = 'Favorite team: ' + author.team;
        return badge;
    }

    function nameNode(msg, label) {
        var who = label || msg.author.name;
        var canWhisper = !msg.mine && msg.friend;
        var node = el(canWhisper ? 'button' : 'span', 'gchat-name', who);
        if (canWhisper) {
            node.type = 'button';
            node.title = 'Whisper ' + who;
            node.addEventListener('click', function () { setWhisper(who); });
        }
        return node;
    }

    var REPORT_REASONS = [
        ['harassment', 'Harassment or bullying'],
        ['hate', 'Hate speech'],
        ['threat', 'Threats'],
        ['sexual', 'Sexual content'],
        ['spam', 'Spam or scam'],
        ['other', 'Something else']
    ];

    function openReportForm(line, msg) {
        // One small inline form under the line: pick a reason, send.
        var existing = line.querySelector('.gchat-report-form');
        if (existing) { existing.remove(); return; }
        var form = el('span', 'gchat-report-form');
        var select = el('select', 'gchat-report-reason');
        select.setAttribute('aria-label', 'Reason for report');
        REPORT_REASONS.forEach(function (r) {
            var o = el('option', null, r[1]);
            o.value = r[0];
            select.appendChild(o);
        });
        var send = el('button', 'btn btn-sm', 'Report');
        send.type = 'button';
        var cancel = el('button', 'btn btn-quiet btn-sm', 'Cancel');
        cancel.type = 'button';
        cancel.addEventListener('click', function () { form.remove(); });
        send.addEventListener('click', function () {
            send.disabled = true;
            post(root.dataset.reportUrl, {
                message_id: msg.id, reason: select.value
            }).then(function (data) {
                form.remove();
                addLocal(data.message || 'Thanks. Staff will review this report.', 'system');
            }).catch(function (err) {
                send.disabled = false;
                addLocal(err.message, 'error');
            });
        });
        form.appendChild(select);
        form.appendChild(send);
        form.appendChild(cancel);
        line.appendChild(form);
    }

    function addReportButton(line, msg) {
        if (msg.mine || !root.dataset.reportUrl) return;
        var btn = el('button', 'gchat-report', '\u2691');
        btn.type = 'button';
        btn.title = 'Report this message';
        btn.setAttribute('aria-label', 'Report this message');
        btn.addEventListener('click', function () { openReportForm(line, msg); });
        line.appendChild(btn);
    }

    function renderMessage(msg) {
        var line = el('div', 'gchat-line gchat-' + msg.kind);
        if (msg.mine) line.classList.add('is-mine');
        if (msg.author) line.dataset.author = msg.author.name.toLowerCase();
        var time = el('span', 'gchat-time', clock(msg.ts));
        line.appendChild(time);

        if (msg.kind === 'system') {
            line.appendChild(el('span', 'gchat-text', msg.body));
            return line;
        }

        if (msg.kind === 'whisper') {
            if (msg.mine) {
                line.appendChild(el('span', 'gchat-pre', 'To '));
                var toBtn = el('button', 'gchat-name', msg.to);
                toBtn.type = 'button';
                toBtn.title = 'Whisper ' + msg.to;
                toBtn.addEventListener('click', function () { setWhisper(msg.to); });
                line.appendChild(toBtn);
                line.appendChild(el('span', 'gchat-colon', ': '));
            } else {
                state.replyTo = msg.author.name;
                var badge = teamBadge(msg.author);
                if (badge) line.appendChild(badge);
                var from = el('button', 'gchat-name', msg.author.name);
                from.type = 'button';
                from.title = 'Whisper ' + msg.author.name;
                from.addEventListener('click', function () { setWhisper(msg.author.name); });
                line.appendChild(from);
                line.appendChild(el('span', 'gchat-pre', ' whispers: '));
            }
            line.appendChild(el('span', 'gchat-text', msg.body));
            addReportButton(line, msg);
            return line;
        }

        if (msg.friend) {
            line.classList.add('is-friend');
            var star = el('span', 'gchat-star', '★');
            star.title = 'Friend';
            line.appendChild(star);
        }
        var teamBadgeNode = teamBadge(msg.author);
        if (teamBadgeNode) line.appendChild(teamBadgeNode);

        if (msg.kind === 'emote') {
            line.appendChild(nameNode(msg));
            line.appendChild(el('span', 'gchat-text', ' ' + msg.body));
        } else if (msg.kind === 'react') {
            line.appendChild(nameNode(msg));
            line.appendChild(el('span', 'gchat-pre', ' reacts '));
            line.appendChild(el('span', 'gchat-emoji', msg.body));
        } else {
            line.appendChild(nameNode(msg));
            line.appendChild(el('span', 'gchat-colon', ': '));
            line.appendChild(el('span', 'gchat-text', msg.body));
        }
        if (msg.kind === 'say' || msg.kind === 'emote') addReportButton(line, msg);
        return line;
    }

    function addLocal(text, kind) {
        // Client-only line (help, errors). Never stored, never sent.
        var stick = nearBottom();
        var line = el('div', 'gchat-line gchat-' + (kind || 'system'));
        line.appendChild(el('span', 'gchat-text', text));
        log.appendChild(line);
        trimLog();
        if (stick) log.scrollTop = log.scrollHeight;
    }

    function addMessages(list) {
        if (!list || !list.length) return;
        var stick = nearBottom();
        var added = false;
        list.forEach(function (msg) {
            if (state.seen[msg.id]) return;
            state.seen[msg.id] = true;
            log.appendChild(renderMessage(msg));
            if (msg.mine) stick = true;
            added = true;
        });
        if (added) {
            trimLog();
            if (stick) log.scrollTop = log.scrollHeight;
        }
    }

    /* ------------------------------------------------------------------ */
    /* panel state                                                         */
    /* ------------------------------------------------------------------ */
    function applyPanelState() {
        var quiet = !state.live;
        stateEl.textContent = !state.open ? 'Closed' : (state.live ? 'Live' : 'Quiet');
        stateEl.className = 'pill' + (state.live && state.open ? ' pill-live' : '');
        // Offer "Start chat" only when nobody has the room going.
        startBox.hidden = !(state.open && quiet);
        var canType = state.open;
        input.disabled = !canType;
        sendBtn.disabled = !canType;
        Array.prototype.forEach.call(emotes.querySelectorAll('button'), function (b) {
            b.disabled = !canType;
        });
        if (!canType) input.placeholder = 'Chat is closed for this game.';
        else input.placeholder = 'Say something…  (/w friend, /me, /help)';
    }

    function updateGameRow(game) {
        rows.forEach(function (row) {
            if (row.dataset.gameId !== game.id) return;
            var line = row.querySelector('[data-game-line]');
            if (!line) return;
            line.textContent = game.away + ' ' + (game.away_score === null ? '' : game.away_score) +
                ' @ ' + game.home + ' ' + (game.home_score === null ? '' : game.home_score);
        });
        if (state.gameId === game.id) {
            titleEl.textContent = game.label +
                (game.away_score !== null && game.home_score !== null
                    ? '  ·  ' + game.away_score + '–' + game.home_score : '');
        }
    }

    function applyPoll(data) {
        state.open = !!data.open;
        state.live = !!data.live;
        state.room = !!data.room;
        if (data.game) updateGameRow(data.game);
        if (data.friends) state.friends = data.friends;
        addMessages(data.messages);
        state.cursor = data.cursor || 0;
        applyPanelState();
    }

    /* ------------------------------------------------------------------ */
    /* polling                                                             */
    /* ------------------------------------------------------------------ */
    function stopPolling() {
        clearTimeout(state.timer);
        state.timer = null;
    }

    function schedule(ms) {
        // Do not keep a one-second timer alive while the drawer/tab is closed.
        if (!isActive()) {
            stopPolling();
            return;
        }
        clearTimeout(state.timer);
        state.timer = setTimeout(tick, ms);
    }

    function tick() {
        state.timer = null;
        if (state.dead || !isActive()) {
            stopPolling();
            return;
        }
        var token = state.token;
        var gid = state.gameId;
        var q = state.cursor === null ? '' : '?after=' + state.cursor;
        fetch(url(root.dataset.pollUrl, gid) + q, {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { 'Accept': 'application/json' }
        }).then(function (resp) {
            if (resp.status === 401) { state.dead = true; throw new Error('auth'); }
            if (!resp.ok) throw new Error('http ' + resp.status);
            return resp.json();
        }).then(function (data) {
            if (token !== state.token) return;           // switched games meanwhile
            state.fails = 0;
            applyPoll(data);
            schedule(POLL_MS);
        }).catch(function (err) {
            if (state.dead) {
                addLocal('Your session has ended. Reload the page to log in again.', 'error');
                return;
            }
            if (!isActive()) { stopPolling(); return; }
            if (token !== state.token) { schedule(POLL_MS); return; }
            state.fails += 1;
            if (state.fails === 3) addLocal('Connection trouble. Retrying…', 'error');
            schedule(Math.min(POLL_MS * Math.pow(2, state.fails), MAX_BACKOFF_MS));
        });
    }

    function pollNow() { schedule(0); }

    /* ------------------------------------------------------------------ */
    /* choosing a game window                                              */
    /* ------------------------------------------------------------------ */
    function ensureGameRow(gameId, label) {
        var existing = rows.filter(function (r) { return r.dataset.gameId === gameId; })[0];
        if (existing) return existing;
        var list = document.getElementById('socialLiveGameList');
        if (!list) return null;
        var li = document.createElement('li');
        li.className = 'live-game-row';
        li.setAttribute('data-live-game', '');
        li.dataset.gameId = gameId;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'live-game-toggle';
        btn.setAttribute('aria-expanded', 'false');
        var line = document.createElement('strong');
        line.setAttribute('data-game-line', '');
        line.textContent = label || ('Game ' + gameId);
        btn.appendChild(line);
        var badge = document.createElement('span');
        badge.className = 'gchat-live-badge pill pill-live';
        badge.hidden = true;
        badge.textContent = 'LIVE';
        btn.appendChild(badge);
        li.appendChild(btn);
        list.appendChild(li);
        rows.push(li);
        btn.addEventListener('click', function () { selectGame(gameId); });
        return li;
    }

    function selectGame(gameId, label) {
        if (!gameId) return false;
        var row = rows.filter(function (r) { return r.dataset.gameId === gameId; })[0];
        if (!row) {
            row = ensureGameRow(gameId, label);
        }
        if (!row) {
            // Still allow chat without a row in the list
            if (state.gameId === gameId) { pollNow(); return true; }
            state.gameId = gameId;
            state.token += 1;
            state.cursor = null;
            state.seen = {};
            state.fails = 0;
            state.live = false;
            state.open = true;
            log.textContent = '';
            titleEl.textContent = label || ('Game ' + gameId);
            panel.hidden = false;
            applyPanelState();
            pollNow();
            return true;
        }
        if (state.gameId === gameId) { pollNow(); return true; }
        state.gameId = gameId;
        state.token += 1;
        state.cursor = null;
        state.seen = {};
        state.fails = 0;
        state.live = false;
        state.open = true;
        log.textContent = '';
        rows.forEach(function (r) {
            var on = r === row;
            r.classList.toggle('is-selected', on);
            var b = r.querySelector('.live-game-toggle');
            if (b) b.setAttribute('aria-pressed', String(on));
        });
        var line = row.querySelector('[data-game-line]');
        titleEl.textContent = line ? line.textContent.replace(/\s+/g, ' ').trim() : (label || 'Game chat');
        panel.hidden = false;
        applyPanelState();
        pollNow();
        return true;
    }

    rows.forEach(function (row) {
        var btn = row.querySelector('.live-game-toggle');
        if (btn) btn.addEventListener('click', function () { selectGame(row.dataset.gameId); });
    });

    function pickDefaultGame() {
        var wanted = root.dataset.initialGame;
        if (wanted && selectGame(wanted)) return;
        var liveRooms = (window.GDPLiveRooms || []).map(function (r) { return r.game_id; });
        var preferred = rows.filter(function (r) { return liveRooms.indexOf(r.dataset.gameId) !== -1; })[0];
        selectGame((preferred || rows[0]).dataset.gameId);
    }

    /* ------------------------------------------------------------------ */
    /* sending                                                             */
    /* ------------------------------------------------------------------ */
    function post(path, fields) {
        var body = new URLSearchParams();
        Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
        return fetch(path, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': root.dataset.csrf,
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: body.toString()
        }).then(function (resp) {
            return resp.json().catch(function () { return {}; }).then(function (data) {
                if (resp.status === 401) state.dead = true;
                if (!resp.ok) {
                    var e = new Error(data.error || 'Something went wrong.');
                    e.status = resp.status;
                    throw e;
                }
                return data;
            });
        });
    }

    function send(fields) {
        if (state.sending || !state.gameId) return Promise.resolve(false);
        state.sending = true;
        sendBtn.disabled = true;
        return post(url(root.dataset.sendUrl, state.gameId), fields).then(function (data) {
            if (data.message) addMessages([data.message]);
            pollNow();
            return true;
        }).catch(function (err) {
            addLocal(err.message, 'error');
            return false;
        }).then(function (ok) {
            state.sending = false;
            sendBtn.disabled = !state.open;
            return ok;
        });
    }

    function setWhisper(name) {
        state.whisperTo = name || '';
        targetBox.hidden = !state.whisperTo;
        targetName.textContent = state.whisperTo;
        input.classList.toggle('is-whisper', !!state.whisperTo);
        input.focus();
    }

    function help() {
        [
            'Chat commands:',
            '/w <friend> <message>  whisper a friend (only they see it)',
            '/r <message>  reply to the last friend who whispered you',
            '/me <action>  emote',
            '/s <message>  say to the room',
            '/friends  list your friends     /clear  clear this window',
            '/mute <name>  hide a player\u2019s lines     /unmute <name>',
            '/block <name>  hide lines and refuse whispers     /unblock <name>',
            '/blocked  list who you have muted or blocked',
            'Tap the \u2691 on a line to report it to the moderators.',
            'Tip: tap a friend\u2019s name to whisper them. ★ marks friends.'
        ].forEach(function (t) { addLocal(t, 'system'); });
    }

    function moderate(action, name) {
        return post(root.dataset.blockUrl, { action: action, username: name }).then(function (data) {
            addLocal(data.message || 'Done.', 'system');
            if (action === 'mute' || action === 'block') {
                // Clear what is already on screen from that player.
                var who = name.toLowerCase();
                Array.prototype.slice.call(log.querySelectorAll('.gchat-line')).forEach(function (line) {
                    if (line.dataset.author !== who) return;
                    if (action === 'mute' && line.classList.contains('gchat-whisper')) return;
                    line.remove();
                });
            }
            return true;
        }).catch(function (err) {
            addLocal(err.message, 'error');
            return false;
        });
    }

    function runCommand(text) {
        var m = /^\/(\S+)\s*([\s\S]*)$/.exec(text);
        var cmd = (m ? m[1] : '').toLowerCase();
        var rest = m ? m[2].trim() : '';
        switch (cmd) {
            case 'help': case '?':
                help(); return Promise.resolve(true);
            case 'clear':
                log.textContent = ''; return Promise.resolve(true);
            case 'friends': case 'f':
                addLocal(state.friends.length
                    ? 'Friends: ' + state.friends.map(function (f) { return f.name; }).join(', ')
                    : 'You have no friends added yet.', 'system');
                return Promise.resolve(true);
            case 's': case 'say':
                if (!rest) return Promise.resolve(true);
                return send({ kind: 'say', body: rest });
            case 'me': case 'emote':
                if (!rest) return Promise.resolve(true);
                return send({ kind: 'emote', body: rest });
            case 'r': case 'reply':
                if (!state.replyTo) { addLocal('Nobody has whispered you yet.', 'error'); return Promise.resolve(false); }
                if (!rest) { setWhisper(state.replyTo); return Promise.resolve(true); }
                return send({ kind: 'whisper', to: state.replyTo, body: rest });
            case 'w': case 'whisper': case 't': case 'tell':
                var parts = /^(\S+)\s*([\s\S]*)$/.exec(rest);
                if (!parts) { addLocal('Usage: /w <friend> <message>', 'error'); return Promise.resolve(false); }
                if (!parts[2].trim()) { setWhisper(parts[1]); return Promise.resolve(true); }
                return send({ kind: 'whisper', to: parts[1], body: parts[2].trim() });
            case 'mute': case 'unmute': case 'block': case 'unblock':
                if (!rest) { addLocal('Usage: /' + cmd + ' <name>', 'error'); return Promise.resolve(false); }
                return moderate(cmd, rest.split(/\s+/)[0]);
            case 'blocked': case 'muted': case 'ignored':
                return fetch(root.dataset.blocksUrl, {
                    credentials: 'same-origin', cache: 'no-store',
                    headers: { 'Accept': 'application/json' }
                }).then(function (resp) { return resp.json(); }).then(function (data) {
                    var list = data.blocks || [];
                    addLocal(list.length
                        ? 'Muted or blocked: ' + list.map(function (b) { return b.username + ' (' + b.kind + ')'; }).join(', ')
                        : 'You have not muted or blocked anyone.', 'system');
                    return true;
                }).catch(function () { addLocal('Could not load the list.', 'error'); return false; });
            default:
                addLocal('Unknown command. Type /help.', 'error');
                return Promise.resolve(false);
        }
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        var text = input.value.trim();
        if (!text || !state.open) return;
        var job;
        if (text.charAt(0) === '/') job = runCommand(text);
        else if (state.whisperTo) job = send({ kind: 'whisper', to: state.whisperTo, body: text });
        else job = send({ kind: 'say', body: text });
        job.then(function (ok) { if (ok) input.value = ''; });
    });

    input.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && state.whisperTo) {
            event.stopPropagation();       // don't also close the drawer
            setWhisper('');
        }
    });
    targetClear.addEventListener('click', function () { setWhisper(''); });

    Array.prototype.forEach.call(emotes.querySelectorAll('button[data-emoji]'), function (btn) {
        btn.addEventListener('click', function () {
            send({ kind: 'react', emoji: btn.dataset.emoji });
        });
    });

    startBtn.addEventListener('click', function () {
        if (!state.gameId) return;
        startBtn.disabled = true;
        post(url(root.dataset.startUrl, state.gameId), {}).then(function () {
            pollNow();
        }).catch(function (err) {
            addLocal(err.message, 'error');
        }).then(function () { startBtn.disabled = false; });
    });

    /* ------------------------------------------------------------------ */
    /* wiring                                                              */
    /* ------------------------------------------------------------------ */
    // "Chat live" badges on the game windows (fed by the site-wide status poll).
    document.addEventListener('gdp:live-rooms', function (event) {
        var live = (event.detail && event.detail.rooms || []).map(function (r) { return r.game_id; });
        rows.forEach(function (row) {
            var badge = row.querySelector('.gchat-live-badge');
            if (badge) badge.hidden = live.indexOf(row.dataset.gameId) === -1;
        });
    });

    document.addEventListener('visibilitychange', function () {
        if (isActive()) pollNow();
        else stopPolling();
    });

    // First time the Live chat section is shown, pick a game and start polling.
    var started = false;
    function maybeStart() {
        if (!isActive()) {
            stopPolling();
            return;
        }
        if (!started) {
            started = true;
            pickDefaultGame();
        } else if (state.gameId) {
            // Resume immediately when the drawer/tab becomes active again.
            pollNow();
        }
    }
    if (window.MutationObserver) {
        var obs = new MutationObserver(maybeStart);
        obs.observe(section, { attributes: true, attributeFilter: ['hidden'] });
        obs.observe(drawer, { attributes: true, attributeFilter: ['class'] });
    }
    maybeStart();

    // Public hooks: used by the dashboard and the site-wide announcement.
    window.GDPChat = {
        isActive: isActive,
        open: function (gameId, label) {
            started = true;
            if (gameId && selectGame(gameId, label)) return;
            pickDefaultGame();
        },
        ensureGame: ensureGameRow
    };

    // No background timer: polling starts only when the Live Chat drawer is active.
})();
