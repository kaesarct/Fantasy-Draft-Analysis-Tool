from django.contrib import admin
from .models import Calciatore, CalciatoreStagione

@admin.register(Calciatore)
class CalciatoreAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ruolo_base')
    search_fields = ('nome',)
    list_filter = ('ruolo_base',)

@admin.register(CalciatoreStagione)
class CalciatoreStagioneAdmin(admin.ModelAdmin):
    list_display = ('calciatore', 'stagione', 'squadra_reale', 'ruolo_stagione', 'quotazione_iniziale')
    list_filter = ('stagione', 'squadra_reale', 'ruolo_stagione')
    search_fields = ('calciatore__nome',)
