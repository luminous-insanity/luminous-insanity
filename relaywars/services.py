import random

from django.db import transaction
from django.db.models import Count, Min, Q
from django.utils import timezone

from api.models import Game
from .models import (
    RelayAbility, RelayAbilityVote, RelayDraftTurn, RelayMatch, RelayMatchSide,
    RelayPick, RelayQueueEntry, RelayTeam, RelayTeamMember,
)

TEAM_SIZE = 4


class RelayWarsError(ValueError):
    pass


def _upcoming_games(season, week):
    return Game.objects.filter(season=season, week=week, kickoff__isnull=False).order_by('kickoff', 'pk')


def open_join_events():
    """NFL weeks still open for Relay Wars joining (before that week's first kickoff)."""
    return list(
        Game.objects.filter(kickoff__isnull=False)
        .values('season', 'week')
        .annotate(total=Count('id'), first_kickoff=Min('kickoff'))
        .filter(first_kickoff__gt=timezone.now())
        .order_by('season', 'week')
        .values('season', 'week', 'total', 'first_kickoff')
    )



def _make_team(name, owner, season, week, is_random=False):
    team = RelayTeam.objects.create(
        name=(name or f'{owner.username}\'s Relay Team')[:40], owner=owner,
        season=season, week=week, is_random=is_random,
    )
    RelayTeamMember.objects.create(team=team, user=owner, draft_priority=0)
    return team


@transaction.atomic
def create_invite_team(user, season, week, name=''):
    if RelayTeamMember.objects.filter(user=user, team__season=season, team__week=week, is_active=True).exists():
        raise RelayWarsError('You are already on a Relay Wars team for that week.')
    first_game = _upcoming_games(season, week).first()
    if not first_game or first_game.kickoff <= timezone.now():
        raise RelayWarsError('That week has already started or has no games to draft.')
    team = _make_team(name, user, season, week)
    RelayQueueEntry.objects.filter(user=user, season=season, week=week).delete()
    return team


@transaction.atomic
def join_invite_team(user, invite_code):
    team = RelayTeam.objects.select_for_update().filter(invite_code=invite_code).first()
    if not team:
        raise RelayWarsError('That team invitation is not valid.')
    if team.status != RelayTeam.RECRUITING:
        raise RelayWarsError('That team is already full or matched.')
    first_game = _upcoming_games(team.season, team.week).first()
    if not first_game or first_game.kickoff <= timezone.now():
        raise RelayWarsError('The event has locked to new players.')
    existing_member = team.members.filter(user=user).first()
    if existing_member and existing_member.is_active:
        return team
    if RelayTeamMember.objects.filter(user=user, team__season=team.season, team__week=team.week, is_active=True).exclude(team=team).exists():
        raise RelayWarsError('You are already on a Relay Wars team for that week.')
    if team.member_count >= TEAM_SIZE:
        raise RelayWarsError('That team is full.')
    if existing_member:
        existing_member.is_active = True
        existing_member.save(update_fields=['is_active'])
    else:
        RelayTeamMember.objects.create(team=team, user=user, draft_priority=team.members.count())
    RelayQueueEntry.objects.filter(user=user, season=team.season, week=team.week).delete()
    if team.member_count == TEAM_SIZE:
        team.status = RelayTeam.READY
        team.save(update_fields=['status'])
        pair_ready_teams(team.season, team.week)
    return team


@transaction.atomic
def join_random_queue(user, season, week):
    if RelayTeamMember.objects.filter(user=user, team__season=season, team__week=week, is_active=True).exists():
        raise RelayWarsError('You are already on a Relay Wars team for that week.')
    first_game = _upcoming_games(season, week).first()
    if not first_game or first_game.kickoff <= timezone.now():
        raise RelayWarsError('That week has already started or has no games to draft.')
    entry, created = RelayQueueEntry.objects.get_or_create(user=user, season=season, week=week)
    while True:
        waiting = list(RelayQueueEntry.objects.select_for_update().filter(season=season, week=week).order_by('queued_at', 'pk')[:TEAM_SIZE])
        if len(waiting) < TEAM_SIZE:
            break
        random.shuffle(waiting)
        owner = waiting[0].user
        team = _make_team(f'Random Team {owner.username}', owner, season, week, is_random=True)
        for index, queued in enumerate(waiting[1:], start=1):
            RelayTeamMember.objects.create(team=team, user=queued.user, draft_priority=index)
        RelayQueueEntry.objects.filter(pk__in=[item.pk for item in waiting]).delete()
        team.status = RelayTeam.READY
        team.save(update_fields=['status'])
        pair_ready_teams(season, week)
    return created


