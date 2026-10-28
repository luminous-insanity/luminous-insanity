# main/views.py
from django.conf import settings
from django.contrib.auth.decorators import login_required
import logging

from django.core.mail import EmailMessage


from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.urls import reverse

from accounts import challenges
from accounts import leaderboard as lb
from accounts.models import PerformanceReaction, FriendRequest, Pick, PlayerIdentity
from accounts.playermenu import menu_data, stats_summary
from accounts.ranking import format_pct
from accounts.team_identity import TEAM_CHOICES, TEAM_DATA, team_division
from accounts.views import _selected_season, get_kickoff_label
from accounts.standings import compute_standings, standing_for
from accounts.playoffs import division_playoff_race
from accounts.playoffs import championship_bracket
from accounts.models import SquaresBoard
from accounts.squares import board_grid
from api.models import Game
from api.rules import grade_pick
from api.services import current_week, MAX_WEEK
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render, redirect


def home(request):
    current = current_week()

    games = (
        Game.objects
        .filter(season=settings.NFL_SEASON, week=current)
        .order_by('game_date', 'kickoff', 'id')[:6]
    )

    standings = compute_standings()[:3]

    return render(request, 'main/home.html', {
        'featured_games': games,
        'current_week': current,
        'top_standings': standings,
    })


def _remembered_filter(request, tab):
    """All Players / Friends, remembered separately for each tab (in the session)."""
    key = f'lb_filter_{tab}'
    chosen = request.GET.get('filter')
    if chosen in lb.FILTERS:
        request.session[key] = chosen
        return chosen
    saved = request.session.get(key, lb.FILTER_ALL)
    return saved if saved in lb.FILTERS else lb.FILTER_ALL


def _week_from_request(request, season):
    """(week, all weeks with games). Falls back to the latest completed week."""
    weeks = lb.season_weeks(season) or [1]
    try:
        week = int(request.GET.get('week', ''))
    except (TypeError, ValueError):
        week = None
    if week not in weeks:
        week = lb.default_week(season)
        if week not in weeks:
            weeks = sorted(set(weeks) | {week})
    return week, weeks


def _pct_text(standing):
    return format_pct(standing.win_pct)


def leaderboard(request):
    selected_season, seasons = _selected_season(request)

    tab = request.GET.get('tab')
    if tab not in ('weekly', 'season'):
        # Old links used ?week=season for the season view and ?week=N for a week.
        tab = 'season' if request.GET.get('week') == 'season' else 'weekly'

    mode = _remembered_filter(request, tab)
    selected_week, weeks = _week_from_request(request, selected_season)
    weekly = tab == 'weekly'

    board = lb.build_board(
        tab=tab, season=selected_season,
        week=selected_week if weekly else None,
        mode=mode, viewer=request.user,
    )
    rows = board['rows']

    # What each row's player menu needs (extra stats live there, not in the list).
    menus = menu_data(
        [row.user for row in rows], request.user, selected_season,
        compare_week=selected_week if weekly else lb.default_week(selected_season),
        show_week=weekly,
    )
    for row in rows:
        row.menu = menus[row.user.id]
        row.is_me = row.menu['is_me']
        row.can_react = request.user.is_authenticated and row.user.id != request.user.id
        row.reaction_url = reverse('react_to_performance', args=[row.user.id])
        row.my_reaction = PerformanceReaction.objects.filter(
            reactor=request.user, player=row.user, season=selected_season,
            week=selected_week
        ).first() if row.can_react else None
        row.reaction_counts = {item['emoji']: item['total'] for item in PerformanceReaction.objects.filter(
            player=row.user, season=selected_season, week=selected_week
        ).values('emoji').annotate(total=Count('id'))}
        row.reaction_clap = row.reaction_counts.get('👏', 0)
        row.reaction_fire = row.reaction_counts.get('🔥', 0)
        row.reaction_crown = row.reaction_counts.get('👑', 0)

    def url(**params):
        base = {'tab': tab, 'season': selected_season}
        if weekly:
            base['week'] = selected_week
        base.update(params)
        return f"{reverse('leaderboard')}?{urlencode(base)}"

    index = weeks.index(selected_week)
    prev_week = weeks[index - 1] if index > 0 else None
    next_week = weeks[index + 1] if index < len(weeks) - 1 else None

    champion = lb.champion_payload(selected_season)
    auto_reveal = lb.should_auto_reveal(request.user, selected_season, champion)

    winners = board['winners']
    week_done = weekly and lb.week_is_complete(selected_season, selected_week)

    return render(
        request,
        'main/leaderboard.html',
        {
            'tab': tab,
            'filter_mode': mode,
            'user_stats': rows,
            'reaction_choices': PerformanceReaction.choices,
            'selected_week': selected_week,
            'weeks': weeks,
            'prev_week': prev_week,
            'next_week': next_week,
            'selected_season': selected_season,
            'seasons': seasons,
            'winners': winners,
            'winner_label': 'WINNER' if week_done else 'LEADER',
            'friends_empty': board['friends_empty'],
            'needs_login': board['needs_login'],
            'champion': champion,
            'auto_reveal': auto_reveal,
            'season_final': champion is not None,
            'weekly_url': url(tab='weekly', week=selected_week),
            'season_url': url(tab='season'),
            'prev_url': url(week=prev_week) if prev_week else '',
            'next_url': url(week=next_week) if next_week else '',
            'all_url': url(filter=lb.FILTER_ALL),
            'friends_url': url(filter=lb.FILTER_FRIENDS),
        }
    )


