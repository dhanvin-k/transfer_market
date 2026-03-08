from django.urls import path
from . import views

urlpatterns = [
    path('<int:competition_id>/',                        views.auction_room,      name='auction_room'),
    path('<int:competition_id>/schedule/',               views.schedule_builder,  name='auction_schedule'),
    path('<int:competition_id>/schedule/generate/',      views.generate_schedule, name='auction_generate'),
    path('<int:competition_id>/schedule/delete/',        views.delete_schedule,   name='auction_delete_schedule'),
    path('<int:competition_id>/schedule/move/',          views.move_lot,          name='auction_move_lot'),
    path('<int:competition_id>/schedule/add-lot/',       views.add_lot,           name='auction_add_lot'),
    path('<int:competition_id>/schedule/remove-lot/',    views.remove_lot,        name='auction_remove_lot'),
    path('<int:competition_id>/trades/',                 views.trade_hub,         name='trade_hub'),
    path('<int:competition_id>/trades/create/',          views.create_trade,      name='trade_create'),
    path('lot/<int:lot_id>/bid/',                        views.place_bid,         name='auction_bid'),
    path('trade/<int:offer_id>/respond/',                views.respond_trade,     name='trade_respond'),
    path('trade/<int:offer_id>/cancel/',                 views.cancel_trade,      name='trade_cancel'),
]
