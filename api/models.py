# api/models.py

from django.db import models
from django.utils import timezone

from . import rules


class NFLWeek(models.Model):
    """Legacy. The current week is now worked out from the schedule
    (see api.services.current_week). Safe to delete later."""
    current_week = models.IntegerField(default=1)
    last_updated = models.DateField(null=True, blank=True)


class Game(models.Model):
    SCHEDULED = rules.SCHEDULED
    LIVE = rules.LIVE
    FINAL = rules.FINAL
    STATUS_CHOICES = [
        (SCHEDULED, "Scheduled"),
        (LIVE, "In progress"),
        (FINAL, "Final"),
    ]

    # Rows that existed before this change are the 2024 test data, so 2024 is
    # the correct default for them. New rows always get the season from settings.
    season = models.IntegerField(default=2024, db_index=True)
    week = models.IntegerField()
    game_id = models.CharField(max_length=100, unique=True)
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    game_date = models.DateField()

    kickoff = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=SCHEDULED)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)

    # Bookkeeping so the sync never wastes API calls.
    schedule_synced_at = models.DateTimeField(null=True, blank=True)
    scores_checked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.away_team} at {self.home_team} (Week {self.week})"

    @property
    def is_final(self):
        return (self.status == self.FINAL
                and self.home_score is not None
                and self.away_score is not None)

    @property
    def lock_at(self):
        return rules.lock_time(self.kickoff, self.game_date)

    @property
    def has_started(self):
        """True once picks are locked for this game."""
        return timezone.now() >= self.lock_at

    @property
    def winner_side(self):
        """'home', 'away', 'tie', or None while the game isn't final."""
        if not self.is_final:
            return None
        if self.home_score == self.away_score:
            return "tie"
        return "home" if self.home_score > self.away_score else "away"

    @property
    def winner_name(self):
        """Winning team's abbreviation, 'Draw', or None while not final."""
        side = self.winner_side
        if side is None:
            return None
        if side == "tie":
            return "Draw"
        return self.home_team if side == "home" else self.away_team


class QuarterScore(models.Model):
    """The running score at the end of a quarter (cumulative, not per quarter).

    Quarters 1-3 are stored here: end of Q1, halftime, end of Q3. The "Final"
    square always uses the game's own final score (overtime included), so
    there is no quarter 4 row.

    `source` says who wrote the row. Today that is "manual" (admin or the
    squares command). A future score sync can write "sync" rows and only ever
    overwrite its own, so hand-entered corrections are never lost.
    """
    MANUAL = 'manual'
    SYNC = 'sync'
    QUARTER_CHOICES = [(1, 'End of Q1'), (2, 'Halftime'), (3, 'End of Q3')]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='quarter_scores')
    quarter = models.PositiveSmallIntegerField(choices=QUARTER_CHOICES)
    home_score = models.PositiveSmallIntegerField()
    away_score = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=10, default=MANUAL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['game', 'quarter']
        constraints = [
            models.UniqueConstraint(fields=['game', 'quarter'], name='unique_quarter_score_per_game'),
        ]

    def __str__(self):
        return f'{self.game}: Q{self.quarter} {self.away_score}-{self.home_score}'


class Score(models.Model):
    """Legacy. Scores now live on Game. Kept so old data isn't lost;
    safe to delete later."""
    game_id = models.CharField(max_length=100, unique=True)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    game_date = models.DateField()

    def __str__(self):
        return f"Score for {self.game_id}: Home Score: {self.home_score}, Away Score: {self.away_score}"
