from django.contrib import admin
from .models import AnalisiPreAsta

@admin.register(AnalisiPreAsta)
class AnalisiPreAstaAdmin(admin.ModelAdmin):
    list_display = ('calciatore_stagione', 'utente', 'fascia', 'prezzo_massimo', 'budget_percentuale', 'pma')
    list_filter = ('utente', 'fascia')
    search_fields = ('calciatore_stagione__calciatore__cognome',)
