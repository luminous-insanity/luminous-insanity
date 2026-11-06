from .common import *
from .common import _game_payload

class GamesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params.get('week', current_week()))
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)
        if not 1 <= week <= 22:
            return Response({'detail': 'Week must be between 1 and 22.'}, status=400)
        games = Game.objects.filter(season=season, week=week).order_by('game_date', 'kickoff', 'pk')
        return Response({
            'season': season, 'week': week,
            'games': [_game_payload(game, request.user, include_community=True) for game in games],
        })


class PicksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params['week']) if request.query_params.get('week') else None
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)
        rows = Pick.objects.filter(user=request.user, game__season=season).select_related('game').order_by('game__week', 'game__kickoff')
        if week is not None:
            rows = rows.filter(game__week=week)
        return Response({'season': season, 'picks': [
            {'game_id': p.game.game_id, 'season': p.game.season, 'week': p.game.week,
             'side': p.team_picked, 'team': p.game.home_team if p.team_picked == Pick.HOME else p.game.away_team,
             'confidence': p.confidence, 'game': _game_payload(p.game, request.user)}
            for p in rows
        ]})

    def post(self, request):
        game_id = str(request.data.get('game_id') or '')
        side = request.data.get('side')
        confidence = request.data.get('confidence')
        game = Game.objects.filter(game_id=game_id).first()
        if not game:
            return Response({'detail': 'Game not found.'}, status=404)
        if side not in (Pick.HOME, Pick.AWAY):
            return Response({'detail': 'Side must be "home" or "away".'}, status=400)
        if confidence in ('', None):
            confidence = None
        else:
            if isinstance(confidence, bool):
                return Response({'detail': 'Confidence must be 1, 2, 3, or null.'}, status=400)
            try:
                confidence = int(confidence)
            except (TypeError, ValueError):
                return Response({'detail': 'Confidence must be 1, 2, 3, or null.'}, status=400)
            if confidence not in (1, 2, 3):
                return Response({'detail': 'Confidence must be 1, 2, 3, or null.'}, status=400)
        if game.has_started:
            return Response({'detail': 'Picks are locked for this game.'}, status=409)
        with transaction.atomic():
            pick, created = Pick.objects.update_or_create(
                user=request.user, game=game,
                defaults={'team_picked': side, 'confidence': confidence},
            )
        touch_activity(request.user)
        return Response({
            'created': created,
            'pick': {'game_id': game.game_id, 'side': pick.team_picked,
                     'team': game.home_team if side == Pick.HOME else game.away_team,
                     'confidence': pick.confidence},
        }, status=201 if created else 200)


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tab = request.query_params.get('tab', 'season')
        mode = request.query_params.get('mode', 'all')
        if tab not in ('weekly', 'season') or mode not in ('all', 'friends'):
            return Response({'detail': 'tab must be weekly/season and mode must be all/friends.'}, status=400)
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params.get('week', default_week(season)))
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)
        board = build_board(tab=tab, season=season, week=week, mode=mode, viewer=request.user)
        return Response({
            'season': season, 'week': week if tab == 'weekly' else None,
            'tab': tab, 'mode': mode,
            'friends_empty': board['friends_empty'],
            'rows': [{
                'rank': row.rank, 'user_id': row.user.id,
                'username': row.user.username, 'wins': row.wins, 'losses': row.losses,
                'ties': row.ties, 'pending': row.pending, 'completed': row.completed,
                'win_pct': row.win_pct, 'movement': row.movement_kind,
                'movement_label': row.movement_label,
                'is_me': row.user.id == request.user.id,
            } for row in board['rows']],
        })


