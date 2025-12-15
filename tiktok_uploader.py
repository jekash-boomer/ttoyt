import os
import time
import json
from datetime import datetime
import subprocess
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

# Configuration
TIKTOK_USERNAME = os.getenv('TIKTOK_USERNAME', 'your_tiktok_username')
UPLOAD_HISTORY_FILE = "uploaded_videos.json"
CREDENTIALS_FILE = "credentials.json"  # YouTube API credentials
TOKEN_FILE = "token.pickle"
VIDEOS_DIR = "tiktok_videos"  # Directory to store downloaded videos

# YouTube API scopes
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def setup_directories():
    """Create necessary directories"""
    if not os.path.exists(VIDEOS_DIR):
        os.makedirs(VIDEOS_DIR)

def load_uploaded_history():
    """Load history of already uploaded videos"""
    if os.path.exists(UPLOAD_HISTORY_FILE):
        with open(UPLOAD_HISTORY_FILE, 'r') as f:
            return json.load(f)
    return {"uploaded_ids": [], "current_index": 0}

def save_uploaded_history(history):
    """Save history of uploaded videos"""
    with open(UPLOAD_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def get_youtube_service():
    """Authenticate and return YouTube service"""
    creds = None
    
    # Load saved credentials
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('youtube', 'v3', credentials=creds)

def get_all_tiktok_videos():
    """
    Fetch ALL videos from the TikTok account in chronological order (oldest first)
    Using yt-dlp Python module
    """
    print(f"Fetching all videos from @{TIKTOK_USERNAME}...")
    
    tiktok_url = f"https://www.tiktok.com/@{TIKTOK_USERNAME}"
    
    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(tiktok_url, download=False)
            
            videos = []
            if 'entries' in info:
                for entry in info['entries']:
                    videos.append({
                        'id': entry.get('id', 'unknown'),
                        'title': entry.get('title', 'TikTok Video'),
                        'url': entry.get('url') or entry.get('webpage_url') or f"https://www.tiktok.com/@{TIKTOK_USERNAME}/video/{entry.get('id')}"
                    })
            
            # Reverse to get oldest first
            videos.reverse()
            
            print(f"Found {len(videos)} videos total")
            return videos
        
    except Exception as e:
        print(f"Error fetching videos: {e}")
        print("\nMake sure yt-dlp is installed: pip install yt-dlp")
        return []

def download_tiktok_video(video_info):
    """Download TikTok video using yt-dlp Python module with browser impersonation"""
    video_id = video_info['id']
    output_file = os.path.join(VIDEOS_DIR, f"tiktok_{video_id}.mp4")
    
    # Check if already downloaded
    if os.path.exists(output_file):
        print(f"Video already downloaded: {output_file}")
        return output_file
    
    print(f"Downloading video {video_id}...")
    
    try:
        import yt_dlp
        
        ydl_opts = {
            'outtmpl': output_file,
            'format': 'best',
            'impersonate': 'chrome',  # Impersonate Chrome browser
            'quiet': False,
            'no_warnings': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_info['url']])
        
        print(f"Downloaded: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error downloading video: {e}")
        print("\nTip: Make sure curl-cffi is installed:")
        print("pip install 'yt-dlp[curl-cffi]'")
        return None

