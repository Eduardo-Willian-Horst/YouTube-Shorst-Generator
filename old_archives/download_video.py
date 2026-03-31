from yt_dlp import YoutubeDL
import os
import shutil

def clean_directory(directory):
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'[error] Failed to delete {file_path}: {str(e)}')

def download_video(url, folder="."):
    last_clips_dir = os.path.join(folder, "last_clips")
    clean_directory(last_clips_dir)
    
    video_path = os.path.join(folder, "new_video.mp4")
    if os.path.exists(video_path):
        os.remove(video_path)
    
    title_path = os.path.join(folder, "title.txt")
    if os.path.exists(title_path):
        os.remove(title_path)

    
    with YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        video_title = info.get('title', 'video')
    

    ydl_opts = {
        "outtmpl": f"{folder}/new_video.%(ext)s",
        "format": "22/18",
        "noplaylist": True,
        "quiet": False,
        # Opções para evitar erro 403
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    with open(f"{folder}/title.txt", 'w', encoding='utf-8') as f:
        f.write(video_title)
    
    return video_title
