import google.generativeai as genai
import time
import os
from decouple import config

# 1. CONFIGURAÇÃO
api_key = config("GOOGLE_API_KEY", default="").strip()
if not api_key:
    raise ValueError("GOOGLE_API_KEY não configurada nas variáveis de ambiente")
genai.configure(api_key=api_key)

def processar_audio_com_gemini(caminho_do_audio):
    print(f"--- Iniciando upload de: {caminho_do_audio} ---")
    
    # 2. UPLOAD DO ARQUIVO (File API)
    # Isso envia o áudio para os servidores do Google temporariamente
    audio_file = genai.upload_file(path=caminho_do_audio)
    print(f"Upload concluído: {audio_file.uri}")

    # 3. VERIFICAR PROCESSAMENTO
    # Arquivos de áudio/vídeo precisam ser processados antes de usar
    while audio_file.state.name == "PROCESSING":
        print("Processando arquivo...")
        time.sleep(5)
        audio_file = genai.get_file(audio_file.name)

    if audio_file.state.name == "FAILED":
        raise ValueError("O processamento do arquivo falhou.")
    
    print("Arquivo pronto!")

    # 4. DEFINIR O MODELO
    # O 'gemini-1.5-flash' é o mais rápido e eficiente para o plano gratuito
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")

    # 5. O PROMPT (SEU PEDIDO)
    # Aqui colocamos o prompt otimizado que discutimos antes
    prompt_texto = """
    Atue como um especialista em edição de vídeos para TikTok e Reels. Analise o vídeo enviado e identifique os segmentos com maior potencial viral (humor, plot twists ou diálogos impactantes).

Gere uma saída estritamente em formato JSON contendo uma lista de objetos. Cada objeto deve ter:

titulo_viral: Um título chamativo, curto e curioso (estilo clickbait para YouTube).

timestamp_inicio: O tempo exato onde o corte deve começar (formato MM:SS).

duracao_segundos: A duração do corte em segundos (busque cortes entre 30s e 60s).

transcricao: O texto exato do que é falado nesse trecho.

motivo_viral: Uma breve explicação do porquê esse trecho vai engajar.

Não inclua texto introdutório, apenas o JSON.
    """

    # 6. FAZER A CHAMADA
    print("Gerando resposta...")
    response = model.generate_content(
        [audio_file, prompt_texto],
        request_options={"timeout": 600} # Aumenta o tempo limite para áudios longos
    )

    # 7. RESULTADO
    print("\n--- RESPOSTA DA IA ---")
    print(response.text)

    # (Opcional) Deletar o arquivo do servidor do Google para limpar
    # genai.delete_file(audio_file.name)

# --- EXECUÇÃO ---
# Salve seu áudio como 'meu_audio.mp3' na mesma pasta do script
# processar_audio_com_gemini("meu_audio.mp3")


processar_audio_com_gemini("voice.mp3")