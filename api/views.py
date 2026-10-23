# api/views.py

import hmac
import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .services import run_sync

log = logging.getLogger(__name__)


@csrf_exempt
def sync_view(request):
    """
    Called by an outside scheduler (e.g. cron-job.org) every ~30 minutes:

        https://YOUR-SITE/api/sync/?token=YOUR_SYNC_TOKEN

    Safe to call as often as you like: it only spends API calls when a game
    has started and isn't final yet. Anyone without the token gets a 403.
    """
    given = request.headers.get('X-Sync-Token') or request.GET.get('token', '')
    expected = settings.SYNC_TOKEN
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        return HttpResponseForbidden('Forbidden')

    try:
        report = run_sync()
    except Exception:
        log.exception('Sync crashed')
        return JsonResponse({'ok': False, 'error': 'sync crashed, see server log'}, status=500)

    ok = not report['errors']
    # 502 on API trouble so the scheduler's dashboard flags the run as failed.
    return JsonResponse({'ok': ok, **report}, status=200 if ok else 502)
