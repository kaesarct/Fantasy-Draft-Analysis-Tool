from django.db import models
from core.models import Stagione, SquadraReale

class Calciatore(models.Model):
    RUOLI = [('P', 'Portiere'), ('D', 'Difensore'), ('C', 'Centrocampista'), ('A', 'Attaccante')]
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    ruolo_base = models.CharField(max_length=1, choices=RUOLI, help_text="Ruolo di default, può essere sovrascritto nella stagione")

    class Meta:
        verbose_name_plural = "Calciatori"
        unique_together = ('nome', 'cognome') 

    def __str__(self):
        return f"{self.cognome} {self.nome}"

class CalciatoreStagione(models.Model):
    """Lega un calciatore a una specifica stagione, permettendo il cambio di ruolo nel tempo"""
    calciatore = models.ForeignKey(Calciatore, on_delete=models.CASCADE, related_name='stagioni')
    stagione = models.ForeignKey(Stagione, on_delete=models.CASCADE, related_name='calciatori')
    squadra_reale = models.ForeignKey(SquadraReale, on_delete=models.CASCADE, related_name='roster')
    
    ruolo_stagione = models.CharField(max_length=1, choices=Calciatore.RUOLI)
    quotazione_iniziale = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name_plural = "Calciatori per Stagione"
        unique_together = ('calciatore', 'stagione')

    def __str__(self):
        return f"{self.calciatore} ({self.stagione})"
