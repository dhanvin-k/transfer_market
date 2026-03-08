from django.db import models
from django.conf import settings


class Squad(models.Model):
    competition = models.ForeignKey(
        'competitions.Competition', on_delete=models.CASCADE, related_name='squads'
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='squads'
    )
    name = models.CharField(max_length=100, blank=True)
    players = models.ManyToManyField(
        'players.EAFCPlayer', through='SquadSlot', blank=True
    )
    formation = models.CharField(max_length=20, default='4-3-3')

    class Meta:
        unique_together = ('competition', 'manager')

    def __str__(self):
        return f"{self.manager}'s squad in {self.competition}"


class SquadSlot(models.Model):
    squad = models.ForeignKey(Squad, on_delete=models.CASCADE)
    player = models.ForeignKey('players.EAFCPlayer', on_delete=models.CASCADE)
    slot_number = models.PositiveSmallIntegerField()
    is_starter = models.BooleanField(default=True)
    price_paid = models.BigIntegerField(default=0)

    class Meta:
        unique_together = ('squad', 'slot_number')
        ordering = ['slot_number']
