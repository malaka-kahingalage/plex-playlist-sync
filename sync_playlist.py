import os
import sys
import glob
import musicbrainzngs
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TXXX
from urllib.parse import urlparse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized
from thefuzz import fuzz
from credential import get_spotify_credentials, get_plex_credentials, get_plex_music_library


def get_spotify_playlist_id_from_url(url):
    """Extracts the playlist ID from a Spotify URL."""
    parsed_url = urlparse(url)
    if parsed_url.netloc == "open.spotify.com":
        path_parts = parsed_url.path.split('/')
        if 'playlist' in path_parts:
            return path_parts[path_parts.index('playlist') + 1]
    return None


def setup_spotify_client():
    """
    Sets up and returns a Spotipy client using client credentials (no user authentication).
    """
    try:
        client_id, client_secret = get_spotify_credentials()
        if not client_id or not client_secret:
            print("Spotify client_id or client_secret not found in .env file.")
            sys.exit(1)
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        sp = spotipy.Spotify(auth_manager=auth_manager)
        print("Successfully connected to Spotify API (client credentials mode)")
        return sp
    except Exception as e:
        print(f"Error setting up Spotify client: {e}")
        sys.exit(1)


def setup_plex_client():
    """
    Sets up and returns an authenticated Plex server client.
    """
    baseurl, token = get_plex_credentials()
    if not baseurl or not token:
        print("Plex URL or Token not found in .env file. Please configure them.")
        sys.exit(1)
    try:
        plex = PlexServer(baseurl, token)
        print(f"Successfully connected to Plex server: {plex.friendlyName}")
        return plex
    except Unauthorized:
        print("Plex authentication failed. The provided PLEX_TOKEN is invalid or has expired.")
        print("Please obtain a new token and update your .env file.")
        sys.exit(1)
    except Exception as e:
        print(f"Error connecting to Plex server at {baseurl}: {e}")
        sys.exit(1)


def get_spotify_playlist_tracks(sp, playlist_id):
    """Fetches all tracks from a Spotify playlist, handling pagination."""
    all_tracks = []
    try:
        playlist_info = sp.playlist(playlist_id, fields='name,tracks.total')
        playlist_name = playlist_info['name']
        total_tracks = playlist_info['tracks']['total']
        print(f"Fetching {total_tracks} tracks from Spotify playlist '{playlist_name}'...")

        results = sp.playlist_items(playlist_id)
        if results and 'items' in results:
            all_tracks.extend(results['items'])
            while results['next']:
                results = sp.next(results)
                all_tracks.extend(results['items'])
        return playlist_name, all_tracks
    except spotipy.exceptions.SpotifyException as e:
        print(f"Error fetching Spotify playlist: {e}")
        print("Please ensure the URL is correct and the playlist is public or accessible.")
        sys.exit(1)


def parse_spotify_tracks(raw_tracks):
    """Parses raw Spotify track data into a clean list of dictionaries."""
    parsed_tracks = []
    for item in raw_tracks:
        track_data = item.get('track')
        if not track_data or not track_data.get('id'):
            continue
        track_name = track_data.get('name')
        album_name = track_data.get('album', {}).get('name')
        artists = track_data.get('artists', [])
        primary_artist = artists[0]['name'] if artists else None
        spotify_url = track_data.get('external_urls', {}).get('spotify')
        if track_name and primary_artist and album_name:
            parsed_tracks.append({
                'title': track_name,
                'artist': primary_artist,
                'album': album_name,
                'url': spotify_url
            })
    return parsed_tracks


def find_plex_match(music_library, spotify_track, threshold=85):
    """
    Finds the best match for a Spotify track in the Plex library using a two-stage process.
    """
    try:
        candidates = music_library.searchTracks(title=spotify_track['title'])
        if not candidates:
            return None
        best_match = None
        highest_score = 0
        for plex_track in candidates:
            if not (plex_track.parentTitle and plex_track.grandparentTitle):
                continue
            artist_score = fuzz.token_sort_ratio(spotify_track['artist'], plex_track.grandparentTitle)
            album_score = fuzz.ratio(spotify_track['album'], plex_track.parentTitle)
            title_score = fuzz.ratio(spotify_track['title'], plex_track.title)
            weighted_score = (title_score * 0.5) + (artist_score * 0.3) + (album_score * 0.2)
            if weighted_score > highest_score:
                highest_score = weighted_score
                best_match = plex_track
        return best_match if highest_score >= threshold else None
    except Exception:
        return None

# Use a simple logger for matching logs
from plex_utils import find_plex_match_robust
class SimpleLogger:
    def info(self, msg):
        print(msg)
logger = SimpleLogger()

def find_plex_match(music_library, spotify_track, threshold=85):
    return find_plex_match_robust(music_library, spotify_track, threshold=threshold, logger=logger)


