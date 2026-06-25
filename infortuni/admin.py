from django.contrib import admin, messages

from .models import Infortunio, SostituzioneTemporanea


@admin.register(Infortunio)
class InfortunioAdmin(admin.ModelAdmin):
    list_display = ('calciatore_stagione', 'data_bollettino', 'rientro_stimato', 'settimane_out', 'qualifica_sostituzione', 'rientro_effettivo')
    list_filter = ('qualifica_sostituzione', 'calciatore_stagione__stagione')
    search_fields = ('calciatore_stagione__calciatore__nome',)
    autocomplete_fields = ('calciatore_stagione',)
    readonly_fields = ('settimane_out', 'qualifica_sostituzione')
    actions = ['azione_calcola_qualifica']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.calcola_qualifica_sostituzione(salva=True)

    @admin.action(description="Calcola qualifica sostituzione (8 settimane)")
    def azione_calcola_qualifica(self, request, queryset):
        for infortunio in queryset:
            infortunio.calcola_qualifica_sostituzione(salva=True)
        self.message_user(request, f"Ricalcolata la qualifica per {queryset.count()} infortunio/i.", messages.SUCCESS)


@admin.register(SostituzioneTemporanea)
class SostituzioneTemporaneaAdmin(admin.ModelAdmin):
    list_display = ('squadra', 'calciatore_sostituto', 'ingaggio_sostituito', 'numero_sostituzione', 'attivata_il', 'terminata_il', 'motivo_fine')
    list_filter = ('squadra', 'motivo_fine')
    autocomplete_fields = ('squadra', 'infortunio', 'ingaggio_sostituito', 'calciatore_sostituto')
