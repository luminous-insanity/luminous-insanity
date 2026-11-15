"""Optional Firebase Cloud Messaging delivery for registered GameDayPicks devices.

Requires FIREBASE_ADMIN_CREDENTIALS to point to a Firebase service-account JSON
file on the Django server. Never put that file in the Flutter app or source ZIP.
"""
import logging

from django.conf import settings

from .models import Device, NotificationPreference

log = logging.getLogger(__name__)
_APP_NAME = 'gamedaypicks_fcm'


def _firebase_app():
    credentials_path = getattr(settings, 'FIREBASE_ADMIN_CREDENTIALS', '')
    if not credentials_path:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials
        try:
            return firebase_admin.get_app(_APP_NAME)
        except ValueError:
            return firebase_admin.initialize_app(
                credentials.Certificate(credentials_path), name=_APP_NAME,
            )
    except Exception:
        log.exception('Could not initialize Firebase Admin for mobile push.')
        return None


def send_user_push(user, title, body, *, preference=None, data=None):
    """Send one push to all active devices for a user; safely no-op if unconfigured."""
    if preference:
        prefs = NotificationPreference.objects.filter(user=user).first()
        if prefs is not None and not getattr(prefs, preference, False):
            return 0

    app = _firebase_app()
    if app is None:
        return 0

    devices = list(Device.objects.filter(user=user, is_active=True))
    if not devices:
        return 0

    try:
        from firebase_admin import messaging
        tokens = [device.token for device in devices]
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={str(k): str(v) for k, v in (data or {}).items()},
            tokens=tokens,
            android=messaging.AndroidConfig(priority='high'),
            apns=messaging.APNSConfig(headers={'apns-priority': '10'}),
        )
        result = messaging.send_each_for_multicast(message, app=app)
        invalid = set()
        for device, response in zip(devices, result.responses):
            if response.success:
                continue
            code = getattr(getattr(response, 'exception', None), 'code', '')
            if code in ('messaging/registration-token-not-registered', 'messaging/invalid-registration-token'):
                invalid.add(device.pk)
        if invalid:
            Device.objects.filter(pk__in=invalid).update(is_active=False)
        return result.success_count
    except Exception:
        log.exception('Firebase push delivery failed for user %s.', user.pk)
        return 0
