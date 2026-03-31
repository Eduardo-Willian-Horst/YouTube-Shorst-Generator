import os
import subprocess
import tempfile
from download.r2_storage import download_file_from_r2, upload_file_to_r2, delete_file_from_r2, file_exists_in_r2

def extract_audio_from_video(video_id, r2_prefix=""):
    audio_key = f"{r2_prefix}{video_id}.mp3" if r2_prefix else f"{video_id}.mp3"
    
    if file_exists_in_r2(audio_key):
        delete_file_from_r2(audio_key)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_video_path = os.path.join(temp_dir, f"{video_id}.mp4")
        temp_audio_path = os.path.join(temp_dir, f"{video_id}.mp3")
        
        video_key = f"{r2_prefix}{video_id}.mp4" if r2_prefix else f"{video_id}.mp4"
        if not download_file_from_r2(video_key, temp_video_path):
            raise Exception(f"Falha ao baixar vídeo {video_id} do R2")
        
        try:
            subprocess.run(
                [
                    'ffmpeg',
                    '-i', temp_video_path,
                    '-vn',
                    '-acodec', 'libmp3lame',
                    '-ab', '192k',
                    '-ar', '44100',
                    '-y',
                    temp_audio_path
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError as e:
            raise Exception(f"Falha ao extrair áudio: {str(e)}")
        except FileNotFoundError:
            raise Exception("ffmpeg não está instalado no sistema")
        
        if not os.path.exists(temp_audio_path):
            raise Exception("Áudio não foi gerado corretamente")
        
        if not upload_file_to_r2(temp_audio_path, audio_key):
            raise Exception(f"Falha ao fazer upload do áudio para {audio_key}")
    
    return audio_key
