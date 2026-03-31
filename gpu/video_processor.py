import os
import subprocess
import tempfile
import re
import json

from download.r2_storage import download_file_from_r2, upload_file_to_r2, get_r2_client


def timestamp_para_segundos(timestamp):
    partes = timestamp.split(':')
    if len(partes) == 2:
        minutos, segundos = map(int, partes)
        return minutos * 60 + segundos
    elif len(partes) == 3:
        horas, minutos, segundos = map(int, partes)
        return horas * 3600 + minutos * 60 + segundos
    return 0


def formatar_timestamp_segundos(segundos):
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segs = segundos % 60
    if horas > 0:
        return f"{horas:02d}:{minutos:02d}:{segs:02d}"
    return f"{minutos:02d}:{segs:02d}"


def verificar_nvenc_disponivel():
    try:
        resultado = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            capture_output=True,
            text=True,
            check=True
        )
        return 'h264_nvenc' in resultado.stdout or 'hevc_nvenc' in resultado.stdout
    except:
        return False


def obter_dimensoes_video(video_path):
    try:
        resultado = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height', '-of', 'json', video_path],
            capture_output=True,
            text=True,
            check=True
        )
        dados = json.loads(resultado.stdout)
        if 'streams' in dados and len(dados['streams']) > 0:
            width = dados['streams'][0].get('width', 0)
            height = dados['streams'][0].get('height', 0)
            return width, height
        return None, None
    except Exception as e:
        return None, None


