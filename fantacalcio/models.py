from django.db import models
from django.conf import settings
from core.models import Stagione
from players.models import CalciatoreStagione

class Lega(models.Model):
    nome = models.CharField(max_length=50)

    class Meta:
        verbose_name_plural = "Leghe"

    def __str__(self):
        return self.nome

class Franchise(models.Model):
    """Identità storica di una squadra, indipendente dalla composizione stagionale."""
    nome = models.CharField(max_length=100, help_text="Nome storico, es. 'I Dragoni'")
    logo = models.ImageField(upload_to='franchise_logos/', null=True, blank=True)
    stagione_fondazione = models.ForeignKey(
        Stagione,
        on_delete=models.PROTECT,
        related_name='franchigie_fondate',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Franchigia"
        verbose_name_plural = "Franchigie"

    def __str__(self):
        return self.nome

class FantaSquadra(models.Model):
    nome = models.CharField(max_length=100)
    lega = models.ForeignKey(Lega, on_delete=models.CASCADE, related_name='squadre')
    stagione = models.ForeignKey(Stagione, on_delete=models.CASCADE, related_name='fantasquadre')
    franchise = models.ForeignKey(
        Franchise,
        on_delete=models.SET_NULL,
        related_name='squadre_stagionali',
        null=True,
        blank=True,
        help_text="Identità storica (vuoto = squadra nuova senza storia)",
    )

    presidenti = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='fantasquadre')
    crediti_iniziali = models.PositiveIntegerField(default=350)
    crediti_residui = models.IntegerField(default=500)
    note_palmares = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Fantasquadre"
        unique_together = ('nome', 'stagione')

    def __str__(self):
        return f"{self.nome} - {self.lega} ({self.stagione})"

class Ingaggio(models.Model):
    """Rappresenta l'acquisto di un giocatore nella rosa di una fantasquadra (in una specifica stagione)"""

    class TipoAcquisizione(models.TextChoices):
        ASTA = 'ASTA', 'Asta'
        RIPARAZIONE = 'RIPARAZIONE', 'Mercato di riparazione'
        SOSTITUZIONE = 'SOSTITUZIONE', 'Sostituzione infortunio'
        SCAMBIO = 'SCAMBIO', 'Scambio'

    fantasquadra = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='rosa')
    calciatore_stagione = models.ForeignKey(CalciatoreStagione, on_delete=models.CASCADE, related_name='ingaggi')
    costo_acquisto = models.PositiveIntegerField()

    data_acquisizione = models.DateField(null=True, blank=True)
    data_cessione = models.DateField(null=True, blank=True, help_text="Valorizzata quando il giocatore lascia la rosa")
    attivo = models.BooleanField(default=True, help_text="True se attualmente in rosa")
    tipo_acquisizione = models.CharField(
        max_length=20,
        choices=TipoAcquisizione.choices,
        default=TipoAcquisizione.ASTA,
    )
    is_sub_temporaneo = models.BooleanField(default=False, help_text="True se sostituzione temporanea da infortunio")
    sostituisce = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name='sostituito_da',
        null=True,
        blank=True,
        help_text="L'ingaggio (titolare infortunato) che questo giocatore sostituisce",
    )

    class Meta:
        verbose_name_plural = "Ingaggi"
        constraints = [
            models.UniqueConstraint(
                fields=['fantasquadra', 'calciatore_stagione'],
                condition=models.Q(attivo=True),
                name='unique_ingaggio_attivo_per_squadra',
            ),
        ]

    def __str__(self):
        return f"{self.calciatore_stagione.calciatore.nome} a {self.fantasquadra.nome}"
