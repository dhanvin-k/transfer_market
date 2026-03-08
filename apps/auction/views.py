import datetime, random
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import F

from apps.competitions.models import Competition, CompetitionBudget
from apps.squads.models import Squad, SquadSlot
from apps.players.models import EAFCPlayer
from .models import AuctionSession, AuctionDay, AuctionLot, Bid, TradeOffer


# ── Auction Room ──────────────────────────────────────────────────────────────

@login_required
def auction_room(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    request.session['active_competition_id'] = competition_id
    _check_participant(request.user, comp)

    session, _ = AuctionSession.objects.get_or_create(competition=comp)
    budget = CompetitionBudget.objects.filter(competition=comp, user=request.user).first()

    now = timezone.now()
    today_window = session.today_window
    active_lots = list(session.active_lots) if today_window else []

    # settle expired lots
    _settle_expired_lots(session)

    upcoming_days = session.days.filter(opens_at__gt=now).order_by('date')[:5]
    past_days = session.days.filter(closes_at__lte=now).order_by('-date')[:3]

    # My winning bids on currently open lots
    my_leading = set(
        AuctionLot.objects.filter(
            day__session=session, current_winner=request.user, is_settled=False
        ).values_list('id', flat=True)
    )

    return render(request, 'auction/room.html', {
        'competition': comp,
        'session': session,
        'budget': budget,
        'today_window': today_window,
        'active_lots': active_lots,
        'upcoming_days': upcoming_days,
        'past_days': past_days,
        'my_leading': my_leading,
        'now': now,
    })


# ── Schedule builder ──────────────────────────────────────────────────────────

@login_required
def schedule_builder(request, competition_id):
    import json
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    session, _ = AuctionSession.objects.get_or_create(competition=comp)
    days = session.days.prefetch_related('lots__player__club').order_by('date')
    all_players = list(comp.get_player_pool().select_related('club').order_by('-overall'))

    used_ids = list(
        AuctionLot.objects.filter(day__session=session, is_settled=False)
        .values_list('player_id', flat=True)
    )
    all_players_json = json.dumps([
        {'id': p.pk, 'name': p.name, 'position': p.position,
         'overall': p.overall, 'club': p.club.name if p.club else ''}
        for p in all_players
    ])
    used_ids_json = json.dumps(used_ids)

    return render(request, 'auction/schedule.html', {
        'competition': comp,
        'session': session,
        'days': days,
        'all_players': all_players,
        'all_players_json': all_players_json,
        'used_ids_json': used_ids_json,
    })


@login_required
@require_POST
def generate_schedule(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    session, _ = AuctionSession.objects.get_or_create(competition=comp)

    try:
        num_days        = int(request.POST.get('num_days', 14))
        players_per_day = int(request.POST.get('players_per_day', 10))
        start_date_str  = request.POST.get('start_date')
        open_hour       = int(request.POST.get('open_hour', 9))
        close_hour      = int(request.POST.get('close_hour', 15))
        start_date = datetime.date.fromisoformat(start_date_str)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid parameters.'}, status=400)

    if session.days.exists():
        return JsonResponse({'error': 'Schedule already exists. Delete it first.'}, status=400)

    pool = list(comp.get_player_pool().order_by('-overall'))
    if not pool:
        return JsonResponse({'error': 'No players in pool. Check min OVR setting.'}, status=400)

    # Build diverse daily sets
    total_needed = num_days * players_per_day
    selected = _pick_diverse(pool, total_needed)
    random.shuffle(selected)

    with transaction.atomic():
        for day_idx in range(num_days):
            d = start_date + datetime.timedelta(days=day_idx)
            import zoneinfo
            tz_name = request.POST.get('timezone', 'UTC')
            try:
                tz = zoneinfo.ZoneInfo(tz_name)
            except Exception:
                tz = datetime.timezone.utc
            opens  = datetime.datetime(d.year, d.month, d.day, open_hour, 0, tzinfo=tz)
            closes = datetime.datetime(d.year, d.month, d.day, close_hour, 0, tzinfo=tz)
            day = AuctionDay.objects.create(session=session, date=d, opens_at=opens, closes_at=closes)
            day_players = selected[day_idx * players_per_day:(day_idx + 1) * players_per_day]
            lots = [
                AuctionLot(
                    day=day, player=p, order=i,
                    starting_price=_starting_price(p.overall),
                    current_price=_starting_price(p.overall),
                    closes_at=closes,
                    status=AuctionLot.STATUS_PENDING,
                )
                for i, p in enumerate(day_players)
            ]
            AuctionLot.objects.bulk_create(lots)

        session.started_at = timezone.now()
        session.save(update_fields=['started_at'])

        # Init budgets
        for user in set(list(comp.participants.all()) + [comp.created_by]):
            CompetitionBudget.objects.get_or_create(
                competition=comp, user=user,
                defaults={'remaining_budget': comp.starting_budget}
            )

    return JsonResponse({'ok': True})


@login_required
@require_POST
def move_lot(request, competition_id):
    """Move a lot from one day to another (host only)."""
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    lot_id  = request.POST.get('lot_id')
    to_date = request.POST.get('to_date')
    try:
        lot = AuctionLot.objects.select_related('day__session').get(
            pk=lot_id, day__session__competition=comp
        )
        target_day = AuctionDay.objects.get(session__competition=comp, date=to_date)
    except (AuctionLot.DoesNotExist, AuctionDay.DoesNotExist):
        return JsonResponse({'error': 'Not found.'}, status=404)
    if lot.day.is_past or lot.is_settled:
        return JsonResponse({'error': 'Cannot move settled or past lots.'}, status=400)
    lot.day = target_day
    lot.closes_at = target_day.closes_at
    lot.save(update_fields=['day', 'closes_at'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def delete_schedule(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    session = get_object_or_404(AuctionSession, competition=comp)
    session.days.all().delete()
    session.started_at = None
    session.save(update_fields=['started_at'])
    return JsonResponse({'ok': True})


# ── Bidding ────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def place_bid(request, lot_id):
    lot = get_object_or_404(
        AuctionLot.objects.select_related('day__session__competition', 'current_winner'),
        pk=lot_id
    )
    comp = lot.day.session.competition
    _check_participant(request.user, comp)

    now = timezone.now()
    if not (lot.day.opens_at <= now < lot.closes_at):
        return JsonResponse({'error': 'Bidding window is closed.'}, status=400)
    if lot.is_settled:
        return JsonResponse({'error': 'This lot is already settled.'}, status=400)

    try:
        amount = int(request.POST['amount'])
    except (KeyError, ValueError):
        return JsonResponse({'error': 'Invalid amount.'}, status=400)

    min_bid = lot.current_price + comp.min_bid_increment
    if amount < min_bid:
        return JsonResponse({'error': f'Minimum bid is ${min_bid:,.0f}'}, status=400)

    budget = get_object_or_404(CompetitionBudget, competition=comp, user=request.user)

    # Reserve calculation: subtract committed bids on other open lots
    committed = _committed_budget(request.user, comp, exclude_lot=lot)
    available = budget.remaining_budget - committed
    if amount > available:
        return JsonResponse({'error': f'You only have ${available:,.0f} uncommitted.'}, status=400)

    with transaction.atomic():
        Bid.objects.create(lot=lot, bidder=request.user, amount=amount)
        lot.current_price  = amount
        lot.current_winner = request.user
        lot.status = AuctionLot.STATUS_OPEN
        lot.save(update_fields=['current_price', 'current_winner', 'status'])
        lot.extend_if_last_10_min()

    # Broadcast via WS
    _broadcast_bid(lot, request.user, amount)
    return JsonResponse({'ok': True, 'new_price': amount})


# ── Trade Offers ──────────────────────────────────────────────────────────────

@login_required
def trade_hub(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    request.session['active_competition_id'] = competition_id
    _check_participant(request.user, comp)

    incoming = TradeOffer.objects.filter(
        competition=comp, to_manager=request.user, status=TradeOffer.STATUS_PENDING
    ).prefetch_related('players_offered', 'players_wanted').select_related('from_manager')

    outgoing = TradeOffer.objects.filter(
        competition=comp, from_manager=request.user
    ).prefetch_related('players_offered', 'players_wanted').select_related('to_manager')[:20]

    history = TradeOffer.objects.filter(
        competition=comp, status__in=['accepted', 'declined', 'cancelled']
    ).filter(
        from_manager=request.user
    ).union(
        TradeOffer.objects.filter(
            competition=comp, status__in=['accepted', 'declined', 'cancelled'],
            to_manager=request.user
        )
    ).order_by('-created_at')[:20]

    # My squad for offer building
    my_squad = Squad.objects.filter(competition=comp, manager=request.user).prefetch_related('squadslot_set__player').first()
    participants = comp.participants.exclude(pk=request.user.pk)

    # Their squads for display
    other_squads = {
        sq.manager_id: sq
        for sq in Squad.objects.filter(competition=comp).exclude(manager=request.user)
        .prefetch_related('squadslot_set__player')
    }

    return render(request, 'auction/trades.html', {
        'competition': comp,
        'incoming': incoming,
        'outgoing': outgoing,
        'history': history,
        'my_squad': my_squad,
        'participants': participants,
        'other_squads': other_squads,
        'budget': CompetitionBudget.objects.filter(competition=comp, user=request.user).first(),
    })


@login_required
@require_POST
def create_trade(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id)
    _check_participant(request.user, comp)

    to_id = request.POST.get('to_manager')
    to_manager = get_object_or_404(comp.participants.model, pk=to_id)

    cash_offered = int(request.POST.get('cash_offered', 0) or 0)
    cash_wanted  = int(request.POST.get('cash_wanted', 0) or 0)
    players_offered_ids = request.POST.getlist('players_offered')
    players_wanted_ids  = request.POST.getlist('players_wanted')
    message = request.POST.get('message', '').strip()

    # Validate offered players are in my squad
    my_player_ids = set(
        SquadSlot.objects.filter(
            squad__competition=comp, squad__manager=request.user
        ).values_list('player_id', flat=True)
    )
    for pid in players_offered_ids:
        if int(pid) not in my_player_ids:
            return JsonResponse({'error': 'You can only offer players you own.'}, status=400)

    # Validate wanted players are in their squad
    their_player_ids = set(
        SquadSlot.objects.filter(
            squad__competition=comp, squad__manager=to_manager
        ).values_list('player_id', flat=True)
    )
    for pid in players_wanted_ids:
        if int(pid) not in their_player_ids:
            return JsonResponse({'error': 'They do not own that player.'}, status=400)

    budget = get_object_or_404(CompetitionBudget, competition=comp, user=request.user)
    if cash_offered > budget.remaining_budget:
        return JsonResponse({'error': 'Insufficient budget.'}, status=400)

    offer = TradeOffer.objects.create(
        competition=comp, from_manager=request.user, to_manager=to_manager,
        cash_offered=cash_offered, cash_wanted=cash_wanted, message=message
    )
    offer.players_offered.set(players_offered_ids)
    offer.players_wanted.set(players_wanted_ids)

    return JsonResponse({'ok': True, 'offer_id': offer.pk})


@login_required
@require_POST
def respond_trade(request, offer_id):
    offer = get_object_or_404(TradeOffer, pk=offer_id, to_manager=request.user, status=TradeOffer.STATUS_PENDING)
    action = request.POST.get('action')

    if action == 'decline':
        offer.status = TradeOffer.STATUS_DECLINED
        offer.resolved_at = timezone.now()
        offer.save()
        return JsonResponse({'ok': True})

    if action != 'accept':
        return JsonResponse({'error': 'Invalid action.'}, status=400)

    comp = offer.competition
    with transaction.atomic():
        # Transfer players offered → to_manager's squad
        to_squad, _ = Squad.objects.get_or_create(competition=comp, manager=offer.to_manager,
                                                   defaults={'name': ''})
        from_squad, _ = Squad.objects.get_or_create(competition=comp, manager=offer.from_manager,
                                                     defaults={'name': ''})

        for player in offer.players_offered.all():
            slot = SquadSlot.objects.filter(squad=from_squad, player=player).first()
            if slot:
                slot.squad = to_squad
                slot.save(update_fields=['squad'])

        for player in offer.players_wanted.all():
            slot = SquadSlot.objects.filter(squad=to_squad, player=player).first()
            if slot:
                slot.squad = from_squad
                slot.save(update_fields=['squad'])

        # Cash transfers
        if offer.cash_offered:
            CompetitionBudget.objects.filter(competition=comp, user=offer.from_manager).update(
                remaining_budget=F('remaining_budget') - offer.cash_offered
            )
            CompetitionBudget.objects.filter(competition=comp, user=offer.to_manager).update(
                remaining_budget=F('remaining_budget') + offer.cash_offered
            )
        if offer.cash_wanted:
            CompetitionBudget.objects.filter(competition=comp, user=offer.to_manager).update(
                remaining_budget=F('remaining_budget') - offer.cash_wanted
            )
            CompetitionBudget.objects.filter(competition=comp, user=offer.from_manager).update(
                remaining_budget=F('remaining_budget') + offer.cash_wanted
            )

        offer.status = TradeOffer.STATUS_ACCEPTED
        offer.resolved_at = timezone.now()
        offer.save()

    return JsonResponse({'ok': True})


@login_required
@require_POST
def cancel_trade(request, offer_id):
    offer = get_object_or_404(TradeOffer, pk=offer_id, from_manager=request.user,
                               status=TradeOffer.STATUS_PENDING)
    offer.status = TradeOffer.STATUS_CANCELLED
    offer.resolved_at = timezone.now()
    offer.save()
    return JsonResponse({'ok': True})


# ── Settle lots (called by Celery beat + on page load) ─────────────────────────

def settle_day(day):
    """Settle all expired lots on a given AuctionDay."""
    now = timezone.now()
    lots = day.lots.filter(is_settled=False, closes_at__lte=now)
    for lot in lots.select_related('current_winner', 'player', 'day__session__competition'):
        _settle_lot(lot)


def _settle_lot(lot):
    comp = lot.day.session.competition
    if lot.current_winner:
        lot.status    = AuctionLot.STATUS_SOLD
        lot.sold_to   = lot.current_winner
        lot.sold_price = lot.current_price
        lot.is_settled = True
        lot.save(update_fields=['status', 'sold_to', 'sold_price', 'is_settled'])

        # Deduct budget
        CompetitionBudget.objects.filter(
            competition=comp, user=lot.current_winner
        ).update(remaining_budget=F('remaining_budget') - lot.sold_price)

        # Add to squad
        squad, _ = Squad.objects.get_or_create(
            competition=comp, manager=lot.current_winner, defaults={'name': ''}
        )
        next_slot = (SquadSlot.objects.filter(squad=squad)
                     .order_by('-slot_number').values_list('slot_number', flat=True).first() or 0) + 1
        SquadSlot.objects.get_or_create(
            squad=squad, player=lot.player,
            defaults={'slot_number': next_slot, 'price_paid': lot.sold_price}
        )
    else:
        # No bids — relist on next available day
        lot.status    = AuctionLot.STATUS_UNSOLD
        lot.is_settled = True
        lot.save(update_fields=['status', 'is_settled'])

        next_day = (AuctionDay.objects
                    .filter(session=lot.day.session, opens_at__gt=timezone.now())
                    .order_by('opens_at').first())
        if next_day:
            AuctionLot.objects.create(
                day=next_day, player=lot.player, order=999,
                starting_price=lot.starting_price, current_price=lot.starting_price,
                closes_at=next_day.closes_at, status=AuctionLot.STATUS_PENDING,
                relisted=True,
            )


def _settle_expired_lots(session):
    now = timezone.now()
    expired = AuctionLot.objects.filter(
        day__session=session, is_settled=False, closes_at__lte=now
    ).select_related('current_winner', 'player', 'day__session__competition')
    for lot in expired:
        _settle_lot(lot)



@login_required
@require_POST
def add_lot(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    player_id = request.POST.get('player_id')
    day_date  = request.POST.get('day_date')
    try:
        player = EAFCPlayer.objects.get(pk=player_id)
        day = AuctionDay.objects.get(session__competition=comp, date=day_date)
    except (EAFCPlayer.DoesNotExist, AuctionDay.DoesNotExist):
        return JsonResponse({'error': 'Not found.'}, status=404)
    if day.is_past:
        return JsonResponse({'error': 'Cannot add to past day.'}, status=400)
    AuctionLot.objects.create(
        day=day, player=player, order=999,
        starting_price=_starting_price(player.overall),
        current_price=_starting_price(player.overall),
        closes_at=day.closes_at,
        status=AuctionLot.STATUS_OPEN if day.is_open else AuctionLot.STATUS_PENDING,
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def remove_lot(request, competition_id):
    comp = get_object_or_404(Competition, pk=competition_id, created_by=request.user)
    lot_id = request.POST.get('lot_id')
    try:
        lot = AuctionLot.objects.get(pk=lot_id, day__session__competition=comp)
    except AuctionLot.DoesNotExist:
        return JsonResponse({'error': 'Not found.'}, status=404)
    if lot.is_settled or lot.bids.exists():
        return JsonResponse({'error': 'Cannot remove settled or bid-on lots.'}, status=400)
    lot.delete()
    return JsonResponse({'ok': True})

# ── Helpers ────────────────────────────────────────────────────────────────────

def _check_participant(user, comp):
    if user != comp.created_by and not comp.participants.filter(pk=user.pk).exists():
        from django.http import Http404
        raise Http404


def _committed_budget(user, comp, exclude_lot=None):
    """How much of the user's budget is already committed to leading bids."""
    qs = AuctionLot.objects.filter(
        day__session__competition=comp,
        current_winner=user, is_settled=False,
        closes_at__gt=timezone.now(),
    )
    if exclude_lot:
        qs = qs.exclude(pk=exclude_lot.pk)
    return sum(qs.values_list('current_price', flat=True))


def _broadcast_bid(lot, user, amount):
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        layer = get_channel_layer()
        group = f"auction_{lot.day.session.competition_id}"
        async_to_sync(layer.group_send)(group, {
            'type': 'broadcast_bid',
            'lot_id': lot.pk,
            'amount': amount,
            'bidder': user.display_name or user.username,
            'seconds_left': lot.seconds_left,
        })
    except Exception:
        pass


def _pick_diverse(pool, total):
    """Pick `total` players with diverse rating + position spread."""
    positions = {}
    for p in pool:
        positions.setdefault(p.position, []).append(p)

    result = []
    pos_keys = list(positions.keys())
    i = 0
    while len(result) < total and any(positions.values()):
        pos = pos_keys[i % len(pos_keys)]
        if positions.get(pos):
            result.append(positions[pos].pop(0))
        i += 1

    if len(result) < total:
        remaining = [p for p in pool if p not in result]
        result += remaining[:total - len(result)]

    return result[:total]


def _starting_price(overall):
    if overall >= 90: return 5_000_000
    if overall >= 85: return 3_000_000
    if overall >= 80: return 1_500_000
    if overall >= 77: return 1_000_000
    return 500_000
