# Test plan: before you deploy to PythonAnywhere

Work top to bottom. Don't move to the next stage until the current one passes.
Run all commands in the PyCharm Terminal, in your project folder.

## Stage 1: Automated tests (no internet, no API calls, about 1 minute)

    python manage.py check
    python manage.py test

PASS: the last line says `OK`.
If something fails, copy the whole failure message and send it to me. A failing test
means either a bug in the site or a mistake in the test, and I'll tell you which.

What these cover:
- Standings are calculated correctly and can't double count
- Picks lock at kickoff, enforced on the server
- Reloading a week never deletes picks
- A bad API response or API outage never breaks the site
- The sync URL refuses anyone without the secret token
- Signup, login, logout, dashboard, history, leaderboard
- Database migrations match the models

## Stage 2: Real data on your own computer (uses a few real API calls)

Needs `NFL_API_KEY` and `SYNC_TOKEN` saved in `.env`.

1. Load the season so far (N = the current NFL week number):

       python manage.py sync_nfl --through N

   PASS: each week prints something like `Week 3: 16 games, 16 with kickoff times, 16 final`.
   - "with kickoff times" should equal the number of games. If it says 0, tell me.
   - Finished weeks should show their games as final. Upcoming weeks show 0 final.

2. Start the site (`python manage.py runserver`) and open http://127.0.0.1:8000/admin
   - Open Games. Spot check 3 finished games against ESPN or NFL.com: scores and winner.
   - PASS: scores match, finished games say Final.

3. Run the sync again right away:

       python manage.py sync_nfl

   PASS: it finishes instantly and the report shows no new schedule or score weeks.
   Then look at your RapidAPI dashboard. The call count should not have jumped.

4. Sign up two test friends at http://127.0.0.1:8000/accounts/signup/ (use a private window for the second).
   PASS: both appear on the home page leaderboard at 0-0-0. Your admin account does NOT appear.

5. As friend 1, on an upcoming game, click a team.
   PASS: the card now says "Your Pick" with Home or Away, and the buttons are gone.
   Refresh the page: the pick is still shown.

6. Change your pick: on the same game click the OTHER team.
   PASS: a "Pick changed" message appears, the highlighted button and "Your Pick" switch to
   the other team, and refreshing keeps the new pick. (Picks can be changed until kickoff.)

7. Pick lock: in /admin open an upcoming game and set its Kickoff to a time in the past, then save.
   PASS: as friend 2 the game says "Picks Unavailable (Game Started)", and you can't pick it.
   Put the kickoff back afterwards.

8. Grading: as friend 1, pick a team on an upcoming game. In /admin, set that game to
   Status = Final with scores where your pick wins, and save.
   PASS: the home page leaderboard shows friend 1 with 1 win. Change the score so the pick loses:
   the leaderboard flips to 1 loss with no other action. Then set the game back to Scheduled
   with blank scores.

9. Browse weeks: on the dashboard use Previous week / Next week / This week.
   PASS: the heading and games change; This week brings you back.

10. Test the sync URL (use your real SYNC_TOKEN):
    - http://127.0.0.1:8000/api/sync/            PASS: "Forbidden"
    - http://127.0.0.1:8000/api/sync/?token=wrong   PASS: "Forbidden"
    - http://127.0.0.1:8000/api/sync/?token=YOUR_TOKEN   PASS: a short JSON report with "ok": true

11. Check your pick history page. PASS: it lists your picks.

## Stage 3: Before you upload anything

- [ ] `.env` is NOT in your git repo, and neither is `db.sqlite3`
- [ ] No API key appears in any file: search the project for `rapidapi-key`
- [ ] Stage 1 and Stage 2 fully pass
- [ ] Your friends' accounts will be regular users (the leaderboard hides admin accounts)

## Stage 4: On PythonAnywhere (I'll walk you through each of these)

1. Get the code onto PythonAnywhere, create the virtualenv, install requirements
2. Create the `.env` file there with SECRET_KEY, NFL_API_KEY, SYNC_TOKEN
3. In settings: DEBUG off, ALLOWED_HOSTS set to your yourname.pythonanywhere.com address
4. Run: `python manage.py migrate`, `collectstatic`, `createsuperuser`
5. Free accounts can only reach whitelisted sites. Test the API from a PythonAnywhere
   console: `python manage.py sync_nfl --week 1`
   - PASS: prints the week summary. FAIL (proxy or connection error): the API host isn't on
     the free whitelist, and I'll help with the options.
6. Open the live site and repeat Stage 2 steps 4, 5, 10 (sign up, pick, sync URL)
7. Set up cron-job.org to call your sync URL every 30 minutes. Check its history shows 200 OK.
8. Calendar reminder: extend the free web app in the PythonAnywhere Web tab before it expires.

## Stage 5: First real game day

- [ ] Before kickoff: friends can pick, buttons disappear at kickoff time
- [ ] An hour after the first game ends: the score and winner show, and the leaderboard moved
- [ ] Check cron-job.org history: runs are 200 OK
- [ ] After Monday night: the next week appears by Tuesday
