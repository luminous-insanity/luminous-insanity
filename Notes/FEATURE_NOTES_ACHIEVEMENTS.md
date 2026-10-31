# Achievement upgrade — football-themed trophy case

## Roster

| Key | Title | Thresholds | Metric |
|-----|--------|------------|--------|
| play_caller | **Play Caller** | 1, 10, 25, 100, 250, 500, 1000 | Picks submitted |
| division_dominator | **Division Dominator** | 1, 3, 5, 10 | Week wins inside your division |
| january_football | **January Football** | 1, 2, 3 | Playoff week wins |
| perfect_drive | **Perfect Drive** | 1, 2, 3 | Perfect weeks |
| red_zone_streak | **Red Zone Streak** | 5, 10, 25 | Best consecutive correct picks |
| iron_man | **Iron Man** | 5, 10, 18 | Distinct weeks with graded picks |
| division_crown | **Division Crown** | 1, 2, 3 | Finalized division #1 finishes |
| super_bowl_bound | **Super Bowl Bound** | 1, 2, 3 | Reached Super Bowl field (after 3 cuts) |
| gameday_lombardi | **Gameday Lombardi** | 1 | Won Super Bowl week in the SB field |
| true_fan | **True Fan** | 1 | Favorite team set on profile |
| never_missed_a_snap | **Never Missed a Snap** | 1 | Picked every regular-season game in a season |
| rivalry_king | **Rivalry King** | 1, 5, 10, 25 | Head-to-head challenge wins |
| franchise_player | **Franchise Player** | 1, 2, 3 | Seasons with at least one pick |
| riding_with_the_team | **Riding with the Team** | 1, 5, 10, 25 | Favorite team wins when you picked them |
| clinched | **Clinched** | 1, 2, 3 | Playoff berths (any route) |
| wild_card_weekend | **Wild Card Weekend** | 1 | Wildcard playoff berth |
| upset_special | **Upset Special** | 1, 5, 15, 50 | Correct underdog picks (team records) |
| locksmith | **Locksmith** | 1, 5, 15, 40 | Correct Lock-confidence picks |
| gridiron_guru | **Gridiron Guru** | 1, 2, 3 | Finalized season ≥ .700 (min 50 picks) |
| film_room | **Film Room** | 25, 100, 300, 750 | Career graded picks |

## Notes
- Old unlock keys (`pick_maker`, etc.) remain in the DB but no longer appear on cards. New keys unlock from current metrics.
- Titles ladder updated to match new keys (`accounts/titles.py`).
- No schema migration required (AchievementUnlock already stores free-form keys/levels).

## Verify
```bash
python manage.py test accounts.test_achievements
python manage.py shell -c "from django.contrib.auth.models import User; from accounts.achievements import achievement_summary; print(achievement_summary(User.objects.first()))"
```