def player_profile(request, user_id):
    """A read-only public profile for another player."""
    player = get_object_or_404(User, pk=user_id, is_superuser=False)
    if request.user.is_authenticated and player.id == request.user.id:
        return redirect('profile')

    selected_season, _seasons = _selected_season(request)
    stats = stats_summary(player, selected_season)
    week = lb.default_week(selected_season)
    week_stats = standing_for(player, week=week, season=selected_season)
    qs = urlencode({'season': selected_season, 'week': week})

    versus = None
    if request.user.is_authenticated:
        won, lost, tied = challenges.record_between(request.user, player)
        versus = {'won': won, 'lost': lost, 'tied': tied,
                  'total': won + lost + tied}

    reaction_counts = {
        row['emoji']: row['total']
        for row in PerformanceReaction.objects.filter(
            player=player, season=selected_season, week=week
        ).values('emoji').annotate(total=Count('id'))
    }
    my_reaction = None
    can_react = False
    if request.user.is_authenticated and request.user.id != player.id:
        can_react = True
        my_reaction = PerformanceReaction.objects.filter(
            reactor=request.user, player=player,
            season=selected_season, week=week
        ).first()

    return render(request, 'main/player_profile.html', {
        'player': player,
        'selected_season': selected_season,
        'stats': stats,
        'stats_week': week,
        'week_stats': week_stats,
        'versus': versus,
        'compare_url': f"{reverse('compare_picks', args=[player.id])}?{qs}",
        'challenge_url': reverse('challenge_new', args=[player.id]),
        'reaction_counts': reaction_counts,
        'my_reaction': my_reaction,
        'can_react': can_react,
        'reaction_url': reverse('react_to_performance', args=[player.id]),
        'reaction_summary': [
            {'emoji': emoji, 'label': label, 'count': reaction_counts.get(emoji, 0)}
            for emoji, label in PerformanceReaction.choices
        ],
    })


def _reaction_return_url(request, player_id, season=None):
    referer = request.META.get('HTTP_REFERER', '')
    # Only redirect back to a local path; never trust an external Referer.
    from urllib.parse import urlsplit
    parsed = urlsplit(referer)
    if referer and not parsed.netloc and parsed.path.startswith('/') and not parsed.path.startswith('//'):
        return referer
    profile_url = reverse('player_profile', args=[player_id])
    return f'{profile_url}?season={season}' if season else profile_url


@login_required
@require_POST
def react_to_performance(request, user_id):
    player = get_object_or_404(User, pk=user_id, is_superuser=False)
    if player.id == request.user.id:
        messages.error(request, 'You cannot react to your own performance.')
        return redirect(_reaction_return_url(request, player.id))
    try:
        season = int(request.POST.get('season', settings.NFL_SEASON))
        week = int(request.POST.get('week', lb.default_week(settings.NFL_SEASON)))
    except (TypeError, ValueError):
        return redirect(_reaction_return_url(request, player.id))
    if not (1 <= week <= MAX_WEEK):
        return redirect(_reaction_return_url(request, player.id))
    emoji = request.POST.get('emoji')
    valid_emojis = dict(PerformanceReaction.choices)
    if emoji not in valid_emojis:
        messages.error(request, 'Choose a valid reaction.')
        return redirect(_reaction_return_url(request, player.id))
    existing = PerformanceReaction.objects.filter(
        reactor=request.user, player=player, season=season, week=week
    ).first()
    if existing and existing.emoji == emoji:
        existing.delete()
        messages.success(request, 'Reaction removed.')
    else:
        PerformanceReaction.objects.update_or_create(
            reactor=request.user, player=player, season=season, week=week,
            defaults={'emoji': emoji},
        )
        messages.success(request, 'Reaction saved.')
    return redirect(_reaction_return_url(request, player.id, season))


