from .common import *

class HistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from api.rules import grade_pick
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
        except (TypeError, ValueError):
            return Response({'detail': 'Season must be a number.'}, status=400)
        picks = Pick.objects.filter(user=request.user, game__season=season).select_related('game').order_by('game__week', 'game__kickoff', 'game__pk')
        rows = []
        for pick in picks:
            game = pick.game
            result = grade_pick(pick.team_picked, game.home_score, game.away_score) if game.is_final else None
            rows.append({
                'game_id': game.game_id, 'week': game.week,
                'home_team': game.home_team, 'away_team': game.away_team,
                'picked_side': pick.team_picked,
                'picked_team': game.home_team if pick.team_picked == Pick.HOME else game.away_team,
                'confidence': pick.confidence, 'status': game.status,
                'home_score': game.home_score, 'away_score': game.away_score,
                'result': result,
            })
        return Response({'season': season, 'picks': rows})


class PlayerProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        from accounts.careerstats import career_for, career_stats
        from accounts.standings import standing_for
        from accounts.models import PlayerIdentity
        player = User.objects.filter(pk=user_id, is_active=True, is_superuser=False).first()
        if not player:
            return Response({'detail': 'Player not found.'}, status=404)
        season = settings.NFL_SEASON
        row = standing_for(player, season=season)
        career = career_for(career_stats(), player.id)
        identity = PlayerIdentity.objects.filter(user=player).first()
        return Response({
            'id': player.id, 'username': player.username,
            'favorite_team': identity.favorite_team if identity else '',
            'active_title': identity.active_title if identity else '',
            'division': identity.division if identity and identity.division_season == season else '',
            'season_record': {'wins': row.wins, 'losses': row.losses, 'ties': row.ties,
                              'completed': row.completed, 'win_pct': row.win_pct},
            'career_record': {'wins': career.wins, 'losses': career.losses,
                              'ties': career.ties, 'win_pct': career.win_pct},
            'is_me': player.id == request.user.id,
        })


class ComparePicksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        from accounts.leaderboard import build_comparison
        from accounts.standings import standing_for
        other = User.objects.filter(pk=user_id, is_active=True, is_superuser=False).first()
        if not other:
            return Response({'detail': 'Player not found.'}, status=404)
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params.get('week', default_week(settings.NFL_SEASON)))
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)
        data = build_comparison(request.user, other, season, week)
        def record(row):
            return {'wins': row.wins, 'losses': row.losses, 'ties': row.ties,
                    'completed': row.completed, 'win_pct': row.win_pct}
        return Response({
            'season': season, 'week': week,
            'other': {'id': other.id, 'username': other.username},
            'are_friends': data['are_friends'], 'differences': data['differ'],
            'hidden': data['hidden'], 'my_missing': data['my_missing'],
            'their_missing': data['their_missing'],
            'my_week': record(data['my_week']), 'their_week': record(data['their_week']),
            'my_season': record(data['my_season']), 'their_season': record(data['their_season']),
            'gap_who': data['gap_who'], 'gap_text': data['gap_text'],
            'games': [{
                'game_id': row['game'].game_id,
                'home_team': row['game'].home_team, 'away_team': row['game'].away_team,
                'kickoff': row['game'].kickoff.isoformat() if row['game'].kickoff else None,
                'my_team': row['my_team'], 'my_state': row['my_state'], 'my_label': row['my_label'],
                'their_team': row['their_team'], 'their_state': row['their_state'],
                'their_label': row['their_label'], 'differs': row['differs'],
            } for row in data['rows']],
        })


class DivisionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.playoffs import DIVISIONS, division_playoff_race
        identity, _ = PlayerIdentity.objects.get_or_create(user=request.user)
        season = settings.NFL_SEASON
        if identity.division_season != season:
            from accounts.team_identity import team_division
            identity.division = team_division(identity.favorite_team) if identity.favorite_team else ''
            identity.division_season = season if identity.division else None
            identity.save(update_fields=['division', 'division_season', 'updated_at'])
        division = request.query_params.get('division') or identity.division
        if division not in DIVISIONS:
            return Response({'divisions': list(DIVISIONS), 'my_division': identity.division,
                             'detail': 'Pass a valid division to retrieve its standings.'})
        race = division_playoff_race(division, season=season)
        return Response({
            'season': season, 'division': division,
            'qualifiers_per_division': race['qualifiers_per_division'],
            'head_to_head_wildcard_spots': race['head_to_head_wildcard_spots'],
            'season_complete': race['season_complete'],
            'qualification_final': race['qualification_final'],
            'active_players': race['active_players'], 'field_size': race['field_size'],
            'standings': [{
                'user_id': row.user.id, 'username': row.user.username,
                'rank': row.rank, 'wins': row.wins, 'losses': row.losses,
                'ties': row.ties, 'pending': row.pending,
                'playoff_qualified': row.playoff_qualified,
                'qualification_route': row.qualification_route,
                'playoff_status': row.playoff_status,
                'distance_from_cutoff': row.distance_from_cutoff,
                'is_me': row.user.id == request.user.id,
            } for row in race['standings']],
        })


class PlayoffsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.playoffs import championship_bracket
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
        except (TypeError, ValueError):
            return Response({'detail': 'Season must be a number.'}, status=400)
        bracket = championship_bracket(season=season)
        def entrant(item):
            return {
                'user_id': item['user_id'], 'username': item['user'].username,
                'division': item['division'], 'record': item['record'],
                'wins': item['wins'], 'losses': item['losses'], 'ties': item['ties'],
                'win_pct': item['win_pct'], 'qualification_route': item['qualification_route'],
                'head_to_head_wins': item['head_to_head_wins'], 'seed': item['seed'],
                'is_me': item['user_id'] == request.user.id,
            }
        return Response({
            'season': bracket['season'], 'field_size': bracket['field_size'],
            'field_count': bracket['field_count'], 'slots_open': bracket['slots_open'],
            'field': [entrant(item) for item in bracket['field']],
            'first_round': [{'high': entrant(pair['high']), 'low': entrant(pair['low']), 'winner': None}
                            for pair in bracket['first_round']],
            'byes': [entrant(item) for item in bracket['byes']],
            'bracket_size': bracket['bracket_size'],
            'is_provisional': bracket['is_provisional'],
            'active_players': bracket['active_players'],
            'qualification_diagnostics': bracket['qualification_diagnostics'],
        })


class SquaresView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.models import SquaresBoard
        from accounts.squares import board_grid
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
        except (TypeError, ValueError):
            return Response({'detail': 'Season must be a number.'}, status=400)
        board = SquaresBoard.objects.filter(season=season).select_related('game').first()
        if not board:
            return Response({'season': season, 'available': False, 'detail': 'The squares board has not been dealt yet.'})
        data = board_grid(board, request.user)
        return Response({
            'season': season, 'available': True,
            'game': ({'game_id': data['game'].game_id, 'home_team': data['home_team'],
                      'away_team': data['away_team']} if data['game'] else None),
            'home_digits': list(data['board'].home_digits) if data['board'].home_digits else [],
            'away_digits': data['away_digits'], 'rows': data['rows'],
            'my_square_count': data['my_count'], 'player_count': data['player_count'],
            'results': [{
                'quarter': item['quarter'], 'label': item['label'], 'scored': item['scored'],
                'home_score': item['home_score'], 'away_score': item['away_score'],
                'home_digit': item['home_digit'], 'away_digit': item['away_digit'],
                'row': item['row'], 'col': item['col'],
                'owner': item['owner'].username if item['owner'] else None,
            } for item in data['results']],
        })


class LiveMomentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.live_features import live_game_moments, confidence_board
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params.get('week', current_week()))
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)
        moments = live_game_moments(season=season, week=week)
        confidence = confidence_board(season=season, week=week)
        return Response({
            'season': season, 'week': week,
            'live_games': [{'game_id': game.game_id, 'home_team': game.home_team,
                            'away_team': game.away_team, 'status': game.status,
                            'home_score': game.home_score, 'away_score': game.away_score}
                           for game in moments['live_games']],
            'reactions': [{'id': reaction.id, 'username': reaction.user.username,
                           'game_id': reaction.game.game_id, 'emoji': reaction.emoji,
                           'created_at': reaction.created_at.isoformat()}
                          for reaction in moments['reactions']],
            'confidence_board': [{'rank': row['rank'], 'user_id': row['user'].id,
                                  'username': row['user'].username, 'points': row['points'],
                                  'underdog_locks': row['underdog_locks'],
                                  'is_me': row['user'].id == request.user.id}
                                 for row in confidence],
        })