def cortar_video_com_gpu(video_path, inicio_segundos, duracao_segundos, output_path):
    print(f"[DEBUG] Iniciando corte de vídeo: {video_path}")
    print(f"[DEBUG] Início: {inicio_segundos}s, Duração: {duracao_segundos}s, Saída: {output_path}")
    
    inicio_formatado = formatar_timestamp_segundos(inicio_segundos)
    print(f"[DEBUG] Timestamp formatado: {inicio_formatado}")
    
    width, height = obter_dimensoes_video(video_path)
    print(f"[DEBUG] Dimensões do vídeo: {width}x{height}")
    if width is None or height is None:
        raise Exception("Não foi possível obter as dimensões do vídeo")
    
    nvenc_disponivel = verificar_nvenc_disponivel()
    print(f"[DEBUG] NVENC disponível: {nvenc_disponivel}")
    
    aspect_ratio_916 = 9 / 16
    aspect_ratio_atual = width / height
    print(f"[DEBUG] Aspect ratio atual: {aspect_ratio_atual:.3f}, Target 9:16: {aspect_ratio_916:.3f}")
    
    largura_final = 1080
    altura_final = 1920
    
    if abs(aspect_ratio_atual - aspect_ratio_916) < 0.01:
        scale_filter = f"scale={largura_final}:{altura_final}"
        print(f"[DEBUG] Vídeo já está em 9:16, apenas redimensionando")
    else:
        if aspect_ratio_atual > aspect_ratio_916:
            new_height = height
            new_width = int(height * aspect_ratio_916)
            x_offset = (width - new_width) // 2
            y_offset = 0
            print(f"[DEBUG] Vídeo mais largo, crop horizontal: {new_width}x{new_height} offset({x_offset}, {y_offset})")
        else:
            new_width = width
            new_height = int(width / aspect_ratio_916)
            x_offset = 0
            y_offset = (height - new_height) // 2
            print(f"[DEBUG] Vídeo mais alto, crop vertical: {new_width}x{new_height} offset({x_offset}, {y_offset})")
        
        scale_filter = f"crop={new_width}:{new_height}:{x_offset}:{y_offset},scale={largura_final}:{altura_final}"
    
    print(f"[DEBUG] Filtro de vídeo: {scale_filter}")
    
    if nvenc_disponivel:
        codec_video = 'h264_nvenc'
        codec_audio = 'aac'
        preset = 'slow'
    else:
        codec_video = 'libx264'
        codec_audio = 'aac'
        preset = 'slow'
    
    print(f"[DEBUG] Codec de vídeo: {codec_video}, Codec de áudio: {codec_audio}")
    
    comando = [
        'ffmpeg',
        '-i', video_path,
        '-ss', inicio_formatado,
        '-t', str(duracao_segundos),
        '-vf', scale_filter,
        '-c:v', codec_video,
        '-preset', preset,
        '-c:a', codec_audio,
        '-b:a', '192k',
        '-movflags', '+faststart',
        '-y',
        output_path
    ]
    
    if nvenc_disponivel:
        comando.extend(['-rc', 'vbr_hq', '-cq', '19', '-b:v', '0'])
    else:
        comando.extend(['-crf', '18'])
    
    print(f"[DEBUG] Comando ffmpeg: {' '.join(comando)}")
    
    try:
        print(f"[DEBUG] Executando ffmpeg...")
        resultado = subprocess.run(
            comando,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        print(f"[DEBUG] Corte concluído com sucesso: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        erro_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[DEBUG] ERRO no ffmpeg: {erro_msg}")
        
        if nvenc_disponivel and ('CUDA' in erro_msg or 'cuda' in erro_msg.lower() or 'nvenc' in erro_msg.lower()):
            print(f"[DEBUG] Erro com NVENC detectado, tentando fallback para CPU...")
            comando_cpu = [
                'ffmpeg',
                '-i', video_path,
                '-ss', inicio_formatado,
                '-t', str(duracao_segundos),
                '-vf', scale_filter,
                '-c:v', 'libx264',
                '-preset', 'slow',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                '-crf', '18',
                '-y',
                output_path
            ]
            print(f"[DEBUG] Comando ffmpeg (fallback CPU): {' '.join(comando_cpu)}")
            try:
                resultado = subprocess.run(
                    comando_cpu,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE
                )
                print(f"[DEBUG] Corte concluído com sucesso usando CPU: {output_path}")
                return True
            except subprocess.CalledProcessError as e2:
                erro_msg2 = e2.stderr.decode('utf-8', errors='ignore') if e2.stderr else str(e2)
                print(f"[DEBUG] ERRO no ffmpeg (fallback CPU): {erro_msg2}")
                raise Exception(f"Erro ao cortar vídeo mesmo com fallback para CPU: {erro_msg2}")
        
        raise Exception(f"Erro ao cortar vídeo: {erro_msg}")
    except FileNotFoundError:
        print(f"[DEBUG] ERRO: ffmpeg não encontrado no sistema")
        raise Exception("ffmpeg não está instalado no sistema")


def processar_clipes(clipes_json, r2_prefix="", video_id=""):
    print(f"[DEBUG] ===== Iniciando processamento de clipes para vídeo: {video_id} =====")
    print(f"[DEBUG] Total de clipes para processar: {len(clipes_json)}")
    
    video_key = f"{r2_prefix}{video_id}.mp4" if r2_prefix else f"{video_id}.mp4"
    clips_prefix = f"{r2_prefix}clips/{video_id}/" if r2_prefix else f"clips/{video_id}/"
    
    print(f"[DEBUG] Video key R2: {video_key}")
    print(f"[DEBUG] Clips prefix R2: {clips_prefix}")
    
    resultados = []
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_video_path = os.path.join(temp_dir, f"{video_id}.mp4")
        print(f"[DEBUG] Diretório temporário: {temp_dir}")
        print(f"[DEBUG] Caminho temporário do vídeo: {temp_video_path}")
        
        print(f"[DEBUG] Baixando vídeo do R2...")
        if not download_file_from_r2(video_key, temp_video_path):
            print(f"[DEBUG] ERRO: Falha ao baixar vídeo {video_key} do R2")
            raise Exception(f"Falha ao baixar vídeo {video_key} do R2")
        
        print(f"[DEBUG] Verificando se vídeo foi baixado...")
        if not os.path.exists(temp_video_path):
            print(f"[DEBUG] ERRO: Vídeo não existe em {temp_video_path}")
            raise Exception("Vídeo não foi baixado corretamente")
        
        file_size = os.path.getsize(temp_video_path)
        print(f"[DEBUG] Vídeo baixado com sucesso. Tamanho: {file_size / (1024*1024):.2f} MB")
        
        for idx, clipe in enumerate(clipes_json):
            print(f"[DEBUG] --- Processando clipe {idx + 1}/{len(clipes_json)} ---")
            try:
                titulo = clipe.get('titulo_viral', f'clip_{idx}')
                timestamp_inicio = clipe.get('timestamp_inicio', '00:00')
                duracao_segundos = clipe.get('duracao_segundos', 30)
                
                print(f"[DEBUG] Clipe {idx} - Título: {titulo}")
                print(f"[DEBUG] Clipe {idx} - Timestamp início: {timestamp_inicio}, Duração: {duracao_segundos}s")
                
                inicio_segundos = timestamp_para_segundos(timestamp_inicio)
                print(f"[DEBUG] Clipe {idx} - Início em segundos: {inicio_segundos}")
                
                nome_arquivo = re.sub(r'[^\w\s-]', '', titulo)
                nome_arquivo = re.sub(r'[-\s]+', '-', nome_arquivo)
                nome_arquivo = nome_arquivo.strip('-')
                nome_arquivo = nome_arquivo[:50] if nome_arquivo else f'clip_{idx}'
                
                clip_filename = f"{nome_arquivo}_{idx}.mp4"
                temp_clip_path = os.path.join(temp_dir, clip_filename)
                r2_clip_key = f"{clips_prefix}{clip_filename}"
                
                print(f"[DEBUG] Clipe {idx} - Arquivo: {clip_filename}")
                print(f"[DEBUG] Clipe {idx} - Caminho temporário: {temp_clip_path}")
                print(f"[DEBUG] Clipe {idx} - Chave R2: {r2_clip_key}")
                
                print(f"[DEBUG] Clipe {idx} - Iniciando corte...")
                cortar_video_com_gpu(
                    temp_video_path,
                    inicio_segundos,
                    duracao_segundos,
                    temp_clip_path
                )
                
                print(f"[DEBUG] Clipe {idx} - Verificando se clipe foi gerado...")
                if not os.path.exists(temp_clip_path):
                    print(f"[DEBUG] Clipe {idx} - ERRO: Arquivo não existe em {temp_clip_path}")
                    raise Exception(f"Clipe {idx} não foi gerado corretamente")
                
                clip_size = os.path.getsize(temp_clip_path)
                print(f"[DEBUG] Clipe {idx} - Clipe gerado com sucesso. Tamanho: {clip_size / (1024*1024):.2f} MB")
                
                print(f"[DEBUG] Clipe {idx} - Fazendo upload para R2...")
                if not upload_file_to_r2(temp_clip_path, r2_clip_key):
                    print(f"[DEBUG] Clipe {idx} - ERRO: Falha no upload para {r2_clip_key}")
                    raise Exception(f"Falha ao fazer upload do clipe {idx} para {r2_clip_key}")
                
                print(f"[DEBUG] Clipe {idx} - Upload concluído com sucesso!")
                resultados.append({
                    'indice': idx,
                    'titulo': titulo,
                    'status': 'sucesso',
                    'r2_key': r2_clip_key,
                    'timestamp_inicio': timestamp_inicio,
                    'duracao_segundos': duracao_segundos
                })
                
            except Exception as e:
                print(f"[DEBUG] Clipe {idx} - ERRO capturado: {str(e)}")
                import traceback
                traceback.print_exc()
                resultados.append({
                    'indice': idx,
                    'titulo': clipe.get('titulo_viral', f'clip_{idx}'),
                    'status': 'erro',
                    'erro': str(e)
                })
    
    print(f"[DEBUG] ===== Processamento de clipes concluído para vídeo: {video_id} =====")
    print(f"[DEBUG] Total de sucessos: {sum(1 for r in resultados if r.get('status') == 'sucesso')}")
    print(f"[DEBUG] Total de erros: {sum(1 for r in resultados if r.get('status') == 'erro')}")
    return resultados


def converter_para_916_com_gpu(video_path, output_path):
    width, height = obter_dimensoes_video(video_path)
    
    if width is None or height is None:
        raise Exception("Não foi possível obter as dimensões do vídeo")
    
    nvenc_disponivel = verificar_nvenc_disponivel()
    
    aspect_ratio_916 = 9 / 16
    aspect_ratio_atual = width / height
    
    if abs(aspect_ratio_atual - aspect_ratio_916) < 0.01:
        comando = [
            'ffmpeg',
            '-i', video_path,
            '-c', 'copy',
            '-y',
            output_path
        ]
    else:
        if aspect_ratio_atual > aspect_ratio_916:
            new_height = height
            new_width = int(height * aspect_ratio_916)
            x_offset = (width - new_width) // 2
            y_offset = 0
        else:
            new_width = width
            new_height = int(width / aspect_ratio_916)
            x_offset = 0
            y_offset = (height - new_height) // 2
        
        largura_final = 1080
        altura_final = 1920
        
        if nvenc_disponivel:
            codec_video = 'h264_nvenc'
            codec_audio = 'aac'
            preset = 'slow'
            scale_filter = f"scale={largura_final}:{altura_final}"
        else:
            codec_video = 'libx264'
            codec_audio = 'aac'
            preset = 'slow'
            scale_filter = f"scale={largura_final}:{altura_final}"
        
        comando = [
            'ffmpeg',
            '-i', video_path,
            '-vf', f"crop={new_width}:{new_height}:{x_offset}:{y_offset},{scale_filter}",
            '-c:v', codec_video,
            '-preset', preset,
            '-c:a', codec_audio,
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-y',
            output_path
        ]
        
        if nvenc_disponivel:
            comando.extend(['-rc', 'vbr_hq', '-cq', '19', '-b:v', '0'])
        else:
            comando.extend(['-crf', '18'])
    
    try:
        resultado = subprocess.run(
            comando,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        return True
    except subprocess.CalledProcessError as e:
        erro_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        
        if nvenc_disponivel and ('CUDA' in erro_msg or 'cuda' in erro_msg.lower() or 'nvenc' in erro_msg.lower()):
            comando_cpu = [
                'ffmpeg',
                '-i', video_path,
                '-vf', f"crop={new_width}:{new_height}:{x_offset}:{y_offset},{scale_filter}",
                '-c:v', 'libx264',
                '-preset', 'slow',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                '-crf', '18',
                '-y',
                output_path
            ]
            try:
                resultado = subprocess.run(
                    comando_cpu,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE
                )
                return True
            except subprocess.CalledProcessError as e2:
                erro_msg2 = e2.stderr.decode('utf-8', errors='ignore') if e2.stderr else str(e2)
                raise Exception(f"Erro ao converter vídeo mesmo com fallback para CPU: {erro_msg2}")
        
        raise Exception(f"Erro ao converter vídeo: {erro_msg}")
    except FileNotFoundError:
        raise Exception("ffmpeg não está instalado no sistema")


def processar_video_916(r2_video_key, r2_output_key):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_video_path = os.path.join(temp_dir, "input_video.mp4")
        temp_output_path = os.path.join(temp_dir, "output_916.mp4")
        
        if not download_file_from_r2(r2_video_key, temp_video_path):
            raise Exception(f"Falha ao baixar vídeo {r2_video_key} do R2")
        
        if not os.path.exists(temp_video_path):
            raise Exception("Vídeo não foi baixado corretamente")
        
        converter_para_916_com_gpu(temp_video_path, temp_output_path)
        
        if not os.path.exists(temp_output_path):
            raise Exception("Vídeo convertido não foi gerado corretamente")
        
        if not upload_file_to_r2(temp_output_path, r2_output_key):
            raise Exception(f"Falha ao fazer upload do vídeo convertido para {r2_output_key}")
        
    return r2_output_key
