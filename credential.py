import os
from dotenv import load_dotenv, find_dotenv


# Load .env if it exists
dotenv_path = find_dotenv()
if dotenv_path:
    load_dotenv(dotenv_path)

def get_spotify_credentials():
    """Returns Spotify client_id and client_secret, using .env if available, else defaults."""
    client_id = os.getenv("SPOTIPY_CLIENT_ID", "")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET must be set in .env")
    return client_id, client_secret

def get_plex_credentials():
    """Returns Plex URL and token, using .env if available, else defaults."""
    plex_url = os.getenv("PLEX_URL", "")
    plex_token = os.getenv("PLEX_TOKEN", "")
    if not plex_url or not plex_token:
        raise RuntimeError("PLEX_URL and PLEX_TOKEN must be set in .env")
    return plex_url, plex_token

def get_plex_music_library():
    return os.getenv("PLEX_MUSIC_LIBRARY", "Music")
