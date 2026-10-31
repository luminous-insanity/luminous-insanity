GameDayPicks — Cumulative Project Update

This archive combines the uploaded project baseline with the accepted dashboard, favorite-team theme, recap, narrative, and alert updates. The alert dropdown now keeps the notification text visible when opened; it removes the unread badge after the read-state request succeeds.

IMPORTANT
- This archive intentionally excludes .env, .git, virtual environments, local SQLite databases, and Python cache files. Keep your existing .env and database files; do not replace them.
- Back up your project before extracting these files into the existing project folder.
- Because the alert read-state migration is included, run `python manage.py showmigrations accounts` first. If `0017_alerts_read_state` is not applied, run `python manage.py migrate`. If it is already applied, do not edit or delete migration/database files.
- Then run `python manage.py check` and `python manage.py test`. Test the dashboard and Alerts dropdown locally before pushing or deploying.

Included accepted changes:
- Dashboard hierarchy: Your record above Your stats; Path to Playoffs below Your stats.
- Collapsible Live Energy section.
- Side Quest, Dog Hunt, and Quests grouped into a collapsible section.
- Favorite-team colors on the account avatar and active desktop navigation underline.
- Persistent alert read state, with alert text remaining visible when the dropdown opens.
- Week recap fix for the Standing user reference.
- Narrative cleanup to avoid duplicate playoff status.
