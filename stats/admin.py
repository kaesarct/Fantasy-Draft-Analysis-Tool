from django.contrib import admin
from .models import VotoPartita, StatisticaCalciatore

@admin.register(VotoPartita)
class VotoPartitaAdmin(admin.ModelAdmin):
    list_display = ('calciatore_stagione', 'giornata', 'voto_base', 'fanta_voto', 'gol_fatti', 'assist')
    list_filter = ('giornata', 'calciatore_stagione__stagione')
    search_fields = ('calciatore_stagione__calciatore__cognome',)

@admin.register(StatisticaCalciatore)
class StatisticaCalciatoreAdmin(admin.ModelAdmin):
    list_display = ('calciatore_stagione', 'partite_a_voto', 'media_voto', 'fanta_media', 'gol_fatti')
    list_filter = ('calciatore_stagione__stagione',)
    search_fields = ('calciatore_stagione__calciatore__cognome',)
