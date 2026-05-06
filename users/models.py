from django.contrib.auth.models import AbstractUser
from django.db import models

class FantaPresidente(AbstractUser):
    class Meta:
        verbose_name = "FantaPresidente"
        verbose_name_plural = "FantaPresidenti"
