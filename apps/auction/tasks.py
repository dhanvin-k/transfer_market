from celery import shared_task
from django.utils import timezone


@shared_task
def settle_expired_lots():
    """Run every minute via Celery beat to settle closed lots."""
    from apps.auction.models import AuctionDay
    from apps.auction.views import settle_day
    now = timezone.now()
    expired_days = AuctionDay.objects.filter(
        closes_at__lte=now,
        lots__is_settled=False
    ).distinct()
    for day in expired_days:
        settle_day(day)


@shared_task
def open_todays_lots():
    """Run at day open time to mark lots as open."""
    from apps.auction.models import AuctionLot, AuctionDay
    now = timezone.now()
    open_days = AuctionDay.objects.filter(opens_at__lte=now, closes_at__gt=now)
    AuctionLot.objects.filter(
        day__in=open_days, status=AuctionLot.STATUS_PENDING
    ).update(status=AuctionLot.STATUS_OPEN)
