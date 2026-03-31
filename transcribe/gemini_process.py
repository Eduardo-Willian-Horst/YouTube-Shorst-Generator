import google.generativeai as genai
import time
import os
import tempfile
from decouple import config
from download.r2_storage import download_file_from_r2, upload_string_to_r2

def processar_audio_com_gemini(r2_audio_key, r2_prefix="", video_id="gemini_result"):
    api_key = config('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY não configurada nas variáveis de ambiente")
    
    genai.configure(api_key=api_key)
    
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_audio_path = os.path.join(temp_dir, "voice.mp3")
        
        if not download_file_from_r2(r2_audio_key, temp_audio_path):
            raise Exception(f"Falha ao baixar áudio {r2_audio_key} do R2")
        
        if not os.path.exists(temp_audio_path):
            raise Exception("Arquivo de áudio não foi baixado corretamente")
        
        audio_file = genai.upload_file(path=temp_audio_path)
        
        while audio_file.state.name == "PROCESSING":
            time.sleep(5)
            audio_file = genai.get_file(audio_file.name)
        
        if audio_file.state.name == "FAILED":
            raise ValueError("O processamento do arquivo falhou.")
        
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        prompt_texto = """
    Atue como um especialista em edição de vídeos para TikTok e Reels. Analise o vídeo enviado e identifique os segmentos com maior potencial viral (humor, plot twists ou diálogos impactantes).

Gere uma saída estritamente em formato JSON contendo uma lista de objetos. Cada objeto deve ter:

titulo_viral: Um título chamativo, curto e curioso (estilo clickbait para YouTube).

timestamp_inicio: O tempo exato onde o corte deve começar (formato MM:SS).

duracao_segundos: A duração do corte em segundos (busque cortes entre 30s e 60s).

transcricao: O texto exato do que é falado nesse trecho.

motivo_viral: Uma breve explicação do porquê esse trecho vai engajar.

Não inclua texto introdutório, apenas o JSON. Crie de 8 a 10 cortes virais.

Tome cuidado para não faltar nenhuma virgula delimitador entre os objetos nem entre os atributos de cada objeto.
    """ 
        
        response = model.generate_content(
            [audio_file, prompt_texto],
            request_options={"timeout": 600}
        )
        
        json_resultado = response.text
        
        json_key = f"{r2_prefix}{video_id}.json" if r2_prefix else f"{video_id}.json"
        if not upload_string_to_r2(json_resultado, json_key):
            raise Exception(f"Falha ao salvar JSON no R2: {json_key}")
        
        for attempt in range(5):
            try:
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
                break
            except PermissionError:
                time.sleep(0.4 * (attempt + 1))

        return json_resultado
