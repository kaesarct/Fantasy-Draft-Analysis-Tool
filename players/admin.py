from django.contrib import admin
from .models import Calciatore, CalciatoreStagione

@admin.register(Calciatore)
class CalciatoreAdmin(admin.ModelAdmin):
    list_display = ('cognome', 'nome', 'ruolo_base')
    search_fields = ('cognome', 'nome')
    list_filter = ('ruolo_base',)

@admin.register(CalciatoreStagione)
class CalciatoreStagioneAdmin(admin.ModelAdmin):
    list_display = ('calciatore', 'stagione', 'squadra_reale', 'ruolo_stagione', 'quotazione_iniziale')
    list_filter = ('stagione', 'squadra_reale', 'ruolo_stagione')
    search_fields = ('calciatore__cognome', 'calciatore__nome')
