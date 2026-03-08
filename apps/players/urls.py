from django.urls import path
from . import views

urlpatterns = [
    path('', views.player_search, name='player_search'),
    path('<int:pk>/', views.player_detail, name='player_detail'),
    path('autocomplete/', views.player_autocomplete, name='player_autocomplete'),
]
