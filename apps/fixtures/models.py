from django.db import models
from django.conf import settings


class Fixture(models.Model):
    STAGE_CHOICES = [
        ('league', 'League'),
        ('group', 'Group Stage'),
        ('r32', 'Round of 32'), ('r16', 'Round of 16'),
        ('qf', 'Quarter-Final'), ('sf', 'Semi-Final'),
        ('final', 'Final'),
    ]

    competition = models.ForeignKey(
        'competitions.Competition', on_delete=models.CASCADE, related_name='fixtures'
    )
    home = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='home_fixtures'
    )
    away = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='away_fixtures'
    )
    round_number = models.PositiveSmallIntegerField(default=1)
    leg = models.PositiveSmallIntegerField(default=1)
    group_label = models.CharField(max_length=5, blank=True, help_text='e.g. A, B, C')
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES, default='league')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['round_number', 'leg', 'id']

    def __str__(self):
        return f'{self.home} vs {self.away} (R{self.round_number})'


class Result(models.Model):
    fixture = models.OneToOneField(Fixture, on_delete=models.CASCADE, related_name='result')
    home_score = models.PositiveSmallIntegerField()
    away_score = models.PositiveSmallIntegerField()
    played_at = models.DateTimeField(auto_now_add=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.fixture}: {self.home_score}–{self.away_score}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mark fixture completed and update records
        self.fixture.is_completed = True
        self.fixture.save(update_fields=['is_completed'])
        from apps.records.utils import update_records_from_result
        update_records_from_result(self)