@transaction.atomic
def pair_ready_teams(season, week):
    teams = list(
        RelayTeam.objects.select_for_update().filter(
            season=season, week=week, status=RelayTeam.READY,
        ).annotate(active_count=Count('members', filter=Q(members__is_active=True)))
        .filter(active_count=TEAM_SIZE).order_by('created_at', 'pk')
    )
    random.shuffle(teams)
    created_matches = []
    while len(teams) >= 2:
        team_a, team_b = teams.pop(0), teams.pop(0)
        games = list(_upcoming_games(season, week))
        if not games:
            continue
        lock_at = games[0].kickoff
        if lock_at <= timezone.now():
            continue
        match = RelayMatch.objects.create(
            season=season, week=week, team_a=team_a, team_b=team_b, lock_at=lock_at,
        )
        RelayMatchSide.objects.create(match=match, team=team_a)
        RelayMatchSide.objects.create(match=match, team=team_b)
        _create_draft_turns(match, team_a, team_b, len(games))
        team_a.status = RelayTeam.MATCHED
        team_b.status = RelayTeam.MATCHED
        team_a.save(update_fields=['status'])
        team_b.save(update_fields=['status'])
        created_matches.append(match)
    return created_matches


def _rotated_members(team, extra_count, offset):
    members = list(team.members.filter(is_active=True).select_related('user').order_by('draft_priority', 'joined_at'))
    if not members:
        return []
    return members[offset % len(members):] + members[:offset % len(members)]


def _member_pick_schedule(team, slots, side_index):
    members = list(team.members.filter(is_active=True).select_related('user').order_by('draft_priority', 'joined_at'))
    if not members:
        return []
    base, extra = divmod(slots, len(members))
    offset = (team.week + side_index) % len(members)
    rotated = _rotated_members(team, extra, offset)
    quotas = {m.user_id: base for m in members}
    for member in rotated[:extra]:
        quotas[member.user_id] += 1
    schedule = []
    while len(schedule) < slots:
        for member in members:
            if quotas[member.user_id] > 0 and sum(1 for x in schedule if x.pk == member.user_id) < quotas[member.user_id]:
                schedule.append(member.user)
                if len(schedule) == slots:
                    break
    return schedule


def _create_draft_turns(match, team_a, team_b, total_games):
    slots_per_team = total_games // 2
    if slots_per_team < 1:
        return
    schedule_a = _member_pick_schedule(team_a, slots_per_team, 0)
    schedule_b = _member_pick_schedule(team_b, slots_per_team, 1)
    position = 1
    for index in range(slots_per_team):
        RelayDraftTurn.objects.create(match=match, position=position, team=team_a, assigned_member=schedule_a[index])
        position += 1
        RelayDraftTurn.objects.create(match=match, position=position, team=team_b, assigned_member=schedule_b[index])
        position += 1


def team_for_user(match, user):
    return next((team for team in (match.team_a, match.team_b)
                 if team.members.filter(user=user, is_active=True).exists()), None)


def close_draft_if_locked(match):
    if timezone.now() >= match.lock_at:
        match.draft_turns.filter(skipped=False).exclude(pick__isnull=False).update(skipped=True)


def draft_state(match):
    turns = list(match.draft_turns.select_related('team', 'assigned_member').prefetch_related('pick__game').order_by('position'))
    next_turn = None
    for turn in turns:
        if turn.skipped or RelayPick.objects.filter(draft_turn=turn).exists():
            continue
        next_turn = turn
        break
    complete = next_turn is None
    return turns, next_turn, complete


