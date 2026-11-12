"""Private leagues: creating, joining, owner tools and standings."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import Game
from accounts import leagues
from accounts.models import League, LeagueMembership, Pick


@override_settings(NFL_SEASON=2026)
class LeagueTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'o@example.com', 'pw')
        self.ann = User.objects.create_user('ann', 'a@example.com', 'pw')
        self.ben = User.objects.create_user('ben', 'b@example.com', 'pw')

    def make(self, name='Office Pool'):
        return leagues.create_league(self.owner, name)

    # ---- create ---------------------------------------------------------
    def test_create_makes_owner_a_member_with_a_code(self):
        league = self.make()
        self.assertTrue(leagues.is_member(league, self.owner))
        self.assertEqual(len(league.invite_code), 8)
        self.assertNotIn('0', league.invite_code)

    def test_name_rules(self):
        for bad in ('', 'ab', 'x' * 61, 'call 555-123-4567', 'see www.bet.com'):
            with self.assertRaises(leagues.LeagueError, msg=bad):
                leagues.clean_name(bad)
        self.assertEqual(leagues.clean_name('  Office   Pool '), 'Office Pool')

    @override_settings(LEAGUE_MAX_OWNED=1)
    def test_owner_limit(self):
        self.make('One')
        with self.assertRaises(leagues.LeagueError) as ctx:
            self.make('Two')
        self.assertEqual(ctx.exception.status, 403)

    # ---- join -------------------------------------------------------------
    def test_join_with_code_ignores_case_and_spaces(self):
        league = self.make()
        joined = leagues.join_by_code(self.ann, f' {league.invite_code.lower()[:4]}-{league.invite_code.lower()[4:]} ')
        self.assertEqual(joined.pk, league.pk)
        self.assertEqual(leagues.member_count(league), 2)

    def test_bad_closed_and_duplicate_joins(self):
        league = self.make()
        with self.assertRaises(leagues.LeagueError) as ctx:
            leagues.join_by_code(self.ann, 'NOPE1234')
        self.assertEqual(ctx.exception.status, 404)
        leagues.join_by_code(self.ann, league.invite_code)
        with self.assertRaises(leagues.LeagueError) as ctx:
            leagues.join_by_code(self.ann, league.invite_code)
        self.assertEqual(ctx.exception.status, 409)
        leagues.set_open(self.owner, league, False)
        with self.assertRaises(leagues.LeagueError) as ctx:
            leagues.join_by_code(self.ben, league.invite_code)
        self.assertEqual(ctx.exception.status, 404)       # same answer as a wrong code

    @override_settings(LEAGUE_MAX_MEMBERS=2)
    def test_full_league(self):
        league = self.make()
        leagues.join_by_code(self.ann, league.invite_code)
        with self.assertRaises(leagues.LeagueError) as ctx:
            leagues.join_by_code(self.ben, league.invite_code)
        self.assertEqual(ctx.exception.status, 403)

    # ---- owner tools --------------------------------------------------------
    def test_only_owner_can_manage(self):
        league = self.make()
        leagues.join_by_code(self.ann, league.invite_code)
        for call in (lambda: leagues.rename(self.ann, league, 'Hacked'),
                     lambda: leagues.regenerate_code(self.ann, league),
                     lambda: leagues.remove_member(self.ann, league, self.owner.id),
                     lambda: leagues.delete_league(self.ann, league)):
            with self.assertRaises(leagues.LeagueError) as ctx:
                call()
            self.assertEqual(ctx.exception.status, 403)

    def test_new_code_kills_the_old_one(self):
        league = self.make()
        old = league.invite_code
        new = leagues.regenerate_code(self.owner, league)
        self.assertNotEqual(old, new)
        with self.assertRaises(leagues.LeagueError):
            leagues.join_by_code(self.ann, old)
        leagues.join_by_code(self.ann, new)

    def test_remove_leave_and_owner_cannot_leave(self):
        league = self.make()
        leagues.join_by_code(self.ann, league.invite_code)
        leagues.join_by_code(self.ben, league.invite_code)
        leagues.remove_member(self.owner, league, self.ann.id)
        self.assertFalse(leagues.is_member(league, self.ann))
        leagues.leave_league(self.ben, league)
        with self.assertRaises(leagues.LeagueError):
            leagues.leave_league(self.owner, league)
        with self.assertRaises(leagues.LeagueError):
            leagues.remove_member(self.owner, league, self.owner.id)

    def test_transfer_needs_a_member(self):
        league = self.make()
        with self.assertRaises(leagues.LeagueError):
            leagues.transfer_ownership(self.owner, league, 'ann')       # not in league yet
        leagues.join_by_code(self.ann, league.invite_code)
        leagues.transfer_ownership(self.owner, league, 'ANN')
        league.refresh_from_db()
        self.assertEqual(league.owner, self.ann)

    def test_delete_removes_memberships(self):
        league = self.make()
        leagues.delete_league(self.owner, league)
        self.assertFalse(League.objects.exists())
        self.assertFalse(LeagueMembership.objects.exists())

    # ---- standings ------------------------------------------------------------
    def test_board_only_ranks_members(self):
        league = self.make()
        leagues.join_by_code(self.ann, league.invite_code)
        game = Game.objects.create(
            season=2026, week=1, game_id='lg-1', home_team='KC', away_team='BUF',
            game_date=timezone.localdate(), kickoff=timezone.now() - timedelta(days=2),
            status=Game.FINAL, home_score=21, away_score=14)
        Pick.objects.create(user=self.ann, game=game, team_picked=Pick.HOME)      # right
        Pick.objects.create(user=self.owner, game=game, team_picked=Pick.AWAY)    # wrong
        Pick.objects.create(user=self.ben, game=game, team_picked=Pick.HOME)      # not a member
        rows = leagues.league_board(league, 'season', 2026, 1)
        self.assertEqual([(r.user.username, r.rank, r.wins) for r in rows],
                         [('ann', 1, 1), ('owner', 2, 0)])
        weekly = leagues.league_board(league, 'weekly', 2026, 1)
        self.assertEqual([r.user.username for r in weekly], ['ann', 'owner'])


@override_settings(NFL_SEASON=2026)
class LeagueViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'o@example.com', 'pw')
        self.ann = User.objects.create_user('ann', 'a@example.com', 'pw')
        self.league = leagues.create_league(self.owner, 'Office Pool')

    def test_pages_need_login(self):
        self.assertEqual(self.client.get(reverse('leagues')).status_code, 302)

    def test_member_sees_league_and_stranger_gets_404(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('league_detail', args=[self.league.pk]))
        self.assertContains(response, 'Office Pool')
        self.assertContains(response, self.league.invite_code)
        self.client.force_login(self.ann)
        self.assertEqual(self.client.get(reverse('league_detail', args=[self.league.pk])).status_code, 404)

    def test_create_and_join_flow(self):
        self.client.force_login(self.ann)
        response = self.client.post(reverse('league_create'), {'name': 'Family'})
        mine = League.objects.get(name='Family')
        self.assertRedirects(response, reverse('league_detail', args=[mine.pk]))
        self.client.post(reverse('league_join'), {'code': self.league.invite_code})
        self.assertTrue(leagues.is_member(self.league, self.ann))

    def test_invite_link_shows_confirmation_then_joins(self):
        self.client.force_login(self.ann)
        url = reverse('league_join_link', args=[self.league.invite_code])
        self.assertContains(self.client.get(url), 'Join Office Pool?')
        self.assertFalse(leagues.is_member(self.league, self.ann))
        self.client.post(url)
        self.assertTrue(leagues.is_member(self.league, self.ann))

    def test_members_cannot_use_owner_tools(self):
        leagues.join_by_code(self.ann, self.league.invite_code)
        self.client.force_login(self.ann)
        self.client.post(reverse('league_manage', args=[self.league.pk]),
                         {'action': 'delete', 'confirm': 'Office Pool'})
        self.assertTrue(League.objects.filter(pk=self.league.pk).exists())

    def test_delete_requires_typing_the_name(self):
        self.client.force_login(self.owner)
        url = reverse('league_manage', args=[self.league.pk])
        self.client.post(url, {'action': 'delete', 'confirm': 'wrong'})
        self.assertTrue(League.objects.filter(pk=self.league.pk).exists())
        self.client.post(url, {'action': 'delete', 'confirm': 'office pool'})
        self.assertFalse(League.objects.filter(pk=self.league.pk).exists())
