from django.contrib import admin
from .models import Stagione, SquadraReale

@admin.register(Stagione)
class StagioneAdmin(admin.ModelAdmin):
    list_display = ('nome', 'attiva')
    list_editable = ('attiva',)

@admin.register(SquadraReale)
class SquadraRealeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'sigla')
    search_fields = ('nome', 'sigla')
