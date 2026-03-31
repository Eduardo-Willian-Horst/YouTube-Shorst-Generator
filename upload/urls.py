from django.urls import path
from . import views

urlpatterns = [
    path('clip/', views.upload_clip, name='upload_clip'),
]