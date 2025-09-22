import sys
import os
from sync_playlist import main

WELCOME = r'''
============================================
  Plex Playlist Sync: Spotify → Plex Music
============================================
This tool will help you synchronize a Spotify playlist with your Plex music library.

You will need:
- Your Spotify playlist URL (public playlists only, or private if you have the right credentials)
- Your Plex server running and accessible
- Credentials set in .env or as defaults in credential.py

Let's get started!
'''

INSTRUCTIONS = '''
Instructions:
1. Make sure your .env file is set up, or edit credential.py for defaults.
2. When prompted, paste the full Spotify playlist URL (e.g. https://open.spotify.com/playlist/xxxx).
3. The script will match tracks and create/update your Plex playlist.
4. A report of missing tracks will be saved in the current directory.
'''

if __name__ == "__main__":
    print(WELCOME)
    print(INSTRUCTIONS)
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
