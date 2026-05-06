from django.contrib import admin
from .models import Lega, FantaSquadra, Ingaggio

@admin.register(Lega)
class LegaAdmin(admin.ModelAdmin):
    list_display = ('nome',)

@admin.register(FantaSquadra)
class FantaSquadraAdmin(admin.ModelAdmin):
    list_display = ('nome', 'lega', 'stagione', 'crediti_residui')
    list_filter = ('lega', 'stagione')
    search_fields = ('nome',)

@admin.register(Ingaggio)
class IngaggioAdmin(admin.ModelAdmin):
    list_display = ('fantasquadra', 'calciatore_stagione', 'costo_acquisto')
    search_fields = ('fantasquadra__nome', 'calciatore_stagione__calciatore__cognome')
