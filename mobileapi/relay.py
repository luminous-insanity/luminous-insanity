from .common import *

class RelayWarsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Q
        from relaywars.models import RelayMatch, RelayQueueEntry, RelayTeamMember
        from relaywars.services import open_join_events
        memberships = RelayTeamMember.objects.filter(user=request.user, is_active=True).select_related('team')
        team_ids = [m.team_id for m in memberships]
        teams = [m.team for m in memberships]
        matches = RelayMatch.objects.filter(Q(team_a_id__in=team_ids) | Q(team_b_id__in=team_ids)).select_related('team_a', 'team_b').order_by('-created_at')
        return Response({
            'open_events': [{**event, 'first_kickoff': event['first_kickoff'].isoformat()} for event in open_join_events()],
            'teams': [self._team_payload(team) for team in teams],
            'matches': [{'id': m.id, 'season': m.season, 'week': m.week, 'status': m.status,
                         'lock_at': m.lock_at.isoformat(), 'team_a': m.team_a.name,
                         'team_b': m.team_b.name} for m in matches],
            'queue': [{'season': q.season, 'week': q.week, 'queued_at': q.queued_at.isoformat()}
                      for q in RelayQueueEntry.objects.filter(user=request.user)],
        })

    @staticmethod
    def _team_payload(team):
        return {
            'id': team.id, 'name': team.name, 'season': team.season, 'week': team.week,
            'status': team.status, 'invite_code': team.invite_code,
            'is_random': team.is_random,
            'members': [{'id': m.user_id, 'username': m.user.username,
                         'draft_priority': m.draft_priority, 'is_owner': m.user_id == team.owner_id}
                        for m in team.members.filter(is_active=True).select_related('user')],
        }

    @idempotent
    def post(self, request):
        from relaywars import services
        from relaywars.models import RelayTeam
        action = request.data.get('action')
        try:
            season = int(request.data.get('season')) if request.data.get('season') is not None else settings.NFL_SEASON
            week = int(request.data.get('week')) if request.data.get('week') is not None else current_week()
            if action == 'create_team':
                team = services.create_invite_team(request.user, season, week, str(request.data.get('name') or '').strip())
                return Response({'team': self._team_payload(team)}, status=201)
            if action == 'random_queue':
                created = services.join_random_queue(request.user, season, week)
                return Response({'queued': True, 'already_queued': not created})
            if action == 'join_team':
                team = services.join_invite_team(request.user, str(request.data.get('invite_code') or ''))
                return Response({'team': self._team_payload(team)})
            if action == 'leave_queue':
                from relaywars.models import RelayQueueEntry
                RelayQueueEntry.objects.filter(user=request.user).delete()
                return Response({'queued': False})
            if action == 'leave_team':
                try:
                    team_id = int(request.data.get('team_id'))
                except (TypeError, ValueError):
                    return Response({'detail': 'A valid team_id is required.'}, status=400)
                team = get_object_or_404(RelayTeam, pk=team_id)
                services.leave_team(team, request.user)
                return Response({'left': True})
        except (TypeError, ValueError, services.RelayWarsError) as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response({'detail': 'Unknown Relay Wars action.'}, status=400)


