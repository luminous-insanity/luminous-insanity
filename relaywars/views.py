from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from api.models import Game
from .models import RelayAbility, RelayMatch, RelayPick, RelayQueueEntry, RelayTeam, RelayTeamMember
from .services import (
    RelayWarsError, cast_ability_vote, close_draft_if_locked, create_invite_team, draft_state, leave_team,
    join_invite_team, join_random_queue, open_join_events, propose_ability, refresh_match_scores,
    skip_turn, submit_pick,
)


def _event_choices():
    return open_join_events()


@login_required
def relay_home(request):
    events = _event_choices()
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            season = int(request.POST.get('season'))
            week = int(request.POST.get('week'))
            if action == 'create_team':
                team = create_invite_team(request.user, season, week, request.POST.get('name', '').strip())
                messages.success(request, 'Your team is ready for invitations. Share its invite link with friends.')
                return redirect('relaywars:home')
            if action == 'random_queue':
                created = join_random_queue(request.user, season, week)
                messages.success(request, 'You joined random matchmaking. A team forms when four players are available.')
                return redirect('relaywars:home')
        except (TypeError, ValueError, RelayWarsError) as exc:
            messages.error(request, str(exc))

    memberships = RelayTeamMember.objects.filter(user=request.user, is_active=True).select_related('team')
    team_ids = memberships.values_list('team_id', flat=True)
    teams = RelayTeam.objects.filter(pk__in=team_ids).prefetch_related('members__user').order_by('-created_at')
    matches = RelayMatch.objects.filter(Q(team_a__in=teams) | Q(team_b__in=teams)).select_related('team_a', 'team_b').order_by('-created_at')
    queued = RelayQueueEntry.objects.filter(user=request.user)
    return render(request, 'relaywars/home.html', {
        'events': events, 'teams': teams, 'matches': matches, 'queued': queued,
    })


@login_required
def join_team(request, invite_code):
    team = get_object_or_404(RelayTeam, invite_code=invite_code)
    if request.method == 'POST':
        try:
            team = join_invite_team(request.user, invite_code)
            messages.success(request, f'You joined {team.name}.')
            return redirect('relaywars:home')
        except RelayWarsError as exc:
            messages.error(request, str(exc))
            return redirect('relaywars:home')
    return render(request, 'relaywars/join.html', {'team': team})


@login_required
def match_detail(request, match_id):
    match = get_object_or_404(
        RelayMatch.objects.select_related('team_a', 'team_b').prefetch_related('sides__team'),
        pk=match_id,
    )
    my_team = next((team for team in (match.team_a, match.team_b)
                    if team.members.filter(user=request.user, is_active=True).exists()), None)
    if not my_team:
        messages.error(request, 'You are not a member of either team in this matchup.')
        return redirect('relaywars:home')

    if request.method == 'POST':
        close_draft_if_locked(match)
        action = request.POST.get('action')
        try:
            if action == 'pick':
                submit_pick(match, request.user, request.POST.get('turn_id'), request.POST.get('game_id'), request.POST.get('side'))
                messages.success(request, 'Your team selection is locked and visible to both teams.')
            elif action == 'skip':
                skip_turn(match, request.user, request.POST.get('turn_id'))
                messages.info(request, 'That draft turn was skipped.')
            elif action == 'ability':
                propose_ability(match, request.user, request.POST.get('pick_id'), request.POST.get('kind'))
                messages.success(request, 'Ability proposed. Your team can vote until the target game kicks off.')
            elif action == 'vote':
                ability = get_object_or_404(RelayAbility, pk=request.POST.get('ability_id'), match=match)
                cast_ability_vote(ability, request.user, request.POST.get('vote') == 'yes')
                messages.success(request, 'Your vote has been recorded.')
        except (ValueError, RelayWarsError) as exc:
            messages.error(request, str(exc))
        return redirect('relaywars:match', match_id=match.pk)

    close_draft_if_locked(match)
    refresh_match_scores(match)
    turns, next_turn, draft_complete = draft_state(match)
    available_games = Game.objects.filter(
        season=match.season, week=match.week, kickoff__gt=timezone.now(),
    ).exclude(relaywars_picks__match=match).order_by('kickoff')
    picks = match.picks.select_related('team', 'assigned_player', 'selected_by', 'game').prefetch_related('abilities__votes').order_by('game__kickoff')
    abilities = match.abilities.select_related('team', 'target_pick__game', 'proposed_by').prefetch_related('votes__user')
    sides = {side.team_id: side for side in match.sides.select_related('team')}
    side_a = sides.get(match.team_a_id)
    side_b = sides.get(match.team_b_id)
    return render(request, 'relaywars/match.html', {
        'match': match, 'my_team': my_team, 'turns': turns, 'next_turn': next_turn,
        'draft_complete': draft_complete, 'available_games': available_games,
        'picks': picks, 'abilities': abilities,
        'side_a': side_a, 'side_b': side_b, 'is_draft_open': not match.draft_locked,
    })


@login_required
@require_POST
def leave_queue(request):
    RelayQueueEntry.objects.filter(user=request.user).delete()
    messages.info(request, 'You left random matchmaking.')
    return redirect('relaywars:home')


@login_required
@require_POST
def leave_team_view(request, team_id):
    team = get_object_or_404(RelayTeam, pk=team_id)
    try:
        leave_team(team, request.user)
        messages.info(request, 'You left the team. Any games already drafted remain with the team.')
    except RelayWarsError as exc:
        messages.error(request, str(exc))
    return redirect('relaywars:home')
