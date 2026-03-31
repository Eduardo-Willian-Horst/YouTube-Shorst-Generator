from django.urls import path
from . import views

urlpatterns = [
    path('', views.getData, name='getData'),
    path('is-processed/', views.check_video_processed, name='check_video_processed'),
    path('mark-processed/', views.mark_video_processed, name='mark_video_processed'),
    path('in-progress/', views.get_in_progress_videos, name='get_in_progress_videos'),
    path('api/flow/run/', views.api_flow_run, name='api_flow_run'),
    path('api/configs/', views.api_channel_configs, name='api_channel_configs'),
    path('api/configs/<int:config_id>/', views.api_channel_config_detail, name='api_channel_config_detail'),
    path('api/credentials/', views.api_channel_credentials, name='api_channel_credentials'),
    path('api/credentials/<int:cred_id>/', views.api_channel_credentials_detail, name='api_channel_credentials_detail'),
    path('api/credentials/<int:cred_id>/upload-secret/', views.api_upload_client_secret, name='api_upload_client_secret'),
    path('api/credentials/<int:cred_id>/verify/', views.api_verify_credentials, name='api_verify_credentials'),
    path('api/videos/processed/', views.api_processed_videos, name='api_processed_videos'),
    path('frontend/', views.frontend, name='frontend'),
    path('api/panel/flow/runs/', views.api_panel_flow_runs, name='api_panel_flow_runs'),
    path('api/panel/flow/runs/<int:run_id>/', views.api_panel_flow_run_detail, name='api_panel_flow_run_detail'),
    path('api/panel/flow/runs/<int:run_id>/logs/', views.api_panel_flow_run_logs, name='api_panel_flow_run_logs'),
    path('api/panel/flow/run/', views.api_panel_flow_run, name='api_panel_flow_run'),
]