@login_required
def compare_picks(request, user_id):
    """Your picks next to another player's, for one week."""
    other = get_object_or_404(User, pk=user_id, is_superuser=False)
    selected_season, _seasons = _selected_season(request)
    selected_week, weeks = _week_from_request(request, selected_season)

    if other.id == request.user.id:
        qs = urlencode({'season': selected_season, 'week': selected_week})
        return redirect(f"{reverse('picks')}?{qs}")

    comparison = lb.build_comparison(
        request.user, other, selected_season, selected_week)

    index = weeks.index(selected_week)

    def week_url(week):
        qs = urlencode({'season': selected_season, 'week': week})
        return f"{reverse('compare_picks', args=[other.id])}?{qs}"

    for row in comparison['rows']:
        row['kickoff_label'] = get_kickoff_label(row['game'])

    return render(request, 'main/compare_picks.html', {
        'other': other,
        'selected_season': selected_season,
        'selected_week': selected_week,
        'weeks': weeks,
        'prev_url': week_url(weeks[index - 1]) if index > 0 else '',
        'next_url': week_url(weeks[index + 1]) if index < len(weeks) - 1 else '',
        'back_url': (f"{reverse('leaderboard')}?"
                     f"{urlencode({'tab': 'weekly', 'season': selected_season, 'week': selected_week})}"),
        'my_season_pct': _pct_text(comparison['my_season']),
        'their_season_pct': _pct_text(comparison['their_season']),
        **comparison,
    })


@login_required
def history_view(request):
    games = (Game.objects.filter(season=settings.NFL_SEASON)
             .order_by('game_date', 'kickoff', 'id'))
    user_picks = {
        pick['game__game_id']: pick['team_picked']
        for pick in Pick.objects.filter(user=request.user).values('game__game_id', 'team_picked')
    }

    outcome_labels = {'win': 'Win', 'loss': 'Loss', 'tie': 'Draw'}
    game_data = []
    for game in games:
        user_pick = user_picks.get(game.game_id, 'Not Picked')
        if user_pick == 'Not Picked':
            result = 'Not Picked'
        elif not game.is_final:
            result = 'Pending'
        else:
            outcome = grade_pick(user_pick, game.home_score, game.away_score)
            result = outcome_labels.get(outcome, 'Pending')
        game_data.append({'game': game, 'user_pick': user_pick, 'result': result})

    return render(request, 'main/history.html', {'game_data': game_data})


@login_required
def profile(request):
    season = settings.NFL_SEASON
    identity, _ = PlayerIdentity.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        favorite_team = request.POST.get('favorite_team', '').strip().upper()
        valid_teams = set(TEAM_DATA)
        if favorite_team and favorite_team not in valid_teams:
            messages.error(request, 'Please choose a valid NFL team.')
        else:
            # A division is assigned on first selection and remains locked for
            # this season. At a new season boundary it follows the current team.
            new_season = identity.division_season != season
            identity.favorite_team = favorite_team
            if favorite_team and (new_season or not identity.division):
                identity.division = team_division(favorite_team)
                identity.division_season = season
            elif not favorite_team and new_season:
                identity.division = ''
                identity.division_season = None
            identity.save()
            messages.success(request, 'Your favorite team has been updated.')
            return redirect('profile')
    elif identity.division_season != season:
        # Refresh the division at the start of a new configured NFL season.
        if identity.favorite_team:
            identity.division = team_division(identity.favorite_team)
            identity.division_season = season
        else:
            identity.division = ''
            identity.division_season = None
        identity.save(update_fields=['division', 'division_season', 'updated_at'])

    return render(request, 'main/profile.html', {
        'stats': stats_summary(request.user, season),
        'stats_season': season,
        'player_identity': identity,
        'team_choices': TEAM_CHOICES,
        'favorite_team_details': TEAM_DATA.get(identity.favorite_team),
    })



DIVISION_CHOICES = (
    'AFC East', 'AFC North', 'AFC South', 'AFC West',
    'NFC East', 'NFC North', 'NFC South', 'NFC West',
)

