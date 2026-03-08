from django.db import models
from django.conf import settings


class PlayerRecord(models.Model):
    """
    Denormalized all-time record for one player.
    Updated automatically after every Result is saved.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='record'
    )
    played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-wins', '-goals_for']

    def __str__(self):
        return f'{self.user}: {self.wins}W {self.draws}D {self.losses}L'

    @property
    def goal_difference(self):
        return self.goals_for - self.goals_against

    @property
    def win_percentage(self):
        if self.played == 0:
            return 0
        return round((self.wins / self.played) * 100, 1)

    @property
    def points(self):
        return self.wins * 3 + self.draws


class H2HRecord(models.Model):
    """Head-to-head record between two specific players."""
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='h2h_records'
    )
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='h2h_opponent_records'
    )
    wins = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    goals_for = models.PositiveIntegerField(default=0)
    goals_against = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('player', 'opponent')

    def __str__(self):
        return f'{self.player} vs {self.opponent}: {self.wins}W {self.draws}D {self.losses}L'