@transaction.atomic
def submit_pick(match, user, turn_id, game_id, side):
    match = RelayMatch.objects.select_for_update().get(pk=match.pk)
    if timezone.now() >= match.lock_at:
        raise RelayWarsError('The draft locked when the first game kicked off.')
    turn = RelayDraftTurn.objects.select_for_update().filter(match=match, pk=turn_id).first()
    if not turn or turn.team_id not in (match.team_a_id, match.team_b_id):
        raise RelayWarsError('That draft turn is not valid.')
    if not turn.team.members.filter(user=user, is_active=True).exists():
        raise RelayWarsError('Only teammates can submit a draft pick.')
    _, next_turn, complete = draft_state(match)
    if complete or next_turn.pk != turn.pk:
        raise RelayWarsError('It is not that turn yet.')
    if side not in (RelayPick.HOME, RelayPick.AWAY):
        raise RelayWarsError('Choose one of the teams in the game.')
    game = _upcoming_games(match.season, match.week).filter(game_id=game_id).first()
    if not game or not game.kickoff or game.kickoff <= timezone.now() or game.has_started:
        raise RelayWarsError('That game is no longer available to draft.')
    if RelayPick.objects.filter(match=match, game=game).exists():
        raise RelayWarsError('Another player has already selected that game.')
    return RelayPick.objects.create(
        match=match, draft_turn=turn, team=turn.team,
        assigned_player=turn.assigned_member, selected_by=user,
        game=game, picked_side=side,
    )


@transaction.atomic
def skip_turn(match, user, turn_id):
    match = RelayMatch.objects.select_for_update().get(pk=match.pk)
    if timezone.now() >= match.lock_at:
        raise RelayWarsError('The draft is already locked.')
    turn = RelayDraftTurn.objects.select_for_update().filter(match=match, pk=turn_id).first()
    if not turn or not turn.team.members.filter(user=user, is_active=True).exists():
        raise RelayWarsError('Only a teammate can skip this turn.')
    _, next_turn, complete = draft_state(match)
    if complete or next_turn.pk != turn.pk:
        raise RelayWarsError('It is not that turn yet.')
    turn.skipped = True
    turn.save(update_fields=['skipped'])
    return turn


@transaction.atomic
def propose_ability(match, user, pick_id, kind):
    match = RelayMatch.objects.select_for_update().get(pk=match.pk)
    if kind not in (RelayAbility.JINX, RelayAbility.PROTECT):
        raise RelayWarsError('Unknown ability.')
    _, _, complete = draft_state(match)
    if not complete:
        raise RelayWarsError('Abilities open after the draft is complete.')
    pick = RelayPick.objects.select_related('game').filter(match=match, pk=pick_id).first()
    if not pick or not pick.game.kickoff or pick.game.kickoff <= timezone.now():
        raise RelayWarsError('That game has already started or is not part of this matchup.')
    team = team_for_user(match, user)
    if not team:
        raise RelayWarsError('You must be on one of the teams to use an ability.')
    if kind == RelayAbility.JINX and pick.team_id == team.pk:
        raise RelayWarsError('Jinx must target an opposing pick.')
    if kind == RelayAbility.PROTECT and pick.team_id != team.pk:
        raise RelayWarsError('Protection must target your own team.')
    side = RelayMatchSide.objects.get(match=match, team=team)
    if side.ability_tokens < 1:
        raise RelayWarsError('Your team has no ability tokens available.')
    if RelayAbility.objects.filter(target_pick=pick, kind=kind).exists():
        raise RelayWarsError('That game already has this ability assigned.')
    ability = RelayAbility.objects.create(
        match=match, team=team, proposed_by=user, target_pick=pick, kind=kind,
    )
    RelayAbilityVote.objects.create(ability=ability, user=user, approved=True)
    _try_resolve_vote(ability)
    return ability


@transaction.atomic
def cast_ability_vote(ability, user, approved):
    ability = RelayAbility.objects.select_for_update().select_related('target_pick__game').get(pk=ability.pk)
    if ability.status != RelayAbility.PENDING:
        raise RelayWarsError('Voting on this ability is closed.')
    if timezone.now() >= ability.target_pick.game.kickoff:
        ability.status = RelayAbility.EXPIRED
        ability.save(update_fields=['status'])
        raise RelayWarsError('The target game has kicked off; voting is closed.')
    if not ability.team.members.filter(user=user, is_active=True).exists():
        raise RelayWarsError('Only your teammates can vote on this ability.')
    RelayAbilityVote.objects.update_or_create(
        ability=ability, user=user, defaults={'approved': bool(approved)},
    )
    _try_resolve_vote(ability)
    return ability


