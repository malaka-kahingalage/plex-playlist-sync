import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy_anon import SpotifyAnon
from urllib.parse import urlparse
from credential import get_spotify_credentials


def get_spotify_playlist_id_from_url(url):
    parsed_url = urlparse(url)
    if parsed_url.netloc == "open.spotify.com":
        path_parts = parsed_url.path.split('/')
        if 'playlist' in path_parts:
            playlist_id = path_parts[path_parts.index('playlist') + 1]
            
            # Check if this is a Spotify algorithmic/curated playlist
            if playlist_id.startswith('37i9dQZF1E'):
                print(f"⚠️  Warning: This appears to be a Spotify curated/algorithmic playlist (ID: {playlist_id})")
                print("These playlists may have limited API access and could cause 404 errors.")
                print("For best results, try using:")
                print("  • User-created public playlists")
                print("  • Your own playlists")
                print("  • Collaborative playlists")
                print("Attempting to proceed anyway...\n")
            
            return playlist_id
    return None


def setup_spotify_client():
    client_id, client_secret = get_spotify_credentials()
    
    # Create both authenticated and anonymous clients
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    sp_authenticated = spotipy.Spotify(auth_manager=auth_manager)
    sp_anonymous = spotipy.Spotify(auth_manager=SpotifyAnon())
    
    return sp_authenticated, sp_anonymous


def get_spotify_playlist_tracks(sp_authenticated, sp_anonymous, playlist_id):
    try:
        # First attempt with authenticated client
        all_tracks = []
        playlist_info = sp_authenticated.playlist(playlist_id, fields='name,tracks.total')
        playlist_name = playlist_info['name']
        results = sp_authenticated.playlist_items(playlist_id)
        if results and 'items' in results:
            all_tracks.extend(results['items'])
            while results['next']:
                results = sp_authenticated.next(results)
                all_tracks.extend(results['items'])
        print(f"✅ Successfully accessed playlist '{playlist_name}' with authenticated client")
        return playlist_name, all_tracks
        
    except spotipy.SpotifyException as e:
        if e.http_status == 404:
            print(f"⚠️  Authenticated access failed for playlist {playlist_id}")
            print("🔄 Trying anonymous authentication (for curated playlists)...")
            
            try:
                # Fallback to anonymous client for curated playlists
                all_tracks = []
                playlist_info = sp_anonymous.playlist(playlist_id, fields='name,tracks.total')
                playlist_name = playlist_info['name']
                results = sp_anonymous.playlist_items(playlist_id)
                if results and 'items' in results:
                    all_tracks.extend(results['items'])
                    while results['next']:
                        results = sp_anonymous.next(results)
                        all_tracks.extend(results['items'])
                print(f"✅ Successfully accessed playlist '{playlist_name}' with anonymous client")
                return playlist_name, all_tracks
                
            except spotipy.SpotifyException as anon_e:
                if anon_e.http_status == 404:
                    error_msg = f"Spotify playlist not found (ID: {playlist_id}). "
                    if playlist_id.startswith('37i9dQZF1E'):
                        error_msg += "\n🔒 This Spotify curated playlist is not accessible via API.\n"
                        error_msg += "Even anonymous authentication failed.\n\n"
                        error_msg += "✅ Try using instead:\n"
                        error_msg += "  • User-created public playlists\n"
                        error_msg += "  • Your own personal playlists\n"
                        error_msg += "  • Collaborative playlists\n"
                        error_msg += "  • Playlists from other users (not Spotify-generated)\n\n"
                        error_msg += "💡 Look for playlist URLs that don't start with '37i9dQZF1E'"
                    else:
                        error_msg += "This could mean:\n"
                        error_msg += "  1. The playlist ID is incorrect\n"
                        error_msg += "  2. The playlist is private and not accessible\n"
                        error_msg += "  3. The playlist has been deleted\n"
                        error_msg += "Please check the playlist URL and make sure it's public."
                    raise ValueError(error_msg)
                elif anon_e.http_status == 401:
                    raise ValueError("Both authenticated and anonymous Spotify access failed.")
                else:
                    raise ValueError(f"Spotify API error (anonymous): {anon_e}")
                    
        elif e.http_status == 401:
            raise ValueError("Spotify authentication failed. Please check your client credentials.")
        else:
            raise ValueError(f"Spotify API error: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error accessing Spotify playlist: {e}")


def parse_spotify_tracks(raw_tracks):
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
        track_number = track_data.get('track_number')
        disc_number = track_data.get('disc_number')
        year = track_data.get('album', {}).get('release_date', '')[:4]
        genre = None  # Spotify API does not provide genre per track by default
        if track_name and primary_artist and album_name:
            parsed_tracks.append({
                'title': track_name,
                'artist': primary_artist,
                'album': album_name,
                'url': spotify_url,
                'track_number': track_number,
                'disc_number': disc_number,
                'year': year,
                'genre': genre
            })
    return parsed_tracks
