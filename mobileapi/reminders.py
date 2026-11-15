"""Weekly pick reminder push (server side). Safe to run every few minutes.

Called from the sync cron (api.services.run_sync) and by the management command
`send_pick_reminders`. Players are reminded at most once per season/week, only
if they have a registered device, have not turned reminders off, and have not
yet picked every game on the first game day.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Pick
from api.models import Game
from api.services import current_week

from .models import PickReminderLog
from .push import send_user_push
from .reminder_rules import first_day_games, reminder_due, reminder_text

log = logging.getLogger(__name__)


def send_pick_reminders(now=None, season=None, week=None):
    """Returns a small report dict. Never raises for "nothing to do"."""
    now = now or timezone.now()
    season = season or settings.NFL_SEASON
    week = week or current_week()
    report = {"week": week, "due": False, "sent": 0, "skipped_picked": 0}

    games = list(Game.objects.filter(season=season, week=week))
    plan = first_day_games([(g.game_id, g.lock_at) for g in games])
    if plan is None:
        return report
    first_lock, day_ids = plan
    if not reminder_due(first_lock, now):
        return report
    report["due"] = True

    day_pks = [g.pk for g in games if g.game_id in set(day_ids)]
    title, body = reminder_text(first_lock)
    User = get_user_model()
    candidates = (
        User.objects.filter(is_active=True, mobile_devices__is_active=True)
        .exclude(mobile_notification_preferences__pick_reminders=False)
        .exclude(pick_reminder_logs__season=season, pick_reminder_logs__week=week)
        .distinct()
    )
    for user in candidates:
        picked = (Pick.objects.filter(user=user, game_id__in=day_pks)
                  .values("game_id").distinct().count())
        if picked >= len(day_pks):
            report["skipped_picked"] += 1
            continue
        delivered = send_user_push(
            user, title, body, preference="pick_reminders",
            data={"screen": "picks", "week": week, "type": "pick_reminder"},
        )
        if delivered > 0:
            PickReminderLog.objects.get_or_create(user=user, season=season, week=week)
            report["sent"] += 1
    return report
