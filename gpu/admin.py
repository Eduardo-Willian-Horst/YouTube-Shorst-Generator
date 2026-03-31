from django.contrib import admin
from .models import ProcessamentoClipes


@admin.register(ProcessamentoClipes)
class ProcessamentoClipesAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'total_videos', 'videos_processados', 'videos_sucesso', 'videos_erro', 'criado_em', 'finalizado_em']
    list_filter = ['status', 'criado_em']
    readonly_fields = ['criado_em', 'atualizado_em', 'finalizado_em']
    search_fields = ['id', 'videos_ids']