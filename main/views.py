# main/views.py
from django.conf import settings
from django.contrib.auth.decorators import login_required
import logging

from django.core.mail import EmailMessage


from accounts.models import Pick
from accounts.views import _selected_season
from accounts.standings import compute_standings
from api.models import Game
from api.rules import grade_pick
from api.services import current_week
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import render, redirect


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


def leaderboard(request):
    current = current_week()
    selected_season, seasons = _selected_season(request)

    selected_week = request.GET.get('week', 'season')

    if selected_week == 'season':
        user_stats = compute_standings(season=selected_season)
    else:
        try:
            selected_week = int(selected_week)
            if not 1 <= selected_week <= 18:
                selected_week = 'season'
        except (TypeError, ValueError):
            selected_week = 'season'

        if selected_week == 'season':
            user_stats = compute_standings(season=selected_season)
        else:
            user_stats = compute_standings(
                week=selected_week,
                season=selected_season,
            )

    return render(
        request,
        'main/leaderboard.html',
        {
            'user_stats': user_stats,
            'selected_week': selected_week,
            'current_week': current,
            'weeks': range(1, 19),
            'selected_season': selected_season,
            'seasons': seasons,
        }
    )



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
    return render(request, 'main/profile.html')


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
