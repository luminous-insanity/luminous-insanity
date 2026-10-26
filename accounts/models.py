# picks/models.py
from django.db import models
from django.contrib.auth.models import User
from api.models import Game


class Pick(models.Model):
    HOME = 'home'
    AWAY = 'away'

    TEAM_CHOICES = [
        (HOME, 'Home Team'),
        (AWAY, 'Away Team'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    team_picked = models.CharField(
        max_length=10,
        choices=TEAM_CHOICES,
        default=HOME,
    )

    class Meta:
        unique_together = ('user', 'game')


class UserStatistics(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    ties = models.IntegerField(default=0)


class FriendRequest(models.Model):
    PENDING = 'pending'
    ACCEPTED = 'accepted'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (ACCEPTED, 'Accepted'),
    ]

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_friend_requests',
    )
    receiver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_friend_requests',
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['sender', 'receiver'],
                name='unique_friend_request_pair',
            ),
            models.CheckConstraint(
                check=~models.Q(sender=models.F('receiver')),
                name='prevent_self_friend_request',
            ),
        ]

    def __str__(self):
        return f'{self.sender} → {self.receiver} ({self.status})'


class UserActivity(models.Model):
    """When a player last did something meaningful (logged in, made a pick,
    interacted with friends). Used only to hide long-gone accounts from the
    *current* leaderboard. Nothing historical is ever deleted."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='activity',
    )
    last_active = models.DateTimeField()

    def __str__(self):
        return f'{self.user} last active {self.last_active:%Y-%m-%d}'


class ChampionRevealSeen(models.Model):
    """Remembers that a player has already seen a season's champion reveal,
    so it only pops up once per player per season."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    season = models.IntegerField()
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'season'],
                name='unique_champion_reveal_per_user_season',
            ),
        ]

    def __str__(self):
        return f'{self.user} saw the {self.season} champion reveal'


class Challenge(models.Model):
    """A head-to-head battle between two players: one game, or a whole week.

    Nothing about the RESULT is stored. Like the leaderboard, the winner is
    always worked out from the two players' picks and the final scores
    (see accounts/challenges.py), so it can never disagree with the standings.
    """
    GAME = 'game'
    WEEK = 'week'
    SCOPE_CHOICES = [(GAME, 'Single game'), (WEEK, 'Whole week')]

    PENDING = 'pending'
    ACCEPTED = 'accepted'
    DECLINED = 'declined'
    CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (ACCEPTED, 'Accepted'),
        (DECLINED, 'Declined'),
        (CANCELLED, 'Cancelled'),
    ]

    challenger = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='challenges_sent')
    opponent = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='challenges_received')
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES)
    season = models.IntegerField()
    week = models.IntegerField()
    game = models.ForeignKey(
        Game, null=True, blank=True, on_delete=models.CASCADE,
        related_name='challenges')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=~models.Q(challenger=models.F('opponent')),
                name='prevent_self_challenge',
            ),
        ]

    def __str__(self):
        target = self.game if self.scope == self.GAME else f'Week {self.week}'
        return f'{self.challenger} vs {self.opponent}: {target} ({self.status})'


class AchievementUnlock(models.Model):
    """A milestone a player has earned. Unlocks remain recorded if scores change later."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='achievement_unlocks')
    achievement_key = models.CharField(max_length=40)
    level = models.PositiveIntegerField(default=1)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-unlocked_at', 'achievement_key', 'level']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'achievement_key', 'level'],
                name='unique_user_achievement_level',
            ),
        ]

    def __str__(self):
        return f'{self.user}: {self.achievement_key} level {self.level}'


class PerformanceReaction(models.Model):
    """A lightweight emoji reaction to a friend's weekly performance."""
    CLAP = '👏'
    FIRE = '🔥'
    CROWN = '👑'
    choices = [(CLAP, 'Clap'), (FIRE, 'Fire'), (CROWN, 'Crown')]

    reactor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='performance_reactions_sent')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='performance_reactions_received')
    season = models.PositiveIntegerField()
    week = models.PositiveSmallIntegerField()
    emoji = models.CharField(max_length=8, choices=choices)
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['reactor', 'player', 'season', 'week'], name='unique_weekly_performance_reaction'),
            models.CheckConstraint(check=~models.Q(reactor=models.F('player')), name='prevent_self_performance_reaction'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reactor} reacted {self.emoji} to {self.player} (S{self.season} W{self.week})'
