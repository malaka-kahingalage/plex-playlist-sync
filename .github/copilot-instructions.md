# GitHub Copilot Custom Instructions for plexPlayList

## Project Overview
This project is a Python command-line application that synchronizes a specified Spotify playlist with a local Plex music library. It automates the process of matching tracks from Spotify to those in Plex, creates or updates a Plex playlist, and generates a report of any missing tracks.

## Key Technologies
- **Python 3**
- **spotipy**: For Spotify Web API access
- **python-plexapi**: For Plex Media Server API access
- **thefuzz** (and optionally **rapidfuzz**): For fuzzy string matching
- **python-dotenv**: For environment variable management

## Coding Guidelines
- Use modular functions for each logical component (authentication, data fetching, matching, playlist management, reporting).
- Do not hardcode credentials; always load from environment variables using `dotenv`.
- Use fuzzy matching (thefuzz) for comparing track metadata between Spotify and Plex.
- Handle API pagination for Spotify playlists.
- Use two-stage matching: first filter with Plex search, then confirm with fuzzy scoring.
- Always check for existing Plex playlists before creating new ones to avoid duplicates.
- Write missing track reports as plain text files, one URL per line.
- Use context managers (`with open(...)`) for file operations.
- Provide clear, user-friendly error messages for authentication and API failures.

## Security
- Never commit `.env` or any credentials to version control.
- Add `.env` to `.gitignore`.

## User Experience
- Prompt the user for the Spotify playlist URL at runtime.
- Print progress and summary information to the console.
- On first run, handle Spotify OAuth flow and cache credentials.

## File Structure
- Main script: `sync_playlist.py`
- Environment variables: `.env`
- Missing track reports: `missing_tracks_<playlist_name>.txt`

## Example Workflow
1. User runs `python sync_playlist.py` in a virtual environment.
2. User is prompted for a Spotify playlist URL.
3. Script authenticates with Spotify and Plex using credentials from `.env`.
4. Script fetches all tracks from the Spotify playlist, matches them to Plex tracks, and creates/updates the Plex playlist.
5. Script generates a report of any missing tracks.

## References
- See `project_scope.md` for full technical details, rationale, and code structure.
