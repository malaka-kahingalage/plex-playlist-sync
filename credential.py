import os
from dotenv import load_dotenv, find_dotenv

# Default values (edit as needed)
#DEFAULT_SPOTIPY_CLIENT_ID = "8260f0f0e143459c8de09e6450051f9e"
#DEFAULT_SPOTIPY_CLIENT_SECRET = "5cf1d2f3862548c1ae15b32768385de5"
###
DEFAULT_SPOTIPY_CLIENT_ID = "4d4ba0679873456f888032bfd264524f"
DEFAULT_SPOTIPY_CLIENT_SECRET = "865aa022f7e64b4899a2a76a76075c3c"
###
DEFAULT_PLEX_URL = "http://10.10.40.21:32400"
DEFAULT_PLEX_TOKEN = "6BbGxxf_2MKoEKzzQqBf"
DEFAULT_PLEX_MUSIC_LIBRARY = "Music"

# Load .env if it exists
dotenv_path = find_dotenv()
if dotenv_path:
    load_dotenv(dotenv_path)

def get_spotify_credentials():
    """Returns Spotify client_id and client_secret, using .env if available, else defaults."""
    client_id = os.getenv("SPOTIPY_CLIENT_ID", DEFAULT_SPOTIPY_CLIENT_ID)
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", DEFAULT_SPOTIPY_CLIENT_SECRET)
    return client_id, client_secret

def get_plex_credentials():
    """Returns Plex URL and token, using .env if available, else defaults."""
    plex_url = os.getenv("PLEX_URL", DEFAULT_PLEX_URL)
    plex_token = os.getenv("PLEX_TOKEN", DEFAULT_PLEX_TOKEN)
    return plex_url, plex_token

def get_plex_music_library():
    return os.getenv("PLEX_MUSIC_LIBRARY", DEFAULT_PLEX_MUSIC_LIBRARY)
