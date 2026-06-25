from django.db import models

from core.models import Stagione
from fantacalcio.models import FantaSquadra, Ingaggio
from players.models import CalciatoreStagione


class Asta(models.Model):
    class Tipo(models.TextChoices):
        INIZIALE = 'INIZIALE', 'Asta iniziale'
        RIPARAZIONE = 'RIPARAZIONE', 'Mercato di riparazione'

    class Stato(models.TextChoices):
        PROGRAMMATA = 'PROGRAMMATA', 'Programmata'
        IN_CORSO = 'IN_CORSO', 'In corso'
        COMPLETATA = 'COMPLETATA', 'Completata'

    stagione = models.ForeignKey(Stagione, on_delete=models.CASCADE, related_name='aste')
    lega = models.CharField(max_length=50, help_text="Es. GOLD / BRONZE / CARBON")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.INIZIALE)
    data = models.DateField(null=True, blank=True)
    stato = models.CharField(max_length=12, choices=Stato.choices, default=Stato.PROGRAMMATA)
    fantalab_url = models.URLField(null=True, blank=True)

    class Meta:
        verbose_name = "Asta"
        verbose_name_plural = "Aste"

    def __str__(self):
        return f"Asta {self.get_tipo_display()} {self.lega} ({self.stagione})"


class OffertaAsta(models.Model):
    asta = models.ForeignKey(Asta, on_delete=models.CASCADE, related_name='offerte')
    calciatore_stagione = models.ForeignKey(CalciatoreStagione, on_delete=models.CASCADE, related_name='offerte_asta')
    squadra_vincitrice = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='aggiudicazioni')
    prezzo_finale = models.PositiveIntegerField()
    chiamata_da = models.ForeignKey(
        FantaSquadra, on_delete=models.SET_NULL, related_name='chiamate', null=True, blank=True,
    )
    ordine_chiamata = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Offerta d'asta"
        verbose_name_plural = "Offerte d'asta"

    def __str__(self):
        return f"{self.calciatore_stagione} -> {self.squadra_vincitrice.nome} ({self.prezzo_finale})"


class Scambio(models.Model):
    class Stato(models.TextChoices):
        PROPOSTO = 'PROPOSTO', 'Proposto'
        CONFERMATO = 'CONFERMATO', 'Confermato'
        RIFIUTATO = 'RIFIUTATO', 'Rifiutato'

    stagione = models.ForeignKey(Stagione, on_delete=models.CASCADE, related_name='scambi')
    data_scambio = models.DateField(null=True, blank=True)
    squadra_a = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='scambi_come_a')
    squadra_b = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='scambi_come_b')
    stato = models.CharField(max_length=12, choices=Stato.choices, default=Stato.PROPOSTO)
    confermato_il = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = "Scambio"
        verbose_name_plural = "Scambi"

    def __str__(self):
        return f"Scambio {self.squadra_a.nome} <-> {self.squadra_b.nome} ({self.get_stato_display()})"


class ScambioItem(models.Model):
    scambio = models.ForeignKey(Scambio, on_delete=models.CASCADE, related_name='items')
    squadra_cedente = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='cessioni_scambio')
    ingaggio = models.ForeignKey(Ingaggio, on_delete=models.CASCADE, related_name='item_scambi')
    prezzo_assegnato = models.PositiveIntegerField(null=True, blank=True, help_text="Prezzo post-scambio calcolato")

    class Meta:
        verbose_name = "Giocatore in scambio"
        verbose_name_plural = "Giocatori in scambio"

    def __str__(self):
        return f"{self.ingaggio} da {self.squadra_cedente.nome}"
