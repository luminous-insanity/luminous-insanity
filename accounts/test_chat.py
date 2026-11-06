"""Live game chat: rooms going live, whispers staying private, rate limits."""
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import Game
from accounts import chat
from accounts.models import (
    FriendRequest, GameReaction, LiveChatMessage, LiveChatRoom, PlayerIdentity,
)


def make_game(game_id="CH-1", started=True, final=False):
    now = timezone.now()
    return Game.objects.create(
        season=2026, week=1, game_id=game_id, home_team="KC", away_team="BUF",
        game_date=timezone.localdate(),
        kickoff=now - timedelta(minutes=30) if started else now + timedelta(hours=5),
        status=Game.FINAL if final else (Game.LIVE if started else Game.SCHEDULED),
        home_score=17 if (started or final) else None,
        away_score=14 if (started or final) else None,
    )


def befriend(a, b):
    FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.ACCEPTED)


@override_settings(NFL_SEASON=2026)
class LiveChatTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "a@example.com", "pw")
        self.bob = User.objects.create_user("bob", "b@example.com", "pw")
        self.cara = User.objects.create_user("cara", "c@example.com", "pw")
        befriend(self.alice, self.bob)            # alice <-> bob are friends, cara is not
        self.game = make_game()
        self.t0 = timezone.now()

    def later(self, seconds):
        return self.t0 + timedelta(seconds=seconds)

    # ---- going live ------------------------------------------------------
    def test_first_public_message_opens_room_and_announces(self):
        chat.post_message(self.game, self.alice, body="Let's go!", now=self.later(0))
        room = LiveChatRoom.objects.get(game=self.game)
        self.assertEqual(room.started_by, self.alice)
        status = chat.live_status(self.bob, now=self.later(5))
        self.assertEqual([r["game_id"] for r in status["live"]], ["CH-1"])
        self.assertFalse(status["live"][0]["mine"])
        self.assertTrue(LiveChatMessage.objects.filter(kind="system", room=room).exists())

    def test_room_goes_idle_then_live_again_with_new_key(self):
        chat.post_message(self.game, self.alice, body="one", now=self.later(0))
        first = chat.live_status(self.bob, now=self.later(1))["live"][0]["key"]
        idle = chat.live_status(self.bob, now=self.later(60 * 11))
        self.assertEqual(idle["live"], [])
        chat.post_message(self.game, self.bob, body="anyone?", now=self.later(60 * 12))
        again = chat.live_status(self.alice, now=self.later(60 * 12 + 1))["live"][0]
        self.assertNotEqual(first, again["key"])
        self.assertEqual(again["started_by"], "bob")

    def test_chat_closed_before_kickoff(self):
        scheduled = make_game("CH-2", started=False)
        with self.assertRaises(chat.ChatError):
            chat.post_message(scheduled, self.alice, body="hi")
        with self.assertRaises(chat.ChatError):
            chat.open_room(scheduled, self.alice)

    # ---- whispers --------------------------------------------------------
    def test_whisper_only_reaches_sender_and_recipient(self):
        chat.post_message(self.game, self.alice, body="psst", kind="whisper", to="bob", now=self.later(0))
        for who, expected in ((self.alice, 1), (self.bob, 1), (self.cara, 0)):
            data = chat.poll(self.game, who, after=None, now=self.later(2))
            self.assertEqual(len(data["messages"]), expected, who.username)

    def test_whisper_requires_friendship(self):
        with self.assertRaises(chat.ChatError) as ctx:
            chat.post_message(self.game, self.alice, body="hey", kind="whisper", to="cara")
        self.assertEqual(ctx.exception.status, 403)
        with self.assertRaises(chat.ChatError):
            chat.post_message(self.game, self.alice, body="hey", kind="whisper", to="alice")
        with self.assertRaises(chat.ChatError):
            chat.post_message(self.game, self.alice, body="hey", kind="whisper", to="nobody")

    def test_whisper_does_not_make_room_live(self):
        chat.post_message(self.game, self.alice, body="psst", kind="whisper", to="bob", now=self.later(0))
        self.assertEqual(chat.live_status(self.cara, now=self.later(1))["live"], [])
        self.assertFalse(chat.poll(self.game, self.cara, after=None, now=self.later(1))["live"])

    def test_whisper_notification_for_recipient_only(self):
        chat.post_message(self.game, self.alice, body="you there?", kind="whisper", to="bob", now=self.later(0))
        bob = chat.live_status(self.bob, whisper_after=0, now=self.later(1))
        self.assertEqual([w["from"] for w in bob["whispers"]], ["alice"])
        self.assertEqual(chat.live_status(self.cara, whisper_after=0, now=self.later(1))["whispers"], [])
        self.assertEqual(chat.live_status(self.alice, whisper_after=0, now=self.later(1))["whispers"], [])

    def test_friend_flag_is_relative_to_the_viewer(self):
        chat.post_message(self.game, self.alice, body="hello", now=self.later(0))
        as_bob = chat.poll(self.game, self.bob, after=None, now=self.later(2))["messages"]
        as_cara = chat.poll(self.game, self.cara, after=None, now=self.later(2))["messages"]
        say = lambda msgs: [m for m in msgs if m["kind"] == "say"][0]
        self.assertTrue(say(as_bob)["friend"])
        self.assertFalse(say(as_cara)["friend"])

    # ---- reactions reuse GameReaction ------------------------------------
    def test_react_writes_chat_line_and_game_reaction(self):
        chat.post_message(self.game, self.alice, kind="react", emoji="🔥", now=self.later(0))
        self.assertEqual(GameReaction.objects.get(user=self.alice, game=self.game).emoji, "🔥")
        self.assertTrue(LiveChatMessage.objects.filter(kind="react", body="🔥").exists())
        with self.assertRaises(chat.ChatError):
            chat.post_message(self.game, self.alice, kind="react", emoji="🍕", now=self.later(5))

    # ---- limits & hygiene ------------------------------------------------
    def test_rate_limit_one_line_per_second(self):
        chat.post_message(self.game, self.alice, body="a", now=self.later(0))
        with self.assertRaises(chat.ChatError) as ctx:
            chat.post_message(self.game, self.alice, body="b", now=self.later(0.3))
        self.assertEqual(ctx.exception.status, 429)
        chat.post_message(self.game, self.alice, body="c", now=self.later(2))

    def test_empty_long_and_control_characters(self):
        with self.assertRaises(chat.ChatError):
            chat.post_message(self.game, self.alice, body="   \n ", now=self.later(0))
        with self.assertRaises(chat.ChatError):
            chat.post_message(self.game, self.alice, body="x" * 241, now=self.later(0))
        msg = chat.post_message(self.game, self.alice, body="hi\x00 there\n\nfriend", now=self.later(0))
        self.assertEqual(msg.body, "hi there friend")

    def test_hidden_messages_disappear_for_everyone(self):
        msg = chat.post_message(self.game, self.alice, body="oops", now=self.later(0))
        LiveChatMessage.objects.filter(pk=msg.pk).update(is_hidden=True)
        data = chat.poll(self.game, self.bob, after=None, now=self.later(2))
        self.assertNotIn("oops", [m["body"] for m in data["messages"]])

    def test_poll_cursor_only_returns_new_lines(self):
        chat.post_message(self.game, self.alice, body="one", now=self.later(0))
        data = chat.poll(self.game, self.bob, after=None, now=self.later(1))
        cursor = data["cursor"]
        self.assertEqual(chat.poll(self.game, self.bob, after=cursor, now=self.later(2))["messages"], [])
        chat.post_message(self.game, self.alice, body="two", now=self.later(3))
        newer = chat.poll(self.game, self.bob, after=cursor, now=self.later(4))["messages"]
        self.assertEqual([m["body"] for m in newer], ["two"])

    def test_team_badge_uses_favorite_team(self):
        PlayerIdentity.objects.create(user=self.alice, favorite_team="KC")
        chat.post_message(self.game, self.alice, body="hi", now=self.later(0))
        say = [m for m in chat.poll(self.game, self.bob, after=None, now=self.later(1))["messages"]
               if m["kind"] == "say"][0]
        self.assertEqual(say["author"]["team"], "KC")
        self.assertEqual(say["author"]["primary"], "#E31837")


