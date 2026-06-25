from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import FantaPresidente

@admin.register(FantaPresidente)
class FantaPresidenteAdmin(UserAdmin):
    # Dato personale (GDPR): visibile solo nell'admin (accesso ristretto a is_staff)
    fieldsets = UserAdmin.fieldsets + (
        ('Telegram', {'fields': ('telegram_user_id',)}),
    )
    list_display = UserAdmin.list_display + ('telegram_user_id',)
