from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/import-dashboard/', include('stats.urls')),
    path('admin/', admin.site.urls),
]
