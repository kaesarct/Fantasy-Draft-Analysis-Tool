from django.db import models

from core.models import Stagione
from fantacalcio.models import FantaSquadra, Ingaggio


class Competizione(models.Model):
    class Tipo(models.TextChoices):
        LEGA = 'LEGA', 'Lega (campionato)'
        COPPA = 'COPPA', 'Coppa'
        SUPERCOPPA = 'SUPERCOPPA', 'Super Coppa'

    class Stato(models.TextChoices):
        NON_INIZIATA = 'NON_INIZIATA', 'Non iniziata'
        IN_CORSO = 'IN_CORSO', 'In corso'
        COMPLETATA = 'COMPLETATA', 'Completata'

    stagione = models.ForeignKey(Stagione, on_delete=models.CASCADE, related_name='competizioni')
    nome = models.CharField(max_length=50, help_text="Es. GOLD, BRONZE, CIEMPIONS, UEFA, COPPA_ITALIA…")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.LEGA)
    stato = models.CharField(max_length=12, choices=Stato.choices, default=Stato.NON_INIZIATA)

    class Meta:
        verbose_name = "Competizione"
        verbose_name_plural = "Competizioni"
        unique_together = ('stagione', 'nome')

    def __str__(self):
        return f"{self.nome} ({self.stagione})"


class Giornata(models.Model):
    class Stato(models.TextChoices):
        PROGRAMMATA = 'PROGRAMMATA', 'Programmata'
        COMPLETATA = 'COMPLETATA', 'Completata'
        RINVIATA = 'RINVIATA', 'Rinviata'

    competizione = models.ForeignKey(Competizione, on_delete=models.CASCADE, related_name='giornate')
    numero = models.PositiveIntegerField(help_text="Numero giornata nella competizione")
    giornata_serie_a = models.PositiveIntegerField(help_text="Giornata di Serie A corrispondente")
    data = models.DateField(null=True, blank=True)
    stato = models.CharField(max_length=12, choices=Stato.choices, default=Stato.PROGRAMMATA)

    class Meta:
        verbose_name = "Giornata"
        verbose_name_plural = "Giornate"
        unique_together = ('competizione', 'numero')
        ordering = ['competizione', 'numero']

    def __str__(self):
        return f"{self.competizione.nome} - G{self.numero}"


class Partita(models.Model):
    class Risultato(models.TextChoices):
        CASA = 'CASA', 'Vittoria casa'
        OSPITE = 'OSPITE', 'Vittoria ospite'
        PAREGGIO = 'PAREGGIO', 'Pareggio'

    giornata = models.ForeignKey(Giornata, on_delete=models.CASCADE, related_name='partite')
    squadra_casa = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='partite_casa')
    squadra_ospite = models.ForeignKey(
        FantaSquadra,
        on_delete=models.CASCADE,
        related_name='partite_ospite',
        null=True,
        blank=True,
        help_text="Vuoto in caso di turno di riposo (bye)",
    )

    punteggio_casa = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    punteggio_ospite = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    gol_casa = models.PositiveIntegerField(null=True, blank=True)
    gol_ospite = models.PositiveIntegerField(null=True, blank=True)
    risultato = models.CharField(max_length=8, choices=Risultato.choices, null=True, blank=True)

    class Meta:
        verbose_name = "Partita"
        verbose_name_plural = "Partite"

    def __str__(self):
        ospite = self.squadra_ospite.nome if self.squadra_ospite else "Riposo"
        return f"{self.squadra_casa.nome} vs {ospite}"


class Classifica(models.Model):
    competizione = models.ForeignKey(Competizione, on_delete=models.CASCADE, related_name='classifica')
    squadra = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='posizioni_classifica')

    giocate = models.PositiveIntegerField(default=0)
    vinte = models.PositiveIntegerField(default=0)
    pareggiate = models.PositiveIntegerField(default=0)
    perse = models.PositiveIntegerField(default=0)
    punti = models.IntegerField(default=0)
    totale_fanta_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    gol_fatti = models.IntegerField(default=0)
    gol_subiti = models.IntegerField(default=0)
    aggiornata_il = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Classifica"
        verbose_name_plural = "Classifiche"
        unique_together = ('competizione', 'squadra')
        ordering = ['-punti', '-totale_fanta_score']

    def __str__(self):
        return f"{self.squadra.nome} - {self.punti} pt"


class Formazione(models.Model):
    class Fonte(models.TextChoices):
        WEB = 'WEB', 'Web'
        TELEGRAM = 'TELEGRAM', 'Telegram'
        SETTIMANA_PRECEDENTE = 'PREC', 'Settimana precedente'

    squadra = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='formazioni')
    partita = models.ForeignKey(
        Partita,
        on_delete=models.SET_NULL,
        related_name='formazioni',
        null=True,
        blank=True,
        help_text="Vuoto per competizioni indipendenti (es. Ciempions/UEFA)",
    )
    giornata_serie_a = models.PositiveIntegerField(help_text="Giornata di Serie A di riferimento per i voti")
    modulo = models.CharField(max_length=10, blank=True, help_text="Es. 4-3-3")
    inviata_il = models.DateTimeField(null=True, blank=True)
    fonte = models.CharField(max_length=10, choices=Fonte.choices, default=Fonte.WEB)

    class Meta:
        verbose_name = "Formazione"
        verbose_name_plural = "Formazioni"

    def __str__(self):
        return f"Formazione {self.squadra.nome} - G{self.giornata_serie_a}"


class FormazioneGiocatore(models.Model):
    class Posizione(models.TextChoices):
        TITOLARE = 'TITOLARE', 'Titolare'
        PANCHINA = 'PANCHINA', 'Panchina'

    formazione = models.ForeignKey(Formazione, on_delete=models.CASCADE, related_name='giocatori')
    ingaggio = models.ForeignKey(Ingaggio, on_delete=models.CASCADE, related_name='convocazioni')
    posizione = models.CharField(max_length=10, choices=Posizione.choices)
    ordine_panchina = models.PositiveIntegerField(null=True, blank=True, help_text="Ordine subentro (1=primo)")
    is_riserva_ufficio = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Giocatore in formazione"
        verbose_name_plural = "Giocatori in formazione"
        unique_together = ('formazione', 'ingaggio')
        ordering = ['posizione', 'ordine_panchina']

    def __str__(self):
        return f"{self.ingaggio} ({self.get_posizione_display()})"


class PunteggioSquadraPartita(models.Model):
    partita = models.ForeignKey(Partita, on_delete=models.CASCADE, related_name='punteggi')
    squadra = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='punteggi_partita')

    totale_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    modificatore_difesa = models.IntegerField(default=0)
    gol_fanta = models.PositiveIntegerField(default=0)
    dettagli = models.JSONField(default=dict, blank=True, help_text="Dettaglio calcolo (voti, sostituzioni, modificatore)")

    class Meta:
        verbose_name = "Punteggio squadra"
        verbose_name_plural = "Punteggi squadra"
        unique_together = ('partita', 'squadra')

    def __str__(self):
        return f"{self.squadra.nome} - {self.totale_score} ({self.partita})"
