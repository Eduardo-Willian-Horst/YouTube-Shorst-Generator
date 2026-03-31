from django.urls import path
from . import views

urlpatterns = [
    path('', views.download, name='download'),
    path('limpar-temporarios/', views.limpar_arquivos_temporarios, name='limpar_arquivos_temporarios'),
]