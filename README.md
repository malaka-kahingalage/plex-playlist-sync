# Plex Spotify Sync

A Python tool to synchronize your Spotify playlists and artists with your local Plex music library. It fetches tracks from Spotify, matches them to your Plex library using fuzzy logic, downloads missing songs from sources like YouTube, SoundCloud, or Bandcamp, updates Plex playlists, and generates reports for unmatched tracks.

## Features
- Sync Spotify playlists and artists to Plex
- Fuzzy matching of tracks (artist/title) to avoid duplicates
- Downloads missing tracks from YouTube, SoundCloud, Bandcamp, and more
- Updates or creates Plex playlists automatically
- Generates plain text reports for missing/unmatched tracks
- Supports lyrics fetching and metadata embedding
- Robust error handling and logging

## Requirements
- Python 3.8+
- Plex Media Server
- Spotify account (for playlist/artist access)
- [spotipy](https://spotipy.readthedocs.io/), [plexapi](https://python-plexapi.readthedocs.io/), [thefuzz](https://github.com/seatgeek/thefuzz), [spotdl](https://github.com/spotDL/spotify-downloader), [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Docker (optional, for containerized deployment)

## Quick Start
1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/plex-spotify-sync.git
   cd plex-spotify-sync
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment:**
   - Copy `.env.example` to `.env` and fill in your Spotify and Plex credentials.
4. **Run the sync script:**
   ```bash
   python sync_playlist.py
   ```
5. **Follow prompts:**
   - Enter a Spotify playlist or artist URL when prompted.
   - The script will match, download, and organize tracks in your Plex library.

## Usage
- **Web UI:**
  - Optionally, run the included FastAPI web server for a simple browser interface.
- **Docker:**
  - Use the provided `docker-compose.yml` for easy deployment.

## Configuration
- All credentials and options are managed via the `.env` file.
- Downloaded tracks are organized by artist in your Plex music folder.
- Reports for missing tracks are saved as `missing_tracks_<playlist_or_artist>.txt`.

## Supported Audio Providers
- YouTube
- YouTube Music
- SoundCloud
- Bandcamp
- Piped

## Supported Lyrics Providers
- Genius
- MusixMatch
- AzLyrics
- Synced

## Troubleshooting
- Ensure your Plex library is scanned after new tracks are added.
- If you see authentication errors, check your `.env` credentials.
- For detailed logs, check the console output or log files.

## License
MIT License

---

**Contributions welcome!**

