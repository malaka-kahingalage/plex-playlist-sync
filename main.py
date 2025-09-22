import os
from spotify_utils import setup_spotify_client, get_spotify_playlist_id_from_url, get_spotify_playlist_tracks, parse_spotify_tracks
from plex_utils import setup_plex_client, get_music_library, create_or_update_plex_playlist, find_plex_match
from download_utils import download_missing_tracks_spotdl

import os
import logging

# Helper to log to both logger and print (for Docker and web UI)
def log_status(msg):
    logger = logging.getLogger(__name__)
    logger.info(msg)
    print(msg)

def sync_playlist(playlist_url):
    import uuid
    run_id = uuid.uuid4()
    log_status(f"[SYNC-START] sync_playlist called. Run ID: {run_id}")
    try:
        playlist_id = get_spotify_playlist_id_from_url(playlist_url)
        if not playlist_id:
            log_status("Invalid Spotify Playlist URL provided.")
            return

        log_status("Setting up Spotify client...")
        sp_authenticated, sp_anonymous = setup_spotify_client()

        log_status("Setting up Plex client...")
        plex = setup_plex_client()
        music_library = get_music_library(plex)

        log_status(f"Fetching Spotify playlist (ID: {playlist_id})...")
        playlist_name, raw_spotify_tracks = get_spotify_playlist_tracks(sp_authenticated, sp_anonymous, playlist_id)

        log_status(f"Found playlist: '{playlist_name}'")
        spotify_tracks = parse_spotify_tracks(raw_spotify_tracks)

        log_status(f"🔍 Matching {len(spotify_tracks)} tracks with Plex library...")

        # Original Plex matching logic
        found_plex_tracks = []
        missing_spotify_tracks = []

        for i, spotify_track in enumerate(spotify_tracks, 1):
            log_status(f"[{i}/{len(spotify_tracks)}] Searching: {spotify_track['artist']} - {spotify_track['title']}")
            plex_match = find_plex_match(music_library, spotify_track)
            if plex_match:
                found_plex_tracks.append(plex_match)
                log_status(f"  ✅ Found in Plex")
            else:
                missing_spotify_tracks.append(spotify_track)
                log_status(f"  ❌ Not found in Plex")

        log_status("---")
        log_status("Matching complete.")
        log_status(f"Found {len(found_plex_tracks)} matching tracks in Plex.")
        log_status(f"{len(missing_spotify_tracks)} tracks not found in Plex.")
        log_status("---\n")

        create_or_update_plex_playlist(plex, playlist_name, found_plex_tracks)

        # Original download with spotDL
        if missing_spotify_tracks:
            log_status(f"📥 Need to download: {len(missing_spotify_tracks)}")
            download_dir = "/app/downloads"
            download_missing_tracks_spotdl(missing_spotify_tracks, download_dir)
        else:
            log_status("✅ All tracks already available in Plex library!")

        # Wait for Plex scan to complete before updating playlist again
        import time
        music_library = get_music_library(plex)
        log_status("Waiting for Plex scan to complete before updating playlist...")
        while True:
            try:
                # Re-fetch the music library section to get updated 'refreshing' state
                music_library = get_music_library(plex)
                if not getattr(music_library, 'refreshing', False):
                    break
                log_status("Plex scan in progress...")
            except Exception as e:
                log_status(f"Error checking Plex scan state: {e}")
                break
            time.sleep(5)
        log_status("Plex scan complete. Updating playlist with new tracks...")

        # Re-scan for newly downloaded tracks and update playlist
        log_status("🔄 Re-scanning for newly downloaded tracks...")
        music_library = get_music_library(plex)

        final_found_tracks = []
        still_missing = []

        for spotify_track in spotify_tracks:
            plex_match = find_plex_match(music_library, spotify_track)
            if plex_match:
                final_found_tracks.append(plex_match)
            else:
                still_missing.append(spotify_track)

        log_status(f"📊 Final playlist will contain {len(final_found_tracks)} tracks")
        if still_missing:
            log_status(f"⚠️  {len(still_missing)} tracks still missing after download attempt")

        create_or_update_plex_playlist(plex, playlist_name, final_found_tracks)
        
    except ValueError as e:
        log_status(f"Error: {e}")
        raise  # Re-raise so web interface can catch it
    except Exception as e:
        log_status(f"Unexpected error during sync: {e}")
        raise  # Re-raise so web interface can catch it

def main():
    playlist_url = input("Enter the Spotify Playlist URL: ")
    sync_playlist(playlist_url)
