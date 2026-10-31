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

    # Optional confidence: 1 = lean, 2 = solid, 3 = lock.
    # Does not change W-L-T; powers Confidence Points and underdog glory.
    CONFIDENCE_LEAN = 1
    CONFIDENCE_SOLID = 2
    CONFIDENCE_LOCK = 3
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_LEAN, 'Lean'),
        (CONFIDENCE_SOLID, 'Solid'),
        (CONFIDENCE_LOCK, 'Lock'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    team_picked = models.CharField(
        max_length=10,
        choices=TEAM_CHOICES,
        default=HOME,
    )
    confidence = models.PositiveSmallIntegerField(
        choices=CONFIDENCE_CHOICES,
        null=True,
        blank=True,
        help_text='Optional. Higher confidence on correct picks earns Confidence Points.',
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
    receiver_seen = models.BooleanField(default=False)

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
    is_read = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['reactor', 'player', 'season', 'week'], name='unique_weekly_performance_reaction'),
            models.CheckConstraint(check=~models.Q(reactor=models.F('player')), name='prevent_self_performance_reaction'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reactor} reacted {self.emoji} to {self.player} (S{self.season} W{self.week})'




class GameReaction(models.Model):
    """Live / post-game emoji reaction to a specific NFL game.

    Distinct from PerformanceReaction (which is about a friend's weekly record).
    These fuel the in-game energy feed while games are live or just finished.
    """
    FIRE = '🔥'
    SHOCK = '😱'
    CLUTCH = '💪'
    HEARTBREAK = '💔'
    PARTY = '🎉'
    choices = [
        (FIRE, 'Fire'),
        (SHOCK, 'Shock'),
        (CLUTCH, 'Clutch'),
        (HEARTBREAK, 'Heartbreak'),
        (PARTY, 'Party'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='game_reactions')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='reactions')
    emoji = models.CharField(max_length=8, choices=choices)
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'game'],
                name='unique_user_game_reaction',
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.emoji} on {self.game_id}'


