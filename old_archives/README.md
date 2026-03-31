# YouTube Shorts Creator

Ferramenta automatizada para criar Shorts do YouTube a partir de vídeos longos, com detecção automática de trechos virais e formatação para o formato vertical 9:16.

## Funcionalidades

- Busca automática pelo último vídeo de um canal do YouTube
- Transcrição de áudio com detecção de idioma
- Identificação automática de trechos virais
- Conversão para formato vertical 9:16 (ideal para Shorts/Reels/TikTok)
- Agendamento de uploads
- Processamento em lote de múltiplos vídeos
- Gerenciamento de vídeos já processados

## Pré-requisitos

- Python 3.8+
- FFmpeg
- Conta no Google Cloud Platform com a API do YouTube ativada

## Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/Eduardo-Willian-Horst/YouTube-Shorts-create.git
   cd YouTube-Shorts-create
   ```

2. Crie e ative um ambiente virtual (recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # OU
   .\venv\Scripts\activate  # Windows
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Instale o FFmpeg:
   - **Ubuntu/Debian**: `sudo apt install ffmpeg`
   - **Fedora**: `sudo dnf install ffmpeg`
   - **macOS**: `brew install ffmpeg`
   - **Windows**: [Baixe o FFmpeg](https://ffmpeg.org/download.html) e adicione ao PATH

## Configuração

1. Crie um arquivo `.env` baseado no `.env-exemple`:
   ```bash
   cp .env-exemple .env
   ```

2. Configure as variáveis de ambiente no arquivo `.env`:
   ```
   YOUTUBE_API_KEY=sua_chave_da_api_aqui
   YOUTUBE_CHANNEL_ID=id_do_canal_aqui
   YOUTUBE_AUTH=client_secret.json
   
   # Configurações de recorte
   TARGET_MIN=20.0  # duração mínima do vídeo em segundos
   TARGET_MAX=60.0  # duração máxima do vídeo em segundos
   TOP_K=10         # número de melhores cortes para manter
   
   # Configuração de hardware
   DEVICE=cuda      # 'cuda' para GPU NVIDIA ou 'cpu'
   ```

3. Obtenha as credenciais da API do YouTube:
   - Acesse o [Google Cloud Console](https://console.cloud.google.com/)
   - Crie um novo projeto ou selecione um existente
   - Ative a API do YouTube Data API v3
   - Crie credenciais do tipo "Aplicativo do tipo Outro"
   - Baixe o arquivo JSON e renomeie para `client_secret.json`

## Como Usar

### 1. Processar vídeos automaticamente
```bash
python main.py
```

### 2. Fazer upload dos vídeos processados
```bash
python main_upload.py
```

## Estrutura de Arquivos

```
.
├── last_clips/          # Pasta com os vídeos processados
├── .env                 # Configurações (não versionado)
├── .env-exemple         # Exemplo de configuração
├── .gitignore
├── README.md
├── requirements.txt
├── client_secret.json   # Credenciais da API (não versionado)
├── token.pickle         # Token de autenticação (não versionado)
├── main.py              # Script principal
├── main_upload.py       # Script de upload agendado
├── download_video.py    # Download de vídeos
├── get_last_video_info.py # Busca informações do último vídeo
├── make_title.py        # Geração de títulos
├── to_vertical_916.py   # Conversão para formato vertical
├── upload_video.py      # Upload para o YouTube
├── video_db.py          # Gerenciamento de vídeos processados
└── viral_cuts.py        # Detecção de trechos virais
```

## Contribuição

Contribuições são bem-vindas! Siga estes passos:

1. Faça um Fork do projeto
2. Crie uma Branch para sua Feature (`git checkout -b feature/AmazingFeature`)
3. Adicione suas mudanças (`git add .`)
4. Comite suas alterações (`git commit -m 'Add some AmazingFeature'`)
5. Faça o Push da Branch (`git push origin feature/AmazingFeature`)
6. Abra um Pull Request

## Contato

Eduardo Willian Horst - [@eduardow.horst](https://www.instagram.com/eduardow.horst)

Link do Projeto: [https://github.com/Eduardo-Willian-Horst/YouTube-Shorts-create](https://github.com/Eduardo-Willian-Horst/YouTube-Shorts-create)

## Agradecimentos

- [OpenAI Whisper](https://github.com/openai/whisper) - Para transcrição de áudio
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Para download de vídeos
- [FFmpeg](https://ffmpeg.org/) - Para processamento de vídeo
- [Google YouTube API](https://developers.google.com/youtube/v3) - Para integração com o YouTube
