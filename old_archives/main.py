import os
import schedule
import time
from dotenv import load_dotenv
from get_last_video_info import get_last_video_info
from video_db import is_video_processed, mark_video_processed
from download_video import download_video
from viral_cuts import make_viral_cuts
from to_vertical_916 import to_vertical_916
from make_title import make_title

load_dotenv()

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
YOUTUBE_CHANNEL_ID = os.getenv('YOUTUBE_CHANNEL_ID')
YOUTUBE_AUTH = os.getenv('YOUTUBE_AUTH')

print('[info] YouTube API key loaded')

def short_create():
    
    video_info = get_last_video_info(YOUTUBE_API_KEY, YOUTUBE_CHANNEL_ID)

    if not video_info:
        print("[error] Unable to get video info.")
        return
    
    video_id = video_info.get('video_id')

    if is_video_processed(video_id):
        return
    
    print(f"[info] Video ID: {video_id}")
    download_video(video_info.get('video_url'))
    make_viral_cuts()
    to_vertical_916()
    make_title()
    



    mark_video_processed(video_id)
    print(f"[success] Video {video_id} marked as processed.")

def execution_controll():
    short_create()
    
    schedule.every().day.at("00:00").do(short_create)
    
    print("[info] Press Ctrl+C to kill the program.")
    print(f"[info] Next execution: {schedule.next_run()}")
    
    while True:
        try:
            schedule.run_pending()  
            time.sleep(60)
        except KeyboardInterrupt:
            print("\n[info] Shutting down Short Creator...")
            break

if __name__ == "__main__":
    print("[info] Starting Short Creator...")
    execution_controll()