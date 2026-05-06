from django.db import models

class Stagione(models.Model):
    nome = models.CharField(max_length=9, unique=True, help_text="Es: 2023/2024")
    attiva = models.BooleanField(default=False, help_text="Segna la stagione attualmente in corso")

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
