from django.urls import path
from . import views

urlpatterns = [
    path('', views.lega_list, name='lega_list'),
    path('<int:lega_id>/', views.lega_detail, name='lega_detail'),
    path('<int:lega_id>/squadra/crea/', views.squadra_crea, name='squadra_crea'),
    path('<int:lega_id>/squadra/<int:squadra_id>/modifica/', views.squadra_edit, name='squadra_edit'),
    path('<int:lega_id>/squadra/<int:squadra_id>/rosa/', views.rosa_view, name='rosa_view'),
    path('<int:lega_id>/squadra/<int:squadra_id>/rosa/<int:ingaggio_id>/rimuovi/', views.ingaggio_rimuovi, name='ingaggio_rimuovi'),
]
