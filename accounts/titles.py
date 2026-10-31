"""Unlockable titles derived from achievement levels.

Titles are cosmetic. Equip one on your profile (PlayerIdentity.active_title).
"""
from .models import AchievementUnlock, PlayerIdentity

TITLE_LADDER = [
    ('gameday_lombardi', 1, 'Lombardi'),
    ('super_bowl_bound', 1, 'Super Bowl Bound'),
    ('super_bowl_bound', 3, 'Perennial Contender'),
    ('division_crown', 1, 'Division Champ'),
    ('division_crown', 3, 'Division Dynasty'),
    ('perfect_drive', 1, 'Perfect Drive'),
    ('perfect_drive', 3, 'Flawless'),
    ('red_zone_streak', 1, 'On Fire'),
    ('red_zone_streak', 2, 'Unstoppable'),
    ('red_zone_streak', 3, 'Untouchable'),
    ('division_dominator', 1, 'Division Weekly'),
    ('division_dominator', 3, 'Division Bully'),
    ('january_football', 1, 'Playoff Heater'),
    ('rivalry_king', 1, 'Rivalry Starter'),
    ('rivalry_king', 3, 'Rivalry King'),
    ('play_caller', 3, 'Play Caller'),
    ('play_caller', 5, 'Offensive Coordinator'),
    ('play_caller', 7, 'Head Coach'),
    ('iron_man', 2, 'Iron Man'),
    ('iron_man', 3, 'Every Sunday'),
    ('franchise_player', 2, 'Franchise Player'),
    ('true_fan', 1, 'True Fan'),
    ('clinched', 1, 'Clinched'),
    ('wild_card_weekend', 1, 'Wild Card'),
    ('never_missed_a_snap', 1, 'Every Snap'),
    ('riding_with_the_team', 2, 'Ride or Die'),
    ('upset_special', 2, 'Upset Artist'),
    ('locksmith', 2, 'Locksmith'),
    ('gridiron_guru', 1, 'Gridiron Guru'),
    ('film_room', 2, 'Film Room'),
]


def available_titles(user):
    level_map = {}
    for u in AchievementUnlock.objects.filter(user=user):
        level_map[u.achievement_key] = max(level_map.get(u.achievement_key, 0), u.level)

    titles = []
    seen = set()
    for key, level, label in TITLE_LADDER:
        if level_map.get(key, 0) >= level and label not in seen:
            titles.append(label)
            seen.add(label)
    return titles


def equip_title(user, title):
    identity, _ = PlayerIdentity.objects.get_or_create(user=user)
    if title and title not in available_titles(user):
        return False
    identity.active_title = title or ''
    identity.save(update_fields=['active_title'])
    return True


def display_title(user):
    identity = PlayerIdentity.objects.filter(user=user).first()
    if identity and identity.active_title:
        return identity.active_title
    return ''
