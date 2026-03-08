from django.contrib import admin
from .models import League, Club, EAFCPlayer

@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'country')
    search_fields = ('name',)

@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ('name', 'league')
    list_filter = ('league',)
    search_fields = ('name',)

@admin.register(EAFCPlayer)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ('name', 'overall', 'position', 'club', 'nationality')
    list_filter = ('position', 'club__league')
    search_fields = ('name', 'club__name', 'nationality')
    ordering = ('-overall',)
