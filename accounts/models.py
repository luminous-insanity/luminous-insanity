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