def division_leaderboard(request):
    """Show the current-season race for one NFL division.

    Division membership comes from each player's season-locked PlayerIdentity;
    records are always computed from existing picks and final scores. This is
    deliberately a standings view, not playoff qualification/elimination logic.
    """
    season = settings.NFL_SEASON
    identity = None
    if request.user.is_authenticated:
        identity = PlayerIdentity.objects.filter(user=request.user).first()
        # Keep the seasonal snapshot in step with the existing profile behavior.
        if identity and identity.division_season != season:
            if identity.favorite_team:
                identity.division = team_division(identity.favorite_team)
                identity.division_season = season
            else:
                identity.division = ''
                identity.division_season = None
            identity.save(update_fields=['division', 'division_season', 'updated_at'])

    division = request.GET.get('division', '').strip()
    if division not in DIVISION_CHOICES:
        division = identity.division if identity and identity.division in DIVISION_CHOICES else 'AFC East'

    tab = request.GET.get('tab', 'season')
    if tab not in ('season', 'weekly'):
        tab = 'season'
    weeks = lb.season_weeks(season)
    try:
        selected_week = int(request.GET.get('week', ''))
    except (TypeError, ValueError):
        selected_week = lb.default_week(season)
    if selected_week not in weeks:
        selected_week = lb.default_week(season)
    if not weeks:
        weeks = [1]

    member_ids = PlayerIdentity.objects.filter(
        division=division, division_season=season, user__is_superuser=False
    ).values_list('user_id', flat=True)
    members = list(User.objects.filter(id__in=member_ids).order_by('username'))
    if tab == 'weekly':
        standings = compute_standings(
            season=season, week=selected_week, users=members, with_pending=True
        )
        playoff_race = None
    else:
        playoff_race = division_playoff_race(division, season)
        standings = playoff_race['standings']
    my_row = next((row for row in standings if request.user.is_authenticated and row.user.id == request.user.id), None)

    return render(request, 'main/divisions.html', {
        'division_choices': DIVISION_CHOICES,
        'selected_division': division,
        'selected_season': season,
        'tab': tab,
        'weeks': weeks,
        'selected_week': selected_week,
        'standings': standings,
        'playoff_race': playoff_race,
        'member_count': len(members),
        'my_row': my_row,
        'my_division': identity.division if identity and identity.division_season == season else '',
        'season_url': f'?division={division.replace(" ", "+")}&tab=season',
        'weekly_url': f'?division={division.replace(" ", "+")}&tab=weekly&week={selected_week}',
    })

def playoffs_view(request):
    """Championship field and first-round bracket preview."""
    season = settings.NFL_SEASON
    bracket = championship_bracket(season=season, field_size=50)
    my_entry = next((p for p in bracket['field']
                     if request.user.is_authenticated and p['user'].id == request.user.id), None)
    return render(request, 'main/playoffs.html', {
        'bracket': bracket,
        'my_entry': my_entry,
        'page': 'playoffs',
    })


def squares_view(request):
    """Super Bowl squares board for the configured season."""
    season = settings.NFL_SEASON
    board = SquaresBoard.objects.filter(season=season).select_related('game').first()
    context = {'page': 'squares', 'season': season, 'board': board}
    if board:
        context.update(board_grid(board, request.user))
    return render(request, 'main/squares.html', context)


def about(request):
    return render(request, 'main/about.html')


def contact(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()

        if not all([name, email, subject, message]):
            messages.error(request, 'Please complete all fields.')
            return render(request, 'main/contact.html', {'form_data': request.POST})

        if len(name) > 100 or len(email) > 254 or len(subject) > 150 or len(message) > 5000:
            messages.error(request, 'One or more fields exceed the allowed length.')
            return render(request, 'main/contact.html', {'form_data': request.POST})

        email_subject = f'GameDayPicks Contact: {subject}'
        email_body = (
            f'From: {name}\n'
            f'Reply email: {email}\n\n'
            f'Message:\n{message}'
        )

        try:

            email_message = EmailMessage(
                subject=email_subject,
                body=email_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.CONTACT_EMAIL],
                reply_to=[email],
            )
            email_message.send(fail_silently=False)

        except Exception:

            logging.exception("Contact form email failed")

            messages.error(
                request,
                'Sorry, your message could not be sent. Please try again later.'
            )
        else:
            messages.success(
                request,
                'Your message has been sent successfully!'
            )
            return redirect('contact')

    return render(request, 'main/contact.html')


def privacy(request):
    return render(request, 'main/privacy.html')


def terms(request):
    return render(request, 'main/terms.html')
