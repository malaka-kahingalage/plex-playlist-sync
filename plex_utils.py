def find_plex_match_robust(music_library, spotify_track, threshold=85, logger=None):
    """
    Multi-stage search for a Plex track matching the given Spotify track dict.
    Tries exact, fuzzy, title-only, artist-only, and album-based searches.
    Logs all attempts if logger is provided.
    """
    import re
    from thefuzz import fuzz
    def normalize(s):
        if not s:
            return ''
        s = s.lower()
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'[^a-z0-9 ]', '', s)
        s = s.replace('&', 'and').replace('feat', 'ft').replace('featuring', 'ft')
        return s.strip()

    title = normalize(spotify_track.get('title'))
    artist = normalize(spotify_track.get('artist'))
    album = normalize(spotify_track.get('album'))
    log = logger.info if logger else print

    # 1. Exact match (all fields)
    try:
        candidates = music_library.searchTracks(title=spotify_track['title'])
        for plex_track in candidates:
            if not (plex_track.parentTitle and plex_track.grandparentTitle):
                continue
            if (normalize(plex_track.title) == title and
                normalize(plex_track.grandparentTitle) == artist and
                normalize(plex_track.parentTitle) == album):
                log(f"🎯 Exact match: {plex_track.title} by {plex_track.grandparentTitle} ({plex_track.parentTitle})")
                return plex_track
    except Exception as e:
        log(f"Exact match search failed: {e}")

    # 2. Fuzzy match (weighted)
    try:
        candidates = music_library.searchTracks(title=spotify_track['title'])
        best_match = None
        highest_score = 0
        for plex_track in candidates:
            if not (plex_track.parentTitle and plex_track.grandparentTitle):
                continue
            artist_score = fuzz.token_set_ratio(artist, normalize(plex_track.grandparentTitle))
            album_score = fuzz.token_set_ratio(album, normalize(plex_track.parentTitle))
            title_score = fuzz.token_set_ratio(title, normalize(plex_track.title))
            weighted_score = (title_score * 0.5) + (artist_score * 0.3) + (album_score * 0.2)
            if weighted_score > highest_score:
                highest_score = weighted_score
                best_match = plex_track
        if best_match and highest_score >= 70:
            log(f"🤏 Fuzzy match: {best_match.title} by {best_match.grandparentTitle} (score={highest_score:.1f})")
            return best_match
    except Exception as e:
        log(f"Fuzzy match search failed: {e}")

    # 3. Title-only search, filter by artist
    try:
        candidates = music_library.searchTracks(title=spotify_track['title'])
        for plex_track in candidates:
            if not plex_track.grandparentTitle:
                continue
            if artist in normalize(plex_track.grandparentTitle):
                log(f"🔎 Title-only match, artist filter: {plex_track.title} by {plex_track.grandparentTitle}")
                return plex_track
    except Exception as e:
        log(f"Title-only search failed: {e}")

    # 4. Artist-only search, filter by title
    try:
        candidates = music_library.searchTracks(artist=spotify_track['artist'])
        for plex_track in candidates:
            if not plex_track.title:
                continue
            if title in normalize(plex_track.title):
                log(f"🔎 Artist-only match, title filter: {plex_track.title} by {plex_track.grandparentTitle}")
                return plex_track
    except Exception as e:
        log(f"Artist-only search failed: {e}")

    # 5. Album search, filter by title/artist
    try:
        candidates = music_library.searchTracks(album=spotify_track['album'])
        for plex_track in candidates:
            if not (plex_track.title and plex_track.grandparentTitle):
                continue
            if (title in normalize(plex_track.title) and artist in normalize(plex_track.grandparentTitle)):
                log(f"🔎 Album match, title+artist filter: {plex_track.title} by {plex_track.grandparentTitle}")
                return plex_track
    except Exception as e:
        log(f"Album search failed: {e}")

    # 6. Fuzzy filename search (final fallback)
    try:
        # Get all tracks in the library (may be slow for huge libraries)
        all_tracks = music_library.all()
        best_match = None
        highest_score = 0
        # Build expected filename (normalize as in download)
        expected_filename = f"{spotify_track['artist']} - {spotify_track['title']}.mp3"
        expected_filename_norm = normalize(expected_filename.replace('.mp3',''))
        for plex_track in all_tracks:
            # Try to get the file path/filename from locations (plexapi)
            locations = getattr(plex_track, 'locations', None)
            if not locations:
                continue
            for loc in locations:
                # Extract just the filename, normalize
                fname = os.path.splitext(os.path.basename(loc))[0]
                fname_norm = normalize(fname)
                score = fuzz.token_set_ratio(expected_filename_norm, fname_norm)
                if score > highest_score:
                    highest_score = score
                    best_match = plex_track
        if best_match and highest_score >= 70:
            log(f"🗂️  Fuzzy filename match: {best_match.title} by {best_match.grandparentTitle} (filename score={highest_score})")
            return best_match
    except Exception as e:
        log(f"Filename search failed: {e}")
    log(f"❌ No match found for: {spotify_track['artist']} - {spotify_track['title']} ({spotify_track['album']})")
    return None
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized
from credential import get_plex_credentials, get_plex_music_library


def setup_plex_client():
    baseurl, token = get_plex_credentials()
    plex = PlexServer(baseurl, token)
    return plex


def get_music_library(plex):
    music_library_name = get_plex_music_library()
    return plex.library.section(music_library_name)


def find_plex_match(music_library, spotify_track, threshold=60):
    import re
    from thefuzz import fuzz
    def normalize(s):
        return re.sub(r'[^a-z0-9 ]', '', s.lower()) if s else ''
    
    print(f"    🔍 Plex search for: '{spotify_track['title']}' by '{spotify_track['artist']}'")
    
    try:
        candidates = music_library.searchTracks(title=spotify_track['title'])
        if not candidates:
            print(f"    ❌ No tracks found with title: '{spotify_track['title']}'")
            return None
        
        print(f"    📚 Found {len(candidates)} candidate tracks")
        
        best_match = None
        highest_score = 0
        for plex_track in candidates:
            if not (plex_track.parentTitle and plex_track.grandparentTitle):
                continue
            
            # Only match on artist and title - IGNORE album completely
            artist_score = fuzz.token_set_ratio(normalize(spotify_track['artist']), normalize(plex_track.grandparentTitle))
            title_score = fuzz.token_set_ratio(normalize(spotify_track['title']), normalize(plex_track.title))
            
            # Weighted score: 70% title, 30% artist (no album)
            weighted_score = (title_score * 0.7) + (artist_score * 0.3)
            
            print(f"    🎵 Checking: '{plex_track.title}' by '{plex_track.grandparentTitle}' (Album: '{plex_track.parentTitle}')")
            print(f"        Title Score: {title_score}%, Artist Score: {artist_score}%, Combined: {weighted_score:.1f}%")
            
            if weighted_score > highest_score:
                highest_score = weighted_score
                best_match = plex_track
                print(f"        ✅ New best match! Score: {weighted_score:.1f}%")
        
        print(f"    🎯 Best match score: {highest_score:.1f}% (threshold: {threshold}%)")
        
        return best_match if highest_score >= threshold else None
    except Exception as e:
        print(f"    ⚠️ Error in Plex search: {e}")
        return None


def create_or_update_plex_playlist(plex, playlist_title, found_plex_tracks):
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
