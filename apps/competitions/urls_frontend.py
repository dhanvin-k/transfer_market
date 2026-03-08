from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('competitions/create/', views.create_competition, name='competition_create'),
    path('competitions/join/', views.join_competition, name='competition_join'),
    path('competitions/<int:competition_id>/', views.competition_detail, name='competition_detail'),
    path('competitions/<int:competition_id>/delete/', views.delete_competition, name='competition_delete'),
    path('competitions/<int:competition_id>/leave/', views.leave_competition, name='competition_leave'),
]
