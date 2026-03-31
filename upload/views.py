import os
import pickle
import tempfile
import ast
import base64
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from decouple import config
from getData.models import InProgressVideo, ChannelCredentials, ChannelConfig
from download.r2_storage import list_files_in_r2_prefix, download_file_from_r2, delete_file_from_r2, file_exists_in_r2
from .models import UploadedClip
from .title_utils import formatar_titulo_shorts

VALID_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')

def youtube_authenticator(channel_id=None):
    credentials = None
    channel_creds = None
    temp_client_secret_file = None
    
    if channel_id:
        try:
            channel_config = ChannelConfig.objects.select_related('credentials').get(target_channel_id=channel_id)
            if not channel_config.credentials:
                raise ValueError(f'Configuração encontrada para o canal {channel_id}, mas não há credenciais vinculadas')
            channel_creds = channel_config.credentials
        except ChannelConfig.DoesNotExist:
            raise ValueError(f'Configuração não encontrada para o canal {channel_id}')
    
    if channel_creds:
        token_data = None
        
        if channel_creds.token_file_path and os.path.exists(channel_creds.token_file_path):
            with open(channel_creds.token_file_path, 'rb') as token:
                credentials = pickle.load(token)
        elif channel_creds.token_data:
            token_bytes = channel_creds.get_token_data()
            if token_bytes:
                credentials = pickle.loads(token_bytes)
        
        if channel_creds.client_secret_r2_key:
            if not file_exists_in_r2(channel_creds.client_secret_r2_key):
                raise FileNotFoundError(f'Arquivo client_secret.json não encontrado no R2: {channel_creds.client_secret_r2_key}')
            
            temp_client_secret_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
            temp_client_secret_file.close()
            
            if not download_file_from_r2(channel_creds.client_secret_r2_key, temp_client_secret_file.name):
                os.unlink(temp_client_secret_file.name)
                raise FileNotFoundError(f'Falha ao baixar arquivo client_secret.json do R2: {channel_creds.client_secret_r2_key}')
            
            client_secret_file = temp_client_secret_file.name
        elif channel_creds.client_secret_file_path:
            client_secret_file = channel_creds.client_secret_file_path
            if not os.path.exists(client_secret_file):
                raise FileNotFoundError(f'Arquivo client_secret.json não encontrado no caminho: {client_secret_file}')
        else:
            raise ValueError(f'Arquivo client_secret.json não configurado para o canal {channel_id}')
    else:
        TOKEN_FILENAME = 'token.pickle'
        if os.path.exists(TOKEN_FILENAME):
            with open(TOKEN_FILENAME, 'rb') as token:
                credentials = pickle.load(token)
        
        client_secret_file = config('YOUTUBE_CLIENT_SECRET_FILE', default='client_secret_2_855835542381-pihouujhhaiggalacnjv7sbngq1lvh7b.apps.googleusercontent.com.json')

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            scopes = ["https://www.googleapis.com/auth/youtube.upload"]
            
            if not os.path.exists(client_secret_file):
                raise FileNotFoundError(f'Arquivo de credenciais não encontrado: {client_secret_file}')
            
            import json
            with open(client_secret_file, 'r') as f:
                client_config = json.load(f)
            
            if 'installed' in client_config:
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, scopes)
                redirect_uris = client_config['installed'].get('redirect_uris', ['http://localhost'])
            elif 'web' in client_config:
                redirect_uris = client_config['web'].get('redirect_uris', ['http://localhost'])
                client_config['installed'] = {
                    'client_id': client_config['web']['client_id'],
                    'client_secret': client_config['web']['client_secret'],
                    'auth_uri': client_config['web']['auth_uri'],
                    'token_uri': client_config['web']['token_uri'],
                    'auth_provider_x509_cert_url': client_config['web'].get('auth_provider_x509_cert_url', ''),
                    'redirect_uris': redirect_uris
                }
                
                temp_config_file = client_secret_file.replace('.json', '_temp_installed.json')
                with open(temp_config_file, 'w') as f:
                    json.dump(client_config, f)
                
                flow = InstalledAppFlow.from_client_secrets_file(temp_config_file, scopes)
            else:
                raise ValueError('Formato de arquivo de credenciais não suportado')
            
            redirect_uri = redirect_uris[0] if redirect_uris else 'http://localhost'
            
            if redirect_uri == 'http://localhost':
                credentials = flow.run_local_server(port=8080, redirect_uri_trailing_slash=False)
            elif redirect_uri.startswith('http://localhost:'):
                port = int(redirect_uri.split(':')[-1].rstrip('/'))
                credentials = flow.run_local_server(port=port, redirect_uri_trailing_slash=False)
            else:
                credentials = flow.run_local_server(port=0, redirect_uri_trailing_slash=False)
            
            if 'temp_config_file' in locals() and os.path.exists(temp_config_file):
                os.remove(temp_config_file)
        
        if channel_creds:
            if channel_creds.token_file_path:
                with open(channel_creds.token_file_path, 'wb') as token:
                    pickle.dump(credentials, token)
            else:
                token_bytes = pickle.dumps(credentials)
                channel_creds.set_token_data(token_bytes)
                channel_creds.save()
        else:
            TOKEN_FILENAME = 'token.pickle'
            with open(TOKEN_FILENAME, 'wb') as token:
                pickle.dump(credentials, token)
    
    youtube_service = build('youtube', 'v3', credentials=credentials)
    
    if temp_client_secret_file and os.path.exists(temp_client_secret_file.name):
        os.unlink(temp_client_secret_file.name)
    
    return youtube_service

