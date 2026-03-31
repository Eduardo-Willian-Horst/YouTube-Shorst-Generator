from django.urls import path
from . import views

urlpatterns = [
    path('processar-clipes/', views.processar_clipes_virais, name='processar_clipes_virais'),
    path('status-processamento/', views.verificar_status_processamento, name='verificar_status_processamento'),
    path('status-processamento/<int:processamento_id>/', views.verificar_status_processamento, name='verificar_status_processamento_id'),
    path('converter-916/', views.converter_video_916, name='converter_video_916'),
]
