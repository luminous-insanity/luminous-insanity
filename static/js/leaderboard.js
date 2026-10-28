/* Leaderboard: player action menu (popup / bottom sheet) and champion reveal. */
(function () {
    'use strict';

    var phone = window.matchMedia('(max-width: 700px)');

    function focusable(root) {
        return Array.prototype.filter.call(
            root.querySelectorAll('a[href], button:not([disabled])'),
            function (el) { return !el.hidden && el.offsetParent !== null; }
        );
    }

    /* Keeps Tab inside an open dialog. */
    function trapTab(event, panel) {
        if (event.key !== 'Tab') { return; }
        var items = focusable(panel);
        if (!items.length) { event.preventDefault(); return; }
        var first = items[0], last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault(); first.focus();
        }
    }

    /* ---------------------------------------------------- player menu --- */
    var menu = document.getElementById('player-menu');
    if (menu) {
        var panel = menu.querySelector('.player-menu-panel');
        var openedFrom = null;

        var el = function (id) { return document.getElementById(id); };

        function placePopup(row) {
            panel.style.transform = '';
            if (phone.matches) {            // CSS pins the bottom sheet
                panel.style.position = '';
                panel.style.top = '';
                panel.style.left = '';
                return;
            }

            /*
             * The desktop menu is inside a grid-centred overlay. Positioning a
             * relatively positioned panel with left/top offsets it from that
             * centred spot, which makes it appear beside the clicked player.
             * Fixed positioning makes these viewport coordinates exact.
             */
            var r = row.getBoundingClientRect();
            var w = panel.offsetWidth, h = panel.offsetHeight;
            var left = Math.min(Math.max(8, r.left + 24), window.innerWidth - w - 8);
            var top = r.bottom + 6;
            if (top + h > window.innerHeight - 8) {
                top = Math.max(8, r.top - h - 6);
            }
            panel.style.position = 'fixed';
            panel.style.left = left + 'px';
            panel.style.top = top + 'px';
        }

        function openMenu(row) {
            var d = row.dataset;
            var self = d.self === '1';
            openedFrom = row;

            el('player-menu-name').textContent = d.username;
            el('pm-season').textContent = d.seasonRecord;
            el('pm-pct').textContent = d.seasonPct;
            el('pm-week-wrap').hidden = !d.weekRecord;
            el('pm-week-label').textContent = d.weekLabel;
            el('pm-week').textContent = d.weekRecord;
            el('pm-weeks-won').textContent = d.weeksWon;
            el('pm-seasons-won').textContent = d.seasonsWon;
            el('pm-challenges').textContent = d.challengeRecord;

            var reactions = el('pm-reactions');
            if (reactions) {
                var canReact = !self && d.reactionAllowed === '1';
                reactions.hidden = !canReact;
                el('pm-reaction-heading').textContent = 'React to ' + d.username + '’s Week ' + d.reactionWeek + ' performance';
                Array.prototype.forEach.call(reactions.querySelectorAll('form'), function (form) {
                    form.action = d.reactionUrl || '#';
                    form.querySelector('[name="season"]').value = d.reactionSeason || '';
                    form.querySelector('[name="week"]').value = d.reactionWeek || '';
                    var button = form.querySelector('button');
                    var emoji = button.getAttribute('data-reaction-emoji');
                    var countKey = emoji === '👏' ? 'reactionClap' : (emoji === '🔥' ? 'reactionFire' : 'reactionCrown');
                    form.querySelector('[data-reaction-count]').textContent = d[countKey] || '0';
                    button.classList.toggle('is-active', d.reactionCurrent === emoji);
                    button.setAttribute('aria-pressed', d.reactionCurrent === emoji ? 'true' : 'false');
                });
            }

            el('pm-profile').href = d.profileUrl;
            el('pm-picks').href = d.picksUrl;
            el('pm-picks').textContent = self ? 'View My Picks' : 'View Picks';
            el('pm-challenge').href = d.challengeUrl;
            el('pm-challenge').hidden = self;   // can't challenge yourself

            menu.hidden = false;
            document.body.classList.add('player-menu-open');
            placePopup(row);
            el('pm-profile').focus();
        }

        function closeMenu() {
            if (menu.hidden) { return; }
            menu.hidden = true;
            panel.style.transform = '';
            document.body.classList.remove('player-menu-open');
            if (openedFrom) { openedFrom.focus(); openedFrom = null; }
        }

        document.addEventListener('click', function (event) {
            var row = event.target.closest('[data-menu-trigger]');
            if (row) { openMenu(row); return; }
            if (event.target.closest('[data-menu-close]')) { closeMenu(); }
        });

        document.addEventListener('keydown', function (event) {
            if (menu.hidden) { return; }
            if (event.key === 'Escape') {
                // Close only the menu, not the friends drawer behind it.
                event.stopImmediatePropagation();
                closeMenu();
                return;
            }
            trapTab(event, panel);
        });

        window.addEventListener('resize', function () {
            if (!menu.hidden) { placePopup(openedFrom || document.body); }
        });

        /* Swipe the bottom sheet down to dismiss it. */
        var startY = null, deltaY = 0;
        panel.addEventListener('touchstart', function (event) {
            if (!phone.matches || panel.scrollTop > 0) { startY = null; return; }
            startY = event.touches[0].clientY;
            deltaY = 0;
            panel.style.transition = 'none';
        }, { passive: true });

        panel.addEventListener('touchmove', function (event) {
            if (startY === null) { return; }
            deltaY = Math.max(0, event.touches[0].clientY - startY);
            panel.style.transform = 'translateY(' + deltaY + 'px)';
        }, { passive: true });

        panel.addEventListener('touchend', function () {
            if (startY === null) { return; }
            panel.style.transition = '';
            startY = null;
            if (deltaY > 90) { closeMenu(); } else { panel.style.transform = ''; }
        });
    }

    /* --------------------------------------------- champion reveal ----- */
    var champ = document.getElementById('champion-modal');
    if (champ) {
        var champPanel = champ.querySelector('.champion-modal-panel');
        var champFrom = null;

        function openChampion(from) {
            champFrom = from || null;
            champ.hidden = false;
            champPanel.focus();
        }

        function closeChampion() {
            if (champ.hidden) { return; }
            champ.hidden = true;
            if (champFrom) { champFrom.focus(); champFrom = null; }
        }

        document.addEventListener('click', function (event) {
            var opener = event.target.closest('[data-champion-open]');
            if (opener) { openChampion(opener); return; }
            if (event.target.closest('[data-champion-close]')) { closeChampion(); }
        });

        document.addEventListener('keydown', function (event) {
            if (champ.hidden) { return; }
            if (event.key === 'Escape') { closeChampion(); return; }
            trapTab(event, champPanel);
        });

        if (champ.dataset.auto === '1') { openChampion(null); }
    }
    document.addEventListener('click', function (event) {
        var requestLink = event.target.closest('[data-open-friend-requests]');
        if (!requestLink) { return; }
        var details = requestLink.closest('details');
        if (details) { details.open = false; }
        var toggle = document.getElementById('friendsToggle');
        if (toggle) { toggle.click(); }
        var tab = document.getElementById('friendsTabRequests');
        if (tab) { tab.click(); }
    });

})();
