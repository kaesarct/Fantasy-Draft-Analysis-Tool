from django.contrib.auth.models import AbstractUser
from django.db import models

class FantaPresidente(AbstractUser):
    telegram_user_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        help_text="ID utente Telegram per il collegamento al bot. Dato personale: accesso ristretto allo staff.",
    )

    class Meta:
        verbose_name = "FantaPresidente"
        verbose_name_plural = "FantaPresidenti"
