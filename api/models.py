# api/models.py

from django.db import models

class NFLWeek(models.Model):
    current_week = models.IntegerField(default=1)

class Game(models.Model):
    week = models.IntegerField()  # The week number
    game_id = models.CharField(max_length=100)  # Unique ID for the game
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    game_date = models.DateField()

    def __str__(self):
        return f"{self.away_team} at {self.home_team} (Week {self.week})"

class Score(models.Model):
    game_id = models.CharField(max_length=100, unique=True)  # Match game_id from Game
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    game_date = models.DateField()  # Or DateTimeField if you want to store time as well

    def __str__(self):
        return f"Score for {self.game_id}: Home Score: {self.home_score}, Away Score: {self.away_score}"
