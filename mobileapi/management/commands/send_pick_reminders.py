from django.core.management.base import BaseCommand

from mobileapi.reminders import send_pick_reminders


class Command(BaseCommand):
    help = ("Send the weekly pick reminder push if it is due (2 hours before the first "
            "game day's first kickoff). The sync cron also does this automatically.")

    def handle(self, *args, **options):
        report = send_pick_reminders()
        self.stdout.write(str(report))
