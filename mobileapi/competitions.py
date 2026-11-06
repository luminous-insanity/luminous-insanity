from .common import *

class ChallengesView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _serialize(challenge, result, viewer_id):
        return {
            'id': challenge.id,
            'challenger': {'id': challenge.challenger_id, 'username': challenge.challenger.username},
            'opponent': {'id': challenge.opponent_id, 'username': challenge.opponent.username},
            'scope': challenge.scope, 'season': challenge.season, 'week': challenge.week,
            'game': ({'game_id': challenge.game.game_id, 'home_team': challenge.game.home_team,
                      'away_team': challenge.game.away_team} if challenge.game_id else None),
            'status': challenge.status, 'result_state': result.state,
            'outcome': result.outcome_for(challenge, viewer_id),
            'challenger_score': result.challenger_score,
            'opponent_score': result.opponent_score,
            'created_at': challenge.created_at.isoformat(),
        }

    def get(self, request):
        from accounts.challenges import evaluate_many
        from accounts.models import Challenge
        rows = list(Challenge.objects.filter(
            Q(challenger=request.user) | Q(opponent=request.user)
        ).select_related('challenger', 'opponent', 'game').order_by('-created_at')[:100])
        results = evaluate_many(rows)
        return Response({'challenges': [self._serialize(row, results[row.id], request.user.id) for row in rows]})

    @idempotent
    def post(self, request):
        from accounts.challenges import create_challenge, ChallengeError
        from accounts.models import Challenge
        try:
            opponent_id = int(request.data.get('opponent_id'))
        except (TypeError, ValueError):
            return Response({'detail': 'A valid opponent_id is required.'}, status=400)
        opponent = User.objects.filter(pk=opponent_id, is_superuser=False).first()
        if not opponent:
            return Response({'detail': 'Opponent not found.'}, status=404)
        scope = request.data.get('scope')
        try:
            if scope == Challenge.GAME:
                game = Game.objects.filter(game_id=request.data.get('game_id')).first()
                challenge = create_challenge(request.user, opponent, scope, game=game)
            elif scope == Challenge.WEEK:
                try:
                    week = int(request.data.get('week'))
                except (TypeError, ValueError):
                    return Response({'detail': 'A valid week is required.'}, status=400)
                challenge = create_challenge(request.user, opponent, scope, week=week)
            else:
                return Response({'detail': 'Scope must be game or week.'}, status=400)
        except ChallengeError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response({'id': challenge.id, 'status': challenge.status}, status=201)


class ChallengeRespondView(APIView):
    permission_classes = [IsAuthenticated]

    @idempotent
    def post(self, request, challenge_id):
        from accounts.models import Challenge
        from accounts.challenges import evaluate_many
        row = get_object_or_404(Challenge, pk=challenge_id)
        action = request.data.get('action')
        if action in ('accept', 'decline'):
            if row.opponent_id != request.user.id or row.status != Challenge.PENDING:
                return Response({'detail': 'Only the challenged player can respond to a pending challenge.'}, status=403)
            if evaluate_many([row])[row.id].state == 'expired':
                return Response({'detail': 'This challenge has expired.'}, status=409)
            row.status = Challenge.ACCEPTED if action == 'accept' else Challenge.DECLINED
        elif action == 'cancel':
            if row.challenger_id != request.user.id or row.status != Challenge.PENDING:
                return Response({'detail': 'Only the challenger can cancel a pending challenge.'}, status=403)
            row.status = Challenge.CANCELLED
        else:
            return Response({'detail': 'Action must be accept, decline, or cancel.'}, status=400)
        row.responded_at = timezone.now()
        row.save(update_fields=['status', 'responded_at'])
        return Response({'id': row.id, 'status': row.status})


class CrossfireView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from accounts.crossfire import week_board, fire_targets_for_game
        try:
            season = int(request.query_params.get('season', settings.NFL_SEASON))
            week = int(request.query_params.get('week', current_week()))
        except (TypeError, ValueError):
            return Response({'detail': 'Season and week must be numbers.'}, status=400)
        board = week_board(season, week, viewer=request.user)
        targets = None
        game_id = request.query_params.get('game_id')
        if game_id:
            game = Game.objects.filter(game_id=game_id, season=season, week=week).first()
            if not game:
                return Response({'detail': 'Game not found in this season/week.'}, status=404)
            targets = [{
                'user_id': item['user'].id, 'username': item['user'].username,
                'opposing_side': item['side'], 'is_friend': item['is_friend'],
            } for item in fire_targets_for_game(request.user, game)]
        def row(item):
            cf = item.crossfire
            return {
                'id': cf.id, 'game_id': cf.game.game_id,
                'game': f'{cf.game.away_team} @ {cf.game.home_team}',
                'attacker': {'id': cf.attacker_id, 'username': cf.attacker.username},
                'target': {'id': cf.target_id, 'username': cf.target.username},
                'attacker_side': cf.attacker_side, 'target_side': cf.target_side,
                'result': item.result, 'game_final': item.game_final,
            }
        return Response({
            'season': season, 'week': week, 'eligible_targets': targets,
            'tokens': board['tokens'], 'total_crossfires': board['total_crossfires'],
            'crossfires': [row(item) for item in board['graded']],
            'sharpshooters': [{
                'user_id': item['user'].id, 'username': item['user'].username,
                'fired': item['fired'], 'hits': item['hits'],
                'misses': item['misses'], 'pending': item['pending'],
            } for item in board['sharpshooters']],
        })

    @idempotent
    def post(self, request):
        from accounts.crossfire import place_crossfire, CrossfireError
        game = Game.objects.filter(game_id=request.data.get('game_id')).first()
        try:
            target_id = int(request.data.get('target_id'))
        except (TypeError, ValueError):
            return Response({'detail': 'A valid target_id is required.'}, status=400)
        target = User.objects.filter(pk=target_id, is_superuser=False).first()
        if not game or not target:
            return Response({'detail': 'A valid game_id and target_id are required.'}, status=400)
        try:
            crossfire = place_crossfire(request.user, target, game)
        except CrossfireError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response({'id': crossfire.id, 'game_id': game.game_id, 'target_id': target.id}, status=201)


class CrossfireCancelView(APIView):
    permission_classes = [IsAuthenticated]

    @idempotent
    def delete(self, request, crossfire_id):
        from accounts.crossfire import cancel_crossfire, CrossfireError
        try:
            cancel_crossfire(request.user, crossfire_id)
        except CrossfireError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(status=204)


