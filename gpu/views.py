from django.http import JsonResponse
from django.utils import timezone
from .gpu_utils import verificar_gpu_disponivel, obter_info_gpu_detalhada, verificar_cuda_disponivel
from .video_processor import processar_clipes, processar_video_916
from .models import ProcessamentoClipes
import json
import requests
import threading
from download.r2_storage import download_string_from_r2
from decouple import config
import ast


def processar_clipes_virais_background(processamento_id):
    processamento = ProcessamentoClipes.objects.get(id=processamento_id)
    
    try:
        processamento.status = 'processando'
        processamento.save()
        
        print(f"[DEBUG] Iniciando processamento em background ID: {processamento_id}")
        print(f"[DEBUG] Total de vídeos: {processamento.total_videos}")
        
        channel_id = ast.literal_eval(config('YOUTUBE_CHANNEL_ID', default=None))
        api_acqm_url = config('API_ACQM_URL', default='http://localhost:8000')
        r2_prefix = ""
        
        results = []
        errors = []
        resultados_detalhados = {}
        
        for video_id in processamento.videos_ids:
            try:
                print(f"[DEBUG] Processando vídeo: {video_id}")
                
                json_key = f"{r2_prefix}{video_id}.json" if r2_prefix else f"{video_id}.json"
                print(f"[DEBUG] Baixando JSON de clipes: {json_key}")
                
                json_content = download_string_from_r2(json_key)
                if json_content is None:
                    print(f"[DEBUG] ERRO: JSON não encontrado para vídeo {video_id}")
                    errors.append(video_id)
                    continue
                
                print(f"[DEBUG] JSON baixado, tamanho: {len(json_content)} caracteres")
                
                json_content = json_content.strip()
                if json_content.startswith('```json'):
                    json_content = json_content[7:]
                if json_content.startswith('```'):
                    json_content = json_content[3:]
                if json_content.endswith('```'):
                    json_content = json_content[:-3]
                json_content = json_content.strip()
                
                try:
                    clipes = json.loads(json_content)
                    print(f"[DEBUG] JSON parseado com sucesso. Total de clipes: {len(clipes)}")
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] ERRO ao fazer parse do JSON para vídeo {video_id}: {str(e)}")
                    errors.append(video_id)
                    continue
                
                print(f"[DEBUG] Iniciando processamento de clipes para vídeo {video_id}")
                resultado = processar_clipes(clipes, r2_prefix, video_id)
                print(f"[DEBUG] Processamento concluído para vídeo {video_id}. Resultados: {len(resultado)}")
                
                results.append(video_id)
                resultados_detalhados[video_id] = resultado
                
                processamento.videos_processados += 1
                processamento.save()
                
            except Exception as e:
                print(f"[DEBUG] ERRO geral ao processar vídeo {video_id}: {str(e)}")
                import traceback
                traceback.print_exc()
                errors.append(video_id)
                processamento.videos_processados += 1
                processamento.save()
        
        processamento.status = 'concluido'
        processamento.videos_sucesso = len(results)
        processamento.videos_erro = len(errors)
        processamento.resultados = resultados_detalhados
        processamento.erros = errors
        processamento.finalizado_em = timezone.now()
        processamento.save()
        
        print(f"[DEBUG] Processamento {processamento_id} concluído. Sucessos: {len(results)}, Erros: {len(errors)}")
        
    except Exception as e:
        print(f"[DEBUG] ERRO crítico no processamento {processamento_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        processamento.status = 'erro'
        processamento.erro = str(e)
        processamento.finalizado_em = timezone.now()
        processamento.save()


def processar_clipes_virais(request):
    if request.method not in ['GET']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    channel_id = ast.literal_eval(config('YOUTUBE_CHANNEL_ID', default=None))
    api_acqm_url = config('API_ACQM_URL', default='http://localhost:8000')
    
    try:
        channel_ids_str = str(channel_id).replace("'", '"')
        response = requests.get(
            f'{api_acqm_url}/getData/in-progress/',
            params={'channel_ids': channel_ids_str},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        videos = data.get('videos', [])
    except Exception as e:
        return JsonResponse({
            'error': f'Erro ao buscar vídeos em processamento: {str(e)}'
        }, status=500)
    
    if not videos:
        return JsonResponse({
            'status': 'sem_videos',
            'message': 'Nenhum vídeo em processamento encontrado'
        }, status=200)
    
    videos_ids = [video.get('video_id') for video in videos if video.get('video_id')]
    
    processamento = ProcessamentoClipes.objects.create(
        status='pendente',
        total_videos=len(videos_ids),
        videos_ids=videos_ids
    )
    
    thread = threading.Thread(
        target=processar_clipes_virais_background,
        args=(processamento.id,)
    )
    thread.daemon = True
    thread.start()
    
    print(f"[DEBUG] Processamento {processamento.id} iniciado em background para {len(videos_ids)} vídeos")
    
    return JsonResponse({
        'status': 'processando',
        'processamento_id': processamento.id,
        'total_videos': processamento.total_videos,
        'videos_ids': videos_ids
    }, status=200)


def verificar_status_processamento(request, processamento_id=None):
    if request.method not in ['GET']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    if processamento_id:
        try:
            processamento = ProcessamentoClipes.objects.get(id=processamento_id)
            return JsonResponse({
                'processamento_id': processamento.id,
                'status': processamento.status,
                'total_videos': processamento.total_videos,
                'videos_processados': processamento.videos_processados,
                'videos_sucesso': processamento.videos_sucesso,
                'videos_erro': processamento.videos_erro,
                'videos_ids': processamento.videos_ids,
                'resultados': processamento.resultados,
                'erros': processamento.erros,
                'erro': processamento.erro,
                'criado_em': processamento.criado_em.isoformat() if processamento.criado_em else None,
                'atualizado_em': processamento.atualizado_em.isoformat() if processamento.atualizado_em else None,
                'finalizado_em': processamento.finalizado_em.isoformat() if processamento.finalizado_em else None,
            }, status=200)
        except ProcessamentoClipes.DoesNotExist:
            return JsonResponse({
                'error': f'Processamento não encontrado: {processamento_id}'
            }, status=404)
    else:
        processamentos = ProcessamentoClipes.objects.all().order_by('-criado_em')[:50]
        processamentos_data = [{
            'processamento_id': p.id,
            'status': p.status,
            'total_videos': p.total_videos,
            'videos_processados': p.videos_processados,
            'videos_sucesso': p.videos_sucesso,
            'videos_erro': p.videos_erro,
            'criado_em': p.criado_em.isoformat() if p.criado_em else None,
            'finalizado_em': p.finalizado_em.isoformat() if p.finalizado_em else None,
        } for p in processamentos]
        
        return JsonResponse({
            'processamentos': processamentos_data,
            'total': len(processamentos_data)
        }, status=200)
    


def converter_video_916(request):
    if request.method not in ['GET', 'POST']:
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    r2_video_key = None
    r2_output_key = None
    r2_prefix = ""
    
    if request.method == 'GET':
        r2_video_key = request.GET.get('video_key')
        r2_output_key = request.GET.get('output_key')
        r2_prefix = request.GET.get('r2_prefix', '')
    elif request.method == 'POST':
        try:
            data = json.loads(request.body) if request.body else {}
            r2_video_key = data.get('video_key')
            r2_output_key = data.get('output_key')
            r2_prefix = data.get('r2_prefix', '')
        except json.JSONDecodeError:
            r2_video_key = request.POST.get('video_key')
            r2_output_key = request.POST.get('output_key')
            r2_prefix = request.POST.get('r2_prefix', '')
    
    if not r2_video_key:
        return JsonResponse({
            'error': 'Parâmetro obrigatório: video_key'
        }, status=400)
    
    if not r2_output_key:
        r2_output_key = f"{r2_prefix}video_916.mp4" if r2_prefix else "video_916.mp4"
    
    try:
        output_key = processar_video_916(r2_video_key, r2_output_key)
        
        return JsonResponse({
            'status': 'ok',
            'video_key': r2_video_key,
            'output_key': output_key
        }, status=200)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Erro ao converter vídeo: {str(e)}'
        }, status=500)
