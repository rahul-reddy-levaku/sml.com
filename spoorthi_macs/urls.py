from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.conf import settings
from django.urls import re_path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('companies.urls')),
    re_path(r'^favicon\.ico$', serve, {'path': 'images/smlLogo1.ico', 'document_root': settings.STATIC_ROOT}),# Routes everything to your app
]

# Media files (for photo uploads)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
