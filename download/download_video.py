from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
import os
import tempfile
from .r2_storage import (
    clean_r2_directory,
    upload_file_to_r2,
    delete_file_from_r2,
    file_exists_in_r2,
    upload_string_to_r2
)


def _download_with_size_fallback(video_id, temp_dir):
    outtmpl = os.path.join(temp_dir, f"{video_id}.%(ext)s")
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    format_candidates = [
        "22",
        "18",
        "best[ext=mp4][height<=720]/best[height<=720]",
        "best[ext=mp4][height<=480]/best[height<=480]",
        "best[ext=mp4][height<=360]/best[height<=360]",
        "worst[ext=mp4]/worst",
    ]

    last_error = None
    for format_code in format_candidates:
        download_ok = False
        ydl_opts = {
            "outtmpl": outtmpl,
            "format": format_code,
            "noplaylist": True,
            "quiet": False,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([source_url])
            download_ok = True
            return
        except DownloadError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
        finally:
            if not download_ok:
                for filename in os.listdir(temp_dir):
                    if filename.startswith(f"{video_id}."):
                        os.remove(os.path.join(temp_dir, filename))

    raise ValueError(f"Nao foi possivel baixar o video: {last_error}")


def download_video(url, r2_prefix=""):
    last_clips_prefix = f"{r2_prefix}last_clips/" if r2_prefix else "last_clips/"
    clean_r2_directory(last_clips_prefix)
    
    video_key = f"{r2_prefix}{url}.mp4" if r2_prefix else f"{url}.mp4"
    if file_exists_in_r2(video_key):
        delete_file_from_r2(video_key)
    
    title_key = f"{r2_prefix}{url}.txt" if r2_prefix else f"{url}.txt"
    if file_exists_in_r2(title_key):
        delete_file_from_r2(title_key)
    
    with YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        video_title = info.get('title', 'video')
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_video_path = os.path.join(temp_dir, f"{url}.mp4")
        _download_with_size_fallback(url, temp_dir)
        
        if os.path.exists(temp_video_path):
            upload_file_to_r2(temp_video_path, video_key)
        else:
            video_files = [f for f in os.listdir(temp_dir) if f.startswith(f"{url}.")]
            if video_files:
                actual_video_path = os.path.join(temp_dir, video_files[0])
                upload_file_to_r2(actual_video_path, video_key)
    
    upload_string_to_r2(video_title, title_key)
    
    return video_title
