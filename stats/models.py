from django.db import models
from players.models import CalciatoreStagione

class VotoPartita(models.Model):
    calciatore_stagione = models.ForeignKey(CalciatoreStagione, on_delete=models.CASCADE, related_name='voti')
    giornata = models.PositiveIntegerField()
    voto_base = models.DecimalField('Voto', max_digits=4, decimal_places=2, null=True, blank=True)
    fanta_voto = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    
    gol_fatti = models.PositiveIntegerField('Gf', default=0)
    gol_subiti = models.PositiveIntegerField('Gs', default=0)
    rigori_parati = models.PositiveIntegerField('Rp', default=0)
    rigori_sbagliati = models.PositiveIntegerField('Rs', default=0)
    rigori_fatti = models.PositiveIntegerField('Rf', default=0)
    autogol = models.PositiveIntegerField('Au', default=0)
    ammonizioni = models.PositiveIntegerField('Amm', default=0)
    espulsioni = models.PositiveIntegerField('Esp', default=0)
    assist = models.PositiveIntegerField('Ass', default=0)

    class Meta:
        verbose_name_plural = "Voti Partita"
        unique_together = ('calciatore_stagione', 'giornata')

class StatisticaCalciatore(models.Model):
    calciatore_stagione = models.OneToOneField(CalciatoreStagione, on_delete=models.CASCADE, related_name='statistiche_riassuntive')
    
    partite_a_voto = models.PositiveIntegerField('Pv', default=0)
    media_voto = models.DecimalField('Mv', max_digits=4, decimal_places=2, default=0.0)
    fanta_media = models.DecimalField('Fm', max_digits=4, decimal_places=2, default=0.0)
    
    gol_fatti = models.PositiveIntegerField('Gf', default=0)
    gol_subiti = models.PositiveIntegerField('Gs', default=0)
    rigori_parati = models.PositiveIntegerField('Rp', default=0)
    rigori_calciati = models.PositiveIntegerField('Rc', default=0)
    rigori_fatti = models.PositiveIntegerField('R+', default=0)
    rigori_sbagliati = models.PositiveIntegerField('R-', default=0)
    assist = models.PositiveIntegerField('Ass', default=0)
    ammonizioni = models.PositiveIntegerField('Amm', default=0)
    espulsioni = models.PositiveIntegerField('Esp', default=0)
    autogol = models.PositiveIntegerField('Au', default=0)
