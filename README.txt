GameDayPicks - Consolidated dashboard and alerts update

This package consolidates the requested changes into one set of files:
- Dashboard hierarchy: Your record above Your stats; Path to Playoffs below stats.
- Collapsible Live Energy section.
- Side Quest, Dog Hunt, and Quests grouped into one collapsible section.
- Favorite-team color theme applied to the account avatar and active desktop navigation underline.
- Alerts marked as read when the Alerts dropdown is opened, with unread state persisted.
- Week recap Standing.user reference fix.
- Narrative cleanup to avoid duplicating playoff status.

HOW TO APPLY
1. Back up your current project first.
2. Extract this ZIP into your existing project root (the folder containing manage.py), preserving folder paths and allowing these files to replace the existing files.
3. From the project's activated virtual environment, run:

   python manage.py check
   python manage.py migrate
   python manage.py test

4. Run the local site and check the dashboard, favorite-team avatar/nav underline, Alerts dropdown, and Week 5 recap.
5. Do not deploy until the local checks pass.

The migration adds receiver_seen and is_read fields so notification read state persists. If you already applied migration 0017 from the earlier Alerts ZIP, Django should report no new migration to apply. Do not delete or edit your database to apply this package.

This is a consolidated update package containing changed files, not a complete replacement project archive. It intentionally does not include .env credentials, your database, or .git internals.
