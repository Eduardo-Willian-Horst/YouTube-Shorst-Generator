import requests
import re
import ast
import json
import os
import tempfile
import datetime
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone
from decouple import config
from .models import (
    ProcessedVideo,
    InProgressVideo,
    ChannelConfig,
    ChannelCredentials,
    FlowRun,
    FlowStepRun,
    FlowLogLine,
)
from download.download_video import download_video
from download.r2_storage import (
    delete_file_from_r2,
    download_string_from_r2,
    has_files_in_r2_prefix,
    upload_file_to_r2,
    download_file_from_r2,
    file_exists_in_r2,
)
from gpu.video_processor import processar_clipes
from transcribe.extract_audio import extract_audio_from_video
from transcribe.gemini_process import processar_audio_com_gemini
from upload.models import UploadedClip
from upload.title_utils import formatar_titulo_shorts
from upload.views import get_next_clip_to_upload, upload_video, youtube_authenticator


FLOW_STEPS = [
    "getdata",
    "download",
    "extractaudio",
    "transcribe",
    "process_clips",
    "clear",
    "markprocessed",
    "upload",
]


def _panel_log(flow_run: FlowRun, message: str, step_name: str | None = None, level: str = FlowLogLine.Level.INFO) -> None:
    try:
        FlowLogLine.objects.create(
            flow_run=flow_run,
            step_name=step_name,
            level=level,
            message=message,
        )
    except Exception:
        pass


def _serialize_flow_run(flow_run: FlowRun) -> dict:
    steps = list(
        flow_run.steps.all().values(
            "step_name",
            "status",
            "ok_count",
            "error_count",
            "result",
            "error_message",
            "created_at",
            "started_at",
            "finished_at",
        )
    )
    for s in steps:
        for k in ("created_at", "started_at", "finished_at"):
            if s.get(k):
                s[k] = s[k].isoformat()

    return {
        "id": flow_run.id,
        "start_from": flow_run.start_from,
        "target_channel_id": flow_run.target_channel_id,
        "video_id": flow_run.video_id,
        "r2_prefix": flow_run.r2_prefix,
        "status": flow_run.status,
        "current_step": flow_run.current_step,
        "error_message": flow_run.error_message,
        "created_at": flow_run.created_at.isoformat() if flow_run.created_at else None,
        "started_at": flow_run.started_at.isoformat() if flow_run.started_at else None,
        "finished_at": flow_run.finished_at.isoformat() if flow_run.finished_at else None,
        "steps": steps,
    }


def _ensure_step_row(flow_run: FlowRun, step_name: str) -> FlowStepRun:
    step_row, _ = FlowStepRun.objects.get_or_create(
        flow_run=flow_run,
        step_name=step_name,
        defaults={"status": FlowStepRun.Status.PENDING},
    )
    return step_row


