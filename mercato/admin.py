from django.contrib import admin, messages

from services.scambi import applica_prezzi_scambio
from .models import Asta, OffertaAsta, Scambio, ScambioItem


class OffertaAstaInline(admin.TabularInline):
    model = OffertaAsta
    extra = 0
    autocomplete_fields = ('calciatore_stagione', 'squadra_vincitrice', 'chiamata_da')


@admin.register(Asta)
class AstaAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'lega', 'stagione', 'data', 'stato')
    list_filter = ('stagione', 'tipo', 'stato', 'lega')
    inlines = [OffertaAstaInline]


@admin.register(OffertaAsta)
class OffertaAstaAdmin(admin.ModelAdmin):
    list_display = ('asta', 'calciatore_stagione', 'squadra_vincitrice', 'prezzo_finale', 'chiamata_da')
    list_filter = ('asta__lega', 'asta__stagione')
    search_fields = ('calciatore_stagione__calciatore__nome', 'squadra_vincitrice__nome')
    autocomplete_fields = ('calciatore_stagione', 'squadra_vincitrice', 'chiamata_da')


class ScambioItemInline(admin.TabularInline):
    model = ScambioItem
    extra = 0
    autocomplete_fields = ('squadra_cedente', 'ingaggio')
    readonly_fields = ('prezzo_assegnato',)


@admin.register(Scambio)
class ScambioAdmin(admin.ModelAdmin):
    list_display = ('squadra_a', 'squadra_b', 'stagione', 'stato', 'data_scambio')
    list_filter = ('stagione', 'stato')
    autocomplete_fields = ('squadra_a', 'squadra_b')
    inlines = [ScambioItemInline]
    actions = ['azione_preview_prezzi', 'azione_applica_prezzi']

    @admin.action(description="Anteprima prezzi post-scambio (non salva)")
    def azione_preview_prezzi(self, request, queryset):
        for scambio in queryset:
            try:
                prezzi = applica_prezzi_scambio(scambio, salva=False)
            except ValueError as e:
                self.message_user(request, f"{scambio}: {e}", messages.ERROR)
                continue
            righe = []
            for item in scambio.items.all():
                righe.append(f"{item.ingaggio} → {prezzi.get(item.id, item.ingaggio.costo_acquisto)}")
            self.message_user(request, f"{scambio}: " + "; ".join(righe), messages.INFO)

    @admin.action(description="Applica prezzi post-scambio (salva)")
    def azione_applica_prezzi(self, request, queryset):
        for scambio in queryset:
            try:
                applica_prezzi_scambio(scambio, salva=True)
            except ValueError as e:
                self.message_user(request, f"{scambio}: {e}", messages.ERROR)
                continue
            self.message_user(request, f"{scambio}: prezzi applicati.", messages.SUCCESS)