class PlayerIdentity(models.Model):
    """Player-controlled favorite team plus the division locked for a season.

    Favorite team can change at any time. Division membership is snapshotted for
    the configured NFL season and refreshed from the current favorite team when
    a new season is first visited/selected.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='player_identity'
    )
    favorite_team = models.CharField(max_length=3, blank=True, default='')
    active_title = models.CharField(
        max_length=40, blank=True, default='',
        help_text='Unlockable title shown on profile and leaderboard.',
    )
    division = models.CharField(max_length=12, blank=True, default='')
    division_season = models.PositiveSmallIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'player identities'

    def __str__(self):
        return f'{self.user} identity'


class PlayoffSettings(models.Model):
    """Per-season playoff format; editable by site staff in Django admin."""
    season = models.PositiveSmallIntegerField(unique=True)
    qualifiers_per_division = models.PositiveSmallIntegerField(default=4)
    head_to_head_wildcard_spots = models.PositiveSmallIntegerField(default=2)
    # 0 = use the fixed number above; 1-100 = that share of each division
    # (rounded, at least one player per division).
    qualifier_percent = models.PositiveSmallIntegerField(default=0)
    # The Super Bowl field the weekly cuts step down to.
    field_target = models.PositiveSmallIntegerField(default=50)
    # Game.week of the Wild Card round. Divisional, Conference and the Super
    # Bowl follow in the next three weeks.
    first_playoff_week = models.PositiveSmallIntegerField(default=19)
    # How many weekly cuts have been applied (0-3). Managed by the cut command.
    rounds_cut = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'playoff settings'
        verbose_name_plural = 'playoff settings'

    def __str__(self):
        return f'{self.season} playoff format ({self.qualifiers_per_division} automatic per division)' 

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.qualifiers_per_division < 1:
            raise ValidationError({'qualifiers_per_division': 'At least one player must qualify automatically per division.'})
        if self.head_to_head_wildcard_spots < 0:
            raise ValidationError({'head_to_head_wildcard_spots': 'Wildcard spots cannot be negative.'})
        if self.qualifier_percent > 100:
            raise ValidationError({'qualifier_percent': 'Use 0 (fixed number) or a percentage from 1 to 100.'})
        if self.field_target < 2:
            raise ValidationError({'field_target': 'The Super Bowl field needs at least 2 players.'})
        if self.first_playoff_week < 1:
            raise ValidationError({'first_playoff_week': 'Enter the week number of the Wild Card round.'})


class PlayoffEntry(models.Model):
    """One player's place in a season's playoff field.

    Created once, when the field is opened. Playoff records are NOT stored:
    like the leaderboard they are worked out from picks and final scores
    (see accounts/playoff_rounds.py). Only the facts needed for tiebreaks are
    frozen here, so a late score fix can't quietly reshuffle who got in.
    """
    ACTIVE = 'active'
    ELIMINATED = 'eliminated'
    STATUS_CHOICES = [(ACTIVE, 'Active'), (ELIMINATED, 'Eliminated')]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='playoff_entries')
    season = models.PositiveSmallIntegerField(db_index=True)
    route = models.CharField(max_length=80, blank=True, default='')
    division = models.CharField(max_length=12, blank=True, default='')
    regular_win_pct = models.FloatField(default=0)
    head_to_head_wins = models.PositiveSmallIntegerField(default=0)
    # Stored once so the final tiebreak is fixed and can't be re-rolled.
    tiebreak_draw = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=ACTIVE)
    eliminated_round = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'playoff entries'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'season'], name='unique_playoff_entry_per_season'),
        ]

    def __str__(self):
        return f'{self.user} in the {self.season} playoffs ({self.status})'


class SquaresBoard(models.Model):
    """The Super Bowl squares board for one season.

    Columns (top) belong to the AWAY team, rows (side) to the HOME team.
    `away_digits[3]` is the digit printed above column 3; `home_digits[7]` is
    the digit beside row 7. Both are drawn once, after the squares are dealt.
    """
    season = models.PositiveSmallIntegerField(unique=True)
    game = models.ForeignKey(
        Game, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='squares_boards')
    home_digits = models.CharField(max_length=10, blank=True, default='')
    away_digits = models.CharField(max_length=10, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'squares boards'

    def __str__(self):
        return f'{self.season} Super Bowl squares'


class BoardSquare(models.Model):
    board = models.ForeignKey(SquaresBoard, on_delete=models.CASCADE, related_name='squares')
    row = models.PositiveSmallIntegerField()
    col = models.PositiveSmallIntegerField()
    owner = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='board_squares')

    class Meta:
        ordering = ['row', 'col']
        constraints = [
            models.UniqueConstraint(fields=['board', 'row', 'col'], name='unique_square_per_board'),
        ]

    def __str__(self):
        return f'Square (row {self.row}, col {self.col}): {self.owner or "open"}'


class Crossfire(models.Model):
    """A directed bet that another player's pick on a specific game is wrong.

    Does not affect W-L-T standings. Outcomes are derived from final scores
    the same way standings are — nothing is stored as a running total.
    """
    season = models.PositiveIntegerField(db_index=True)
    week = models.PositiveIntegerField(db_index=True)
    attacker = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='crossfires_fired',
    )
    target = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='crossfires_received',
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='crossfires')
    # Snapshot of sides at the moment the crossfire was placed so later pick
    # changes cannot rewrite history. Attacker must be opposite of target.
    attacker_side = models.CharField(max_length=10, choices=Pick.TEAM_CHOICES)
    target_side = models.CharField(max_length=10, choices=Pick.TEAM_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['attacker', 'game'],
                name='unique_crossfire_per_attacker_game',
            ),
            models.CheckConstraint(
                check=~models.Q(attacker=models.F('target')),
                name='crossfire_not_self',
            ),
        ]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['season', 'week'], name='acc_cf_szn_wk_idx'),
            models.Index(fields=['target', 'season', 'week'], name='acc_cf_tgt_szn_wk_idx'),
        ]

    def __str__(self):
        return f'{self.attacker_id} → {self.target_id} on {self.game_id} (W{self.week})'
