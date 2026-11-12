"""Live-chat moderation: filters, timeouts, mute/block and player reports.

Layers, cheapest first:
  1. Sanctions   a timed-out player cannot post (ChatSanction).
  2. Text rules  moderation_rules.screen_text(): profanity masked, threats,
                 links, phone numbers and spam blocked.
  3. Duplicates  the same line twice within DUPLICATE_WINDOW is refused.
  4. AI hook     optional. Point settings.CHAT_AI_MODERATOR at a function
                 `check(text, user)` that returns None / 'ok' to allow, or
                 'block' / {'action': 'block', 'reason': '...'} to refuse.
                 It is skipped (message allowed) if it errors, so an outage
                 never silences the chat.
  5. Players     mute / block (ChatBlock) and report (ChatReport).
  6. Staff       review reports in Django admin: hide a line, time a player out.

Settings (all optional):
  CHAT_BLOCKED_TERMS        list of extra terms that block a message
  CHAT_PROFANITY_EXTRA      list of extra words to star out
  CHAT_ALLOW_LINKS          True to allow links (default False)
  CHAT_AI_MODERATOR         dotted path to the AI hook above
  CHAT_REPORTS_TO_HIDE      distinct reporters that auto-hide a line (default 3)
  CHAT_AUTO_TIMEOUT_AFTER   auto-hidden lines in 24h that earn a timeout (default 3)
  CHAT_AUTO_TIMEOUT_MINUTES length of that timeout (default 15)
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import ChatBlock, ChatReport, ChatSanction, LiveChatMessage
from .moderation_rules import ALLOW, BLOCK, screen_text

log = logging.getLogger(__name__)

DUPLICATE_WINDOW = timedelta(seconds=30)


class ModerationBlocked(Exception):
    def __init__(self, message, status=403):
        super().__init__(message)
        self.message = message
        self.status = status


def _setting(name, default):
    return getattr(settings, name, default)


# --------------------------------------------------------------------------
# Timeouts
# --------------------------------------------------------------------------
def active_sanction(user, now=None):
    """The player's current chat timeout, or None."""
    now = now or timezone.now()
    for sanction in ChatSanction.objects.filter(user=user, revoked=False):
        if sanction.until is None or sanction.until > now:
            return sanction
    return None


def check_can_post(user, now=None):
    sanction = active_sanction(user, now)
    if sanction is None:
        return
    if sanction.until is None:
        raise ModerationBlocked('You are muted from chat until staff lift it.')
    when = timezone.localtime(sanction.until).strftime('%I:%M %p').lstrip('0')
    raise ModerationBlocked(f'You are timed out from chat until {when}.')


def timeout_user(user, minutes=None, reason='', created_by=None, source=ChatSanction.STAFF):
    """Time a player out of chat. minutes=None means until staff lift it."""
    until = timezone.now() + timedelta(minutes=minutes) if minutes else None
    return ChatSanction.objects.create(
        user=user, until=until, reason=reason[:200], created_by=created_by, source=source)


# --------------------------------------------------------------------------
# Screening a message
# --------------------------------------------------------------------------
def _ai_decision(text, user):
    path = _setting('CHAT_AI_MODERATOR', '')
    if not path:
        return None
    try:
        decision = import_string(path)(text, user)
    except Exception:
        log.exception('CHAT_AI_MODERATOR failed; allowing the message')
        return None
    if decision in (None, 'ok', 'allow', True):
        return None
    if decision == 'block':
        return 'That message breaks the chat rules.'
    if isinstance(decision, dict) and decision.get('action') == 'block':
        return decision.get('reason') or 'That message breaks the chat rules.'
    return None


def screen_body(user, body, now=None):
    """Return the text to store, or raise ModerationBlocked."""
    now = now or timezone.now()
    result = screen_text(
        body,
        extra_profanity=_setting('CHAT_PROFANITY_EXTRA', ()),
        blocked_terms=_setting('CHAT_BLOCKED_TERMS', ()),
        allow_links=_setting('CHAT_ALLOW_LINKS', False),
    )
    if result.action == BLOCK:
        raise ModerationBlocked(result.reason, status=400)
    text = result.text
    if LiveChatMessage.objects.filter(
            author=user, body=text, created_at__gte=now - DUPLICATE_WINDOW,
    ).exclude(kind=LiveChatMessage.SYSTEM).exists():
        raise ModerationBlocked("You just said that. Try something new.", status=429)
    reason = _ai_decision(text, user)
    if reason:
        raise ModerationBlocked(reason, status=400)
    return text


# --------------------------------------------------------------------------
# Mute / block
# --------------------------------------------------------------------------
def block_sets(user):
    """(muted_ids, blocked_ids) for what `user` has muted or blocked.

    muted_ids covers both kinds (their public lines are hidden from you).
    blocked_ids covers blocks only (whispers are cut off too).
    """
    pairs = list(ChatBlock.objects.filter(blocker=user).values_list('blocked_id', 'kind'))
    muted = {blocked_id for blocked_id, _kind in pairs}
    blocked = {blocked_id for blocked_id, kind in pairs if kind == ChatBlock.BLOCK}
    return muted, blocked


def check_whisper_allowed(sender, recipient):
    """Refuse a whisper if either side has blocked the other."""
    if ChatBlock.objects.filter(blocker=sender, blocked=recipient).exists():
        raise ModerationBlocked(f'You have {recipient.username} muted or blocked. '
                                f'Use /unblock {recipient.username} first.')
    if ChatBlock.objects.filter(
            blocker=recipient, blocked=sender, kind=ChatBlock.BLOCK).exists():
        raise ModerationBlocked(f"{recipient.username} isn't accepting whispers.")


