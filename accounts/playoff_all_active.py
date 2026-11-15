"""Small-league rule: when 50 or fewer players are active, every active
player qualifies for the playoffs.

This sits ON TOP of accounts/playoff_qualification.py and never edits it. The
capacity algorithm there still decides the field for leagues larger than the
threshold. Set PLAYOFF_ALL_ACTIVE_MAX = 0 in settings (or .env) to switch this
rule off and return to the unmodified algorithm.

No Django in here on purpose, so it can be tested on its own.

With the whole active field qualified, the weekly cuts do nothing:
cut_targets(start <= 50, 50) keeps everyone, and all of them are dealt squares.
"""
from .playoff_qualification import qualification_key

ROUTE_LABEL = 'Active player'


def apply_all_active_rule(result, players, threshold, sealed_draws=None):
    """Return `result`, replaced by "all active players" when N <= threshold.

    `players` are the PlayerRecord objects that were passed to qualify_players
    (it sets `.active` on them). `result` is the QualificationResult it returned.
    Leagues above the threshold are returned untouched.
    """
    if not threshold or threshold < 1:
        return result
    active = [p for p in players if p.active]
    if not active or len(active) > threshold:
        return result

    draws = sealed_draws or {}
    ordered = sorted(active, key=lambda p: qualification_key(p) + (-draws.get(p.user_id, 0),))
    for seed, player in enumerate(ordered, start=1):
        player.qualification_route = ROUTE_LABEL
        player.seed = seed
    result.qualified = ordered
    result.E = len(ordered)
    result.N = len(ordered)
    result.lapsed = 0
    result.rolled_down = 0
    return result
