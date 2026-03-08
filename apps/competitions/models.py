from django.db import models
from django.conf import settings


class Competition(models.Model):
    FORMAT_CHOICES = [
        ('league', 'League'),
        ('knockout', 'Knockout Cup'),
        ('group_knockout', 'Group Stage + Knockout'),
        ('round_robin', 'Round Robin'),
    ]
    STATUS_CHOICES = [
        ('setup', 'Setup'),
        ('auction', 'Auction'),
        ('playing', 'Playing'),
        ('completed', 'Completed'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_competitions'
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='competitions', blank=True
    )

    # ── Format ────────────────────────────────────────────
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default='league')
    group_count = models.PositiveSmallIntegerField(default=2)
    legs_per_fixture = models.PositiveSmallIntegerField(default=1)

    # ── Auction settings ──────────────────────────────────
    transfer_window_seconds = models.PositiveIntegerField(
        default=120, help_text='Seconds per auction lot (the transfer window timer)'
    )
    starting_budget = models.BigIntegerField(default=100_000_000)
    squad_size = models.PositiveSmallIntegerField(default=18)
    min_bid_increment = models.BigIntegerField(default=500_000)
    unsold_rule = models.CharField(
        max_length=20,
        choices=[('requeue', 'Re-queue'), ('highest', 'Goes to highest'), ('skip', 'Skip')],
        default='highest'
    )

    # ── Player pool filters ───────────────────────────────
    allowed_clubs = models.ManyToManyField(
        'players.Club', blank=True, related_name='competitions'
    )
    allowed_leagues = models.ManyToManyField(
        'players.League', blank=True, related_name='competitions'
    )
    min_player_rating = models.PositiveSmallIntegerField(default=75)
    max_player_rating = models.PositiveSmallIntegerField(default=99)
    nominated_players = models.ManyToManyField(
        'players.EAFCPlayer', blank=True, related_name='nominated_in'
    )

    # ── Invite ────────────────────────────────────────────
    invite_code = models.CharField(max_length=12, unique=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='setup')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_player_pool(self):
        from apps.players.models import EAFCPlayer
        if self.nominated_players.exists():
            return self.nominated_players.all()
        qs = EAFCPlayer.objects.filter(
            overall__gte=self.min_player_rating,
            overall__lte=self.max_player_rating,
        )
        if self.allowed_clubs.exists():
            qs = qs.filter(club__in=self.allowed_clubs.all())
        elif self.allowed_leagues.exists():
            qs = qs.filter(club__league__in=self.allowed_leagues.all())
        return qs

    def save(self, *args, **kwargs):
        if not self.invite_code:
            import random, string
            self.invite_code = 'TM-' + ''.join(
                random.choices(string.ascii_uppercase + string.digits, k=4)
            )
        super().save(*args, **kwargs)


class CompetitionBudget(models.Model):
    """Tracks each manager's remaining budget within a competition."""
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='budgets')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    remaining_budget = models.BigIntegerField()

    class Meta:
        unique_together = ('competition', 'user')

    def __str__(self):
        return f'{self.user} in {self.competition}: £{self.remaining_budget:,}'
