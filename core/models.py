from django.db import models

class Stagione(models.Model):
    nome = models.CharField(max_length=9, unique=True, help_text="Es: 2023/2024")
    attiva = models.BooleanField(default=False, help_text="Segna la stagione attualmente in corso")

    data_inizio_serie_a = models.DateField(null=True, blank=True, help_text="Data della 1a giornata di Serie A")
    data_fine_serie_a = models.DateField(null=True, blank=True, help_text="Data dell'ultima giornata di Serie A")
    crediti_default = models.PositiveIntegerField(default=350, help_text="Crediti (FM) iniziali di default per le squadre della stagione")

    class Meta:
        verbose_name_plural = "Stagioni"

    def __str__(self):
        return self.nome

class SquadraReale(models.Model):
    nome = models.CharField(max_length=50, unique=True)
    sigla = models.CharField(max_length=3, unique=True)

    class Meta:
        verbose_name_plural = "Squadre Reali"

    def __str__(self):
        return self.nome

class ImportTask(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'In Attesa'),
        ('RUNNING', 'In Corso'),
        ('COMPLETED', 'Completato'),
        ('ERROR', 'Errore'),
    ]
    
    task_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_items = models.IntegerField(default=0)
    processed_items = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Task di Importazione"
        verbose_name_plural = "Task di Importazione"

    def __str__(self):
        return f"{self.task_name} - {self.get_status_display()} ({self.processed_items}/{self.total_items})"
