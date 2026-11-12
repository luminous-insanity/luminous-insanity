"""Chat moderation: text rules, timeouts, mute/block, reports."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import chat, moderation
from accounts.models import ChatBlock, ChatReport, ChatSanction, LiveChatMessage
from accounts.moderation_rules import ALLOW, BLOCK, MASK, screen_text
from accounts.test_chat import befriend, make_game


class ScreenTextTests(SimpleTestCase):
    def test_normal_football_talk_is_untouched(self):
        for text in ('Great game, that pass was thrown perfectly', 'hell of a game',
                     'Dick Butkus was great', 'passing yards: 312', 'Final: 31 - 28',
                     'class act, bass is loud'):
            self.assertEqual(screen_text(text).action, ALLOW, text)

    def test_strong_profanity_is_starred_out(self):
        result = screen_text('what the fuck was that')
        self.assertEqual((result.action, result.text), (MASK, 'what the f*** was that'))
        self.assertEqual(screen_text('sh1t call').text, 's*** call')

    def test_threats_phone_email_and_links_are_blocked(self):
        for text in ('you suck, kys', 'k y s', 'call me at 555-123-4567',
                     'email me bob@example.com', 'check out www.bet.com'):
            self.assertEqual(screen_text(text).action, BLOCK, text)

    def test_links_can_be_allowed(self):
        self.assertEqual(screen_text('see www.nfl.com', allow_links=True).action, ALLOW)

    def test_spam(self):
        self.assertEqual(screen_text('buy buy buy buy buy buy buy').action, BLOCK)
        self.assertEqual(screen_text('GOOOOOOOAL!!!!!!!').text, 'GOOOAL!!!')

    def test_custom_blocked_terms(self):
        self.assertEqual(screen_text('xx badword xx', blocked_terms=['badword']).action, BLOCK)
        # Short terms only match whole words, so innocent words are safe.
        self.assertEqual(screen_text('badminton', blocked_terms=['bad']).action, ALLOW)
        self.assertEqual(screen_text('so bad', blocked_terms=['bad']).action, BLOCK)


@override_settings(NFL_SEASON=2026)
class ChatModerationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('alice', 'a@example.com', 'pw')
        self.bob = User.objects.create_user('bob', 'b@example.com', 'pw')
        self.cara = User.objects.create_user('cara', 'c@example.com', 'pw')
        befriend(self.alice, self.bob)
        self.game = make_game()
        self.t0 = timezone.now()

    def later(self, seconds):
        return self.t0 + timedelta(seconds=seconds)

    def say(self, user, body, at=0, **kwargs):
        return chat.post_message(self.game, user, body=body, now=self.later(at), **kwargs)

    def bodies(self, viewer):
        return [m['body'] for m in chat.poll(self.game, viewer)['messages']]

    # ---- filters ------------------------------------------------------------
    def test_profanity_is_masked_when_stored(self):
        msg = self.say(self.alice, 'what the fuck')
        self.assertEqual(msg.body, 'what the f***')

    def test_blocked_text_is_refused(self):
        with self.assertRaises(chat.ChatError) as ctx:
            self.say(self.alice, 'visit www.scam.com now')
        self.assertEqual(ctx.exception.status, 400)
        self.assertFalse(LiveChatMessage.objects.filter(kind='say').exists())

    def test_same_line_twice_is_refused(self):
        self.say(self.alice, 'Touchdown!', at=0)
        with self.assertRaises(chat.ChatError) as ctx:
            self.say(self.alice, 'Touchdown!', at=3)
        self.assertEqual(ctx.exception.status, 429)

    @override_settings(CHAT_BLOCKED_TERMS=['zebra'])
    def test_settings_terms_apply(self):
        with self.assertRaises(chat.ChatError):
            self.say(self.alice, 'a zebra appeared')

    # ---- timeouts -----------------------------------------------------------
    def test_timed_out_player_cannot_post(self):
        moderation.timeout_user(self.alice, minutes=15, reason='test')
        with self.assertRaises(chat.ChatError) as ctx:
            self.say(self.alice, 'hello')
        self.assertEqual(ctx.exception.status, 403)

    def test_expired_and_lifted_timeouts_do_not_block(self):
        ChatSanction.objects.create(user=self.alice, until=timezone.now() - timedelta(minutes=1))
        ChatSanction.objects.create(user=self.alice, until=None, revoked=True)
        self.assertIsNone(moderation.active_sanction(self.alice))
        self.say(self.alice, 'hello')

    def test_timeout_until_lifted_blocks(self):
        ChatSanction.objects.create(user=self.alice, until=None)
        self.assertIsNotNone(moderation.active_sanction(self.alice))

    # ---- mute / block ---------------------------------------------------------
    def test_mute_hides_public_lines_only_for_the_muter(self):
        self.say(self.bob, 'bob here', at=0)
        self.say(self.cara, 'cara here', at=2)
        moderation.set_block(self.alice, 'bob', 'mute')
        self.assertEqual(self.bodies(self.alice), ['cara here'])
        self.assertIn('bob here', self.bodies(self.cara))      # others still see it

    def test_mute_keeps_whispers_but_block_cuts_them(self):
        self.say(self.bob, 'psst', at=0, kind='whisper', to='alice')
        moderation.set_block(self.alice, 'bob', 'mute')
        self.assertIn('psst', self.bodies(self.alice))
        moderation.set_block(self.alice, 'bob', 'block')
        self.assertNotIn('psst', self.bodies(self.alice))

    def test_block_refuses_whispers_both_ways(self):
        moderation.set_block(self.alice, 'bob', 'block')
        with self.assertRaises(chat.ChatError):
            self.say(self.bob, 'hey', kind='whisper', to='alice')
        with self.assertRaises(chat.ChatError):
            self.say(self.alice, 'hey', at=3, kind='whisper', to='bob')

    def test_unmute_restores_lines(self):
        self.say(self.bob, 'bob here')
        moderation.set_block(self.alice, 'bob', 'mute')
        moderation.set_block(self.alice, 'bob', 'unmute')
        self.assertIn('bob here', self.bodies(self.alice))

    def test_cannot_mute_self_staff_or_strangers(self):
        for username, status in (('alice', 400), ('nobody', 404)):
            with self.assertRaises(moderation.ModerationBlocked) as ctx:
                moderation.set_block(self.alice, username, 'mute')
            self.assertEqual(ctx.exception.status, status)
        self.bob.is_staff = True
        self.bob.save()
        with self.assertRaises(moderation.ModerationBlocked):
            moderation.set_block(self.alice, 'bob', 'block')

    # ---- reports ------------------------------------------------------------------
    def test_report_records_snapshot_and_rejects_duplicates(self):
        msg = self.say(self.bob, 'rude words')
        report, created = moderation.report_message(self.alice, msg.id, ChatReport.HARASSMENT, 'mean')
        self.assertTrue(created)
        self.assertEqual((report.body_snapshot, report.reported_user), ('rude words', self.bob))
        _again, created = moderation.report_message(self.alice, msg.id, ChatReport.HARASSMENT)
        self.assertFalse(created)
        self.assertEqual(ChatReport.objects.count(), 1)

    def test_report_rules(self):
        own = self.say(self.alice, 'mine')
        whisper = self.say(self.bob, 'secret', at=3, kind='whisper', to='alice')
        for message_id, reason in ((own.id, 'spam'), (999999, 'spam'), (own.id, 'bogus')):
            with self.assertRaises(moderation.ModerationBlocked):
                moderation.report_message(self.alice, message_id, reason)
        with self.assertRaises(moderation.ModerationBlocked):      # not the recipient
            moderation.report_message(self.cara, whisper.id, 'spam')
        moderation.report_message(self.alice, whisper.id, 'spam')  # recipient may report

    def test_many_reporters_auto_hide_the_line(self):
        msg = self.say(self.bob, 'awful')
        extra = [User.objects.create_user(f'u{i}', f'u{i}@example.com', 'pw') for i in range(3)]
        for reporter in extra[:2]:
            moderation.report_message(reporter, msg.id, 'hate')
        msg.refresh_from_db()
        self.assertFalse(msg.is_hidden)
        moderation.report_message(extra[2], msg.id, 'hate')
        msg.refresh_from_db()
        self.assertTrue(msg.is_hidden)

    def test_staff_resolution_hides_and_times_out(self):
        staff = User.objects.create_user('mod', 'm@example.com', 'pw', is_staff=True)
        msg = self.say(self.bob, 'awful')
        report, _ = moderation.report_message(self.alice, msg.id, 'harassment')
        closed = moderation.resolve_reports(
            ChatReport.objects.filter(pk=report.pk), staff, 'hide_timeout', minutes=60)
        self.assertEqual(closed, 1)
        msg.refresh_from_db()
        report.refresh_from_db()
        self.assertTrue(msg.is_hidden)
        self.assertEqual((report.status, report.reviewed_by), (ChatReport.ACTIONED, staff))
        self.assertIsNotNone(moderation.active_sanction(self.bob))

    def test_dismiss_changes_nothing_else(self):
        staff = User.objects.create_user('mod', 'm@example.com', 'pw', is_staff=True)
        msg = self.say(self.bob, 'fine')
        report, _ = moderation.report_message(self.alice, msg.id, 'other')
        moderation.resolve_reports(ChatReport.objects.all(), staff, 'dismiss')
        msg.refresh_from_db()
        self.assertFalse(msg.is_hidden)
        self.assertIsNone(moderation.active_sanction(self.bob))

    @override_settings(CHAT_AI_MODERATOR='accounts.test_moderation.fake_ai_blocks_cats')
    def test_ai_hook_can_block(self):
        with self.assertRaises(chat.ChatError):
            self.say(self.alice, 'I love cats')
        self.say(self.alice, 'I love dogs', at=3)

    @override_settings(CHAT_AI_MODERATOR='accounts.test_moderation.fake_ai_crashes')
    def test_ai_hook_failure_fails_open(self):
        self.say(self.alice, 'still works')

    # ---- endpoints ----------------------------------------------------------------
    def test_report_and_block_endpoints(self):
        msg = self.say(self.bob, 'rude')
        self.client.force_login(self.alice)
        response = self.client.post(reverse('chat_report'), {'message_id': msg.id, 'reason': 'spam'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['created'])
        response = self.client.post(reverse('chat_block'), {'username': 'bob', 'action': 'mute'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse('chat_blocks')).json()['blocks'][0]['username'], 'bob')
        response = self.client.post(reverse('chat_block'), {'username': 'nobody', 'action': 'mute'})
        self.assertEqual(response.status_code, 404)

    def test_endpoints_need_login(self):
        self.assertEqual(self.client.post(reverse('chat_report'), {}).status_code, 401)


def fake_ai_blocks_cats(text, user):
    return {'action': 'block', 'reason': 'No cats.'} if 'cats' in text else None


def fake_ai_crashes(text, user):
    raise RuntimeError('model is down')
