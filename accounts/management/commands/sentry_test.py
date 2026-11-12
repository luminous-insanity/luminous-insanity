"""Send a test event to Sentry so you know error reporting works.

    python manage.py sentry_test
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test message and a test error to Sentry.'

    def handle(self, *args, **options):
        if not settings.SENTRY_DSN:
            raise CommandError('SENTRY_DSN is not set in .env, so Sentry is switched off.')
        try:
            import sentry_sdk
        except ImportError:
            raise CommandError('sentry-sdk is not installed. Run: pip install -r requirements.txt')
        sentry_sdk.capture_message('GameDayPicks test message from manage.py sentry_test')
        try:
            raise RuntimeError('GameDayPicks test error from manage.py sentry_test')
        except RuntimeError as exc:
            sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(timeout=5)
        self.stdout.write(self.style.SUCCESS('Sent. Check your Sentry project in a minute.'))
