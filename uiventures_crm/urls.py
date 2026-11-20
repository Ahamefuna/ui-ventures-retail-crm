"""Root URL configuration for UI Ventures Retail CRM System."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("crm.urls")),
]
