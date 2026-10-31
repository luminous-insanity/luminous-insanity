from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from api.models import Game
from .models import RelayAbility, RelayDraftTurn, RelayMatch, RelayMatchSide, RelayPick, RelayTeam, RelayTeamMember
from .services import refresh_match_scores, _create_draft_turns


class RelayWarsScoringTests(TestCase):
    def setUp(self):
        self.users = [User.objects.create_user(username=f'p{i}', password='test') for i in range(8)]
        self.team_a = RelayTeam.objects.create(name='A', owner=self.users[0], season=2026, week=10)
        self.team_b = RelayTeam.objects.create(name='B', owner=self.users[4], season=2026, week=10)
        for index in range(4):
            RelayTeamMember.objects.create(team=self.team_a, user=self.users[index], draft_priority=index)
            RelayTeamMember.objects.create(team=self.team_b, user=self.users[index + 4], draft_priority=index)
        self.match = RelayMatch.objects.create(
            season=2026, week=10, team_a=self.team_a, team_b=self.team_b,
            lock_at=timezone.now() - timedelta(hours=1),
        )
        self.side_a = RelayMatchSide.objects.create(match=self.match, team=self.team_a)
        self.side_b = RelayMatchSide.objects.create(match=self.match, team=self.team_b)

    def make_pick(self, position, team, player, winner='home', selected='home'):
        game = Game.objects.create(
            season=2026, week=10, game_id=f'test-{position}', home_team='HOME', away_team='AWAY',
            game_date=timezone.localdate() - timedelta(days=1),
            kickoff=timezone.now() - timedelta(hours=position + 1), status=Game.FINAL,
            home_score=24 if winner == 'home' else 10, away_score=10 if winner == 'home' else 24,
        )
        turn = RelayDraftTurn.objects.create(match=self.match, position=position, team=team, assigned_member=player)
        return RelayPick.objects.create(
            match=self.match, draft_turn=turn, team=team, assigned_player=player,
            selected_by=player, game=game, picked_side=selected,
        )

    def test_protection_pauses_chain_after_loss(self):
        p1 = self.make_pick(1, self.team_a, self.users[0], winner='home', selected='home')
        p2 = self.make_pick(3, self.team_a, self.users[1], winner='home', selected='home')
        p3 = self.make_pick(5, self.team_a, self.users[2], winner='away', selected='home')
        p4 = self.make_pick(7, self.team_a, self.users[3], winner='home', selected='home')
        RelayAbility.objects.create(match=self.match, team=self.team_a, proposed_by=self.users[0], target_pick=p3, kind=RelayAbility.PROTECT, status=RelayAbility.ACTIVE, token_spent=True)
        refresh_match_scores(self.match)
        self.side_a.refresh_from_db()
        self.assertEqual(self.side_a.current_chain, 3)
        self.assertEqual(self.side_a.best_chain, 3)

    def test_successful_jinx_adds_chain_point_and_token(self):
        own_win = self.make_pick(4, self.team_b, self.users[4], winner='home', selected='home')
        target = self.make_pick(2, self.team_a, self.users[1], winner='away', selected='home')
        RelayAbility.objects.create(match=self.match, team=self.team_b, proposed_by=self.users[4], target_pick=target, kind=RelayAbility.JINX, status=RelayAbility.ACTIVE, token_spent=True)
        refresh_match_scores(self.match)
        self.side_b.refresh_from_db()
        self.assertEqual(self.side_b.current_chain, 2)
        self.assertEqual(self.side_b.best_chain, 2)
        self.assertEqual(self.side_b.ability_tokens, 3)

    def test_four_player_teams_receive_seven_turns_each_for_fourteen_games(self):
        _create_draft_turns(self.match, self.team_a, self.team_b, 14)
        self.assertEqual(self.match.draft_turns.filter(team=self.team_a).count(), 7)
        self.assertEqual(self.match.draft_turns.filter(team=self.team_b).count(), 7)


class RelayWarsMembershipTests(TestCase):
    """Team membership, permissions, and invite/join rules."""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='test')
        self.member = User.objects.create_user(username='member', password='test')
        self.outsider = User.objects.create_user(username='outsider', password='test')
        from django.utils import timezone
        from datetime import timedelta
        self.future = timezone.now() + timedelta(days=2)
        # Upcoming week with a game so team creation is allowed
        self.game = Game.objects.create(
            season=2026, week=12, game_id='rw-perm-1',
            home_team='KC', away_team='BAL',
            game_date=timezone.localdate() + timedelta(days=2),
            kickoff=self.future, status=Game.SCHEDULED,
        )

    def test_create_invite_team_adds_owner_as_member(self):
        from .services import create_invite_team
        team = create_invite_team(self.owner, 2026, 12, 'Test Squad')
        self.assertTrue(
            RelayTeamMember.objects.filter(team=team, user=self.owner, is_active=True).exists()
        )
        self.assertEqual(team.member_count, 1)

    def test_cannot_join_two_teams_same_week(self):
        from .services import create_invite_team, join_invite_team, RelayWarsError
        team_a = create_invite_team(self.owner, 2026, 12, 'A')
        team_b = create_invite_team(self.member, 2026, 12, 'B')
        with self.assertRaises(RelayWarsError):
            join_invite_team(self.owner, team_b.invite_code)

    def test_join_invite_increases_membership(self):
        from .services import create_invite_team, join_invite_team
        team = create_invite_team(self.owner, 2026, 12, 'Invite Me')
        join_invite_team(self.member, team.invite_code)
        self.assertEqual(team.member_count, 2)

    def test_match_detail_rejects_non_member(self):
        from django.test import Client
        from .services import create_invite_team
        team = create_invite_team(self.owner, 2026, 12, 'Private')
        # Minimal match for URL access
        other = User.objects.create_user(username='otherowner', password='test')
        team_b = RelayTeam.objects.create(name='B', owner=other, season=2026, week=12)
        RelayTeamMember.objects.create(team=team_b, user=other)
        match = RelayMatch.objects.create(
            season=2026, week=12, team_a=team, team_b=team_b,
            lock_at=self.future,
        )
        client = Client()
        client.login(username='outsider', password='test')
        response = client.get(f'/relay-wars/match/{match.pk}/')
        # Should redirect away (not a member)
        self.assertIn(response.status_code, (302, 403))
