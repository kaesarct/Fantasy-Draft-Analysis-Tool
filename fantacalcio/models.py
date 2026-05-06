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

class FantaSquadra(models.Model):
    nome = models.CharField(max_length=100)
    lega = models.ForeignKey(Lega, on_delete=models.CASCADE, related_name='squadre')
    stagione = models.ForeignKey(Stagione, on_delete=models.CASCADE, related_name='fantasquadre')
    
    presidenti = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='fantasquadre')
    crediti_residui = models.IntegerField(default=500)

    class Meta:
        verbose_name_plural = "Fantasquadre"
        unique_together = ('nome', 'stagione')

    def __str__(self):
        return f"{self.nome} - {self.lega} ({self.stagione})"

class Ingaggio(models.Model):
    """Rappresenta l'acquisto di un giocatore nella rosa di una fantasquadra (in una specifica stagione)"""
    fantasquadra = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='rosa')
    calciatore_stagione = models.ForeignKey(CalciatoreStagione, on_delete=models.CASCADE, related_name='ingaggi')
    costo_acquisto = models.PositiveIntegerField()

    class Meta:
        verbose_name_plural = "Ingaggi"
        unique_together = ('fantasquadra', 'calciatore_stagione')

    def __str__(self):
        return f"{self.calciatore_stagione.calciatore.cognome} a {self.fantasquadra.nome}"
