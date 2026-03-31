from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .extract_audio import extract_audio_from_video
from .gemini_process import processar_audio_com_gemini
import json
import ast
from decouple import config
from getData.models import InProgressVideo

@csrf_exempt
def extract_audio(request):
    if request.method not in ['GET']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    target_channel_id = request.GET.get('target_channel_id')
    
    videos = InProgressVideo.objects.filter(is_finished=False)
    if target_channel_id:
        videos = videos.filter(target_channel_id=target_channel_id)
    
    r2_prefix = ""
    
    results = []
    errors = []

    for video in videos:
        try:
            extract_audio_from_video(video.video_id, r2_prefix)
            results.append(video.video_id)
        except Exception as e:
            errors.append(video.video_id)
    
    return JsonResponse({'results': results, 'errors': errors}, status=200)
    
@csrf_exempt
def transcribe(request):
    if request.method not in ['GET']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    target_channel_id = request.GET.get('target_channel_id')
    
    videos = InProgressVideo.objects.filter(is_finished=False)
    if target_channel_id:
        videos = videos.filter(target_channel_id=target_channel_id)

    r2_prefix = ""

    results = []
    errors = []

    for video in videos:
        try:
            resultado = processar_audio_com_gemini(f"{r2_prefix}{video.video_id}.mp3", r2_prefix, video.video_id)
            results.append(video.video_id)
        except Exception as e:
            errors.append(video.video_id)
    
    return JsonResponse({'results': results, 'errors': errors}, status=200)