class RelayMatchView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _payload(match, user):
        from relaywars.models import RelayAbility, RelayPick
        from relaywars.services import close_draft_if_locked, draft_state, refresh_match_scores, team_for_user
        close_draft_if_locked(match)
        refresh_match_scores(match)
        turns, next_turn, complete = draft_state(match)
        my_team = team_for_user(match, user)
        if not my_team:
            return None
        picks = list(match.picks.select_related('team', 'assigned_player', 'selected_by', 'game').prefetch_related('abilities__votes').order_by('game__kickoff'))
        abilities = list(match.abilities.select_related('team', 'target_pick__game', 'proposed_by').prefetch_related('votes__user'))
        available_games = Game.objects.filter(
            season=match.season, week=match.week, kickoff__gt=timezone.now(),
        ).exclude(relaywars_picks__match=match).order_by('kickoff')
        sides = {side.team_id: side for side in match.sides.select_related('team')}
        return {
            'id': match.id, 'season': match.season, 'week': match.week,
            'status': match.status, 'lock_at': match.lock_at.isoformat(),
            'draft_locked': match.draft_locked, 'draft_complete': complete,
            'my_team_id': my_team.id,
            'teams': [{
                'id': team.id, 'name': team.name,
                'members': [{'id': m.user_id, 'username': m.user.username} for m in team.members.filter(is_active=True).select_related('user')],
                'ability_tokens': sides[team.id].ability_tokens if team.id in sides else 0,
                'current_chain': sides[team.id].current_chain if team.id in sides else 0,
                'best_chain': sides[team.id].best_chain if team.id in sides else 0,
            } for team in (match.team_a, match.team_b)],
            'available_games': [{
                'game_id': game.game_id, 'home_team': game.home_team,
                'away_team': game.away_team, 'kickoff': game.kickoff.isoformat(),
            } for game in available_games],
            'turns': [{
                'id': turn.id, 'position': turn.position, 'team_id': turn.team_id,
                'assigned_player': {'id': turn.assigned_member_id, 'username': turn.assigned_member.username},
                'skipped': turn.skipped,
                'completed': turn.skipped or RelayPick.objects.filter(draft_turn=turn).exists(),
                'is_next': bool(next_turn and next_turn.id == turn.id),
            } for turn in turns],
            'picks': [{
                'id': pick.id, 'team_id': pick.team_id,
                'assigned_player': pick.assigned_player.username,
                'selected_by': pick.selected_by.username,
                'game_id': pick.game.game_id, 'home_team': pick.game.home_team,
                'away_team': pick.game.away_team, 'picked_side': pick.picked_side,
                'picked_team': pick.picked_team, 'result': pick.result,
                'abilities': [{
                    'id': ability.id, 'kind': ability.kind, 'status': ability.status,
                    'team_id': ability.team_id, 'proposed_by': ability.proposed_by.username,
                    'votes': [{'username': vote.user.username, 'approved': vote.approved} for vote in ability.votes.all()],
                } for ability in pick.abilities.all()],
            } for pick in picks],
            'abilities': [{
                'id': ability.id, 'kind': ability.kind, 'status': ability.status,
                'team_id': ability.team_id, 'target_pick_id': ability.target_pick_id,
                'game_id': ability.target_pick.game.game_id,
            } for ability in abilities],
        }

    def get(self, request, match_id):
        from relaywars.models import RelayMatch
        match = get_object_or_404(RelayMatch.objects.select_related('team_a', 'team_b'), pk=match_id)
        payload = self._payload(match, request.user)
        if payload is None:
            return Response({'detail': 'You are not a member of this matchup.'}, status=403)
        return Response(payload)

    @idempotent
    def post(self, request, match_id):
        from relaywars.models import RelayAbility, RelayMatch
        from relaywars import services
        match = get_object_or_404(RelayMatch.objects.select_related('team_a', 'team_b'), pk=match_id)
        if not services.team_for_user(match, request.user):
            return Response({'detail': 'You are not a member of this matchup.'}, status=403)
        action = request.data.get('action')
        try:
            if action == 'pick':
                pick = services.submit_pick(match, request.user, request.data.get('turn_id'), request.data.get('game_id'), request.data.get('side'))
                result = {'pick_id': pick.id}
            elif action == 'skip':
                turn = services.skip_turn(match, request.user, request.data.get('turn_id'))
                result = {'turn_id': turn.id, 'skipped': True}
            elif action == 'propose_ability':
                ability = services.propose_ability(match, request.user, request.data.get('pick_id'), request.data.get('kind'))
                result = {'ability_id': ability.id, 'status': ability.status}
            elif action == 'vote':
                try:
                    ability_id = int(request.data.get('ability_id'))
                except (TypeError, ValueError):
                    return Response({'detail': 'A valid ability_id is required.'}, status=400)
                ability = get_object_or_404(RelayAbility, pk=ability_id, match=match)
                approved = request.data.get('approved')
                if not isinstance(approved, bool):
                    return Response({'detail': 'approved must be true or false.'}, status=400)
                ability = services.cast_ability_vote(ability, request.user, approved)
                result = {'ability_id': ability.id, 'status': ability.status}
            else:
                return Response({'detail': 'Action must be pick, skip, propose_ability, or vote.'}, status=400)
        except (ValueError, services.RelayWarsError) as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response({'ok': True, **result, 'match': self._payload(match, request.user)})


