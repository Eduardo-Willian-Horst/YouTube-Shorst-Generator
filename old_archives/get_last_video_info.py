import requests
import re

def parse_iso8601_duration(duration_str):
    if not duration_str or duration_str.startswith('P0D'): 
        return 0
        
    hours = 0
    minutes = 0
    seconds = 0

    duration_str = duration_str[2:]

    hour_match = re.search(r'(\d+)H', duration_str)
    minute_match = re.search(r'(\d+)M', duration_str)
    second_match = re.search(r'(\d+)S', duration_str)

    if hour_match:
        hours = int(hour_match.group(1))
    if minute_match:
        minutes = int(minute_match.group(1))
    if second_match:
        seconds = int(second_match.group(1))

    return (hours * 3600) + (minutes * 60) + seconds


def get_video_details(api_key, video_id):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        'part': 'contentDetails,snippet',
        'id': video_id,
        'key': api_key
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data


def get_last_video_info(api_key, channel_id):
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {
        'part': 'contentDetails',
        'id': channel_id,
        'key': api_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status() 
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except requests.exceptions.RequestException as e:
        print(f"[error] Failed to get channel info: {str(e)}")
        return None
    except (KeyError, IndexError) as e:
        print(f"[error] Failed to process API response: {str(e)}")
        return None

    print(f"[info] Found playlist ID: {playlist_id}")
    
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    params = {
        'part': 'snippet',
        'playlistId': playlist_id,
        'maxResults': 10,
        'key': api_key
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if 'items' in data and len(data['items']) > 0:
            for item in data['items']:
                video_id = item['snippet']['resourceId']['videoId']
                details = get_video_details(api_key, video_id)
                
                if 'items' in details and len(details['items']) > 0:
                    duration_str = details['items'][0]['contentDetails']['duration']
                    
                    if parse_iso8601_duration(duration_str) > 180:
                        print(f"[info] Video found: {video_id}")
                        return {
                            'video_id': video_id,
                            'video_url': f'https://www.youtube.com/watch?v={video_id}'
                        }
                    
                        

        print("[info] No video with more than 3 minutes found in the last 10 videos")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"[error] Failed to get video info: {str(e)}")
        return None
    except (KeyError, IndexError) as e:
        print(f"[error] Failed to process API response: {str(e)}")
        return None