def create_or_update_plex_playlist(plex, playlist_title, found_plex_tracks):
    """Creates a new Plex playlist or adds new tracks to an existing one."""
    if not found_plex_tracks:
        print("No matching tracks found in Plex. No playlist will be created or updated.")
        return
    try:
        playlist = plex.playlist(playlist_title)
        print(f"Playlist '{playlist_title}' already exists. Updating with new tracks...")
        existing_track_keys = [track.ratingKey for track in playlist.items()]
        new_tracks_to_add = [track for track in found_plex_tracks if track.ratingKey not in existing_track_keys]
        if new_tracks_to_add:
            playlist.addItems(new_tracks_to_add)
            print(f"Added {len(new_tracks_to_add)} new tracks to the playlist.")
        else:
            print("No new tracks to add. Playlist is already up to date.")
    except NotFound:
        print(f"Playlist '{playlist_title}' not found. Creating a new playlist...")
        plex.createPlaylist(title=playlist_title, items=found_plex_tracks)
        print(f"Successfully created playlist '{playlist_title}' with {len(found_plex_tracks)} tracks.")



def download_missing_tracks_spotdl(missing_tracks_urls, download_dir):
    # Setup MusicBrainz client
    musicbrainzngs.set_useragent("plexplaylist-sync", "1.0", "https://github.com/yourrepo")
    """Downloads missing tracks using spotDL to the specified directory."""
    if not missing_tracks_urls:
        print("No missing tracks to download.")
        return
    os.makedirs(download_dir, exist_ok=True)
    # Required Metadata Tags for Plex:
    # Artist, Album Artist, Album, Track Title, Track Number, Disc Number, Year, Genre, MusicBrainz IDs
    # spotDL embeds most tags by default if available from Spotify/YouTube
    for url in missing_tracks_urls:
        print(f"Downloading: {url}")
        output_template = f"{download_dir}/{{artist}}/{{album}}/{{track_number}} - {{title}}.{{output-ext}}"
        fallback_template = f"{download_dir}/{{artist}} - {{title}}.{{output-ext}}"
        spotdl_cmd = (
            f"spotdl download --output '{output_template}' --format mp3 --bitrate 320k {url}"
        )
        exit_code = os.system(spotdl_cmd)
        downloaded_path = None
        if exit_code != 0:
            print(f"[WARN] Download with album/track_number failed or metadata missing for: {url}\nRetrying with artist-title fallback...")
            spotdl_cmd_fallback = (
                f"spotdl download --output '{fallback_template}' --format mp3 --bitrate 320k {url}"
            )
            exit_code2 = os.system(spotdl_cmd_fallback)
            if exit_code2 != 0:
                print(f"Failed to download: {url}")
                continue
            else:
                print(f"Downloaded (fallback): {url}")
                downloaded_path = fallback_template.replace("{{artist}}", "*").replace("{{title}}", "*").replace("{{output-ext}}", "mp3")
        else:
            print(f"Downloaded: {url}")
            downloaded_path = output_template.replace("{{artist}}", "*").replace("{{album}}", "*").replace("{{track_number}}", "*").replace("{{title}}", "*").replace("{{output-ext}}", "mp3")

        # MusicBrainz tagging: try to find and embed MBIDs
        if downloaded_path:
            for file_path in glob.glob(downloaded_path):
                try:
                    audio = EasyID3(file_path)
                    artist = audio.get('artist', [None])[0]
                    album = audio.get('album', [None])[0]
                    title = audio.get('title', [None])[0]
                    mbid = None
                    if artist and title:
                        try:
                            result = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=1)
                            recordings = result.get('recording-list', [])
                            if recordings:
                                mbid = recordings[0]['id']
                        except Exception as e:
                            print(f"MusicBrainz search error: {e}")
                    if mbid:
                        id3 = ID3(file_path)
                        id3.add(TXXX(encoding=3, desc='MusicBrainz Track Id', text=mbid))
                        id3.save()
                        print(f"Embedded MusicBrainz Track ID: {mbid} in {file_path}")
                    else:
                        print(f"No MusicBrainz Track ID found for {file_path}")
                except Exception as e:
                    print(f"MusicBrainz tagging failed for {file_path}: {e}")


