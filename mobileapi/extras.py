"""Mobile API for private leagues, The Score is Right, insights, matchup
context (odds + injuries) and chat moderation. Thin wrappers: every rule lives
in the accounts/ and api/ modules the website uses, so app and site agree."""
from .common import *

from api import matchups
from accounts import leagues, moderation, tiebreaker
from accounts.insights import build_insights
from accounts.leaderboard import default_week, season_weeks
from accounts.models import League, LeagueMembership


def _season_week(request, default_week_value=None):
    season = int(request.query_params.get('season', settings.NFL_SEASON))
    week_default = default_week_value if default_week_value is not None else current_week()
    week = int(request.query_params.get('week', week_default))
    if not 1 <= week <= 22:
        raise ValueError('week')
    return season, week


def _league_payload(league, user, members=None):
    return {
        'id': league.pk,
        'name': league.name,
        'invite_code': league.invite_code,
        'is_open': league.is_open,
        'owner': {'id': league.owner_id, 'username': league.owner.username},
        'is_owner': league.owner_id == user.id,
        'members': members if members is not None else leagues.member_count(league),
    }


def _row_payload(row, viewer):
    return {
        'rank': row.rank, 'user_id': row.user.id, 'username': row.user.username,
        'wins': row.wins, 'losses': row.losses, 'ties': row.ties,
        'pending': row.pending, 'completed': row.completed, 'win_pct': row.win_pct,
        'tiebreak_label': row.tiebreak_label or None,
        'is_me': row.user.id == viewer.id,
    }


def _league_error(exc):
    return Response({'detail': exc.message}, status=exc.status)


class LeaguesView(APIView):
    """GET: my leagues. POST {name}: start one."""
    permission_classes = [IsAuthenticated]

    @property
    def throttle_scope(self):
        return 'league_write' if self.request.method == 'POST' else None

    def get(self, request):
        return Response({
            'leagues': [_league_payload(l, request.user, l.members) for l in leagues.my_leagues(request.user)],
            'limits': {'max_owned': leagues.max_owned(), 'max_members': leagues.max_members(),
                       'max_joined': leagues.max_joined()},
        })

    @idempotent
    def post(self, request):
        name = request.data.get('name', '')
        if not isinstance(name, str):
            return Response({'detail': 'League name must be text.'}, status=400)
        try:
            league = leagues.create_league(request.user, name)
        except leagues.LeagueError as exc:
            return _league_error(exc)
        return Response({'league': _league_payload(league, request.user)}, status=201)


class LeagueJoinView(APIView):
    """POST {code}: join with an invite code."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'league_join'

    @idempotent
    def post(self, request):
        code = request.data.get('code', '')
        if not isinstance(code, str):
            return Response({'detail': 'Invite code must be text.'}, status=400)
        try:
            league = leagues.join_by_code(request.user, code)
        except leagues.LeagueError as exc:
            return _league_error(exc)
        return Response({'league': _league_payload(league, request.user)})


class LeagueDetailView(APIView):
    """GET: standings (?tab=season|weekly&season=&week=). DELETE {confirm}: owner deletes."""
    permission_classes = [IsAuthenticated]

    def _league(self, request, league_id):
        league = League.objects.select_related('owner').filter(pk=league_id).first()
        if league is None or not leagues.is_member(league, request.user):
            return None
        return league

    def get(self, request, league_id):
        league = self._league(request, league_id)
        if league is None:
            return Response({'detail': 'League not found.'}, status=404)
        tab = request.query_params.get('tab', 'season')
        if tab not in ('season', 'weekly'):
            return Response({'detail': 'tab must be season or weekly.'}, status=400)
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params.get('week', default_week(season)))
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)
        rows = leagues.league_board(league, tab, season, week)
        members = LeagueMembership.objects.filter(league=league).select_related('user').order_by('joined_at', 'id')
        return Response({
            'league': _league_payload(league, request.user, len(rows)),
            'season': season, 'week': week if tab == 'weekly' else None, 'tab': tab,
            'weeks': season_weeks(season),
            'rows': [_row_payload(r, request.user) for r in rows],
            'members': [{'user_id': m.user_id, 'username': m.user.username,
                         'is_owner': m.user_id == league.owner_id} for m in members],
        })

    def delete(self, request, league_id):
        league = self._league(request, league_id)
        if league is None:
            return Response({'detail': 'League not found.'}, status=404)
        confirm = request.data.get('confirm', '') if hasattr(request.data, 'get') else ''
        if not isinstance(confirm, str) or confirm.strip().lower() != league.name.lower():
            return Response({'detail': 'Send the exact league name in "confirm" to delete it.'}, status=400)
        try:
            leagues.delete_league(request.user, league)
        except leagues.LeagueError as exc:
            return _league_error(exc)
        return Response(status=204)


class LeagueActionView(APIView):
    """POST {action, ...}: leave | rename(name) | toggle_open | new_code |
    remove(user_id) | transfer(username). Owner tools need the owner."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'league_write'

    def post(self, request, league_id):
        league = League.objects.select_related('owner').filter(pk=league_id).first()
        if league is None or not leagues.is_member(league, request.user):
            return Response({'detail': 'League not found.'}, status=404)
        action = request.data.get('action')
        try:
            if action == 'leave':
                leagues.leave_league(request.user, league)
                return Response({'ok': True})
            if action == 'rename':
                name = request.data.get('name', '')
                if not isinstance(name, str):
                    return Response({'detail': 'League name must be text.'}, status=400)
                leagues.rename(request.user, league, name)
            elif action == 'toggle_open':
                leagues.set_open(request.user, league, not league.is_open)
            elif action == 'new_code':
                leagues.regenerate_code(request.user, league)
            elif action == 'remove':
                leagues.remove_member(request.user, league, int(request.data.get('user_id')))
            elif action == 'transfer':
                username = request.data.get('username', '')
                if not isinstance(username, str):
                    return Response({'detail': 'Username must be text.'}, status=400)
                leagues.transfer_ownership(request.user, league, username)
            else:
                return Response({'detail': 'Unknown action.'}, status=400)
        except (TypeError, ValueError):
            return Response({'detail': 'user_id must be a number.'}, status=400)
        except leagues.LeagueError as exc:
            return _league_error(exc)
        league.refresh_from_db()
        return Response({'league': _league_payload(league, request.user)})


