from django.db import models
from django.conf import settings
from players.models import CalciatoreStagione

class AnalisiPreAsta(models.Model):
    calciatore_stagione = models.ForeignKey(CalciatoreStagione, on_delete=models.CASCADE, related_name='analisi_pre_asta')
    utente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='strategie_asta')
    
    obiettivo = models.CharField('Obiett.', max_length=50, blank=True)
    # fascia: valore libero (es. 'Top', 'A', 'B', 'C', ...) come usato da Fantalab
    fascia = models.CharField('Fascia', max_length=20, null=True, blank=True)
    prezzo_massimo = models.PositiveIntegerField('Prezzo', default=0)
    budget_percentuale = models.DecimalField('Budget %', max_digits=5, decimal_places=2, help_text="Su base budget 350", null=True, blank=True)
    pma = models.DecimalField('PMA', max_digits=6, decimal_places=2, null=True, blank=True, help_text="Prezzo Medio Altre Leghe")
    quotazione = models.PositiveIntegerField('Quo', default=0)
    
    titolarita = models.PositiveIntegerField('Titolarità', null=True, blank=True)
    affidabilita = models.PositiveIntegerField('Affidabilità', null=True, blank=True)
    integrita = models.PositiveIntegerField('Integrità', null=True, blank=True)
    
    commento = models.TextField('Commento', blank=True)
    nota_1 = models.CharField('Nota 1', max_length=255, blank=True)
    nota_2 = models.CharField('Nota 2', max_length=255, blank=True)
    nota_3 = models.CharField('Nota 3', max_length=255, blank=True)
    nota_4 = models.CharField('Nota 4', max_length=255, blank=True)
    nota_5 = models.CharField('Nota 5', max_length=255, blank=True)
    
    fmv_exp = models.DecimalField('FMV Exp.', max_digits=4, decimal_places=2, null=True, blank=True)
    pt_tit = models.DecimalField('Pt. Tit.', max_digits=5, decimal_places=2, null=True, blank=True)
    minuti = models.PositiveIntegerField('Minuti', null=True, blank=True)
    pt_inf = models.DecimalField('Pt. Inf.', max_digits=5, decimal_places=2, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Analisi Pre-Asta"
        unique_together = ('calciatore_stagione', 'utente')

    def __str__(self):
        return f"Strategia {self.utente.username} - {self.calciatore_stagione.calciatore.nome}"
