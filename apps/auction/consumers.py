import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class AuctionConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.competition_id = self.scope["url_route"]["kwargs"]["competition_id"]
        self.group_name = f"auction_{self.competition_id}"
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        state = await self.get_current_state()
        await self.send(text_data=json.dumps(state))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get("type") == "bid":
            await self.handle_bid(data)

    async def handle_bid(self, data):
        try:
            amount = int(data["amount"])
        except (KeyError, ValueError, TypeError):
            await self.send_error("Invalid bid amount.")
            return
        result = await self.process_bid(amount)
        if result["ok"]:
            await self.channel_layer.group_send(self.group_name, {
                "type": "broadcast_bid",
                **result,
            })
        else:
            await self.send_error(result["error"])

    @database_sync_to_async
    def process_bid(self, amount):
        from apps.auction.models import AuctionSession, Bid
        from apps.competitions.models import CompetitionBudget

        try:
            session = AuctionSession.objects.select_related("competition").get(
                competition_id=self.competition_id
            )
        except AuctionSession.DoesNotExist:
            return {"ok": False, "error": "Auction not found."}

        lot = session.current_lot
        if not lot:
            return {"ok": False, "error": "No active lot."}
        if timezone.now() > lot.ends_at:
            return {"ok": False, "error": "Bidding has closed for this lot."}

        min_next = lot.current_price + session.competition.min_bid_increment
        if amount < min_next:
            return {"ok": False, "error": f"Minimum bid is {_fmt(min_next)}"}

        try:
            budget = CompetitionBudget.objects.get(
                competition_id=self.competition_id, user=self.user
            )
        except CompetitionBudget.DoesNotExist:
            return {"ok": False, "error": "You are not a participant."}

        if amount > budget.remaining_budget:
            return {"ok": False, "error": f"Insufficient budget. You have {_fmt(budget.remaining_budget)}"}

        Bid.objects.create(lot=lot, bidder=self.user, amount=amount)
        lot.current_price = amount
        lot.current_winner = self.user
        lot.save(update_fields=["current_price", "current_winner"])
        lot.extend_if_needed()
        lot.refresh_from_db()

        seconds_left = max(0, int((lot.ends_at - timezone.now()).total_seconds()))

        return {
            "ok": True,
            "lot_id": lot.id,
            "amount": amount,
            "bidder": self.user.display_name or self.user.username,
            "bidder_initials": self.user.initials,
            "seconds_left": seconds_left,
        }

    @database_sync_to_async
    def get_current_state(self):
        from apps.auction.models import AuctionSession
        from apps.competitions.models import CompetitionBudget

        try:
            session = AuctionSession.objects.select_related("competition").get(
                competition_id=self.competition_id
            )
        except AuctionSession.DoesNotExist:
            return {"type": "error", "message": "Auction not found."}

        if session.completed_at:
            return {"type": "auction_end"}

        lot = session.current_lot
        if not lot:
            return {"type": "auction_end"}

        seconds_left = max(0, int((lot.ends_at - timezone.now()).total_seconds()))
        budgets = list(
            CompetitionBudget.objects.filter(competition_id=self.competition_id)
            .select_related("user")
            .values("user__username", "user__display_name", "remaining_budget")
        )
        recent_bids = list(
            lot.bids.select_related("bidder")
            .values("bidder__display_name", "bidder__username", "amount")[:5]
        )

        return {
            "type": "state",
            "lot_id": lot.id,
            "order": lot.order,
            "total_lots": session.lots.count(),
            "seconds_left": seconds_left,
            "current_price": lot.current_price,
            "current_winner": (
                lot.current_winner.display_name or lot.current_winner.username
                if lot.current_winner else None
            ),
            "player": _player_dict(lot.player),
            "budgets": budgets,
            "recent_bids": [
                {"name": b["bidder__display_name"] or b["bidder__username"], "amount": b["amount"]}
                for b in recent_bids
            ],
        }

    # ── Channel layer handlers ────────────────────────────────────────────────
    async def broadcast_bid(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_bid",
            "lot_id": event.get("lot_id"),
            "amount": event["amount"],
            "bidder": event["bidder"],
            "seconds_left": event["seconds_left"],
        }))

    async def broadcast_tick(self, event):
        await self.send(text_data=json.dumps({"type": "tick", "seconds_left": event["seconds_left"]}))

    async def broadcast_next_lot(self, event):
        await self.send(text_data=json.dumps({**event, "type": "next_lot"}))

    async def broadcast_lot_sold(self, event):
        await self.send(text_data=json.dumps({**event, "type": "lot_sold"}))

    async def broadcast_auction_end(self, event):
        await self.send(text_data=json.dumps({"type": "auction_end"}))

    async def send_error(self, message):
        await self.send(text_data=json.dumps({"type": "error", "message": message}))


def _fmt(n):
    if n >= 1_000_000: return f"£{n/1_000_000:.1f}M"
    if n >= 1_000: return f"£{n/1_000:.0f}K"
    return f"£{n}"


def _player_dict(player):
    return {
        "id": player.id,
        "name": player.name,
        "overall": player.overall,
        "position": player.position,
        "club": player.club.name if player.club else "",
        "nationality": player.nationality,
        "photo_url": player.photo_url,
        "stats": player.stats_dict(),
    }
