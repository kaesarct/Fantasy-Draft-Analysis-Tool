from django.urls import path
from . import views_analisi

urlpatterns = [
    path('giocatore/', views_analisi.giocatore_view, name='analisi_giocatore'),
    path('classifica/', views_analisi.classifica_view, name='analisi_classifica'),
    path('confronto/', views_analisi.confronto_view, name='analisi_confronto'),
    path('run-ai-analysis/', views_analisi.run_ai_analysis, name='run_ai_analysis'),
    path('report/', views_analisi.visualizza_report, name='visualizza_report'),
]
