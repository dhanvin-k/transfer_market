from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('auction/', include('apps.auction.urls')),
    path('fixtures/', include('apps.fixtures.urls')),
    path('records/', include('apps.records.urls')),
    path('squads/', include('apps.squads.urls')),
    path('players/', include('apps.players.urls')),
    path('', include('apps.competitions.urls_frontend')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
