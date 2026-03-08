from django.urls import path
from . import views

urlpatterns = [
    path('<int:competition_id>/', views.leaderboard, name='leaderboard'),
]
