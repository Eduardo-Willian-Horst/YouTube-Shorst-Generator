import json
import os

DB_FILE = "processed_videos.json"

def setup_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, 'w') as f:
            json.dump({"processed_videos": []}, f, indent=4)
        print(f'[info] Created new database file: {DB_FILE}')

def is_video_processed(video_id: str) -> bool:
    setup_db()
    try:
        with open(DB_FILE, 'r') as f:
            data = json.load(f)
        is_processed = video_id in data["processed_videos"]
        if is_processed:
            print(f'[info] Video {video_id} is already processed')
        return is_processed
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f'[error] Error checking if video {video_id} is processed: {str(e)}')
        return False

def mark_video_processed(video_id: str):
    setup_db()
    try:
        with open(DB_FILE, 'r+') as f:
            data = json.load(f)
            if video_id not in data["processed_videos"]:
                data["processed_videos"].append(video_id)
                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
                print(f'[success] Marked video {video_id} as processed')
            else:
                print(f'[info] Video {video_id} was already marked as processed')
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f'[warning] Error reading database, creating new one: {str(e)}')
        with open(DB_FILE, 'w') as f:
            json.dump({"processed_videos": [video_id]}, f, indent=4)
            print(f'[info] Created new database with video {video_id}')