def _find_user(username):
    name = (username or '').strip()
    return User.objects.filter(username__iexact=name).first() if name else None


def set_block(user, username, action):
    """action: mute / block / unmute / unblock. Returns a short confirmation."""
    if action not in ('mute', 'block', 'unmute', 'unblock'):
        raise ModerationBlocked('Unknown action.', status=400)
    target = _find_user(username)
    if target is None:
        raise ModerationBlocked(f'No player named {(username or "").strip()}.', status=404)
    if target.id == user.id:
        raise ModerationBlocked("You can't do that to yourself.", status=400)
    if action in ('mute', 'block'):
        if target.is_staff:
            raise ModerationBlocked('Staff members cannot be muted or blocked. '
                                    'Use Report if something is wrong.', status=403)
        ChatBlock.objects.update_or_create(
            blocker=user, blocked=target, defaults={'kind': action})
        if action == 'mute':
            return f'Muted {target.username}. You will not see their chat lines.'
        return f'Blocked {target.username}. Their lines and whispers are hidden.'
    deleted, _ = ChatBlock.objects.filter(blocker=user, blocked=target).delete()
    if not deleted:
        return f'{target.username} was not muted or blocked.'
    return f'{target.username} is unmuted.'


def list_blocks(user):
    rows = ChatBlock.objects.filter(blocker=user).select_related('blocked').order_by(
        'blocked__username')
    return [{'user_id': r.blocked_id, 'username': r.blocked.username, 'kind': r.kind}
            for r in rows]


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def _game_label(message):
    try:
        game = message.room.game
        return f'{game.away_team} @ {game.home_team}'
    except Exception:
        return ''


def report_message(reporter, message_id, reason, details=''):
    """Record a report. Returns (report, created). Raises ModerationBlocked."""
    valid = dict(ChatReport.REASON_CHOICES)
    if reason not in valid:
        raise ModerationBlocked('Choose a reason for the report.', status=400)
    message = LiveChatMessage.objects.select_related('author', 'room__game').filter(
        pk=message_id).first()
    if message is None or message.kind == LiveChatMessage.SYSTEM:
        raise ModerationBlocked('That message is no longer available.', status=404)
    if message.author_id == reporter.id:
        raise ModerationBlocked("You can't report your own message.", status=400)
    if message.kind == LiveChatMessage.WHISPER and message.recipient_id != reporter.id:
        raise ModerationBlocked('That message is no longer available.', status=404)

    report, created = ChatReport.objects.get_or_create(
        reporter=reporter, message=message,
        defaults={
            'reported_user': message.author,
            'body_snapshot': message.body,
            'game_label': _game_label(message),
            'reason': reason,
            'details': (details or '').strip()[:200],
        },
    )
    if created:
        _auto_escalate(message)
    return report, created


def _auto_escalate(message):
    """Hide a line many different players reported; repeat offenders get a timeout."""
    needed = int(_setting('CHAT_REPORTS_TO_HIDE', 3))
    reporters = ChatReport.objects.filter(message=message).values('reporter_id').distinct().count()
    if message.is_hidden or reporters < needed:
        return
    LiveChatMessage.objects.filter(pk=message.pk).update(is_hidden=True)
    author = message.author
    if author.is_staff:
        return
    since = timezone.now() - timedelta(hours=24)
    strikes = LiveChatMessage.objects.filter(
        author=author, is_hidden=True, created_at__gte=since).count()
    limit = int(_setting('CHAT_AUTO_TIMEOUT_AFTER', 3))
    if strikes >= limit and active_sanction(author) is None:
        minutes = int(_setting('CHAT_AUTO_TIMEOUT_MINUTES', 15))
        timeout_user(author, minutes=minutes, source=ChatSanction.AUTO,
                     reason=f'Automatic: {strikes} lines hidden after player reports in 24 hours.')


# --------------------------------------------------------------------------
# Staff actions (used by Django admin)
# --------------------------------------------------------------------------
def resolve_reports(reports, staff, action, minutes=None, note=''):
    """Close reports with an outcome.

    action: 'dismiss' | 'hide' | 'hide_timeout'
    Returns the number of reports closed.
    """
    now = timezone.now()
    closed = 0
    timed_out = set()
    for report in reports:
        if report.status != ChatReport.OPEN:
            continue
        outcome = ChatReport.DISMISSED
        resolution = note or 'Dismissed.'
        if action in ('hide', 'hide_timeout'):
            outcome = ChatReport.ACTIONED
            if report.message_id:
                LiveChatMessage.objects.filter(pk=report.message_id).update(is_hidden=True)
            resolution = note or 'Message hidden.'
            if (action == 'hide_timeout' and report.reported_user_id
                    and report.reported_user_id not in timed_out):
                timeout_user(report.reported_user, minutes=minutes,
                             reason=f'Report #{report.pk}: {report.get_reason_display()}',
                             created_by=staff)
                timed_out.add(report.reported_user_id)
                resolution = note or 'Message hidden and player timed out.'
        report.status = outcome
        report.reviewed_by = staff
        report.reviewed_at = now
        report.resolution = resolution[:200]
        report.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'resolution'])
        closed += 1
    return closed
