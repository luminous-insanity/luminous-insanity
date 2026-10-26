"""Pages for head-to-head challenges."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from api.models import Game

from . import challenges as ch
from .leaderboard import build_comparison
from .models import Challenge
from .views import get_kickoff_label


def _title(c):
    if c.scope == Challenge.GAME:
        return f"{c.game.away_team} at {c.game.home_team}"
    return f"Week {c.week}"


def _subtitle(c):
    if c.scope == Challenge.GAME:
        return f"Week {c.week} · single game"
    return "Whole week"


STATE_LABELS = {
    "pending": "Waiting for a reply",
    "open": "In progress",
    "final": "Finished",
    "declined": "Declined",
    "cancelled": "Cancelled",
    "expired": "Expired",
}


def _row(c, result, me):
    i_sent = c.challenger_id == me.id
    other = c.opponent if i_sent else c.challenger
    outcome = result.outcome_for(c, me.id)
    return {
        "challenge": c,
        "result": result,
        "other": other,
        "i_sent": i_sent,
        "title": _title(c),
        "subtitle": _subtitle(c),
        "state_label": STATE_LABELS[result.state],
        "outcome": outcome,
        "outcome_label": {"won": "You won", "lost": "You lost", "tied": "Tied"}.get(outcome, ""),
        "my_score": result.challenger_score if i_sent else result.opponent_score,
        "their_score": result.opponent_score if i_sent else result.challenger_score,
        "can_accept": (not i_sent) and result.state == "pending",
        "can_cancel": i_sent and result.state == "pending",
        "detail_url": reverse("challenge_detail", args=[c.id]),
    }


@login_required
def challenges(request):
    me = request.user
    mine = list(
        Challenge.objects.filter(Q(challenger=me) | Q(opponent=me))
        .select_related("challenger", "opponent", "game"))
    results = ch.evaluate_many(mine)
    rows = [_row(c, results[c.id], me) for c in mine]

    incoming = [r for r in rows if r["can_accept"]]
    outgoing = [r for r in rows if r["can_cancel"]]
    active = [r for r in rows if r["result"].state == "open"]
    finished = [r for r in rows if r["result"].state == "final"]
    past = [r for r in rows if r["result"].state in ("declined", "cancelled", "expired")]

    won, lost, tied = ch.records([me.id]).get(me.id, [0, 0, 0])
    return render(request, "accounts/challenges.html", {
        "incoming": incoming,
        "outgoing": outgoing,
        "active": active,
        "finished": finished,
        "past": past,
        "record": f"{won}–{lost}–{tied}",
        "won": won,
        "battles": won + lost + tied,
        "nothing_yet": not rows,
    })


@login_required
def challenge_new(request, user_id):
    opponent = get_object_or_404(User, pk=user_id, is_superuser=False)
    if opponent.id == request.user.id:
        messages.error(request, "You can't challenge yourself.")
        return redirect("challenges")

    season = settings.NFL_SEASON
    error = ""
    chosen = {"scope": Challenge.WEEK, "week": "", "game": ""}

    if request.method == "POST":
        scope = request.POST.get("scope", "")
        chosen.update(scope=scope, week=request.POST.get("week", ""),
                      game=request.POST.get("game", ""))
        try:
            if scope == Challenge.GAME:
                game = Game.objects.filter(pk=request.POST.get("game") or 0).first()
                created = ch.create_challenge(
                    request.user, opponent, scope, game=game)
            else:
                try:
                    week = int(request.POST.get("week", ""))
                except ValueError:
                    week = None
                created = ch.create_challenge(
                    request.user, opponent, scope, week=week)
        except ch.ChallengeError as problem:
            error = str(problem)
        else:
            messages.success(
                request, f"Challenge sent to {opponent.username}!")
            return redirect("challenges")

    games = ch.open_games(season)
    for game in games:
        game.kickoff_label = get_kickoff_label(game)

    return render(request, "accounts/challenge_new.html", {
        "opponent": opponent,
        "open_weeks": ch.open_weeks(season),
        "open_games": games,
        "season": season,
        "error": error,
        "chosen": chosen,
    })


@login_required
@require_POST
def challenge_respond(request, challenge_id, action):
    c = get_object_or_404(Challenge, pk=challenge_id)
    me = request.user
    state = ch.evaluate_many([c])[c.id].state

    if action in ("accept", "decline"):
        if c.opponent_id != me.id:
            messages.error(request, "Only the player who was challenged can reply.")
        elif c.status != Challenge.PENDING:
            messages.error(request, "That challenge has already been answered.")
        elif state == "expired":
            messages.error(request, "That challenge has expired. The game or week is already underway.")
        else:
            c.status = Challenge.ACCEPTED if action == "accept" else Challenge.DECLINED
            c.responded_at = timezone.now()
            c.save()
            if action == "accept":
                messages.success(request, f"Challenge accepted. Game on against {c.challenger.username}!")
            else:
                messages.success(request, "Challenge declined.")
    elif action == "cancel":
        if c.challenger_id != me.id or c.status != Challenge.PENDING:
            messages.error(request, "That challenge can't be cancelled.")
        else:
            c.status = Challenge.CANCELLED
            c.responded_at = timezone.now()
            c.save()
            messages.success(request, "Challenge cancelled.")
    else:
        messages.error(request, "Unknown action.")

    return redirect("challenges")


@login_required
def challenge_detail(request, challenge_id):
    c = get_object_or_404(
        Challenge.objects.select_related("challenger", "opponent", "game"),
        pk=challenge_id)
    me = request.user
    if me.id not in (c.challenger_id, c.opponent_id):
        # Not your challenge: don't even confirm it exists.
        return redirect("challenges")

    result = ch.evaluate_many([c])[c.id]
    row = _row(c, result, me)
    other = row["other"]

    comparison = build_comparison(me, other, c.season, c.week)
    games = comparison["rows"]
    if c.scope == Challenge.GAME:
        games = [g for g in games if g["game"].pk == c.game_id]
    for g in games:
        g["kickoff_label"] = get_kickoff_label(g["game"])

    return render(request, "accounts/challenge_detail.html", {
        **row,
        "me": me,
        "games": games,
        "my_week": comparison["my_week"],
        "their_week": comparison["their_week"],
        "winner": (c.challenger if result.winner_id == c.challenger_id
                   else c.opponent) if result.winner_id else None,
        "i_am_winner": result.winner_id == me.id,
    })
