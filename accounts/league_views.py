"""Pages for private leagues. Rules live in leagues.py."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import leagues
from .leaderboard import default_week, season_weeks
from .models import League, LeagueMembership
from .ratelimit import ratelimit
from .views import _selected_season, _selected_week


def _member_league_or_404(request, league_id):
    league = get_object_or_404(League, pk=league_id)
    if not leagues.is_member(league, request.user):
        # Not a member: pretend it doesn't exist rather than confirm it does.
        from django.http import Http404
        raise Http404('No such league.')
    return league


@login_required
def leagues_home(request):
    return render(request, 'accounts/leagues.html', {
        'leagues': leagues.my_leagues(request.user),
        'max_owned': leagues.max_owned(),
        'max_members': leagues.max_members(),
        'join_code': request.GET.get('code', ''),
    })


@login_required
@require_POST
@ratelimit('league_create', limit=10, window=3600, key='user', fallback='leagues')
def league_create(request):
    try:
        league = leagues.create_league(request.user, request.POST.get('name', ''))
    except leagues.LeagueError as exc:
        messages.error(request, exc.message)
        return redirect('leagues')
    messages.success(request, f'{league.name} created. Share the invite code to bring friends in.')
    return redirect('league_detail', league_id=league.pk)


@login_required
@require_POST
@ratelimit('league_join', limit=20, window=600, key='user', fallback='leagues')
def league_join(request):
    try:
        league = leagues.join_by_code(request.user, request.POST.get('code', ''))
    except leagues.LeagueError as exc:
        messages.error(request, exc.message)
        return redirect('leagues')
    messages.success(request, f'Welcome to {league.name}!')
    return redirect('league_detail', league_id=league.pk)


@login_required
@ratelimit('league_join', limit=20, window=600, key='user', fallback='leagues')
def league_join_link(request, code):
    """Invite link: shows what you're joining, then a Join button."""
    normalized = leagues.normalize_code(code)
    league = League.objects.filter(invite_code=normalized, is_open=True).select_related('owner').first()
    if league is None:
        messages.error(request, "That invite link didn't work. Ask the league owner for a new one.")
        return redirect('leagues')
    if leagues.is_member(league, request.user):
        return redirect('league_detail', league_id=league.pk)
    if request.method == 'POST':
        try:
            leagues.join_by_code(request.user, normalized)
        except leagues.LeagueError as exc:
            messages.error(request, exc.message)
            return redirect('leagues')
        messages.success(request, f'Welcome to {league.name}!')
        return redirect('league_detail', league_id=league.pk)
    return render(request, 'accounts/league_join.html', {
        'league': league, 'members': leagues.member_count(league), 'code': normalized})


@login_required
def league_detail(request, league_id):
    league = _member_league_or_404(request, league_id)
    season, seasons = _selected_season(request)
    tab = 'weekly' if request.GET.get('tab') == 'weekly' else 'season'
    weeks = season_weeks(season) or [1]
    week = _selected_week(request, default_week(season))
    if week not in weeks:
        fallback = default_week(season)
        week = fallback if fallback in weeks else weeks[-1]
    rows = leagues.league_board(league, tab, season, week)
    is_owner = league.owner_id == request.user.id
    for row in rows:
        row.is_me = row.user.id == request.user.id
        row.is_owner = row.user.id == league.owner_id
    memberships = list(
        LeagueMembership.objects.filter(league=league).select_related('user').order_by('joined_at', 'id'))
    return render(request, 'accounts/league_detail.html', {
        'league': league,
        'is_owner': is_owner,
        'rows': rows,
        'tab': tab,
        'selected_season': season,
        'seasons': seasons,
        'weeks': weeks,
        'selected_week': week,
        'memberships': memberships,
        'invite_url': request.build_absolute_uri(
            reverse('league_join_link', args=[league.invite_code])),
        'max_members': leagues.max_members(),
    })


@login_required
@require_POST
@ratelimit('league_manage', limit=60, window=600, key='user', fallback='leagues')
def league_manage(request, league_id):
    """Owner tools and Leave, chosen by the `action` field."""
    league = _member_league_or_404(request, league_id)
    action = request.POST.get('action', '')
    back = redirect('league_detail', league_id=league.pk)
    try:
        if action == 'leave':
            leagues.leave_league(request.user, league)
            messages.success(request, f'You left {league.name}.')
            return redirect('leagues')
        if action == 'rename':
            leagues.rename(request.user, league, request.POST.get('name', ''))
            messages.success(request, 'League renamed.')
        elif action == 'toggle_open':
            leagues.set_open(request.user, league, not league.is_open)
            messages.success(request, 'Joining is now open.' if league.is_open else 'Joining is now closed.')
        elif action == 'new_code':
            leagues.regenerate_code(request.user, league)
            messages.success(request, 'New invite code created. The old one no longer works.')
        elif action == 'remove':
            leagues.remove_member(request.user, league, request.POST.get('user_id', 0))
            messages.success(request, 'Player removed.')
        elif action == 'transfer':
            target = leagues.transfer_ownership(request.user, league, request.POST.get('username', ''))
            messages.success(request, f'{target.username} now owns {league.name}.')
        elif action == 'delete':
            if request.POST.get('confirm', '').strip().lower() != league.name.lower():
                messages.error(request, 'Type the league name exactly to delete it.')
                return back
            leagues.delete_league(request.user, league)
            messages.success(request, 'League deleted.')
            return redirect('leagues')
        else:
            messages.error(request, 'Unknown action.')
    except (leagues.LeagueError, ValueError) as exc:
        messages.error(request, getattr(exc, 'message', 'Something went wrong.'))
    return back
