from django.db import models

from fantacalcio.models import FantaSquadra, Ingaggio
from players.models import CalciatoreStagione


class Infortunio(models.Model):
    calciatore_stagione = models.ForeignKey(CalciatoreStagione, on_delete=models.CASCADE, related_name='infortuni')
    data_bollettino = models.DateField(help_text="Data del bollettino ufficiale")
    rientro_stimato = models.DateField(null=True, blank=True)
    rientro_possibile = models.DateField(null=True, blank=True, help_text="Rientro anticipato possibile")
    url_bollettino = models.URLField(null=True, blank=True)
    settimane_out = models.PositiveIntegerField(null=True, blank=True, help_text="Calcolato o inserito a mano")
    qualifica_sostituzione = models.BooleanField(default=False, help_text=">= 8 settimane (calcolato)")
    rientro_effettivo = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = "Infortunio"
        verbose_name_plural = "Infortuni"

    def __str__(self):
        return f"Infortunio {self.calciatore_stagione} ({self.data_bollettino})"

    def calcola_qualifica_sostituzione(self, salva=False):
        """Calcola settimane_out e qualifica_sostituzione secondo la logica 8 settimane.

        Delega la logica a services.infortuni per tenerla testabile e in un unico punto.
        """
        from services.infortuni import valuta_infortunio
        settimane, qualifica = valuta_infortunio(self)
        self.settimane_out = settimane
        self.qualifica_sostituzione = qualifica
        if salva:
            self.save(update_fields=['settimane_out', 'qualifica_sostituzione'])
        return qualifica


class SostituzioneTemporanea(models.Model):
    class MotivoFine(models.TextChoices):
        RIENTRO = 'RIENTRO', 'Rientro del titolare'
        FINE_STAGIONE = 'FINE_STAGIONE', 'Fine stagione'
        MANUALE = 'MANUALE', 'Manuale'

    squadra = models.ForeignKey(FantaSquadra, on_delete=models.CASCADE, related_name='sostituzioni_temporanee')
    infortunio = models.ForeignKey(Infortunio, on_delete=models.CASCADE, related_name='sostituzioni')
    ingaggio_sostituito = models.ForeignKey(
        Ingaggio, on_delete=models.CASCADE, related_name='sostituzioni_subite',
        help_text="L'ingaggio del titolare infortunato",
    )
    calciatore_sostituto = models.ForeignKey(
        CalciatoreStagione, on_delete=models.CASCADE, related_name='ingressi_sostituzione',
        help_text="Lo svincolato acquisito come sostituto",
    )
    prezzo_acquisto_sostituto = models.PositiveIntegerField(default=0)
    attivata_il = models.DateField(null=True, blank=True)
    terminata_il = models.DateField(null=True, blank=True)
    motivo_fine = models.CharField(max_length=14, choices=MotivoFine.choices, null=True, blank=True)
    numero_sostituzione = models.PositiveSmallIntegerField(default=1, help_text="1-3 (limite per squadra)")

    class Meta:
        verbose_name = "Sostituzione temporanea"
        verbose_name_plural = "Sostituzioni temporanee"

    def __str__(self):
        return f"Sub {self.numero_sostituzione}: {self.calciatore_sostituto} per {self.ingaggio_sostituito}"
