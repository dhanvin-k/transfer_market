from django.urls import path
from . import views

urlpatterns = [
    path('<int:competition_id>/', views.fixture_list, name='fixture_list'),
    path('<int:competition_id>/generate/', views.generate_fixtures, name='fixture_generate'),
    path('result/<int:fixture_id>/', views.submit_result, name='fixture_result'),
]
