from django.contrib import admin
from .models import AnalisiPreAsta

@admin.register(AnalisiPreAsta)
class AnalisiPreAstaAdmin(admin.ModelAdmin):
    list_display = ('calciatore_stagione', 'utente', 'obiettivo', 'fascia', 'prezzo_massimo')
    list_filter = ('utente', 'fascia', 'obiettivo')
    search_fields = ('calciatore_stagione__calciatore__cognome',)