@override_settings(NFL_SEASON=2026)
class LiveChatEndpointTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "a@example.com", "pw")
        self.bob = User.objects.create_user("bob", "b@example.com", "pw")
        befriend(self.alice, self.bob)
        self.game = make_game()

    def test_anonymous_gets_401_json(self):
        for name, args in (("chat_status", []), ("chat_poll", ["CH-1"])):
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response["Cache-Control"], "no-store")

    def test_send_then_poll_round_trip(self):
        self.client.force_login(self.alice)
        sent = self.client.post(reverse("chat_send", args=["CH-1"]), {"body": "Kickoff!"})
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(sent.json()["message"]["body"], "Kickoff!")
        self.client.force_login(self.bob)
        data = self.client.get(reverse("chat_poll", args=["CH-1"])).json()
        self.assertTrue(data["live"])
        self.assertIn("Kickoff!", [m["body"] for m in data["messages"]])
        self.assertEqual([f["name"] for f in data["friends"]], ["alice"])

    def test_start_endpoint_and_errors(self):
        self.client.force_login(self.alice)
        started = self.client.post(reverse("chat_start", args=["CH-1"]))
        self.assertTrue(started.json()["went_live"])
        self.assertEqual(self.client.post(reverse("chat_send", args=["NOPE"]), {"body": "x"}).status_code, 404)
        bad = self.client.post(reverse("chat_send", args=["CH-1"]), {"body": ""})
        self.assertEqual(bad.status_code, 400)

    def test_dashboard_renders_chat_for_live_games(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, 'id="gameChat"')
        self.assertContains(response, 'data-game-id="CH-1"')
        self.assertContains(response, "js/livechat.js")
        self.assertContains(response, "js/chat_live.js")     # site-wide announcer from base.html

    def test_one_second_message_polling_is_scoped_to_open_live_chat_drawer(self):
        project_root = Path(__file__).resolve().parents[1]
        livechat_js = (project_root / "static" / "js" / "livechat.js").read_text(encoding="utf-8")
        announcer_js = (project_root / "static" / "js" / "chat_live.js").read_text(encoding="utf-8")

        # The message poller must stop its timer whenever the drawer/tab is inactive.
        self.assertIn("if (!isActive())", livechat_js)
        self.assertIn("function stopPolling()", livechat_js)
        self.assertIn("No background timer", livechat_js)
        # The separate site-wide announcement poll remains deliberately slower.
        self.assertIn("var INTERVAL_MS = 10000", announcer_js)