def _run_flow_with_persistence(*, start_from: str, target_channel_id: str | None, video_id: str | None, r2_prefix: str, only_step: bool) -> FlowRun:
    flow_run = FlowRun.objects.create(
        start_from=start_from,
        target_channel_id=target_channel_id,
        video_id=video_id,
        r2_prefix=r2_prefix or "",
        status=FlowRun.Status.PENDING,
    )

    start_ts = timezone.now()
    FlowRun.objects.filter(id=flow_run.id).update(status=FlowRun.Status.RUNNING, started_at=start_ts)
    flow_run.refresh_from_db()

    steps = FLOW_STEPS
    if start_from not in steps:
        flow_run.status = FlowRun.Status.ERROR
        flow_run.error_message = f"start_from inválido: {start_from}"
        flow_run.finished_at = timezone.now()
        flow_run.save(update_fields=["status", "error_message", "finished_at"])
        return flow_run

    if only_step:
        steps_to_run = [start_from]
    else:
        steps_to_run = steps[steps.index(start_from) :]

    _panel_log(
        flow_run,
        f"[run] iniciado start_from={start_from} only_step={only_step} target_channel_id={target_channel_id or '-'} video_id={video_id or '-'} r2_prefix={r2_prefix or '-'}",
    )

    try:
        for step in steps_to_run:
            FlowRun.objects.filter(id=flow_run.id).update(current_step=step)
            flow_run.refresh_from_db(fields=["current_step"])

            step_row = _ensure_step_row(flow_run, step)
            step_row.status = FlowStepRun.Status.RUNNING
            step_row.started_at = timezone.now()
            step_row.error_message = None
            step_row.save(update_fields=["status", "started_at", "error_message"])

            _panel_log(flow_run, f"[{step}] iniciando", step_name=step)

            try:
                if step == "getdata":
                    res = _run_getdata_step(target_channel_id=target_channel_id)
                    step_row.result = res
                    step_row.ok_count = int(res.get("created") or 0)
                    step_row.error_count = 0
                    step_row.status = FlowStepRun.Status.SUCCESS
                    step_row.finished_at = timezone.now()
                    step_row.save(update_fields=["result", "ok_count", "error_count", "status", "finished_at"])
                    _panel_log(flow_run, f"[{step}] ok created={step_row.ok_count}", step_name=step)
                    continue

                if step == "upload":
                    res = _run_upload_step(target_channel_id=target_channel_id, flow_run=flow_run)
                    ok_list = res.get("ok") or []
                    err_list = res.get("error") or []
                    step_row.result = res
                    step_row.ok_count = len(ok_list)
                    step_row.error_count = len(err_list)
                    step_row.status = FlowStepRun.Status.SUCCESS if step_row.error_count == 0 else FlowStepRun.Status.ERROR
                    step_row.error_message = "\n".join(err_list)[:4000] if err_list else None
                    step_row.finished_at = timezone.now()
                    step_row.save(
                        update_fields=[
                            "result",
                            "ok_count",
                            "error_count",
                            "status",
                            "error_message",
                            "finished_at",
                        ]
                    )
                    _panel_log(flow_run, f"[{step}] ok={step_row.ok_count} error={step_row.error_count}", step_name=step, level=FlowLogLine.Level.INFO if step_row.error_count == 0 else FlowLogLine.Level.ERROR)
                    if step_row.error_count:
                        raise RuntimeError("Falha no upload (ver logs da etapa)")
                    continue

                video_ids = _get_videos_for_flow(video_id=video_id, target_channel_id=target_channel_id)
                ok: list[str] = []
                error: list[str] = []

                _panel_log(flow_run, f"[{step}] videos_alvo={len(video_ids)}", step_name=step)

                for vid in video_ids:
                    try:
                        if step == "download":
                            download_video(vid, r2_prefix=r2_prefix)
                        elif step == "extractaudio":
                            extract_audio_from_video(vid, r2_prefix)
                        elif step == "transcribe":
                            processar_audio_com_gemini(f"{r2_prefix}{vid}.mp3", r2_prefix, vid)
                        elif step == "process_clips":
                            json_key = f"{r2_prefix}{vid}.json" if r2_prefix else f"{vid}.json"
                            json_content = download_string_from_r2(json_key)
                            if not json_content:
                                raise RuntimeError(f"JSON não encontrado no R2: {json_key}")

                            json_content = json_content.strip()
                            if json_content.startswith("```json"):
                                json_content = json_content[7:]
                            if json_content.startswith("```"):
                                json_content = json_content[3:]
                            if json_content.endswith("```"):
                                json_content = json_content[:-3]
                            json_content = json_content.strip()

                            clipes = json.loads(json_content)
                            processar_clipes(clipes, r2_prefix, vid)
                        elif step == "clear":
                            keys = [
                                f"{r2_prefix}{vid}.json" if r2_prefix else f"{vid}.json",
                                f"{r2_prefix}{vid}.mp4" if r2_prefix else f"{vid}.mp4",
                                f"{r2_prefix}{vid}.txt" if r2_prefix else f"{vid}.txt",
                                f"{r2_prefix}{vid}.mp3" if r2_prefix else f"{vid}.mp3",
                            ]
                            for key in keys:
                                delete_file_from_r2(key)
                        elif step == "markprocessed":
                            clips_prefix = f"{r2_prefix}clips/{vid}/" if r2_prefix else f"clips/{vid}/"
                            if has_files_in_r2_prefix(clips_prefix):
                                with transaction.atomic():
                                    InProgressVideo.objects.filter(video_id=vid).update(is_finished=True)
                        else:
                            raise RuntimeError(f"Etapa não suportada: {step}")

                        ok.append(vid)
                    except Exception as exc:
                        error_msg = f"{vid}: {str(exc)}"
                        error.append(error_msg)
                        _panel_log(flow_run, f"[{step}] erro {error_msg}", step_name=step, level=FlowLogLine.Level.ERROR)

                step_row.result = {"ok": ok, "error": error, "count": len(video_ids)}
                step_row.ok_count = len(ok)
                step_row.error_count = len(error)
                step_row.status = FlowStepRun.Status.SUCCESS if step_row.error_count == 0 else FlowStepRun.Status.ERROR
                step_row.error_message = "\n".join(error)[:4000] if error else None
                step_row.finished_at = timezone.now()
                step_row.save(
                    update_fields=[
                        "result",
                        "ok_count",
                        "error_count",
                        "status",
                        "error_message",
                        "finished_at",
                    ]
                )

                _panel_log(flow_run, f"[{step}] final ok={step_row.ok_count} error={step_row.error_count}", step_name=step, level=FlowLogLine.Level.INFO if step_row.error_count == 0 else FlowLogLine.Level.ERROR)

                if step_row.error_count:
                    raise RuntimeError("Falha na etapa (ver logs)")

            except Exception as exc:
                step_row.status = FlowStepRun.Status.ERROR
                step_row.error_message = (step_row.error_message or str(exc))[:4000]
                step_row.finished_at = timezone.now()
                step_row.save(update_fields=["status", "error_message", "finished_at"])
                raise

        flow_run.status = FlowRun.Status.SUCCESS
        flow_run.finished_at = timezone.now()
        flow_run.current_step = None
        flow_run.error_message = None
        flow_run.save(update_fields=["status", "finished_at", "current_step", "error_message"])
        _panel_log(flow_run, "[run] finalizado com sucesso")
        return flow_run

    except Exception as exc:
        flow_run.status = FlowRun.Status.ERROR
        flow_run.finished_at = timezone.now()
        flow_run.error_message = str(exc)[:4000]
        flow_run.save(update_fields=["status", "finished_at", "error_message"])
        _panel_log(flow_run, f"[run] erro {flow_run.error_message}", level=FlowLogLine.Level.ERROR)
        return flow_run


