
import os
import logging
import musicbrainzngs
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TXXX
from spotdl.download.downloader import Downloader
from spotdl.types.song import Song

# Configure logging to always output to console
logger = logging.getLogger(__name__)
logger.propagate = True  # Ensure logs go to root logger
root_logger = logging.getLogger()
if not root_logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(handler)
root_logger.setLevel(logging.INFO)
logger.setLevel(logging.INFO)

# Suppress noisy logs from spotdl, pytube, etc.
logging.getLogger("spotdl").setLevel(logging.WARNING)
logging.getLogger("pytube").setLevel(logging.ERROR)
logging.getLogger("yt_dlp").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

def download_missing_tracks_spotdl(tracks, download_dir):
    # Initialize spotDL Spotify client
    from credential import get_spotify_credentials
    from spotdl.utils.spotify import SpotifyClient
    client_id, client_secret = get_spotify_credentials()
    
    # Try to initialize SpotifyClient, but don't fail if already initialized
    try:
        SpotifyClient.init(client_id, client_secret, user_auth=False)
    except Exception as e:
        if "already been initialized" in str(e):
            logger.info("🔄 SpotifyClient already initialized, reusing existing client")
        else:
            logger.warning(f"SpotifyClient initialization warning: {e}")
    
    """
    Downloads missing tracks using spotDL as a library, then tags MBIDs if missing.
    Expects tracks as a list of dicts with at least 'title', 'artist', 'album', 'url'.
    """
    if not tracks:
        logger.info("No missing tracks to download.")
        return
    
    logger.info(f"🎵 Starting download of {len(tracks)} missing tracks...")
    os.makedirs(download_dir, exist_ok=True)
    
    # Prepare list of Spotify URLs for spotDL
    track_urls = [t['url'] for t in tracks if t.get('url')]
    if not track_urls:
        logger.warning("No valid Spotify URLs to download.")
        return
    import subprocess
    import sys
    # Write URLs to a temporary file
    # Use spotDL as a library: create Song objects from URLs and download
    from spotdl.types.song import Song
    from spotdl.download.downloader import Downloader
    from thefuzz import process
    import shutil
    from plex_utils import setup_plex_client, get_music_library
    # Create Song objects using Song.from_url
    song_objs = []
    logger.info("🔍 Creating download objects for tracks...")
    for i, t in enumerate(tracks, 1):
        url = t.get('url')
        if not url:
            continue
        try:
            song = Song.from_url(url)
            song_objs.append(song)
            logger.info(f"  [{i}/{len(tracks)}] ✅ {t.get('artist', 'Unknown')} - {t.get('title', 'Unknown')}")
        except Exception as e:
            logger.error(f"  [{i}/{len(tracks)}] ❌ Failed to create Song object for {url}: {e}")
    
    if not song_objs:
        logger.warning("No valid Song objects to download.")
        return
    logger.info("🚀 Starting download process...")
    threads = int(os.environ.get('SPOTDL_THREADS', '5'))
    settings = {
        'output': f'{download_dir}/{{artist}} - {{title}}.{{output-ext}}',
        'format': 'mp3',
        'bitrate': '320k',
        'threads': threads,  # Download N songs at a time
        'audio_providers': ['youtube', 'youtube-music'],
        'lyrics_providers': ['genius', 'musixmatch'],
        'overwrite': 'skip',
        'scan_for_songs': True,  # Enable skipping of already-downloaded files
        'print_errors': True,
    }
    import subprocess
    from concurrent.futures import ThreadPoolExecutor, as_completed
    logger.info(f"📥 Downloading {len(song_objs)} tracks using spotDL CLI subprocesses (threads={threads})...")
    def download_one(track):
        url = getattr(track, 'url', None)
        artist = getattr(track, 'artist', None) or (track.artists[0] if hasattr(track, 'artists') and track.artists else 'Unknown')
        title = getattr(track, 'name', None) or getattr(track, 'title', None) or 'Unknown'
        if not url:
            logger.error(f"No URL for track: {track}")
            return (track, None)
        output_path = f"{download_dir}/{artist} - {title}.mp3"
        # Check if file already exists to avoid redownload
        if os.path.exists(output_path):
            logger.info(f"[spotDL] ⏭️ Skipped (exists): {artist} - {title}")
            return (track, output_path)
        cmd = [
            "spotdl",
            "download",
            url,
            "--output", f"{download_dir}/{{title}}.{{output-ext}}",
            "--format", "mp3",
            "--bitrate", "320k"
        ]
        logger.info(f"[spotDL] [START] {artist} - {title}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                # Find the actual downloaded file in download_dir
                # spotDL sanitizes filenames, so we need to be more flexible in matching
                import re
                def sanitize_for_match(s):
                    # Remove common problematic characters that spotDL removes/changes
                    return re.sub(r'["\':?*<>|/\\]', '', s).strip()
                
                sanitized_title = sanitize_for_match(title.lower())
                potential_files = []
                
                # First try: exact match with sanitized title
                for f in os.listdir(download_dir):
                    if f.endswith('.mp3') and sanitized_title in sanitize_for_match(f.lower()):
                        potential_files.append(f)
                
                # Second try: partial match with artist name
                if not potential_files:
                    sanitized_artist = sanitize_for_match(artist.lower())
                    for f in os.listdir(download_dir):
                        if f.endswith('.mp3') and sanitized_artist in sanitize_for_match(f.lower()):
                            potential_files.append(f)
                
                if potential_files:
                    # Pick the most recently created file if multiple matches
                    actual_file_name = max(potential_files, key=lambda f: os.path.getctime(os.path.join(download_dir, f)))
                    actual_file = os.path.join(download_dir, actual_file_name)
                    # Rename to standardized format
                    if actual_file != output_path:
                        os.rename(actual_file, output_path)
                    logger.info(f"[spotDL] ✅ Downloaded: {artist} - {title}")
                    return (track, output_path)
                else:
                    logger.error(f"[spotDL] ❌ Downloaded but file not found: {artist} - {title}")
                    logger.debug(f"Available files: {[f for f in os.listdir(download_dir) if f.endswith('.mp3')]}")
                    return (track, None)
            else:
                logger.error(f"[spotDL] ❌ Failed: {artist} - {title} | {result.stderr}")
                return (track, None)
        except subprocess.TimeoutExpired:
            logger.error(f"[spotDL] ❌ Timeout: {artist} - {title}")
            return (track, None)
        except Exception as e:
            logger.error(f"[spotDL] Exception: {artist} - {title} | {e}")
            return (track, None)

    results = []
    logger.info(f"[spotDL] Launching ThreadPoolExecutor with {threads} threads...")
    with ThreadPoolExecutor(max_workers=threads) as executor:
        future_to_track = {executor.submit(download_one, t): t for t in song_objs}
        for future in as_completed(future_to_track):
            track = future_to_track[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"[spotDL] Exception in thread: {e}")
                results.append((track, None))
    success_count = sum(1 for _, path in results if path)
    fail_count = sum(1 for _, path in results if not path)
    logger.info(f"[spotDL] Download summary: {success_count} succeeded, {fail_count} failed.")
    # Move each downloaded file to the correct Plex artist folder and trigger Plex scan
    logger.info("📁 Organizing downloaded files into Plex library...")
    plex = setup_plex_client()
    music_library = get_music_library(plex)
    plex_music_path = "/app/Songs"
    # Get all artist folders in Plex music path
    import re
    def normalize(s):
        return re.sub(r'[^a-z0-9 ]', '', s.lower()) if s else ''
    artist_folders = [d for d in os.listdir(plex_music_path) if os.path.isdir(os.path.join(plex_music_path, d))]
    import time
    scan_triggered = False
    successful_moves = 0
    failed_moves = 0
    for result in results:
        # Unpack tuple safely
        if isinstance(result, tuple) and len(result) == 2:
            track, file_path = result
        else:
            logger.error(f"❌ Invalid result entry (expected (track, file_path)): {result}")
            failed_moves += 1
            continue
        if not file_path:
            failed_moves += 1
            continue
        
        # Extract artist and title from track object
        artist = getattr(track, 'artist', None) or (track.artists[0] if hasattr(track, 'artists') and track.artists else 'Unknown')
        title = getattr(track, 'name', None) or getattr(track, 'title', None) or 'Unknown'
        
        if not artist or not title:
            logger.warning(f"⚠️  Skipping move for {file_path}: missing artist or title.")
            failed_moves += 1
            continue
        # Fuzzy match artist folder
        best_artist, score = process.extractOne(normalize(artist), [normalize(a) for a in artist_folders]) if artist_folders else (None, 0)
        # Map normalized best_artist back to original folder name
        best_artist_folder = None
        if best_artist:
            for folder in artist_folders:
                if normalize(folder) == best_artist:
                    best_artist_folder = folder
                    break
        if score < 90 or not best_artist_folder:
            # If no good match, create a new folder for the artist
            dest_folder = os.path.join(plex_music_path, artist)
            if not os.path.exists(dest_folder):
                try:
                    os.makedirs(dest_folder)
                    logger.info(f"📂 Created new artist folder: {artist}")
                except Exception as e:
                    logger.error(f"❌ Failed to create artist folder {dest_folder}: {e}")
                    failed_moves += 1
                    continue
        else:
            dest_folder = os.path.join(plex_music_path, best_artist_folder)
        dest_path = os.path.join(dest_folder, f"{artist} - {title}.mp3")
        # Move and overwrite if exists
        try:
            if os.path.exists(file_path):
                shutil.move(file_path, dest_path)
                logger.info(f"✅ Moved: {artist} - {title}")
                successful_moves += 1
                scan_triggered = True
            else:
                logger.error(f"❌ Source file not found: {file_path}")
                failed_moves += 1
        except Exception as e:
            logger.error(f"❌ Failed to move {file_path} to {dest_path}: {e}")
            failed_moves += 1
            continue
    
    # After all moves, trigger and track Plex scan
    logger.info(f"📊 Download Summary: {successful_moves} successful, {failed_moves} failed")
    if scan_triggered:
        try:
            section = music_library
            section.update()
            logger.info("🔄 Triggered Plex library scan. Waiting for scan to complete...")
            # Poll for scan completion
            while getattr(section, 'refreshing', False):
                logger.info("📡 Plex scan in progress...")
                time.sleep(5)
            logger.info("✅ Plex scan complete. Library updated successfully!")
        except Exception as e:
            logger.error(f"❌ Failed to trigger or track Plex scan: {e}")
    else:
        logger.info("ℹ️  No files were moved, skipping Plex scan.")


def download_missing_artist_tracks_spotdl(artist_url, download_dir):
    """
    Downloads missing tracks for a specific artist using spotDL, then organizes into Plex library.
    Expects artist_url as a Spotify artist URL.
    """
    # Initialize spotDL Spotify client
    from credential import get_spotify_credentials
    from spotdl.utils.spotify import SpotifyClient
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    
    client_id, client_secret = get_spotify_credentials()
    
    # Try to initialize SpotifyClient, but don't fail if already initialized
    try:
        SpotifyClient.init(client_id, client_secret, user_auth=False)
    except Exception as e:
        if "already been initialized" in str(e):
            logger.info("🔄 SpotifyClient already initialized, reusing existing client")
        else:
            logger.warning(f"SpotifyClient initialization warning: {e}")
    
    # Initialize Spotify client for fetching artist data
    sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))
    
    logger.info(f"🎤 Starting artist sync for: {artist_url}")
    os.makedirs(download_dir, exist_ok=True)
    
    # Extract artist ID from URL
    if '/artist/' not in artist_url:
        logger.error("Invalid Spotify artist URL")
        return
    
    artist_id = artist_url.split('/artist/')[-1].split('?')[0]
    
    try:
        # Get artist info
        artist_info = sp.artist(artist_id)
        artist_name = artist_info['name']
        logger.info(f"📀 Fetching all tracks for artist: {artist_name}")
        
        # Get all albums for the artist
        albums = []
        offset = 0
        limit = 50
        
        while True:
            response = sp.artist_albums(artist_id, album_type='album,single', limit=limit, offset=offset)
            if not response or not response.get('items'):
                break
            albums.extend(response['items'])
            if not response.get('next'):
                break
            offset += limit
        
        logger.info(f"📚 Found {len(albums)} albums/singles")
        
        # Get all tracks from all albums (filter by album artist)
        all_tracks = []
        for album in albums:
            try:
                album_details = sp.album(album['id'])
                # Only include tracks where the artist is the album artist
                album_artists = [artist['name'] for artist in album_details.get('artists', [])]
                if artist_name in album_artists:
                    tracks = sp.album_tracks(album['id'])
                    for track in tracks['items']:
                        track_info = {
                            'title': track['name'],
                            'artist': artist_name,  # Use album artist
                            'album': album_details['name'],
                            'url': f"https://open.spotify.com/track/{track['id']}",
                            'album_artist': artist_name,
                            'release_date': album_details.get('release_date', ''),
                            'track_number': track['track_number']
                        }
                        all_tracks.append(track_info)
            except Exception as e:
                logger.error(f"Error fetching album {album['name']}: {e}")
                continue
        
        logger.info(f"🎵 Found {len(all_tracks)} total tracks by {artist_name}")
        
        if not all_tracks:
            logger.warning("No tracks found for this artist")
            return
        
        # Compare with Plex library to find missing tracks
        from plex_utils import setup_plex_client, get_music_library
        import shutil
        plex = setup_plex_client()
        music_library = get_music_library(plex)
        
        logger.info("🔍 Scanning Plex library for existing tracks...")
        
        # First, let's verify Plex connection and do a basic search
        try:
            test_tracks = music_library.searchTracks()
            logger.info(f"🔍 Plex connection test: Found {len(test_tracks)} total tracks in library")
            
            # Look for any tracks by this artist
            artist_tracks = []
            for track in test_tracks:
                track_artist = getattr(track, 'grandparentTitle', '')
                if track_artist.lower() == artist_name.lower():
                    artist_tracks.append(track)
                    logger.info(f"🔍 Found track by {artist_name}: '{track.title}' (Album: {getattr(track, 'parentTitle', 'Unknown')})")
            
            logger.info(f"🔍 Direct search found {len(artist_tracks)} tracks by {artist_name}")
            
        except Exception as e:
            logger.error(f"Plex connection test failed: {e}")
        
        # Get all tracks in Plex for this artist using the same robust logic as playlist sync
        try:
            from plex_utils import find_plex_match
            plex_track_titles = set()
            
            logger.info(f"🔍 Checking {len(all_tracks)} tracks against Plex library...")
            
            # Use the same multi-stage search logic as playlist sync
            for i, track in enumerate(all_tracks, 1):
                spotify_track = {
                    'title': track['title'],
                    'artist': track['artist'],
                    'album': track['album']
                }
                
                logger.info(f"  [{i}/{len(all_tracks)}] Searching: {spotify_track['artist']} - {spotify_track['title']} (Album: {spotify_track['album']})")
                
                # Use find_plex_match to check if track exists in Plex
                plex_match = find_plex_match(music_library, spotify_track)
                if plex_match:
                    # Track exists in Plex, add to existing tracks set
                    plex_track_titles.add(track['title'].lower().strip())
                    logger.info(f"  [{i}/{len(all_tracks)}] ✅ Found in Plex: {plex_match.title} by {getattr(plex_match, 'grandparentTitle', 'Unknown')}")
                else:
                    logger.info(f"  [{i}/{len(all_tracks)}] ❌ Not found in Plex")
            
            logger.info(f"📊 Found {len(plex_track_titles)} existing tracks in Plex")
            
        except Exception as e:
            logger.error(f"Error searching Plex: {e}")
            plex_track_titles = set()
        
        # Find missing tracks
        missing_tracks = []
        for track in all_tracks:
            track_title = track['title'].lower().strip()
            if track_title not in plex_track_titles:
                missing_tracks.append(track)
        
        logger.info(f"📥 Found {len(missing_tracks)} missing tracks to download")
        
        if not missing_tracks:
            logger.info("✅ All tracks already exist in Plex library")
            return
        
        # Use the same download logic as the playlist function
        from spotdl.types.song import Song
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import subprocess
        
        # Create Song objects for missing tracks
        song_objs = []
        logger.info("🔍 Creating download objects for missing tracks...")
        for i, track in enumerate(missing_tracks, 1):
            url = track.get('url')
            if not url:
                continue
            try:
                song = Song.from_url(url)
                song_objs.append(song)
                logger.info(f"  [{i}/{len(missing_tracks)}] ✅ {track['artist']} - {track['title']}")
            except Exception as e:
                logger.error(f"  [{i}/{len(missing_tracks)}] ❌ Failed to create Song object for {url}: {e}")
        
        if not song_objs:
            logger.warning("No valid Song objects to download.")
            return
        
        logger.info("🚀 Starting download process...")
        threads = int(os.environ.get('SPOTDL_THREADS', '5'))
        
        def download_one_artist_track(track):
            url = getattr(track, 'url', None)
            artist = getattr(track, 'artist', None) or (track.artists[0] if hasattr(track, 'artists') and track.artists else 'Unknown')
            title = getattr(track, 'name', None) or getattr(track, 'title', None) or 'Unknown'
            if not url:
                logger.error(f"No URL for track: {track}")
                return (track, None)
            output_path = f"{download_dir}/{artist} - {title}.mp3"
            # Check if file already exists to avoid redownload
            if os.path.exists(output_path):
                logger.info(f"[spotDL] ⏭️ Skipped (exists): {artist} - {title}")
                return (track, output_path)
            cmd = [
                "spotdl",
                "download",
                url,
                "--output", f"{download_dir}/{{title}}.{{output-ext}}",
                "--format", "mp3",
                "--bitrate", "320k"
            ]
            logger.info(f"[spotDL] [START] {artist} - {title}")
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if result.returncode == 0:
                    # Find the actual downloaded file in download_dir
                    # spotDL sanitizes filenames, so we need to be more flexible in matching
                    import re
                    def sanitize_for_match(s):
                        # Remove common problematic characters that spotDL removes/changes
                        return re.sub(r'["\':?*<>|/\\]', '', s).strip()
                    
                    sanitized_title = sanitize_for_match(title.lower())
                    potential_files = []
                    
                    # First try: exact match with sanitized title
                    for f in os.listdir(download_dir):
                        if f.endswith('.mp3') and sanitized_title in sanitize_for_match(f.lower()):
                            potential_files.append(f)
                    
                    # Second try: partial match with artist name
                    if not potential_files:
                        sanitized_artist = sanitize_for_match(artist.lower())
                        for f in os.listdir(download_dir):
                            if f.endswith('.mp3') and sanitized_artist in sanitize_for_match(f.lower()):
                                potential_files.append(f)
                    
                    if potential_files:
                        # Pick the most recently created file if multiple matches
                        actual_file_name = max(potential_files, key=lambda f: os.path.getctime(os.path.join(download_dir, f)))
                        actual_file = os.path.join(download_dir, actual_file_name)
                        # Rename to standardized format
                        if actual_file != output_path:
                            os.rename(actual_file, output_path)
                        logger.info(f"[spotDL] ✅ Downloaded: {artist} - {title}")
                        return (track, output_path)
                    else:
                        logger.error(f"[spotDL] ❌ Downloaded but file not found: {artist} - {title}")
                        logger.debug(f"Available files: {[f for f in os.listdir(download_dir) if f.endswith('.mp3')]}")
                        return (track, None)
                else:
                    logger.error(f"[spotDL] ❌ Failed: {artist} - {title} | {result.stderr}")
                    return (track, None)
            except subprocess.TimeoutExpired:
                logger.error(f"[spotDL] ❌ Timeout: {artist} - {title}")
                return (track, None)
            except Exception as e:
                logger.error(f"[spotDL] Exception: {artist} - {title} | {e}")
                return (track, None)

        results = []
        logger.info(f"[spotDL] Launching ThreadPoolExecutor with {threads} threads...")
        with ThreadPoolExecutor(max_workers=threads) as executor:
            future_to_track = {executor.submit(download_one_artist_track, t): t for t in song_objs}
            for future in as_completed(future_to_track):
                track = future_to_track[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"[spotDL] Exception in thread: {e}")
                    results.append((track, None))
        
        success_count = sum(1 for _, path in results if path)
        fail_count = sum(1 for _, path in results if not path)
        logger.info(f"[spotDL] Download summary: {success_count} succeeded, {fail_count} failed.")
        
        # Organize downloaded files into artist folder in Plex library
        logger.info(f"📁 Organizing downloaded files into Plex library for artist: {artist_name}")
        plex_music_path = "/app/Songs"
        artist_folder = os.path.join(plex_music_path, artist_name)
        
        # Create artist folder if it doesn't exist
        if not os.path.exists(artist_folder):
            try:
                os.makedirs(artist_folder)
                logger.info(f"📂 Created new artist folder: {artist_name}")
            except Exception as e:
                logger.error(f"❌ Failed to create artist folder {artist_folder}: {e}")
                return
        
        successful_moves = 0
        failed_moves = 0
        scan_triggered = False
        
        for result in results:
            # Unpack tuple safely
            if isinstance(result, tuple) and len(result) == 2:
                track, file_path = result
            else:
                logger.error(f"❌ Invalid result entry (expected (track, file_path)): {result}")
                failed_moves += 1
                continue
            if not file_path:
                failed_moves += 1
                continue
            
            # Extract artist and title from track object
            track_artist = getattr(track, 'artist', None) or (track.artists[0] if hasattr(track, 'artists') and track.artists else 'Unknown')
            track_title = getattr(track, 'name', None) or getattr(track, 'title', None) or 'Unknown'
            
            dest_path = os.path.join(artist_folder, f"{track_artist} - {track_title}.mp3")
            
            # Move and overwrite if exists
            try:
                if os.path.exists(file_path):
                    shutil.move(file_path, dest_path)
                    logger.info(f"✅ Moved: {track_artist} - {track_title}")
                    successful_moves += 1
                    scan_triggered = True
                else:
                    logger.error(f"❌ Source file not found: {file_path}")
                    failed_moves += 1
            except Exception as e:
                logger.error(f"❌ Failed to move {file_path} to {dest_path}: {e}")
                failed_moves += 1
                continue
        
        # After all moves, trigger and track Plex scan
        logger.info(f"📊 Artist Download Summary: {successful_moves} successful, {failed_moves} failed")
        if scan_triggered:
            try:
                import time
                section = music_library
                section.update()
                logger.info("🔄 Triggered Plex library scan. Waiting for scan to complete...")
                # Poll for scan completion
                while getattr(section, 'refreshing', False):
                    logger.info("📡 Plex scan in progress...")
                    time.sleep(5)
                logger.info(f"✅ Plex scan complete. Artist {artist_name} library updated successfully!")
            except Exception as e:
                logger.error(f"❌ Failed to trigger or track Plex scan: {e}")
        else:
            logger.info("ℹ️  No files were moved, skipping Plex scan.")
            
    except Exception as e:
        logger.error(f"❌ Error during artist sync: {e}", exc_info=True)