def main():
    playlist_url = input("Enter the Spotify Playlist URL: ")
    playlist_id = get_spotify_playlist_id_from_url(playlist_url)
    if not playlist_id:
        print("Invalid Spotify Playlist URL provided.")
        sys.exit(1)
    sp = setup_spotify_client()
    plex = setup_plex_client()
    music_library_name = get_plex_music_library()
    try:
        music_library = plex.library.section(music_library_name)
    except NotFound:
        print(f"Plex music library '{music_library_name}' not found.")
        print("Please ensure PLEX_MUSIC_LIBRARY in your .env file matches a library on your server.")
        sys.exit(1)
    playlist_name, raw_spotify_tracks = get_spotify_playlist_tracks(sp, playlist_id)
    spotify_tracks = parse_spotify_tracks(raw_spotify_tracks)
    found_plex_tracks = []
    missing_spotify_tracks = []
    print(f"Processing and matching {len(spotify_tracks)} tracks...")
    for i, track in enumerate(spotify_tracks):
        match = find_plex_match(music_library, track)
        if match:
            found_plex_tracks.append(match)
        else:
            missing_spotify_tracks.append(track['url'])
        # Simple progress bar
        progress = i + 1
        bar_length = 40
        filled_length = int(bar_length * progress // len(spotify_tracks))
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        print(f'\rProcessing: |{bar}| {progress}/{len(spotify_tracks)}', end='\r')
    print("\n---")
    print("Matching complete.")
    print(f"Found {len(found_plex_tracks)} matching tracks in Plex.")
    print(f"{len(missing_spotify_tracks)} tracks not found in Plex.")
    print("---\n")

    # Wait for Plex scan to complete (if needed)
    print("Waiting for Plex scan to complete before updating playlist...")
    import time
    sleep_time = int(os.environ.get('PLEX_SCAN_SLEEP_SECONDS', '300'))
    time.sleep(sleep_time)
    print("Plex scan complete. Updating playlist with new tracks...")

    # Download Spotify playlist cover image
    playlist_info = sp.playlist(playlist_id, fields='images')
    cover_url = None
    cover_path = None
    if playlist_info and 'images' in playlist_info and playlist_info['images']:
        cover_url = playlist_info['images'][0]['url']
        print(f"[ARTWORK] Spotify playlist cover URL: {cover_url}")
        try:
            import requests
            img_data = requests.get(cover_url).content
            cover_path = f"/tmp/{playlist_id}_cover.jpg"
            with open(cover_path, 'wb') as handler:
                handler.write(img_data)
            print(f"[ARTWORK] Downloaded cover to: {cover_path}")
        except Exception as e:
            print(f"[ARTWORK] Failed to download cover image: {e}")
    else:
        print("[ARTWORK] No Spotify playlist cover found.")
        cover_path = None


    # Create/update playlist
    create_or_update_plex_playlist(plex, playlist_name, found_plex_tracks)

    # Always attempt to set Plex playlist poster/background, even if no new tracks were added
    print(f"[ARTWORK] cover_path: {cover_path}")
    print(f"[ARTWORK] cover_url: {cover_url}")
    try:
        print(f"[ARTWORK] Entering artwork logic for playlist: '{playlist_name}'")
        if cover_path or cover_url:
            print(f"[ARTWORK] Attempting to set Plex playlist poster/background...")
            try:
                print(f"[ARTWORK] Attempting to fetch playlist from Plex: '{playlist_name}'")
                try:
                    playlist = plex.playlist(playlist_name)
                    print(f"[ARTWORK] Successfully fetched playlist from Plex: '{playlist_name}'")
                except Exception as e:
                    print(f"[ARTWORK] Failed to fetch playlist from Plex: '{playlist_name}'. Error: {e}")
                    playlist = None
                if not playlist:
                    print(f"[ARTWORK] Playlist '{playlist_name}' not found in Plex. Skipping artwork update.")
                else:
                    if cover_path:
                        try:
                            print(f"[ARTWORK] Trying file upload: {cover_path}")
                            playlist.uploadPoster(filepath=cover_path)
                            print(f"[ARTWORK] Plex playlist poster updated from Spotify cover file.")
                            playlist.uploadArt(filepath=cover_path)
                            print(f"[ARTWORK] Plex playlist background updated from Spotify cover file.")
                        except Exception as e:
                            print(f"[ARTWORK] File upload failed: {e}. Trying URL method...")
                            # Try URL method as fallback
                            if cover_url:
                                try:
                                    print(f"[ARTWORK] Trying URL upload: {cover_url}")
                                    playlist.editPoster(url=cover_url)
                                    print(f"[ARTWORK] Plex playlist poster updated from Spotify cover URL.")
                                    playlist.editArt(url=cover_url)
                                    print(f"[ARTWORK] Plex playlist background updated from Spotify cover URL.")
                                except Exception as e2:
                                    print(f"[ARTWORK] Failed to set Plex playlist poster/background from URL: {e2}")
                    elif cover_url:
                        try:
                            print(f"[ARTWORK] Trying URL upload: {cover_url}")
                            playlist.editPoster(url=cover_url)
                            print(f"[ARTWORK] Plex playlist poster updated from Spotify cover URL.")
                            playlist.editArt(url=cover_url)
                            print(f"[ARTWORK] Plex playlist background updated from Spotify cover URL.")
                        except Exception as e:
                            print(f"[ARTWORK] Failed to set Plex playlist poster/background from URL: {e}")
            except Exception as e:
                print(f"[ARTWORK] Failed to set Plex playlist poster/background: {e}")
        else:
            print("[ARTWORK] No Spotify playlist cover found to set as Plex playlist poster/background.")
    except Exception as e:
        print(f"[ARTWORK] Top-level artwork logic error: {e}")

    # Download missing tracks using spotDL instead of writing a report file
    # Use /app/downloads as the download directory (local to container)
    # To persist downloads, map a host directory to /app/downloads:
    #   docker run -v $(pwd)/downloads:/app/downloads ...
    download_dir = "/app/downloads"
    download_missing_tracks_spotdl(missing_spotify_tracks, download_dir)