def parse_iso8601_duration(duration_str):
    if not duration_str or duration_str.startswith('P0D'): 
        return 0
        
    hours = 0
    minutes = 0
    seconds = 0

    duration_str = duration_str[2:]

    hour_match = re.search(r'(\d+)H', duration_str)
    minute_match = re.search(r'(\d+)M', duration_str)
    second_match = re.search(r'(\d+)S', duration_str)

    if hour_match:
        hours = int(hour_match.group(1))
    if minute_match:
        minutes = int(minute_match.group(1))
    if second_match:
        seconds = int(second_match.group(1))

    return (hours * 3600) + (minutes * 60) + seconds


def get_video_details(api_key, video_id):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        'part': 'contentDetails,snippet',
        'id': video_id,
        'key': api_key
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data


def get_last_video_info(api_key, channel_id):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        'part': 'contentDetails',
        'id': channel_id,
        'key': api_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status() 
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        else:
            return None
    except requests.exceptions.RequestException as e:
        return None
    except (KeyError, IndexError) as e:
        return None
    
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    params = {
        'part': 'snippet',
        'playlistId': playlist_id,
        'maxResults': 10,
        'key': api_key
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'items' in data and len(data['items']) > 0:
            for item in data['items']:
                video_id = item['snippet']['resourceId']['videoId']
                details = get_video_details(api_key, video_id)
                
                if 'items' in details and len(details['items']) > 0:
                    duration_str = details['items'][0]['contentDetails']['duration']
                    
                    if parse_iso8601_duration(duration_str) > 180:
                        return {
                            'video_id': video_id,
                            'video_url': f'https://www.youtube.com/watch?v={video_id}'
                        }

        return None
        
    except requests.exceptions.RequestException as e:
        return None
    except (KeyError, IndexError) as e:
        return None


def getData(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    default_api_key = config('YOUTUBE_API_KEY', default=None)
    
    channel_configs = ChannelConfig.objects.filter(is_active=True).select_related('credentials')
    
    if not channel_configs.exists():
        return JsonResponse({
            'error': 'Nenhuma configuração de canal ativa encontrada'
        }, status=500)
    
    results = []
    errors = []
    
    for config_obj in channel_configs:
        target_channel_id = config_obj.target_channel_id
        source_channel_ids = config_obj.get_source_channel_ids_list()
        
        api_key = config_obj.get_api_key()
        if not api_key:
            api_key = default_api_key
        
        if not api_key:
            errors.append({
                'target_channel_id': target_channel_id,
                'error': 'API key não configurada para este canal'
            })
            continue
        
        for source_channel_id in source_channel_ids:
            result = get_last_video_info(api_key, source_channel_id)
            
            if result:
                video_id = result['video_id']
                if not InProgressVideo.objects.filter(
                    video_id=video_id,
                    target_channel_id=target_channel_id
                ).exists():
                    InProgressVideo.objects.create(
                        video_id=video_id,
                        source_channel_id=source_channel_id,
                        target_channel_id=target_channel_id
                    )
                results.append({
                    'video_id': video_id,
                    'source_channel_id': source_channel_id,
                    'target_channel_id': target_channel_id
                })
            else:
                errors.append({
                    'source_channel_id': source_channel_id,
                    'target_channel_id': target_channel_id,
                    'error': 'Não foi possível obter informações do vídeo'
                })
    
    if results:
        return JsonResponse({
            'response': 'ok',
            'videos_encontrados': len(results),
            'erros': len(errors)
        }, status=200)
    else:
        return JsonResponse({
            'error': 'Nenhum vídeo novo encontrado',
            'erros': len(errors)
        }, status=404)

















def is_video_processed(video_id: str) -> bool:
    try:
        is_processed = ProcessedVideo.objects.filter(video_id=video_id).exists()
        return is_processed
    except Exception as e:
        return False

def check_video_processed(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    video_id = request.GET.get('video_id')
    
    videos_id = InProgressVideo.objects.filter(video_id=video_id).filter(is_finished=False).values_list('video_id', flat=True)

    print(videos_id)
    if not video_id:
        return JsonResponse({
            'error': 'Parâmetro obrigatório: video_id'
        }, status=400)
    
    try:
        is_processed = ProcessedVideo.objects.filter(video_id=video_id).exists()
        return JsonResponse({
            'video_id': video_id,
            'is_processed': is_processed
        }, status=200)
    except Exception as e:
        return JsonResponse({
            'error': f'Erro ao verificar vídeo: {str(e)}'
        }, status=500)

def mark_video_processed(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    target_channel_id = request.GET.get('target_channel_id')
    
    if target_channel_id:
        videos = InProgressVideo.objects.filter(
            target_channel_id=target_channel_id,
            is_finished=False
        )
    else:
        videos = InProgressVideo.objects.filter(is_finished=False)
    videos_processados = []
    
    for video in videos:
        clips_prefix = f"clips/{video.video_id}/"
        tem_arquivos = has_files_in_r2_prefix(clips_prefix)
        
        if tem_arquivos:
            videos_processados.append(video.video_id)
            video.is_finished = True
            video.save()

    return JsonResponse({
        'status': 'ok',
        'videos_processados': len(videos_processados)
    }, status=200)




def get_in_progress_videos(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        target_channel_id = request.GET.get('target_channel_id')
        source_channel_id = request.GET.get('source_channel_id')
        is_finished_param = request.GET.get('is_finished')
        
        videos = InProgressVideo.objects.all()
        
        if target_channel_id:
            videos = videos.filter(target_channel_id=target_channel_id)
        
        if source_channel_id:
            videos = videos.filter(source_channel_id=source_channel_id)
        
        if is_finished_param is not None:
            is_finished = is_finished_param.lower() == 'true'
            videos = videos.filter(is_finished=is_finished)
        else:
            videos = videos.filter(is_finished=False)
        
        videos_data = [{
            'video_id': video.video_id,
            'source_channel_id': video.source_channel_id,
            'target_channel_id': video.target_channel_id,
            'is_finished': video.is_finished,
            'created_at': video.created_at.isoformat()
        } for video in videos]
        
        return JsonResponse({
            'videos': videos_data,
            'count': len(videos_data)
        }, status=200)
    except Exception as e:
        return JsonResponse({
            'error': f'Erro ao buscar vídeos em processamento: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_channel_configs(request):
    if request.method == 'GET':
        try:
            configs = ChannelConfig.objects.all().select_related('credentials')
            configs_data = []
            for config_obj in configs:
                configs_data.append({
                    'id': config_obj.id,
                    'target_channel_id': config_obj.target_channel_id,
                    'source_channel_ids': config_obj.source_channel_ids,
                    'source_channel_ids_list': config_obj.get_source_channel_ids_list(),
                    'upload_category_id': config_obj.upload_category_id,
                    'is_active': config_obj.is_active,
                    'credentials_id': config_obj.credentials.id if config_obj.credentials else None,
                    'created_at': config_obj.created_at.isoformat(),
                    'updated_at': config_obj.updated_at.isoformat()
                })
            return JsonResponse({'configs': configs_data}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            target_channel_id = data.get('target_channel_id')
            source_channel_ids = data.get('source_channel_ids', '')
            credentials_id = data.get('credentials_id')
            is_active = data.get('is_active', True)
            upload_category_id = str(data.get('upload_category_id') or '17').strip()
            
            if not target_channel_id:
                return JsonResponse({'error': 'target_channel_id é obrigatório'}, status=400)
            
            credentials = None
            if credentials_id:
                try:
                    credentials = ChannelCredentials.objects.get(id=credentials_id)
                except ChannelCredentials.DoesNotExist:
                    return JsonResponse({'error': 'Credenciais não encontradas'}, status=404)
            
            config_obj = ChannelConfig.objects.create(
                target_channel_id=target_channel_id,
                source_channel_ids=source_channel_ids,
                credentials=credentials,
                is_active=is_active,
                upload_category_id=upload_category_id
            )
            
            return JsonResponse({
                'id': config_obj.id,
                'target_channel_id': config_obj.target_channel_id,
                'source_channel_ids': config_obj.source_channel_ids,
                'source_channel_ids_list': config_obj.get_source_channel_ids_list(),
                'upload_category_id': config_obj.upload_category_id,
                'is_active': config_obj.is_active,
                'credentials_id': config_obj.credentials.id if config_obj.credentials else None,
                'created_at': config_obj.created_at.isoformat(),
                'updated_at': config_obj.updated_at.isoformat()
            }, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_channel_config_detail(request, config_id):
    try:
        config_obj = ChannelConfig.objects.get(id=config_id)
    except ChannelConfig.DoesNotExist:
        return JsonResponse({'error': 'Configuração não encontrada'}, status=404)
    
    if request.method == 'GET':
        return JsonResponse({
            'id': config_obj.id,
            'target_channel_id': config_obj.target_channel_id,
            'source_channel_ids': config_obj.source_channel_ids,
            'source_channel_ids_list': config_obj.get_source_channel_ids_list(),
            'upload_category_id': config_obj.upload_category_id,
            'is_active': config_obj.is_active,
            'credentials_id': config_obj.credentials.id if config_obj.credentials else None,
            'created_at': config_obj.created_at.isoformat(),
            'updated_at': config_obj.updated_at.isoformat()
        }, status=200)
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            
            if 'target_channel_id' in data:
                config_obj.target_channel_id = data['target_channel_id']
            if 'source_channel_ids' in data:
                config_obj.source_channel_ids = data['source_channel_ids']
            if 'is_active' in data:
                config_obj.is_active = data['is_active']
            if 'upload_category_id' in data:
                config_obj.upload_category_id = str(data['upload_category_id'] or '17').strip()
            if 'credentials_id' in data:
                if data['credentials_id']:
                    try:
                        config_obj.credentials = ChannelCredentials.objects.get(id=data['credentials_id'])
                    except ChannelCredentials.DoesNotExist:
                        return JsonResponse({'error': 'Credenciais não encontradas'}, status=404)
                else:
                    config_obj.credentials = None
            
            config_obj.save()
            
            return JsonResponse({
                'id': config_obj.id,
                'target_channel_id': config_obj.target_channel_id,
                'source_channel_ids': config_obj.source_channel_ids,
                'source_channel_ids_list': config_obj.get_source_channel_ids_list(),
                'upload_category_id': config_obj.upload_category_id,
                'is_active': config_obj.is_active,
                'credentials_id': config_obj.credentials.id if config_obj.credentials else None,
                'created_at': config_obj.created_at.isoformat(),
                'updated_at': config_obj.updated_at.isoformat()
            }, status=200)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    elif request.method == 'DELETE':
        config_obj.delete()
        return JsonResponse({'message': 'Configuração deletada com sucesso'}, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_channel_credentials(request):
    if request.method == 'GET':
        try:
            creds = ChannelCredentials.objects.all()
            creds_data = []
            for cred in creds:
                creds_data.append({
                    'id': cred.id,
                    'channel_id': cred.channel_id,
                    'youtube_api_key': cred.youtube_api_key,
                    'client_secret_file_path': cred.client_secret_file_path,
                    'client_secret_r2_key': cred.client_secret_r2_key,
                    'token_file_path': cred.token_file_path,
                    'has_token': bool(cred.token_data or cred.token_file_path),
                    'created_at': cred.created_at.isoformat(),
                    'updated_at': cred.updated_at.isoformat()
                })
            return JsonResponse({'credentials': creds_data}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            channel_id = data.get('channel_id')
            youtube_api_key = data.get('youtube_api_key', '')
            client_secret_file_path = data.get('client_secret_file_path', '')
            
            if not channel_id:
                return JsonResponse({'error': 'channel_id é obrigatório'}, status=400)
            
            cred = ChannelCredentials.objects.create(
                channel_id=channel_id,
                youtube_api_key=youtube_api_key,
                client_secret_file_path=client_secret_file_path
            )
            
            return JsonResponse({
                'id': cred.id,
                'channel_id': cred.channel_id,
                'youtube_api_key': cred.youtube_api_key,
                'client_secret_file_path': cred.client_secret_file_path,
                'client_secret_r2_key': cred.client_secret_r2_key,
                'token_file_path': cred.token_file_path,
                'has_token': bool(cred.token_data or cred.token_file_path),
                'created_at': cred.created_at.isoformat(),
                'updated_at': cred.updated_at.isoformat()
            }, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def api_channel_credentials_detail(request, cred_id):
    try:
        cred = ChannelCredentials.objects.get(id=cred_id)
    except ChannelCredentials.DoesNotExist:
        return JsonResponse({'error': 'Credenciais não encontradas'}, status=404)
    
    if request.method == 'GET':
        return JsonResponse({
            'id': cred.id,
            'channel_id': cred.channel_id,
            'youtube_api_key': cred.youtube_api_key,
            'client_secret_file_path': cred.client_secret_file_path,
            'client_secret_r2_key': cred.client_secret_r2_key,
            'token_file_path': cred.token_file_path,
            'has_token': bool(cred.token_data or cred.token_file_path),
            'created_at': cred.created_at.isoformat(),
            'updated_at': cred.updated_at.isoformat()
        }, status=200)
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            
            if 'channel_id' in data:
                cred.channel_id = data['channel_id']
            if 'youtube_api_key' in data:
                cred.youtube_api_key = data['youtube_api_key']
            if 'client_secret_file_path' in data:
                cred.client_secret_file_path = data['client_secret_file_path']
            if 'token_file_path' in data:
                cred.token_file_path = data['token_file_path']
            
            cred.save()
            
            return JsonResponse({
                'id': cred.id,
                'channel_id': cred.channel_id,
                'youtube_api_key': cred.youtube_api_key,
                'client_secret_file_path': cred.client_secret_file_path,
                'client_secret_r2_key': cred.client_secret_r2_key,
                'token_file_path': cred.token_file_path,
                'has_token': bool(cred.token_data or cred.token_file_path),
                'created_at': cred.created_at.isoformat(),
                'updated_at': cred.updated_at.isoformat()
            }, status=200)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    elif request.method == 'DELETE':
        cred.delete()
        return JsonResponse({'message': 'Credenciais deletadas com sucesso'}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def api_upload_client_secret(request, cred_id):
    try:
        cred = ChannelCredentials.objects.get(id=cred_id)
    except ChannelCredentials.DoesNotExist:
        return JsonResponse({'error': 'Credenciais não encontradas'}, status=404)
    
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Arquivo não fornecido'}, status=400)
    
    file = request.FILES['file']
    if not file.name.endswith('.json'):
        return JsonResponse({'error': 'Arquivo deve ser um JSON'}, status=400)
    
    try:
        import tempfile
        
        r2_key = f'credentials/client_secret_{cred.id}_{file.name}'
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
            for chunk in file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name
        
        if not upload_file_to_r2(temp_file_path, r2_key):
            os.unlink(temp_file_path)
            return JsonResponse({'error': 'Falha ao fazer upload do arquivo para o R2'}, status=500)
        
        os.unlink(temp_file_path)
        
        if not file_exists_in_r2(r2_key):
            return JsonResponse({'error': 'Arquivo não encontrado no R2 após upload'}, status=500)
        
        cred.client_secret_r2_key = r2_key
        cred.save(update_fields=['client_secret_r2_key', 'updated_at'])
        
        cred.refresh_from_db()
        
        if not cred.client_secret_r2_key or cred.client_secret_r2_key != r2_key:
            return JsonResponse({
                'error': 'Falha ao atualizar chave R2 no banco de dados',
                'r2_key': r2_key,
                'db_r2_key': cred.client_secret_r2_key
            }, status=500)
        
        return JsonResponse({
            'message': 'Arquivo enviado com sucesso para o R2',
            'r2_key': r2_key,
            'file_exists_in_r2': file_exists_in_r2(r2_key),
            'cred_id': cred.id,
            'channel_id': cred.channel_id
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_processed_videos(request):
    try:
        videos = ProcessedVideo.objects.all().order_by('-created_at')[:100]
        videos_data = [{
            'video_id': video.video_id,
            'created_at': video.created_at.isoformat()
        } for video in videos]
        return JsonResponse({'videos': videos_data, 'count': len(videos_data)}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_verify_credentials(request, cred_id):
    try:
        cred = ChannelCredentials.objects.get(id=cred_id)
        
        file_exists_local = False
        file_exists_r2 = False
        file_path = None
        r2_key = None
        
        if cred.client_secret_r2_key:
            r2_key = cred.client_secret_r2_key
            file_exists_r2 = file_exists_in_r2(r2_key)
        
        if cred.client_secret_file_path:
            file_path = cred.client_secret_file_path
            file_exists_local = os.path.exists(file_path)
        
        channel_configs = ChannelConfig.objects.filter(credentials=cred)
        configs_data = []
        for config_obj in channel_configs:
            configs_data.append({
                'id': config_obj.id,
                'target_channel_id': config_obj.target_channel_id,
                'is_active': config_obj.is_active
            })
        
        return JsonResponse({
            'cred_id': cred.id,
            'channel_id': cred.channel_id,
            'client_secret_file_path': cred.client_secret_file_path,
            'client_secret_r2_key': cred.client_secret_r2_key,
            'file_exists_local': file_exists_local,
            'file_exists_r2': file_exists_r2,
            'file_path': file_path,
            'r2_key': r2_key,
            'has_token': bool(cred.token_data or cred.token_file_path),
            'linked_configs': configs_data,
            'linked_configs_count': len(configs_data)
        }, status=200)
    except ChannelCredentials.DoesNotExist:
        return JsonResponse({'error': 'Credenciais não encontradas'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def frontend(request):
    return render(request, 'getData/frontend.html')


@csrf_exempt
@require_http_methods(["GET"])
def api_panel_flow_runs(request):
    limit = request.GET.get("limit")
    try:
        limit_int = int(limit) if limit else 20
    except Exception:
        limit_int = 20

    runs = FlowRun.objects.all().order_by("-created_at")[: max(1, min(limit_int, 200))]
    data = [_serialize_flow_run(r) for r in runs]
    return JsonResponse({"runs": data, "count": len(data)}, status=200)


@csrf_exempt
@require_http_methods(["GET"])
def api_panel_flow_run_detail(request, run_id: int):
    try:
        run = FlowRun.objects.get(id=run_id)
    except FlowRun.DoesNotExist:
        return JsonResponse({"error": "Execução não encontrada"}, status=404)

    return JsonResponse({"run": _serialize_flow_run(run)}, status=200)


@csrf_exempt
@require_http_methods(["GET"])
def api_panel_flow_run_logs(request, run_id: int):
    after_id = request.GET.get("after_id")
    try:
        after_int = int(after_id) if after_id else 0
    except Exception:
        after_int = 0

    try:
        run = FlowRun.objects.get(id=run_id)
    except FlowRun.DoesNotExist:
        return JsonResponse({"error": "Execução não encontrada"}, status=404)

    lines_qs = FlowLogLine.objects.filter(flow_run=run, id__gt=after_int).order_by("id")[:500]
    lines = []
    last_id = after_int
    for line in lines_qs:
        last_id = line.id
        lines.append(
            {
                "id": line.id,
                "created_at": line.created_at.isoformat(),
                "level": line.level,
                "step_name": line.step_name,
                "message": line.message,
            }
        )

    return JsonResponse({"lines": lines, "last_id": last_id}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def api_panel_flow_run(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    start_from = str(payload.get("start_from") or "").strip()
    target_channel_id = None
    video_id = payload.get("video_id")
    r2_prefix = payload.get("r2_prefix") or ""
    only_step = bool(payload.get("only_step") or False)

    if start_from not in FLOW_STEPS:
        return JsonResponse({"error": "start_from inválido", "valid": FLOW_STEPS}, status=400)

    run = _run_flow_with_persistence(
        start_from=start_from,
        target_channel_id=target_channel_id,
        video_id=video_id,
        r2_prefix=r2_prefix,
        only_step=only_step,
    )
    return JsonResponse({"run": _serialize_flow_run(run)}, status=200 if run.status != FlowRun.Status.ERROR else 500)


def _get_videos_for_flow(video_id: str | None, target_channel_id: str | None):
    if video_id:
        return [video_id]

    videos = InProgressVideo.objects.filter(is_finished=False)
    if target_channel_id:
        videos = videos.filter(target_channel_id=target_channel_id)
    return list(videos.values_list("video_id", flat=True))


def _run_getdata_step(target_channel_id: str | None) -> dict:
    default_api_key = config("YOUTUBE_API_KEY", default=None)
    channel_configs = ChannelConfig.objects.filter(is_active=True).select_related("credentials")
    if target_channel_id:
        channel_configs = channel_configs.filter(target_channel_id=target_channel_id)

    created = 0
    for config_obj in channel_configs:
        api_key = config_obj.get_api_key() or default_api_key
        if not api_key:
            continue

        for source_channel_id in config_obj.get_source_channel_ids_list():
            result = get_last_video_info(api_key, source_channel_id)
            if not result:
                continue

            new_video_id = result["video_id"]
            if not InProgressVideo.objects.filter(
                video_id=new_video_id,
                target_channel_id=config_obj.target_channel_id,
            ).exists():
                InProgressVideo.objects.create(
                    video_id=new_video_id,
                    source_channel_id=source_channel_id,
                    target_channel_id=config_obj.target_channel_id,
                )
                created += 1

    return {"created": created}


def _run_upload_step(target_channel_id: str | None, flow_run: FlowRun | None = None) -> dict:
    ok: list[str] = []
    error: list[str] = []

    if target_channel_id:
        target_channel_ids = [target_channel_id]
    else:
        target_channel_ids = list(
            InProgressVideo.objects.filter(is_finished=True)
            .values_list("target_channel_id", flat=True)
            .distinct()
        )

    if flow_run:
        _panel_log(
            flow_run,
            f"[upload] canais_alvo={len(target_channel_ids)} ids={','.join(target_channel_ids) if target_channel_ids else '-'}",
            step_name="upload",
        )

    for channel_id in target_channel_ids:
        if flow_run:
            _panel_log(
                flow_run,
                f"[upload] verificando próximo clipe para canal {channel_id}",
                step_name="upload",
            )

        clip_info = get_next_clip_to_upload(channel_id)
        if not clip_info:
            if flow_run:
                _panel_log(
                    flow_run,
                    f"[upload] nenhum clipe pendente para canal {channel_id}",
                    step_name="upload",
                )
            continue

        r2_key = clip_info["r2_key"]
        try:
            youtube = youtube_authenticator(channel_id)
            filename = r2_key.split("/")[-1]
            title = formatar_titulo_shorts(filename)
            description = ""
            category_id = "17"
            try:
                channel_config = ChannelConfig.objects.only("upload_category_id").get(
                    target_channel_id=channel_id
                )
                category_id = channel_config.upload_category_id or "17"
            except ChannelConfig.DoesNotExist:
                category_id = "17"

            privacy_status = "public"
            with tempfile.TemporaryDirectory() as temp_dir:
                local_file_path = os.path.join(temp_dir, filename)
                if not download_file_from_r2(r2_key, local_file_path):
                    raise RuntimeError(f"Falha ao baixar clipe {r2_key} do R2")

                youtube_video_id = upload_video(
                    youtube,
                    local_file_path,
                    title,
                    description,
                    category_id,
                    privacy_status,
                )

            UploadedClip.objects.create(
                r2_key=r2_key,
                video_id=clip_info["video_id"],
                channel_id=channel_id,
                youtube_video_id=youtube_video_id,
            )

            delete_file_from_r2(r2_key)
            ok.append(r2_key)

            if flow_run:
                _panel_log(
                    flow_run,
                    f"[upload] sucesso canal={channel_id} video_id={clip_info['video_id']} youtube_video_id={youtube_video_id} r2_key={r2_key}",
                    step_name="upload",
                )
            continue
        except Exception as exc:
            error.append(f"{r2_key}: {str(exc)}")
            if flow_run:
                _panel_log(
                    flow_run,
                    f"[upload] erro canal={channel_id} r2_key={r2_key} detalhe={str(exc)}",
                    step_name="upload",
                    level=FlowLogLine.Level.ERROR,
                )
            continue

    return {"ok": ok, "error": error}


@csrf_exempt
@require_http_methods(["POST"])
def api_generate_channel_token(request, target_channel_id: str):
    try:
        config_obj = ChannelConfig.objects.select_related("credentials").get(
            target_channel_id=target_channel_id
        )
        if not config_obj.credentials:
            return JsonResponse(
                {"error": "Configuração não tem credenciais vinculadas"},
                status=400,
            )

        cred = config_obj.credentials
        cred.token_data = None
        cred.token_file_path = ""
        cred.save(update_fields=["token_data", "token_file_path", "updated_at"])

        youtube_authenticator(target_channel_id)

        return JsonResponse(
            {
                "status": "ok",
                "message": "Token recriado com sucesso para o canal",
                "target_channel_id": target_channel_id,
                "credentials_id": cred.id,
            },
            status=200,
        )
    except ChannelConfig.DoesNotExist:
        return JsonResponse(
            {"error": "Configuração de canal não encontrada"},
            status=404,
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_flow_run(request):
    """
    Dispara o fluxo a partir de um ponto.

    Body (JSON):
    - start_from: getdata|download|extractaudio|transcribe|process_clips|clear|markprocessed|upload
    - target_channel_id: opcional
    - video_id: opcional (quando informado, roda somente para este vídeo nas etapas por-vídeo)
    - r2_prefix: opcional (padrão "")
    """
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    start_from = str(payload.get("start_from") or "").strip()
    target_channel_id = payload.get("target_channel_id")
    video_id = payload.get("video_id")
    r2_prefix = payload.get("r2_prefix") or ""

    steps = [
        "getdata",
        "download",
        "extractaudio",
        "transcribe",
        "process_clips",
        "clear",
        "markprocessed",
        "upload",
    ]
    if start_from not in steps:
        return JsonResponse(
            {"error": "start_from inválido", "valid": steps},
            status=400,
        )

    results: list[dict] = []
    start_index = steps.index(start_from)

    for step in steps[start_index:]:
        if step == "getdata":
            res = _run_getdata_step(target_channel_id=target_channel_id)
            results.append({"step": step, "result": res})
            continue

        if step == "upload":
            res = _run_upload_step(target_channel_id=target_channel_id)
            results.append({"step": step, "result": res})
            continue

        video_ids = _get_videos_for_flow(video_id=video_id, target_channel_id=target_channel_id)
        ok: list[str] = []
        error: list[str] = []

        for vid in video_ids:
            try:
                if step == "download":
                    download_video(vid, r2_prefix=r2_prefix)
                elif step == "extractaudio":
                    extract_audio_from_video(vid, r2_prefix)
                elif step == "transcribe":
                    processar_audio_com_gemini(f"{r2_prefix}{vid}.mp3", r2_prefix, vid)
                elif step == "process_clips":
                    json_key = f"{r2_prefix}{vid}.json" if r2_prefix else f"{vid}.json"
                    json_content = download_string_from_r2(json_key)
                    if not json_content:
                        raise RuntimeError(f"JSON não encontrado no R2: {json_key}")

                    json_content = json_content.strip()
                    if json_content.startswith("```json"):
                        json_content = json_content[7:]
                    if json_content.startswith("```"):
                        json_content = json_content[3:]
                    if json_content.endswith("```"):
                        json_content = json_content[:-3]
                    json_content = json_content.strip()

                    clipes = json.loads(json_content)
                    processar_clipes(clipes, r2_prefix, vid)
                elif step == "clear":
                    keys = [
                        f"{r2_prefix}{vid}.json" if r2_prefix else f"{vid}.json",
                        f"{r2_prefix}{vid}.mp4" if r2_prefix else f"{vid}.mp4",
                        f"{r2_prefix}{vid}.txt" if r2_prefix else f"{vid}.txt",
                        f"{r2_prefix}{vid}.mp3" if r2_prefix else f"{vid}.mp3",
                    ]
                    for key in keys:
                        delete_file_from_r2(key)
                elif step == "markprocessed":
                    clips_prefix = f"{r2_prefix}clips/{vid}/" if r2_prefix else f"clips/{vid}/"
                    if has_files_in_r2_prefix(clips_prefix):
                        with transaction.atomic():
                            InProgressVideo.objects.filter(video_id=vid).update(is_finished=True)
                else:
                    raise RuntimeError(f"Etapa não suportada: {step}")

                ok.append(vid)
            except Exception as exc:
                error.append(f"{vid}: {str(exc)}")

        results.append({"step": step, "ok": ok, "error": error, "count": len(video_ids)})

    return JsonResponse(
        {
            "status": "ok",
            "start_from": start_from,
            "target_channel_id": target_channel_id,
            "video_id": video_id,
            "r2_prefix": r2_prefix,
            "results": results,
        },
        status=200,
    )