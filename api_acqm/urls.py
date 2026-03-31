"""
URL configuration for api_acqm project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('getData.urls')),
    path('getData/', include('getData.urls')),
    path('download/', include('download.urls')),
    path('transcribe/', include('transcribe.urls')),
    path('upload/', include('upload.urls')),
    path('gpu/', include('gpu.urls')),
]
