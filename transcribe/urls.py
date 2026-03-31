from django.urls import path
from . import views

urlpatterns = [
    path('', views.transcribe, name='transcribe'),
    path('extract-audio/', views.extract_audio, name='extract_audio'),
]