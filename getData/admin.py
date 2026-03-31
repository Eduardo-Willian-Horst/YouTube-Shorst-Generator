from django.contrib import admin
from .models import ProcessedVideo, InProgressVideo, ChannelConfig, ChannelCredentials


@admin.register(ChannelCredentials)
class ChannelCredentialsAdmin(admin.ModelAdmin):
    list_display = ('channel_id', 'youtube_api_key', 'has_token', 'created_at')
    search_fields = ('channel_id', 'youtube_api_key')
    readonly_fields = ('created_at', 'updated_at', 'has_token')
    list_filter = ('created_at',)
    fields = ('channel_id', 'youtube_api_key', 'client_secret_file_path', 'token_file_path', 'token_data', 'has_token', 'created_at', 'updated_at')
    
    def has_token(self, obj):
        return bool(obj.token_data or obj.token_file_path)
    has_token.boolean = True
    has_token.short_description = 'Token configurado'


@admin.register(ChannelConfig)
class ChannelConfigAdmin(admin.ModelAdmin):
    list_display = ('target_channel_id', 'has_credentials', 'is_active', 'created_at')
    search_fields = ('target_channel_id', 'source_channel_ids')
    readonly_fields = ('created_at', 'updated_at', 'has_credentials')
    list_filter = ('is_active', 'created_at')
    fields = ('target_channel_id', 'source_channel_ids', 'credentials', 'is_active', 'has_credentials', 'created_at', 'updated_at')
    
    def has_credentials(self, obj):
        return bool(obj.credentials)
    has_credentials.boolean = True
    has_credentials.short_description = 'Credenciais configuradas'

@admin.register(ProcessedVideo)
class ProcessedVideoAdmin(admin.ModelAdmin):
    list_display = ('video_id', 'created_at')
    search_fields = ('video_id',)
    readonly_fields = ('created_at',)

@admin.register(InProgressVideo)
class InProgressVideoAdmin(admin.ModelAdmin):
    list_display = ('video_id', 'source_channel_id', 'target_channel_id', 'is_finished', 'created_at')
    search_fields = ('video_id', 'source_channel_id', 'target_channel_id')
    list_filter = ('is_finished', 'target_channel_id', 'source_channel_id', 'created_at')
    readonly_fields = ('created_at',)
