"""Make a safe copy of the SQLite database.

    python manage.py backup_db                 # keeps the newest 14 copies
    python manage.py backup_db --keep 30
    python manage.py backup_db --dir /home/you/gdp-backups

Uses SQLite's own backup routine, so the copy is consistent even while the
site is running (a plain file copy can catch a half-written page). Schedule it
daily from your host's task scheduler. Copies are named
db-YYYYmmdd-HHMMSS.sqlite3 and the oldest are deleted past --keep.
Copy the backup folder somewhere off the server now and then; a backup on the
same disk won't survive losing the server.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create a consistent backup of the SQLite database and prune old copies.'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default='', help='Where to put backups (default: <project>/backups).')
        parser.add_argument('--keep', type=int, default=14, help='How many copies to keep (default 14).')

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        if 'sqlite' not in db['ENGINE']:
            raise CommandError('backup_db only works with SQLite. Use pg_dump once you move to Postgres.')
        source = Path(db['NAME'])
        if not source.exists():
            raise CommandError(f'Database file not found: {source}')
        if options['keep'] < 1:
            raise CommandError('--keep must be at least 1.')

        target_dir = Path(options['dir'] or Path(settings.BASE_DIR) / 'backups')
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f'db-{datetime.now():%Y%m%d-%H%M%S}.sqlite3'

        src = sqlite3.connect(str(source))
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

        copies = sorted(target_dir.glob('db-*.sqlite3'))
        for old in copies[:-options['keep']]:
            old.unlink()

        size_kb = target.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(
            f'Backup saved: {target} ({size_kb:,.0f} KB). Keeping the newest {options["keep"]}.'))
