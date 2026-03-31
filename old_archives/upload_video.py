import os
import re
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

VIDEOS_FOLDER = 'last_clips'
VALID_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')
TOKEN_FILENAME = 'token.pickle'

def youtube_authenticator():
    credentials = None
    if os.path.exists(TOKEN_FILENAME):
        with open(TOKEN_FILENAME, 'rb') as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            scopes = ["https://www.googleapis.com/auth/youtube.upload"]
            flow = InstalledAppFlow.from_client_secrets_file('client_secret_2_1059095800701-k86q717lbqhm54pt0bl4174p3j7etb52.apps.googleusercontent.com.json', scopes)
            credentials = flow.run_local_server(port=0)
        
        with open(TOKEN_FILENAME, 'wb') as token:
            pickle.dump(credentials, token)
            
    return build('youtube', 'v3', credentials=credentials)

def upload_video(youtube, file_path, title, description, category, privacy):
    request_body = {
        'snippet': {
            'title': title,
            'description': description,
            'categoryId': category
        },
        'status': {
            'privacyStatus': privacy,
            'madeForKids': False
        }
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part=','.join(request_body.keys()),
        body=request_body,
        media_body=media
    )
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[info] Upload progress: {int(status.progress() * 100)}%")
            
    print(f"[success] Upload complete! Video ID: {response.get('id')}")
    return response.get('id')

def get_next_video(folder):
    videos_to_upload = []
    for file in os.listdir(folder):
        if file.lower().endswith(VALID_EXTENSIONS):
            match = re.search(r'(\d+)\.\w+$', file)
            if match:
                order_number = int(match.group(1))
                full_path = os.path.join(folder, file)
                videos_to_upload.append((order_number, full_path))
    
    videos_to_upload.sort()
    return videos_to_upload[0][1] if videos_to_upload else None

if __name__ == '__main__':
    next_video = get_next_video(VIDEOS_FOLDER)

    if not next_video:
        print("[info] No video found in the folder.")
    else:
        print(f"[info] Next video to upload: {next_video}")
        
        try:
            youtube = youtube_authenticator()

            filename = os.path.basename(next_video)
            
            title = f"{filename} #Shorts"
            
            description = ""
            category_id = "17" 
            privacy_status = "public" 
            
            upload_video(youtube, next_video, title, description, category_id, privacy_status)

            print(f"[success] Deleting processed video: {next_video}")
            os.remove(next_video)

        except FileNotFoundError:
            print("[error] The file 'client_secret.json' was not found.")
            print("[info] Please follow the instructions in Part 1 to configure the YouTube API.")
        except Exception as e:
            print(f"[error] An unexpected error occurred: {str(e)}")