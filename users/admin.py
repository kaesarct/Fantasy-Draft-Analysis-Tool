from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import FantaPresidente

@admin.register(FantaPresidente)
class FantaPresidenteAdmin(UserAdmin):
    pass
