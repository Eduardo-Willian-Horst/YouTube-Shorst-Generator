from django.db import models
from django.utils import timezone


class ProcessamentoClipes(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('processando', 'Processando'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
    ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente', db_index=True)
    total_videos = models.IntegerField(default=0)
    videos_processados = models.IntegerField(default=0)
    videos_sucesso = models.IntegerField(default=0)
    videos_erro = models.IntegerField(default=0)
    
    videos_ids = models.JSONField(default=list, help_text='Lista de IDs de vídeos sendo processados')
    resultados = models.JSONField(default=dict, help_text='Resultados do processamento por vídeo')
    erros = models.JSONField(default=list, help_text='Lista de vídeos com erro')
    
    erro = models.TextField(null=True, blank=True, help_text='Mensagem de erro geral se houver')
    
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'processamento_clipes'
        ordering = ['-criado_em']
        verbose_name = 'Processamento de Clipes'
        verbose_name_plural = 'Processamentos de Clipes'
    
    def __str__(self):
        return f"Processamento {self.id} - {self.status} ({self.videos_processados}/{self.total_videos})"