def upload_to_youtube(youtube, video_file, title, description):
    """Upload video to YouTube"""
    print(f"Uploading {video_file} to YouTube...")
    
    # Limit title to 100 characters (YouTube limit)
    title = title[:97] + "..." if len(title) > 100 else title
    
    body = {
        'snippet': {
            'title': title,
            'description': description + "\n\n📱 Share and subscribe\n#Shorts",
            'tags': ['TikTok', 'shorts', TIKTOK_USERNAME],
            'categoryId': '22'  # People & Blogs
        },
        'status': {
            'privacyStatus': 'public',  # Change to 'private' or 'unlisted' if needed
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")
    
    print(f"✓ Upload complete! Video ID: {response['id']}")
    return response['id']

def main(upload_all=False):
    """
    Main automation function
    upload_all=True: Upload ALL videos at once
    upload_all=False: Upload one video per run (for daily automation)
    """
    print(f"\n{'='*60}")
    print(f"TikTok to YouTube Uploader - {datetime.now()}")
    print(f"{'='*60}\n")
    
    # Setup
    setup_directories()
    
    # Load upload history
    history = load_uploaded_history()
    current_index = history.get('current_index', 0)
    uploaded_ids = history.get('uploaded_ids', [])
    
    # Get all TikTok videos
    all_videos = get_all_tiktok_videos()
    
    if not all_videos:
        print("No videos found or error fetching videos.")
        return
    
    # Check if we've uploaded all videos
    if current_index >= len(all_videos):
        print(f"All {len(all_videos)} videos have been uploaded!")
        return
    
    # Authenticate YouTube once
    youtube = get_youtube_service()
    
    # Determine how many videos to upload
    if upload_all:
        videos_to_process = all_videos[current_index:]
        print(f"\n🚀 BULK UPLOAD MODE: Uploading {len(videos_to_process)} videos")
        print("This may take a while...\n")
    else:
        videos_to_process = [all_videos[current_index]]
        print(f"📤 SINGLE UPLOAD MODE: Uploading 1 video")
    
    # Upload videos
    successful_uploads = 0
    failed_uploads = 0
    
    for idx, video_to_upload in enumerate(videos_to_process):
        actual_index = current_index + idx
        
        print(f"\n{'─'*60}")
        print(f"Progress: {actual_index + 1}/{len(all_videos)}")
        print(f"Video: {video_to_upload['title']}")
        print(f"{'─'*60}")
        
        # Check if already uploaded (safety check)
        if video_to_upload['id'] in uploaded_ids:
            print(f"⚠️ Already uploaded. Skipping.")
            history['current_index'] = actual_index + 1
            save_uploaded_history(history)
            continue
        
        # Download video
        video_file = download_tiktok_video(video_to_upload)
        
        if not video_file:
            print("❌ Failed to download. Skipping.")
            failed_uploads += 1
            continue
        
        # Upload to YouTube
        try:
            youtube_id = upload_to_youtube(
                youtube,
                video_file,
                video_to_upload['title'],
                video_to_upload.get('description', 'Check out my other content!')
            )
            
            # Update history
            uploaded_ids.append(video_to_upload['id'])
            history['uploaded_ids'] = uploaded_ids
            history['current_index'] = actual_index + 1
            save_uploaded_history(history)
            
            successful_uploads += 1
            print(f"✅ Successfully uploaded! ({successful_uploads} done)")
            
            # Optional: Delete downloaded file to save space
            # os.remove(video_file)
            
            # Add small delay to avoid rate limits
            if upload_all and idx < len(videos_to_process) - 1:
                print("⏳ Waiting 10 seconds before next upload...")
                time.sleep(10)
            
        except Exception as e:
            print(f"❌ Error uploading: {e}")
            failed_uploads += 1
            continue
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"📊 UPLOAD SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Successful: {successful_uploads}")
    print(f"❌ Failed: {failed_uploads}")
    print(f"📈 Total Progress: {history['current_index']}/{len(all_videos)}")
    
    if history['current_index'] >= len(all_videos):
        print(f"\n🎉 ALL VIDEOS UPLOADED! ({len(all_videos)} total)")
    else:
        remaining = len(all_videos) - history['current_index']
        print(f"\n📋 Remaining: {remaining} videos")
        if not upload_all:
            print("Run again to upload the next video.")

if __name__ == "__main__":
    # Install required packages first:
    # pip install yt-dlp google-api-python-client google-auth
    
    # Choose mode:
    
    # MODE 1: Upload ALL videos at once
    # main(upload_all=True)
    
    # MODE 2: Upload one video (for daily automation)
    main(upload_all=False)
    
    # For 24-hour automation using system scheduler:
    # Linux/Mac: Add to crontab:  0 9 * * * /usr/bin/python3 /path/to/script.py
    # Windows: Use Task Scheduler to run daily
    
    # Or uncomment below to run in continuous loop (not recommended, use cron instead):
    # while True:
    #     try:
    #         main(upload_all=False)
    #     except Exception as e:
    #         print(f"Error: {e}")
    #     print("\nWaiting 24 hours for next upload...")
    #     time.sleep(24 * 60 * 60)
