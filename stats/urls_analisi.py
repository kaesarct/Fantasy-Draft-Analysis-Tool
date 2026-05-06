from django.urls import path
from . import views_analisi

urlpatterns = [
    path('giocatore/', views_analisi.giocatore_view, name='analisi_giocatore'),
    path('classifica/', views_analisi.classifica_view, name='analisi_classifica'),
    path('confronto/', views_analisi.confronto_view, name='analisi_confronto'),
]
