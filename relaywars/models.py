import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from api.models import Game


class RelayTeam(models.Model):
    RECRUITING = 'recruiting'
    READY = 'ready'
    MATCHED = 'matched'
    STATUS_CHOICES = [(RECRUITING, 'Recruiting'), (READY, 'Ready'), (MATCHED, 'Matched')]

    season = models.PositiveSmallIntegerField(db_index=True)
    week = models.PositiveSmallIntegerField(db_index=True)
    name = models.CharField(max_length=40)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_owned_teams')
    invite_code = models.CharField(max_length=32, unique=True, editable=False)
    is_random = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=RECRUITING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = secrets.token_urlsafe(12)
        super().save(*args, **kwargs)

    @property
    def active_members(self):
        return self.members.filter(is_active=True).select_related('user')

    @property
    def member_count(self):
        return self.members.filter(is_active=True).count()

    def __str__(self):
        return self.name


class RelayTeamMember(models.Model):
    team = models.ForeignKey(RelayTeam, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    draft_priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['draft_priority', 'joined_at']
        constraints = [models.UniqueConstraint(fields=['team', 'user'], name='rw_unique_team_member')]


class RelayQueueEntry(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_queue_entries')
    season = models.PositiveSmallIntegerField()
    week = models.PositiveSmallIntegerField()
    queued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['queued_at']
        constraints = [models.UniqueConstraint(fields=['user', 'season', 'week'], name='rw_unique_queue_entry')]


class RelayMatch(models.Model):
    DRAFT = 'draft'
    ACTIVE = 'active'
    COMPLETE = 'complete'
    STATUS_CHOICES = [(DRAFT, 'Drafting'), (ACTIVE, 'In progress'), (COMPLETE, 'Complete')]

    season = models.PositiveSmallIntegerField(db_index=True)
    week = models.PositiveSmallIntegerField(db_index=True)
    team_a = models.OneToOneField(RelayTeam, on_delete=models.CASCADE, related_name='match_as_a')
    team_b = models.OneToOneField(RelayTeam, on_delete=models.CASCADE, related_name='match_as_b')
    lock_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.team_a} vs {self.team_b} — {self.season} Week {self.week}'

    @property
    def draft_locked(self):
        return timezone.now() >= self.lock_at

    @property
    def winner_team(self):
        if self.status != self.COMPLETE:
            return None
        a = self.sides.filter(team=self.team_a).first()
        b = self.sides.filter(team=self.team_b).first()
        if not a or not b or a.best_chain == b.best_chain:
            return None
        return self.team_a if a.best_chain > b.best_chain else self.team_b

    @property
    def is_tied(self):
        if self.status != self.COMPLETE:
            return False
        a = self.sides.filter(team=self.team_a).first()
        b = self.sides.filter(team=self.team_b).first()
        return bool(a and b and a.best_chain == b.best_chain)


class RelayMatchSide(models.Model):
    match = models.ForeignKey(RelayMatch, on_delete=models.CASCADE, related_name='sides')
    team = models.ForeignKey(RelayTeam, on_delete=models.CASCADE, related_name='match_sides')
    ability_tokens = models.PositiveSmallIntegerField(default=2)
    current_chain = models.PositiveSmallIntegerField(default=0)
    best_chain = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['match', 'team'], name='rw_unique_match_side')]


class RelayDraftTurn(models.Model):
    match = models.ForeignKey(RelayMatch, on_delete=models.CASCADE, related_name='draft_turns')
    position = models.PositiveSmallIntegerField()
    team = models.ForeignKey(RelayTeam, on_delete=models.CASCADE, related_name='draft_turns')
    assigned_member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_assigned_turns')
    skipped = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position']
        constraints = [models.UniqueConstraint(fields=['match', 'position'], name='rw_unique_draft_position')]

    @property
    def completed(self):
        return self.skipped or hasattr(self, 'pick')


class RelayPick(models.Model):
    HOME = 'home'
    AWAY = 'away'
    SIDE_CHOICES = [(HOME, 'Home'), (AWAY, 'Away')]

    match = models.ForeignKey(RelayMatch, on_delete=models.CASCADE, related_name='picks')
    draft_turn = models.OneToOneField(RelayDraftTurn, on_delete=models.CASCADE, related_name='pick')
    team = models.ForeignKey(RelayTeam, on_delete=models.CASCADE, related_name='relaywars_picks')
    assigned_player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_picks')
    selected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_submitted_picks')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='relaywars_picks')
    picked_side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['game__kickoff', 'created_at']
        constraints = [models.UniqueConstraint(fields=['match', 'game'], name='rw_unique_game_per_match')]

    @property
    def picked_team(self):
        return self.game.home_team if self.picked_side == self.HOME else self.game.away_team

    @property
    def result(self):
        if not self.game.is_final:
            return 'pending'
        if self.game.winner_side == 'tie':
            return 'tie'
        return 'win' if self.game.winner_side == self.picked_side else 'loss'


class RelayAbility(models.Model):
    JINX = 'jinx'
    PROTECT = 'protect'
    KIND_CHOICES = [(JINX, 'Jinx'), (PROTECT, 'Protection')]
    PENDING = 'pending'
    ACTIVE = 'active'
    RESOLVED = 'resolved'
    EXPIRED = 'expired'
    STATUS_CHOICES = [(PENDING, 'Voting'), (ACTIVE, 'Active'), (RESOLVED, 'Resolved'), (EXPIRED, 'Expired')]

    match = models.ForeignKey(RelayMatch, on_delete=models.CASCADE, related_name='abilities')
    team = models.ForeignKey(RelayTeam, on_delete=models.CASCADE, related_name='relaywars_abilities')
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_proposals')
    target_pick = models.ForeignKey(RelayPick, on_delete=models.CASCADE, related_name='abilities')
    kind = models.CharField(max_length=8, choices=KIND_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    token_spent = models.BooleanField(default=False)
    reward_granted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['target_pick', 'kind'], name='rw_one_ability_kind_per_pick')]


class RelayAbilityVote(models.Model):
    ability = models.ForeignKey(RelayAbility, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='relaywars_ability_votes')
    approved = models.BooleanField()
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['ability', 'user'], name='rw_one_vote_per_member')]