def upload_video(youtube, file_path, title, description, category, privacy):
    request_body = {
        'snippet': {
            'title': title,
            'description': description,
            'categoryId': category
        },
        'status': {
            'selfDeclaredMadeForKids': False,
            'privacyStatus': privacy,
            'madeForKids': False
        }
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part=','.join(request_body.keys()),
        body=request_body,
        media_body=media
    )
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[info] Upload progress: {int(status.progress() * 100)}%")
            
    print(f"[success] Upload complete! Video ID: {response.get('id')}")
    return response.get('id')

def get_next_clip_to_upload(target_channel_id=None):
    videos = InProgressVideo.objects.filter(is_finished=True).order_by('-created_at')
    
    if target_channel_id:
        videos = videos.filter(target_channel_id=target_channel_id)
    
    if not videos.exists():
        return None
    
    uploaded_clips_keys = set(
        UploadedClip.objects.values_list('r2_key', flat=True)
    )
    
    for video in videos:
        clips_prefix = f"clips/{video.video_id}/"
        clips = list_files_in_r2_prefix(clips_prefix)
        
        valid_clips = [
            clip for clip in clips 
            if clip.lower().endswith(VALID_EXTENSIONS) 
            and clip not in uploaded_clips_keys
        ]
        
        if valid_clips:
            valid_clips.sort()
            return {
                'r2_key': valid_clips[0],
                'video_id': video.video_id,
                'source_channel_id': video.source_channel_id,
                'target_channel_id': video.target_channel_id
            }
    
    return None

@csrf_exempt
def upload_clip(request):
    if request.method not in ['GET', 'POST']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        target_channel_id_param = request.GET.get('target_channel_id') if request.method == 'GET' else None
        if request.method == 'POST':
            import json
            try:
                body = json.loads(request.body)
                target_channel_id_param = body.get('target_channel_id')
            except:
                pass
        
        if target_channel_id_param:
            target_channel_ids = [target_channel_id_param]
        else:
            target_channel_ids = list(
                InProgressVideo.objects.filter(is_finished=True)
                .values_list('target_channel_id', flat=True)
                .distinct()
            )
        
        if not target_channel_ids:
            return JsonResponse({
                'message': 'Nenhum canal com vídeos processados encontrado',
                'uploaded': False,
                'uploads': []
            }, status=200)
        
        uploads = []
        errors = []
        
        for target_channel_id in target_channel_ids:
            try:
                clip_info = get_next_clip_to_upload(target_channel_id)
                
                if not clip_info:
                    continue
                
                r2_key = clip_info['r2_key']
                video_id = clip_info['video_id']
                source_channel_id = clip_info['source_channel_id']
                target_channel_id = clip_info['target_channel_id']
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    local_file_path = os.path.join(temp_dir, os.path.basename(r2_key))
                    
                    if not download_file_from_r2(r2_key, local_file_path):
                        errors.append({
                            'target_channel_id': target_channel_id,
                            'error': f'Falha ao baixar clipe {r2_key} do R2'
                        })
                        continue
                    
                    youtube = youtube_authenticator(target_channel_id)
                    
                    filename = os.path.basename(r2_key)
                    title = formatar_titulo_shorts(filename)
                    description = ""
                    category_id = "17"
                    try:
                        channel_config = ChannelConfig.objects.only("upload_category_id").get(
                            target_channel_id=target_channel_id
                        )
                        category_id = channel_config.upload_category_id or "17"
                    except ChannelConfig.DoesNotExist:
                        category_id = "17"
                    privacy_status = "public"
                    
                    video_id_youtube = upload_video(
                        youtube, 
                        local_file_path, 
                        title, 
                        description, 
                        category_id, 
                        privacy_status
                    )
                    
                    UploadedClip.objects.create(
                        r2_key=r2_key,
                        video_id=video_id,
                        channel_id=target_channel_id,
                        youtube_video_id=video_id_youtube
                    )
                    
                    if not delete_file_from_r2(r2_key):
                        print(f"[warning] Falha ao deletar {r2_key} do R2 após upload")
                    
                    uploads.append({
                        'r2_key': r2_key,
                        'video_id': video_id,
                        'source_channel_id': source_channel_id,
                        'target_channel_id': target_channel_id,
                        'youtube_video_id': video_id_youtube
                    })
                    
            except FileNotFoundError as e:
                errors.append({
                    'target_channel_id': target_channel_id,
                    'error': f'Arquivo client_secret.json não encontrado: {str(e)}'
                })
            except Exception as e:
                errors.append({
                    'target_channel_id': target_channel_id,
                    'error': f'Erro ao fazer upload: {str(e)}'
                })
        
        if uploads:
            return JsonResponse({
                'message': f'{len(uploads)} upload(s) realizado(s) com sucesso',
                'uploaded': True,
                'uploads': uploads,
                'errors': errors,
                'total_uploads': len(uploads),
                'total_errors': len(errors)
            }, status=200)
        else:
            return JsonResponse({
                'message': 'Nenhum clipe disponível para upload',
                'uploaded': False,
                'uploads': [],
                'errors': errors,
                'total_uploads': 0,
                'total_errors': len(errors)
            }, status=200)
            
    except Exception as e:
        return JsonResponse({
            'error': f'Erro geral ao processar uploads: {str(e)}'
        }, status=500)
