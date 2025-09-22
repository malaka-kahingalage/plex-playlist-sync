import os
import logging
import time
import re
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import musicbrainzngs
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TXXX
from spotdl.download.downloader import Downloader
from spotdl.types.song import Song
from ytmusicapi import YTMusic
from thefuzz import fuzz, process
import shutil

# Configure logging
logger = logging.getLogger(__name__)

# Suppress noisy logs
logging.getLogger("spotdl").setLevel(logging.WARNING)
logging.getLogger("pytube").setLevel(logging.ERROR)
logging.getLogger("yt_dlp").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

class EnhancedDownloader:
    def __init__(self, download_dir: str = "/app/downloads", max_workers: int = 3):
        self.download_dir = download_dir
        self.max_workers = max_workers
        self.ytmusic = YTMusic()
        
        # Initialize spotDL
        from credential import get_spotify_credentials
        from spotdl.utils.spotify import SpotifyClient
        client_id, client_secret = get_spotify_credentials()
        SpotifyClient.init(client_id, client_secret, user_auth=False)
        
        # SpotDL settings
        self.spotdl_settings = {
            'output': f'{download_dir}/{{artist}} - {{title}}.{{output-ext}}',
            'format': 'mp3',
            'bitrate': '320k',
            'audio_providers': ['youtube', 'youtube-music'],
            'lyrics_providers': ['genius', 'musixmatch'],
            'overwrite': 'skip',
            'scan_for_songs': False,
            'print_errors': False,
        }
        
        os.makedirs(download_dir, exist_ok=True)

    def string_cleaner(self, input_string: str) -> str:
        """Clean string for file names and matching"""
        if not input_string:
            return ""
        raw_string = re.sub(r'[\/:*?"<>|]', " ", input_string)
        temp_string = re.sub(r"\s+", " ", raw_string)
        return temp_string.strip()

    def enhanced_youtube_search(self, artist: str, title: str) -> Optional[str]:
        """Enhanced YouTube search with multiple fallback strategies"""
        try:
            cleaned_artist = self.string_cleaner(artist).lower()
            cleaned_title = self.string_cleaner(title).lower()
            
            logger.info(f"🔍 Searching YouTube for: {artist} - {title}")
            
            # Primary search
            search_results = self.ytmusic.search(
                query=f"{artist} {title}", 
                filter="songs", 
                limit=10
            )
            
            if not search_results:
                logger.warning(f"⚠️  No YouTube results found for: {artist} - {title}")
                return None
            
            # Strategy 1: Exact title match
            for item in search_results:
                cleaned_youtube_title = self.string_cleaner(item["title"]).lower()
                if cleaned_title in cleaned_youtube_title:
                    youtube_url = f"https://www.youtube.com/watch?v={item['videoId']}"
                    logger.info(f"✅ Exact match found: {item['title']}")
                    return youtube_url
            
            # Strategy 2: Fuzzy matching with high thresholds
            best_match = None
            best_score = 0
            
            for item in search_results:
                cleaned_youtube_title = self.string_cleaner(item["title"]).lower()
                cleaned_youtube_artists = ", ".join(
                    self.string_cleaner(x["name"]).lower() 
                    for x in item.get("artists", [])
                )
                
                # Calculate fuzzy scores
                title_score = fuzz.ratio(cleaned_title, cleaned_youtube_title)
                artist_score = fuzz.ratio(cleaned_artist, cleaned_youtube_artists)
                
                # Weighted combined score
                combined_score = (title_score * 0.7) + (artist_score * 0.3)
                
                if combined_score > best_score and (title_score >= 85 or artist_score >= 90):
                    best_score = combined_score
                    best_match = item
            
            if best_match:
                youtube_url = f"https://www.youtube.com/watch?v={best_match['videoId']}"
                logger.info(f"✅ Fuzzy match found (score: {best_score:.1f}): {best_match['title']}")
                return youtube_url
            
            # Strategy 3: Top result fallback
            try:
                top_search_results = self.ytmusic.search(query=cleaned_title, limit=5)
                if top_search_results:
                    top_result = top_search_results[0]
                    if top_result.get("category") == "Top result" or top_result.get("resultType") in ["song", "video"]:
                        youtube_url = f"https://www.youtube.com/watch?v={top_result['videoId']}"
                        logger.info(f"📍 Using top result: {top_result['title']}")
                        return youtube_url
            except Exception as e:
                logger.debug(f"Top result search failed: {e}")
            
            # Strategy 4: Best available fallback
            if search_results:
                fallback = search_results[0]
                youtube_url = f"https://www.youtube.com/watch?v={fallback['videoId']}"
                logger.warning(f"⚠️  Using fallback result: {fallback['title']}")
                return youtube_url
            
            logger.error(f"❌ No suitable YouTube match found for: {artist} - {title}")
            return None
            
        except Exception as e:
            logger.error(f"❌ YouTube search failed for {artist} - {title}: {e}")
            return None

    def download_single_track(self, track: Dict, track_index: int, total_tracks: int) -> Tuple[bool, str, Optional[str]]:
        """Download a single track with enhanced progress tracking"""
        artist = track.get('artist', 'Unknown Artist')
        title = track.get('title', 'Unknown Title')
        spotify_url = track.get('url', '')
        
        try:
            msg = f"🎵 [{track_index}/{total_tracks}] Processing: {artist} - {title}"
            logger.info(msg)
            print(msg)
            
            # Check if file already exists
            filename = f"{self.string_cleaner(artist)} - {self.string_cleaner(title)}.mp3"
            filepath = os.path.join(self.download_dir, filename)
            
            if os.path.exists(filepath):
                msg = f"⏭️  [{track_index}/{total_tracks}] Already exists: {artist} - {title}"
                logger.info(msg)
                print(msg)
                return True, f"File already exists: {filename}", filepath
            
            # Enhanced YouTube search
            youtube_url = self.enhanced_youtube_search(artist, title)
            if not youtube_url:
                return False, f"No YouTube match found for: {artist} - {title}", None
            
            # Create Song object and download using spotDL
            try:
                if spotify_url:
                    song = Song.from_url(spotify_url)
                else:
                    # Create song from search if no Spotify URL
                    song = Song.from_search_term(f"{artist} {title}")
                
                # Override with our found YouTube URL
                song.download_url = youtube_url
                
                downloader = Downloader(self.spotdl_settings)
                result_path = downloader.download_song(song)
                
                if result_path:
                    msg = f"✅ [{track_index}/{total_tracks}] Downloaded: {artist} - {title}"
                    logger.info(msg)
                    print(msg)
                    return True, f"Successfully downloaded: {filename}", result_path
                else:
                    msg = f"❌ [{track_index}/{total_tracks}] Download failed: {artist} - {title}"
                    logger.error(msg)
                    print(msg)
                    return False, f"SpotDL download failed for: {artist} - {title}", None
                    
            except Exception as e:
                msg = f"❌ [{track_index}/{total_tracks}] SpotDL error for {artist} - {title}: {e}"
                logger.error(msg)
                print(msg)
                return False, f"Download error: {str(e)}", None
                
        except Exception as e:
            msg = f"❌ [{track_index}/{total_tracks}] Unexpected error for {artist} - {title}: {e}"
            logger.error(msg)
            print(msg)
            return False, f"Unexpected error: {str(e)}", None

    def download_missing_tracks_enhanced(self, tracks: List[Dict]) -> Dict:
        """Enhanced download with individual song processing and progress tracking"""
        if not tracks:
            logger.info("No missing tracks to download.")
            return {"total": 0, "successful": 0, "failed": 0, "results": []}
        
        total_tracks = len(tracks)
        logger.info(f"🚀 Starting enhanced download of {total_tracks} missing tracks...")
        logger.info(f"⚙️  Using {self.max_workers} parallel workers")
        
        results = {
            "total": total_tracks,
            "successful": 0,
            "failed": 0,
            "results": [],
            "downloaded_files": []
        }
        
        # Process tracks with ThreadPoolExecutor for controlled parallelism
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all download tasks
            future_to_track = {
                executor.submit(self.download_single_track, track, i+1, total_tracks): (track, i+1)
                for i, track in enumerate(tracks)
            }
            
            # Process completed downloads
            for future in as_completed(future_to_track):
                track, track_index = future_to_track[future]
                try:
                    success, message, file_path = future.result()
                    
                    result_entry = {
                        "track": f"{track.get('artist', 'Unknown')} - {track.get('title', 'Unknown')}",
                        "success": success,
                        "message": message,
                        "file_path": file_path
                    }
                    results["results"].append(result_entry)
                    
                    if success:
                        results["successful"] += 1
                        if file_path:
                            results["downloaded_files"].append(file_path)
                    else:
                        results["failed"] += 1
                        
                except Exception as e:
                    msg = f"❌ Task execution failed for track {track_index}: {e}"
                    logger.error(msg)
                    print(msg)
                    results["failed"] += 1
                    results["results"].append({
                        "track": f"{track.get('artist', 'Unknown')} - {track.get('title', 'Unknown')}",
                        "success": False,
                        "message": f"Task execution error: {str(e)}",
                        "file_path": None
                    })
        
        # Summary
        summary_msgs = [
            f"📊 Download Summary:",
            f"  ✅ Successful: {results['successful']}",
            f"  ❌ Failed: {results['failed']}",
            f"  📁 Total files: {len(results['downloaded_files'])}"
        ]
        for msg in summary_msgs:
            logger.info(msg)
            print(msg)
        
        return results


def download_missing_tracks_enhanced_main(tracks: List[Dict], download_dir: str = "/app/downloads", max_workers: int = 3) -> Dict:
    """Main function to use the enhanced downloader"""
    downloader = EnhancedDownloader(download_dir, max_workers)
    return downloader.download_missing_tracks_enhanced(tracks)