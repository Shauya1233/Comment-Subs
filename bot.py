import discord
from discord.ext import commands, tasks
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import json

# Config
TOKEN = os.getenv('DISCORD_TOKEN')
YOUTUBE_TOKEN_JSON = os.getenv('YOUTUBE_TOKEN_JSON')
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
VERIFIED_SUB_THRESHOLD = 100000
CHECK_INTERVAL = 30  # seconds

# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# YouTube service
youtube_service = None
checked_comments = set()

def authenticate_youtube():
    """Load YouTube credentials from environment variable"""
    global youtube_service
    try:
        if not YOUTUBE_TOKEN_JSON:
            print("Error: YOUTUBE_TOKEN_JSON environment variable not set")
            return False
        
        # Parse the JSON token
        token_data = json.loads(YOUTUBE_TOKEN_JSON)
        
        # Create credentials from the token
        creds = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )
        
        youtube_service = build('youtube', 'v3', credentials=creds)
        print("YouTube authenticated successfully")
        return True
    except Exception as e:
        print(f"YouTube auth error: {e}")
        return False

def get_latest_video_id():
    """Get latest video from your channel"""
    try:
        channels = youtube_service.channels().list(part='contentDetails', mine=True).execute()
        playlist_id = channels['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        videos = youtube_service.playlistItems().list(
            playlistId=playlist_id, part='snippet', maxResults=1
        ).execute()
        
        return videos['items'][0]['snippet']['resourceId']['videoId']
    except Exception as e:
        print(f"Error getting video: {e}")
        return None

def get_subscriber_count(channel_id):
    """Get channel subscriber count"""
    try:
        channel = youtube_service.channels().list(part='statistics', id=channel_id).execute()
        if channel['items']:
            return int(channel['items'][0]['statistics'].get('subscriberCount', 0))
    except:
        pass
    return 0

def moderate_comments():
    """Check and delete non-verified comments"""
    video_id = get_latest_video_id()
    if not video_id:
        return
    
    try:
        comments = youtube_service.commentThreads().list(
            part='snippet', videoId=video_id, maxResults=100, textFormat='plainText'
        ).execute()
        
        if not comments.get('items'):
            return
        
        for thread in comments['items']:
            comment = thread['snippet']['topLevelComment']
            comment_id = comment['id']
            channel_id = comment['snippet']['authorChannelId']['value']
            author = comment['snippet']['authorDisplayName']
            
            if comment_id in checked_comments:
                continue
            
            checked_comments.add(comment_id)
            
            sub_count = get_subscriber_count(channel_id)
            
            if sub_count < VERIFIED_SUB_THRESHOLD:
                try:
                    youtube_service.comments().delete(id=comment_id).execute()
                    print(f"Deleted: {author} ({sub_count} subs)")
                except Exception as e:
                    print(f"Error deleting {comment_id}: {e}")
    
    except Exception as e:
        print(f"Error moderating: {e}")

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_comments_task():
    """Run moderation every 30 seconds"""
    if youtube_service:
        moderate_comments()

@bot.event
async def on_ready():
    """Bot started"""
    print(f"Bot logged in as {bot.user}")
    if not check_comments_task.is_running():
        check_comments_task.start()

if __name__ == '__main__':
    if authenticate_youtube():
        bot.run(TOKEN)
    else:
        print("Failed to authenticate YouTube")