def _try_resolve_vote(ability):
    active_ids = list(ability.team.members.filter(is_active=True).values_list('user_id', flat=True))
    members = len(active_ids)
    if not members:
        ability.status = RelayAbility.EXPIRED
        ability.save(update_fields=['status'])
        return
    required = members // 2 + 1
    active_votes = ability.votes.filter(user_id__in=active_ids)
    yes = active_votes.filter(approved=True).count()
    no = active_votes.filter(approved=False).count()
    if yes >= required:
        side = RelayMatchSide.objects.select_for_update().get(match=ability.match, team=ability.team)
        if side.ability_tokens < 1:
            ability.status = RelayAbility.EXPIRED
        else:
            side.ability_tokens -= 1
            side.save(update_fields=['ability_tokens'])
            ability.status = RelayAbility.ACTIVE
            ability.token_spent = True
        ability.save(update_fields=['status', 'token_spent'])
    elif no >= required or yes + (members - yes - no) < required:
        ability.status = RelayAbility.EXPIRED
        ability.save(update_fields=['status'])


@transaction.atomic
def refresh_match_scores(match):
    sides = {side.team_id: side for side in match.sides.select_for_update()}
    for ability in match.abilities.select_related('target_pick__game', 'team'):
        if ability.status == RelayAbility.PENDING and timezone.now() >= ability.target_pick.game.kickoff:
            ability.status = RelayAbility.EXPIRED
            ability.save(update_fields=['status'])
        if ability.status != RelayAbility.ACTIVE or not ability.target_pick.game.is_final:
            continue
        if ability.kind == RelayAbility.JINX and ability.target_pick.result != 'win' and not ability.reward_granted:
            side = sides[ability.team_id]
            side.ability_tokens += 1
            side.save(update_fields=['ability_tokens'])
            ability.reward_granted = True
            ability.status = RelayAbility.RESOLVED
            ability.resolved_at = timezone.now()
            ability.save(update_fields=['reward_granted', 'status', 'resolved_at'])
        elif ability.target_pick.game.is_final:
            ability.status = RelayAbility.RESOLVED
            ability.resolved_at = timezone.now()
            ability.save(update_fields=['status', 'resolved_at'])

    for team_id, side in sides.items():
        current = 0
        best = 0
        events = []
        own_picks = match.picks.filter(team_id=team_id).select_related('game')
        for pick in own_picks:
            if pick.game.is_final:
                events.append((pick.game.kickoff, 0, pick))
        successful_jinxes = match.abilities.filter(
            team_id=team_id, kind=RelayAbility.JINX,
            status=RelayAbility.RESOLVED, reward_granted=True,
        ).select_related('target_pick__game')
        for ability in successful_jinxes:
            events.append((ability.target_pick.game.kickoff, 1, ability))

        for _, event_type, item in sorted(events, key=lambda event: (event[0], event[1], event[2].pk)):
            if event_type == 1:
                # A successful Jinx is a bonus chain link for the attacking team.
                current += 1
            else:
                protected = item.abilities.filter(
                    kind=RelayAbility.PROTECT,
                    status__in=[RelayAbility.ACTIVE, RelayAbility.RESOLVED],
                ).exists()
                if item.result == 'win':
                    current += 1
                elif item.result == 'loss' and not protected:
                    current = 0
                # A tie is neither a win nor a loss, so it pauses the chain.
            best = max(best, current)
        side.current_chain = current
        side.best_chain = best
        side.save(update_fields=['current_chain', 'best_chain'])

    draft_closed = not match.draft_turns.filter(skipped=False).exclude(pick__isnull=False).exists()
    all_picks_final = all(pick.game.is_final for pick in match.picks.select_related('game'))
    if draft_closed and all_picks_final:
        match.status = RelayMatch.COMPLETE
    elif timezone.now() >= match.lock_at:
        match.status = RelayMatch.ACTIVE
    match.save(update_fields=['status'])
    return sides


@transaction.atomic
def leave_team(team, user):
    membership = RelayTeamMember.objects.select_for_update().filter(team=team, user=user, is_active=True).first()
    if not membership:
        raise RelayWarsError('You are not an active member of that team.')
    membership.is_active = False
    membership.save(update_fields=['is_active'])
    active_members = team.members.filter(is_active=True)
    if team.owner_id == user.pk:
        replacement = active_members.select_related('user').order_by('joined_at').first()
        if replacement:
            team.owner = replacement.user
            team.save(update_fields=['owner'])
    if not active_members.exists() and team.status != RelayTeam.MATCHED:
        team.delete()
        return team
    if team.status != RelayTeam.MATCHED and active_members.count() < TEAM_SIZE:
        team.status = RelayTeam.RECRUITING
        team.save(update_fields=['status'])
    for ability in team.relaywars_abilities.filter(status=RelayAbility.PENDING):
        _try_resolve_vote(ability)
    return team
