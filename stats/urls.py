from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='import_dashboard'),
    path('task/<int:task_id>/', views.task_status, name='import_task_status'),
]
