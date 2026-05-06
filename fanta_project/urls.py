from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from stats.views_analisi import home_view

urlpatterns = [
    path('admin/import-dashboard/', include('stats.urls')),
    path('admin/', admin.site.urls),

    # Home dashboard
    path('', home_view, name='home'),

    # Auth
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),

    # Analisi incrociata dati
    path('analisi/', include('stats.urls_analisi')),

    # Gestione fantacompetizioni
    path('leghe/', include('fantacalcio.urls')),
]