class TiebreakerView(APIView):
    """GET (?season&week): this week's tiebreaker. POST {game_id, total_points}: save a guess."""
    permission_classes = [IsAuthenticated]

    @property
    def throttle_scope(self):
        return 'tiebreaker' if self.request.method == 'POST' else None

    @staticmethod
    def _payload(card):
        if card is None:
            return None
        return {k: card[k] for k in ('game_id', 'label', 'locked', 'guess', 'actual', 'result')}

    def get(self, request):
        try:
            season, week = _season_week(request)
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers (week 1-22).'}, status=400)
        return Response({'season': season, 'week': week,
                         'tiebreaker': self._payload(tiebreaker.weekly_card(request.user, season, week))})

    @idempotent
    def post(self, request):
        game = Game.objects.filter(game_id=str(request.data.get('game_id') or '')).first()
        if game is None:
            return Response({'detail': 'Game not found.'}, status=404)
        expected = tiebreaker.tiebreaker_game(game.season, game.week)
        if expected is None or expected.pk != game.pk:
            return Response({'detail': "That game is not this week's tiebreaker."}, status=400)
        try:
            pick = tiebreaker.save_guess(request.user, game, request.data.get('total_points'))
        except tiebreaker.TiebreakerError as exc:
            return Response({'detail': exc.message}, status=exc.status)
        return Response({'ok': True, 'total_points': pick.total_points,
                         'tiebreaker': self._payload(tiebreaker.weekly_card(request.user, game.season, game.week))})


class InsightsView(APIView):
    """GET (?season): the player's own pick habits."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
        except (TypeError, ValueError):
            return Response({'detail': 'Season must be a number.'}, status=400)
        return Response(build_insights(request.user, season))


class MatchupsView(APIView):
    """GET (?season&week): Vegas line + injuries for every game that week."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            season, week = _season_week(request)
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers (week 1-22).'}, status=400)
        games = list(Game.objects.filter(season=season, week=week).select_related('odds')
                     .order_by('game_date', 'kickoff', 'pk'))
        injuries = matchups.injuries_by_team(
            season, week, {t for g in games for t in (g.home_team, g.away_team)})
        return Response({'season': season, 'week': week,
                         'games': [matchups.matchup_payload(g, injuries) for g in games]})


class GameMatchupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id):
        game = Game.objects.select_related('odds').filter(game_id=game_id).first()
        if game is None:
            return Response({'detail': 'Game not found.'}, status=404)
        return Response(matchups.matchup_payload(game))


class ChatReportView(APIView):
    """POST {message_id, reason, details?}: report a chat line."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'chat_report'

    @idempotent
    def post(self, request):
        try:
            message_id = int(request.data.get('message_id'))
        except (TypeError, ValueError):
            return Response({'detail': 'message_id must be a number.'}, status=400)
        reason = request.data.get('reason', '')
        details = request.data.get('details', '')
        if not isinstance(reason, str) or not isinstance(details, str):
            return Response({'detail': 'Reason and details must be text.'}, status=400)
        try:
            _report, created = moderation.report_message(request.user, message_id, reason, details)
        except moderation.ModerationBlocked as exc:
            return Response({'detail': exc.message}, status=exc.status)
        return Response({'ok': True, 'created': created}, status=201 if created else 200)


class ChatBlockView(APIView):
    """GET: who I muted or blocked. POST {username, action: mute|block|unmute|unblock}."""
    permission_classes = [IsAuthenticated]

    @property
    def throttle_scope(self):
        return 'chat_block' if self.request.method == 'POST' else None

    def get(self, request):
        return Response({'blocks': moderation.list_blocks(request.user)})

    def post(self, request):
        username = request.data.get('username', '')
        action = request.data.get('action', '')
        if not isinstance(username, str) or not isinstance(action, str):
            return Response({'detail': 'Username and action must be text.'}, status=400)
        try:
            note = moderation.set_block(request.user, username, action)
        except moderation.ModerationBlocked as exc:
            return Response({'detail': exc.message}, status=exc.status)
        return Response({'ok': True, 'message': note, 'blocks': moderation.list_blocks(request.user)})
