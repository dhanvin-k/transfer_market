"""
Daily window auction model.

AuctionSession      — one per competition, tracks overall auction state
AuctionDay          — one per calendar day, has open/close time + player slots
AuctionLot          — one listing per player per day; runs concurrently with others on that day
Bid                 — individual bid placed on a lot
TradeOffer          — manager-to-manager trade (cash / player / both)
"""
import datetime
from django.db import models
from django.conf import settings
from django.utils import timezone


class AuctionSession(models.Model):
    competition = models.OneToOneField(
        'competitions.Competition', on_delete=models.CASCADE, related_name='auction_session'
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_active(self):
        return self.started_at is not None and self.completed_at is None

    @property
    def today_window(self):
        today = timezone.localdate()
        return self.days.filter(date=today).first()

    @property
    def active_lots(self):
        now = timezone.now()
        return AuctionLot.objects.filter(
            day__session=self,
            day__opens_at__lte=now,
            closes_at__gt=now,
            is_settled=False,
        ).select_related('player', 'player__club', 'current_winner')

    def __str__(self):
        return f'Auction: {self.competition.name}'


class AuctionDay(models.Model):
    session = models.ForeignKey(AuctionSession, on_delete=models.CASCADE, related_name='days')
    date = models.DateField()
    opens_at = models.DateTimeField()   # e.g. 9:00 AM local
    closes_at = models.DateTimeField()  # e.g. 3:00 PM local — default close for lots
    label = models.CharField(max_length=60, blank=True, help_text='Optional label e.g. "Day 1 — Stars"')

    class Meta:
        ordering = ['date']
        unique_together = ('session', 'date')

    def __str__(self):
        return f'{self.session.competition.name} — {self.date}'

    @property
    def is_open(self):
        now = timezone.now()
        return self.opens_at <= now < self.closes_at

    @property
    def is_past(self):
        return timezone.now() >= self.closes_at

    @property
    def is_future(self):
        return timezone.now() < self.opens_at


class AuctionLot(models.Model):
    STATUS_OPEN     = 'open'
    STATUS_SOLD     = 'sold'
    STATUS_UNSOLD   = 'unsold'
    STATUS_PENDING  = 'pending'   # day not started yet
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_OPEN,    'Open'),
        (STATUS_SOLD,    'Sold'),
        (STATUS_UNSOLD,  'Unsold'),
    ]

    day = models.ForeignKey(AuctionDay, on_delete=models.CASCADE, related_name='lots')
    player = models.ForeignKey('players.EAFCPlayer', on_delete=models.PROTECT, related_name='auction_lots')
    order = models.PositiveSmallIntegerField(default=0)

    starting_price = models.BigIntegerField(default=1_000_000)
    current_price  = models.BigIntegerField(default=1_000_000)
    current_winner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='leading_lots'
    )

    # Each lot closes when the day closes, but can be extended by late bids
    closes_at = models.DateTimeField(null=True, blank=True)

    is_settled = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    sold_to    = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='won_lots'
    )
    sold_price = models.BigIntegerField(null=True, blank=True)
    relisted   = models.BooleanField(default=False, help_text='Was this a relist from a previous unsold lot?')

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.player.name} on {self.day.date}'

    @property
    def time_left(self):
        if not self.closes_at:
            return None
        delta = self.closes_at - timezone.now()
        return max(delta, datetime.timedelta(0))

    @property
    def seconds_left(self):
        if not self.closes_at:
            return 0
        return max(0, int((self.closes_at - timezone.now()).total_seconds()))

    def extend_if_last_10_min(self):
        """Extend close by 10 min if bid lands in final 10 min of the day window."""
        if not self.closes_at:
            return
        remaining = (self.closes_at - timezone.now()).total_seconds()
        if remaining < 600:  # 10 minutes
            self.closes_at = timezone.now() + datetime.timedelta(minutes=10)
            self.save(update_fields=['closes_at'])


class Bid(models.Model):
    lot       = models.ForeignKey(AuctionLot, on_delete=models.CASCADE, related_name='bids')
    bidder    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bids')
    amount    = models.BigIntegerField()
    placed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-placed_at']

    def __str__(self):
        return f'{self.bidder} bid ${self.amount:,} on {self.lot}'


class TradeOffer(models.Model):
    STATUS_PENDING  = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_ACCEPTED,  'Accepted'),
        (STATUS_DECLINED,  'Declined'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    competition    = models.ForeignKey('competitions.Competition', on_delete=models.CASCADE, related_name='trade_offers')
    from_manager   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_offers')
    to_manager     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_offers')

    # What the sender is offering
    cash_offered   = models.BigIntegerField(default=0)
    players_offered = models.ManyToManyField(
        'players.EAFCPlayer', blank=True, related_name='offered_in_trades'
    )

    # What the sender wants in return
    cash_wanted    = models.BigIntegerField(default=0)
    players_wanted = models.ManyToManyField(
        'players.EAFCPlayer', blank=True, related_name='wanted_in_trades'
    )

    status     = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    message    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Trade: {self.from_manager} → {self.to_manager} ({self.status})'
