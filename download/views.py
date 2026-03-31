from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .download_video import download_video
from .r2_storage import delete_file_from_r2, file_exists_in_r2
import json
from getData.models import InProgressVideo



@csrf_exempt
def download(request):
    if request.method not in ['GET']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    target_channel_id = request.GET.get('target_channel_id')
    
    videos = InProgressVideo.objects.filter(is_finished=False)
    if target_channel_id:
        videos = videos.filter(target_channel_id=target_channel_id)

    results = []
    errors = []
    
    for video in videos:
        try:
            download_video(video.video_id)
            results.append(video.video_id)
        except Exception as e:
            errors.append(video.video_id)
    
    
    return JsonResponse({'results': results, 'errors': errors}, status=200)


@csrf_exempt
def limpar_arquivos_temporarios(request):
    if request.method not in ['GET', 'POST']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    target_channel_id = request.GET.get('target_channel_id') if request.method == 'GET' else None
    if request.method == 'POST':
        try:
            import json
            body = json.loads(request.body)
            target_channel_id = body.get('target_channel_id')
        except:
            pass
    
    videos = InProgressVideo.objects.filter(is_finished=False)
    if target_channel_id:
        videos = videos.filter(target_channel_id=target_channel_id)
    
    for video in videos:
        r2_prefix = f""
        arquivos_para_excluir = [
            f'{video.video_id}.json',
            f'{video.video_id}.mp4',
            f'{video.video_id}.txt',
            f'{video.video_id}.mp3'
        ]

        resultados = {
            'sucessos': [],
            'erros': [],
            'nao_encontrados': []
        }

        for arquivo in arquivos_para_excluir:
            r2_key = f"{r2_prefix}{arquivo}" if r2_prefix else arquivo

            try:
                if file_exists_in_r2(r2_key):
                    if delete_file_from_r2(r2_key):
                        resultados['sucessos'].append(r2_key)
                    else:
                        resultados['erros'].append({
                            'arquivo': r2_key,
                            'erro': 'Falha ao excluir arquivo'
                        })
                else:
                    resultados['nao_encontrados'].append(r2_key)
            except Exception as e:
                resultados['erros'].append({
                    'arquivo': r2_key,
                    'erro': str(e)
                })

    return JsonResponse({'status': 'ok'}, status=200)