from django.contrib import admin, messages

from services.classifiche import aggiorna_classifica
from services.scoring import calcola_partita
from .models import (
    Competizione, Giornata, Partita, Classifica,
    Formazione, FormazioneGiocatore, PunteggioSquadraPartita,
)


@admin.register(Competizione)
class CompetizioneAdmin(admin.ModelAdmin):
    list_display = ('nome', 'stagione', 'tipo', 'stato')
    list_filter = ('stagione', 'tipo', 'stato')
    search_fields = ('nome',)
    actions = ['azione_aggiorna_classifica']

    @admin.action(description="Aggiorna classifica")
    def azione_aggiorna_classifica(self, request, queryset):
        for competizione in queryset:
            aggiorna_classifica(competizione)
        self.message_user(request, f"Classifica aggiornata per {queryset.count()} competizione/i.", messages.SUCCESS)


class PartitaInline(admin.TabularInline):
    model = Partita
    extra = 0
    autocomplete_fields = ('squadra_casa', 'squadra_ospite')


@admin.register(Giornata)
class GiornataAdmin(admin.ModelAdmin):
    list_display = ('competizione', 'numero', 'giornata_serie_a', 'data', 'stato')
    list_filter = ('competizione', 'stato')
    inlines = [PartitaInline]
    actions = ['azione_calcola_giornata']

    @admin.action(description="Calcola giornata (punteggi + classifica)")
    def azione_calcola_giornata(self, request, queryset):
        partite_calcolate = 0
        for giornata in queryset:
            for partita in giornata.partite.all():
                calcola_partita(partita)
                partite_calcolate += 1
            giornata.stato = Giornata.Stato.COMPLETATA
            giornata.save()
            aggiorna_classifica(giornata.competizione)
        self.message_user(request, f"Calcolate {partite_calcolate} partita/e e aggiornate le classifiche.", messages.SUCCESS)


@admin.register(Partita)
class PartitaAdmin(admin.ModelAdmin):
    list_display = ('giornata', 'squadra_casa', 'squadra_ospite', 'punteggio_casa', 'punteggio_ospite', 'gol_casa', 'gol_ospite', 'risultato')
    list_filter = ('giornata__competizione',)
    search_fields = ('squadra_casa__nome', 'squadra_ospite__nome')
    autocomplete_fields = ('squadra_casa', 'squadra_ospite')
    actions = ['azione_calcola_partita']

    @admin.action(description="Calcola partita")
    def azione_calcola_partita(self, request, queryset):
        for partita in queryset:
            calcola_partita(partita)
        self.message_user(request, f"Calcolate {queryset.count()} partita/e.", messages.SUCCESS)


@admin.register(Classifica)
class ClassificaAdmin(admin.ModelAdmin):
    list_display = ('competizione', 'squadra', 'punti', 'giocate', 'vinte', 'pareggiate', 'perse', 'gol_fatti', 'gol_subiti', 'totale_fanta_score')
    list_filter = ('competizione',)


class FormazioneGiocatoreInline(admin.TabularInline):
    model = FormazioneGiocatore
    extra = 0
    autocomplete_fields = ('ingaggio',)


@admin.register(Formazione)
class FormazioneAdmin(admin.ModelAdmin):
    list_display = ('squadra', 'giornata_serie_a', 'partita', 'modulo', 'fonte', 'inviata_il')
    list_filter = ('fonte', 'giornata_serie_a')
    autocomplete_fields = ('squadra', 'partita')
    inlines = [FormazioneGiocatoreInline]


@admin.register(PunteggioSquadraPartita)
class PunteggioSquadraPartitaAdmin(admin.ModelAdmin):
    list_display = ('partita', 'squadra', 'totale_score', 'modificatore_difesa', 'gol_fanta')
    list_filter = ('squadra',)
