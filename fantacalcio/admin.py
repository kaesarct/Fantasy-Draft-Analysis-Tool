from django.contrib import admin
from .models import Lega, Franchise, FantaSquadra, Ingaggio

@admin.register(Lega)
class LegaAdmin(admin.ModelAdmin):
    list_display = ('nome',)

@admin.register(Franchise)
class FranchiseAdmin(admin.ModelAdmin):
    list_display = ('nome', 'stagione_fondazione')
    search_fields = ('nome',)

class IngaggioInline(admin.TabularInline):
    model = Ingaggio
    extra = 0
    autocomplete_fields = ('calciatore_stagione', 'sostituisce')
    fields = ('calciatore_stagione', 'costo_acquisto', 'tipo_acquisizione', 'attivo', 'data_acquisizione', 'data_cessione')

@admin.register(FantaSquadra)
class FantaSquadraAdmin(admin.ModelAdmin):
    list_display = ('nome', 'lega', 'stagione', 'franchise', 'crediti_iniziali', 'crediti_residui')
    list_filter = ('lega', 'stagione', 'franchise')
    search_fields = ('nome',)
    filter_horizontal = ('presidenti',)
    inlines = [IngaggioInline]

@admin.register(Ingaggio)
class IngaggioAdmin(admin.ModelAdmin):
    list_display = ('fantasquadra', 'calciatore_stagione', 'costo_acquisto', 'tipo_acquisizione', 'attivo')
    list_filter = ('attivo', 'tipo_acquisizione', 'fantasquadra__lega')
    search_fields = ('fantasquadra__nome', 'calciatore_stagione__calciatore__nome')
    autocomplete_fields = ('calciatore_stagione', 'sostituisce')
