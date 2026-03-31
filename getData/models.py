from django.db import models
import base64


class ChannelCredentials(models.Model):
    channel_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="ID do canal de destino")
    youtube_api_key = models.CharField(max_length=200, help_text="API Key do YouTube para buscar dados")
    client_secret_file_path = models.CharField(max_length=500, null=True, blank=True, help_text="Caminho local do arquivo client_secret.json (deprecated, usar client_secret_r2_key)")
    client_secret_r2_key = models.CharField(max_length=500, null=True, blank=True, help_text="Chave R2 do arquivo client_secret.json")
    token_data = models.BinaryField(null=True, blank=True, help_text="Token OAuth serializado (pickle)")
    token_file_path = models.CharField(max_length=500, null=True, blank=True, help_text="Caminho alternativo do arquivo token.pickle (se não usar token_data)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'channel_credentials'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Credenciais do canal {self.channel_id}"
    
    def get_token_data(self):
        if self.token_data:
            return base64.b64decode(self.token_data)
        return None
    
    def set_token_data(self, token_bytes):
        if token_bytes:
            self.token_data = base64.b64encode(token_bytes)
        else:
            self.token_data = None


class ChannelConfig(models.Model):
    target_channel_id = models.CharField(max_length=100, unique=True, db_index=True, help_text="ID do canal de destino (seu canal)")
    source_channel_ids = models.TextField(help_text="IDs dos canais fonte separados por vírgula")
    credentials = models.ForeignKey(ChannelCredentials, on_delete=models.SET_NULL, null=True, blank=True, related_name='channel_configs', help_text="Credenciais de autenticação do canal")
    upload_category_id = models.CharField(max_length=20, default="17", help_text="Category ID usada no upload para este canal")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'channel_configs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Canal {self.target_channel_id}"
    
    def get_source_channel_ids_list(self):
        return [c.strip() for c in self.source_channel_ids.split(',') if c.strip()]
    
    def get_api_key(self):
        if self.credentials:
            return self.credentials.youtube_api_key
        return None



class ProcessedVideo(models.Model):
    video_id = models.CharField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'processed_videos'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.video_id


class InProgressVideo(models.Model):
    video_id = models.CharField(max_length=100, db_index=True)
    source_channel_id = models.CharField(max_length=100, db_index=True, help_text="ID do canal fonte (de onde veio o vídeo)")
    target_channel_id = models.CharField(max_length=100, db_index=True, help_text="ID do canal de destino (onde será feito upload)")
    is_finished = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'in_progress_videos'
        ordering = ['-created_at']
        unique_together = [['video_id', 'target_channel_id']]

    def __str__(self):
        return f"{self.video_id} -> {self.target_channel_id}"


class FlowRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        RUNNING = "running", "Executando"
        SUCCESS = "success", "Sucesso"
        ERROR = "error", "Erro"

    start_from = models.CharField(max_length=50, db_index=True)
    target_channel_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    video_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    r2_prefix = models.CharField(max_length=200, blank=True, default="")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    current_step = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "flow_runs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"FlowRun#{self.id} {self.status}"


class FlowStepRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        RUNNING = "running", "Executando"
        SUCCESS = "success", "Sucesso"
        ERROR = "error", "Erro"
        SKIPPED = "skipped", "Ignorado"

    flow_run = models.ForeignKey(FlowRun, on_delete=models.CASCADE, related_name="steps")
    step_name = models.CharField(max_length=50, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    ok_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "flow_step_runs"
        ordering = ["id"]
        unique_together = [["flow_run", "step_name"]]

    def __str__(self) -> str:
        return f"{self.flow_run_id}:{self.step_name} {self.status}"


class FlowLogLine(models.Model):
    class Level(models.TextChoices):
        DEBUG = "debug", "Debug"
        INFO = "info", "Info"
        WARNING = "warning", "Aviso"
        ERROR = "error", "Erro"

    flow_run = models.ForeignKey(FlowRun, on_delete=models.CASCADE, related_name="logs")
    step_name = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO, db_index=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "flow_log_lines"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.flow_run_id}:{self.level}:{self.step_name or '-'}"
