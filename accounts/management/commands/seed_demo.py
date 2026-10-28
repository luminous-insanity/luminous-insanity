"""
Fill a TEST database with fake players so you can watch the whole playoff flow.

    python manage.py seed_demo --yes --players 200
    python manage.py manage_playoffs open
    python manage.py manage_playoffs cut        # x3
    python manage.py squares build              # deal the Super Bowl squares
    python manage.py seed_demo --yes --clear    # remove everything it made

Everything it creates is named so --clear can remove it and nothing else:
users are demo_001, demo_002 ... and games have ids starting "demo-".
Run it against a COPY of your database, not your real one.
It also adds fake final games for the regular season (only if fewer than 8
final ones exist) and for the four playoff weeks.
"""
import random
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Challenge, Pick, PlayerIdentity, SquaresBoard
from accounts.playoff_rounds import get_config
from accounts.playoffs import DIVISIONS, REGULAR_SEASON_WEEKS
from api.models import Game, QuarterScore

PREFIX_USER = 'demo_'
PREFIX_GAME = 'demo-'
TEAMS = ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB',
         'HOU', 'IND', 'JAX', 'KC', 'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
         'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WAS']


class Command(BaseCommand):
    help = 'Create (or with --clear, remove) fake demo players, picks and challenges.'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Confirm you are on a test database.')
        parser.add_argument('--clear', action='store_true', help='Remove all demo data and stop.')
        parser.add_argument('--players', type=int, default=120)
        parser.add_argument('--season', type=int, default=settings.NFL_SEASON)
        parser.add_argument('--seed', type=int, default=1, help='Same seed gives the same demo data.')

    def handle(self, *args, **opts):
        if not opts['yes']:
            raise CommandError('This adds fake users and games. Run it on a copy of your database '
                               'and add --yes to confirm.')
        if opts['clear']:
            SquaresBoard.objects.filter(game__game_id__startswith=PREFIX_GAME).delete()
            games = Game.objects.filter(game_id__startswith=PREFIX_GAME).delete()[0]
            users = User.objects.filter(username__startswith=PREFIX_USER).delete()[0]
            self.stdout.write(self.style.SUCCESS(f'Removed demo data ({users} user rows, {games} game rows incl. picks).'))
            return
        if User.objects.filter(username__startswith=PREFIX_USER).exists():
            raise CommandError('Demo data already exists. Run with --clear first.')

        rng = random.Random(opts['seed'])
        season = opts['season']
        config = get_config(season)

        regular = self.regular_games(season, rng)
        playoff = self.playoff_games(season, config, rng)

        users = self.make_users(opts['players'], season, rng)
        n_picks = self.make_picks(users, regular, playoff, rng)
        n_challenges = self.make_challenges(users, regular, rng)

        self.stdout.write(self.style.SUCCESS(
            f'Created {len(users)} players, {n_picks} picks, {n_challenges} challenges.'))
        self.stdout.write('Next: python manage.py manage_playoffs open   (add --force if it says the regular season is unfinished)')

    # -- games -----------------------------------------------------------------
    def fake_game(self, season, week, number, rng):
        home, away = rng.sample(TEAMS, 2)
        day = date(season, 9, 7) + timedelta(days=7 * (week - 1))
        home_score, away_score = rng.randint(6, 38), rng.randint(6, 38)
        return Game(
            season=season, week=week, game_id=f'{PREFIX_GAME}{season}-w{week}-{number}',
            home_team=home, away_team=away, game_date=day, status=Game.FINAL,
            home_score=home_score, away_score=away_score)

    def regular_games(self, season, rng):
        existing = list(Game.objects.filter(season=season, status=Game.FINAL,
                                            week__lte=REGULAR_SEASON_WEEKS))
        if len(existing) >= 8:
            return existing
        Game.objects.bulk_create([self.fake_game(season, week, n, rng)
                                  for week in range(1, 7) for n in range(1, 7)])
        return list(Game.objects.filter(season=season, status=Game.FINAL,
                                        week__lte=REGULAR_SEASON_WEEKS))

    def playoff_games(self, season, config, rng):
        # Wild Card 6, Divisional 4, Conference 2, Super Bowl 1.
        sizes = {1: 6, 2: 4, 3: 2, 4: 1}
        games = []
        for round_no, count in sizes.items():
            week = config.first_playoff_week + round_no - 1
            for n in range(1, count + 1):
                games.append(self.fake_game(season, week, n, rng))
        Game.objects.bulk_create(games)
        found = list(Game.objects.filter(game_id__startswith=PREFIX_GAME,
                                         week__gte=config.first_playoff_week, season=season))
        # Give the fake Super Bowl running scores so the squares page has winners.
        sb = [g for g in found if g.week == config.first_playoff_week + 3][0]
        for quarter, share in ((1, 0.25), (2, 0.5), (3, 0.75)):
            QuarterScore.objects.create(game=sb, quarter=quarter,
                                        home_score=int(sb.home_score * share),
                                        away_score=int(sb.away_score * share))
        return found

    # -- people ----------------------------------------------------------------
    def make_users(self, count, season, rng):
        # Uneven division sizes on purpose, so percentage qualifying has work to do.
        weights = [rng.uniform(0.5, 2.0) for _ in DIVISIONS]
        users = []
        for i in range(1, count + 1):
            user = User.objects.create_user(username=f'{PREFIX_USER}{i:03d}')
            PlayerIdentity.objects.create(
                user=user, division=rng.choices(DIVISIONS, weights)[0], division_season=season)
            # skill = chance of picking the winner; join_week lets some start late.
            user.skill = rng.uniform(0.40, 0.75)
            user.join_week = 1 if rng.random() < 0.75 else rng.randint(2, 5)
            user.attendance = rng.uniform(0.7, 1.0)
            users.append(user)
        return users

    def make_picks(self, users, regular, playoff, rng):
        picks = []
        for user in users:
            for game in regular + playoff:
                if game.week <= REGULAR_SEASON_WEEKS and game.week < user.join_week:
                    continue
                if rng.random() > user.attendance:
                    continue
                if game.home_score == game.away_score:
                    side = rng.choice([Pick.HOME, Pick.AWAY])
                else:
                    winner = Pick.HOME if game.home_score > game.away_score else Pick.AWAY
                    loser = Pick.AWAY if winner == Pick.HOME else Pick.HOME
                    side = winner if rng.random() < user.skill else loser
                picks.append(Pick(user=user, game=game, team_picked=side))
        Pick.objects.bulk_create(picks, batch_size=500, ignore_conflicts=True)
        return len(picks)

    def make_challenges(self, users, regular, rng):
        made, seen = 0, set()
        for _ in range(len(users)):
            a, b = rng.sample(users, 2)
            game = rng.choice(regular)
            key = (frozenset((a.id, b.id)), game.id)
            if key in seen:
                continue
            seen.add(key)
            Challenge.objects.create(
                challenger=a, opponent=b, scope=Challenge.GAME, season=game.season,
                week=game.week, game=game, status=Challenge.ACCEPTED,
                responded_at=timezone.now())
            made += 1
        return made
