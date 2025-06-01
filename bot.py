import os
import requests
import time
from datetime import datetime
from googleapiclient.discovery import build
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer
from langdetect import detect

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
YT_API_KEY = os.getenv('YT_API_KEY')
PORT = int(os.getenv('PORT', 10000))
CHECK_INTERVAL = 300  # 5 minutes

# Language Templates
LANGUAGE_TEMPLATES = {
    'en': {
        'upload': '🎥 New video from {channel}!\n\n📌 {title}\n⏰ {time}\n🔗 {url}',
        'live': '🔴 {channel} is LIVE!\n\n📌 {title}\n👀 {url}',
        'default': '✨ New activity from {channel}!\n\n📌 {title}\n⏰ {time}\n🔗 {url}'
    },
    'es': {
        'upload': '🎥 ¡Nuevo video de {channel}!\n\n📌 {title}\n⏰ {time}\n🔗 {url}',
        'live': '🔴 ¡{channel} está EN VIVO!\n\n📌 {title}\n👀 {url}',
        'default': '✨ Nueva actividad de {channel}!\n\n📌 {title}\n⏰ {time}\n🔗 {url}'
    },
    'ru': {
        'upload': '🎥 Новое видео от {channel}!\n\n📌 {title}\n⏰ {time}\n🔗 {url}',
        'live': '🔴 {channel} в ЭФИРЕ!\n\n📌 {title}\n👀 {url}',
        'default': '✨ Новая активность от {channel}!\n\n📌 {title}\n⏰ {time}\n🔗 {url}'
    }
}

class YouTubeMonitor:
    def __init__(self):
        self.youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
        self.channel_cache = {}  # Stores channel_id: language
    
    def detect_language(self, text):
        try:
            return detect(text[:500])  # Only analyze first 500 chars for performance
        except:
            return 'en'  # Default fallback
    
    def get_channel_info(self, channel_id):
        """Get channel language and title"""
        if channel_id in self.channel_cache:
            return self.channel_cache[channel_id]
        
        request = self.youtube.channels().list(
            part='snippet',
            id=channel_id
        )
        response = request.execute()
        
        if not response.get('items'):
            return {'title': 'Unknown Channel', 'lang': 'en'}
        
        snippet = response['items'][0]['snippet']
        channel_title = snippet['title']
        lang = self.detect_language(snippet.get('description', '') + ' ' + channel_title)
        
        self.channel_cache[channel_id] = {'title': channel_title, 'lang': lang}
        return self.channel_cache[channel_id]

    def get_activities(self, channel_id):
        activities = []
        request = self.youtube.activities().list(
            part='snippet,contentDetails',
            channelId=channel_id,
            maxResults=10
        )
        
        try:
            response = request.execute()
            for item in response.get('items', []):
                activity_type = item['snippet']['type']
                if activity_type not in ['upload', 'live']:
                    continue
                    
                activities.append({
                    'type': activity_type,
                    'title': item['snippet']['title'],
                    'time': item['snippet']['publishedAt'],
                    'video_id': item['contentDetails'].get('upload', {}).get('videoId') or
                              item['contentDetails'].get('liveBroadcast', {}).get('activeLiveChatId')
                })
        except Exception as e:
            print(f"YouTube API Error: {e}")
        return activities

class TelegramNotifier:
    @staticmethod
    def format_message(activity, channel_info):
        lang = channel_info['lang']
        templates = LANGUAGE_TEMPLATES.get(lang, LANGUAGE_TEMPLATES['en'])
        
        activity_time = datetime.fromisoformat(activity['time'].replace('Z', '+00:00'))
        formatted_time = activity_time.strftime('%Y-%m-%d %H:%M')
        
        url = (f"https://youtu.be/{activity['video_id']}" if activity['type'] == 'upload'
              else f"https://youtube.com/watch?v={activity['video_id']}")
        
        return templates.get(activity['type'], templates['default']).format(
            channel=channel_info['title'],
            title=activity['title'],
            time=formatted_time,
            url=url
        )
    
    @staticmethod
    def send_notification(message):
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                'chat_id': CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
        )

def monitor_channels():
    monitor = YouTubeMonitor()
    last_activities = {}
    
    # Track channels by ID or username (@handle)
    channels_to_monitor = [
        "@MrBeast",  # English
        "@wylsacom",  # Russian
        "@HolaSoyGerman"  # Spanish
    ]
    
    while True:
        for channel in channels_to_monitor:
            try:
                # Convert @username to channel ID if needed
                if channel.startswith('@'):
                    search = monitor.youtube.search().list(
                        q=channel,
                        part='id',
                        type='channel',
                        maxResults=1
                    ).execute()
                    if not search.get('items'):
                        continue
                    channel_id = search['items'][0]['id']['channelId']
                else:
                    channel_id = channel
                
                # Get channel language and activities
                channel_info = monitor.get_channel_info(channel_id)
                activities = monitor.get_activities(channel_id)
                
                for activity in activities:
                    activity_key = f"{channel_id}_{activity['video_id']}"
                    if activity_key not in last_activities:
                        message = TelegramNotifier.format_message(activity, channel_info)
                        TelegramNotifier.send_notification(message)
                        last_activities[activity_key] = activity['time']
                        
            except Exception as e:
                print(f"Error processing {channel}: {str(e)}")
        
        time.sleep(CHECK_INTERVAL)

# Health Check and Server Setup (same as before)
# ...

if __name__ == '__main__':
    # Install additional dependency first:
    # pip install langdetect
    
    Thread(target=monitor_channels, daemon=True).start()
    
    # Health server
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'YT Tracker Active')
    
    HTTPServer(('0.0.0.0', PORT), HealthHandler).serve_forever()