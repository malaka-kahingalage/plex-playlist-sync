import logging
from typing import List, Dict, Optional, Tuple
from thefuzz import fuzz, process
import re

logger = logging.getLogger(__name__)

class EnhancedPlexMatcher:
    def __init__(self, plex_client, music_library):
        self.plex = plex_client
        self.music_library = music_library
        self.track_cache = {}
        self.artist_cache = {}
        
    def normalize_string(self, s: str) -> str:
        """Normalize strings for better matching"""
        if not s:
            return ""
        # Remove special characters, convert to lowercase, remove extra spaces
        normalized = re.sub(r'[^\w\s]', ' ', s.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def extract_features(self, text: str) -> set:
        """Extract key features from text for matching"""
        if not text:
            return set()
        
        # Remove common words that don't help with matching
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an'}
        
        words = self.normalize_string(text).split()
        features = set()
        
        # Add individual words
        for word in words:
            if len(word) > 2 and word not in stop_words:
                features.add(word)
        
        # Add bigrams for better context
        for i in range(len(words) - 1):
            if words[i] not in stop_words and words[i+1] not in stop_words:
                features.add(f"{words[i]} {words[i+1]}")
        
        return features
    
    def calculate_enhanced_similarity(self, spotify_track: Dict, plex_track) -> float:
        """Calculate enhanced similarity score between Spotify and Plex tracks"""
        try:
            # Extract data
            spotify_title = spotify_track.get('title', '')
            spotify_artist = spotify_track.get('artist', '')
            spotify_album = spotify_track.get('album', '')
            
            plex_title = getattr(plex_track, 'title', '')
            plex_artist = getattr(plex_track, 'grandparentTitle', '') or getattr(plex_track, 'artist', '')
            plex_album = getattr(plex_track, 'parentTitle', '') or getattr(plex_track, 'album', '')
            
            # Title matching (most important)
            title_score = fuzz.ratio(self.normalize_string(spotify_title), self.normalize_string(plex_title))
            
            # Artist matching (very important)
            artist_score = fuzz.ratio(self.normalize_string(spotify_artist), self.normalize_string(plex_artist))
            
            # Album matching (helpful but less critical)
            album_score = fuzz.ratio(self.normalize_string(spotify_album), self.normalize_string(plex_album))
            
            # Feature-based matching for robustness
            spotify_features = self.extract_features(f"{spotify_title} {spotify_artist}")
            plex_features = self.extract_features(f"{plex_title} {plex_artist}")
            
            if spotify_features and plex_features:
                common_features = len(spotify_features.intersection(plex_features))
                total_features = len(spotify_features.union(plex_features))
                feature_score = (common_features / total_features * 100) if total_features > 0 else 0
            else:
                feature_score = 0
            
            # Weighted combination
            # Title: 40%, Artist: 35%, Album: 15%, Features: 10%
            combined_score = (
                title_score * 0.40 +
                artist_score * 0.35 +
                album_score * 0.15 +
                feature_score * 0.10
            )
            
            logger.debug(f"Similarity scores for '{spotify_title}' vs '{plex_title}': "
                        f"Title={title_score:.1f}, Artist={artist_score:.1f}, "
                        f"Album={album_score:.1f}, Features={feature_score:.1f}, "
                        f"Combined={combined_score:.1f}")
            
            return combined_score
            
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    def smart_plex_search(self, spotify_track: Dict) -> List[Tuple[any, float]]:
        """Perform smart Plex search with multiple strategies"""
        title = spotify_track.get('title', '')
        artist = spotify_track.get('artist', '')
        album = spotify_track.get('album', '')
        
        candidates = []
        
        try:
            logger.info(f"🔍 Enhanced search for: {artist} - {title}")
            
            # Strategy 1: Exact title search (using correct API)
            try:
                exact_results = self.music_library.searchTracks(title=title)
                logger.info(f"  Title search returned {len(exact_results)} results")
                for track in exact_results:
                    score = self.calculate_enhanced_similarity(spotify_track, track)
                    candidates.append((track, score))
                    logger.debug(f"Title search candidate: {getattr(track, 'title', 'Unknown')} (score: {score:.1f})")
            except Exception as e:
                logger.warning(f"Title search failed: {e}")
            
            # Strategy 2: Search by combined query
            try:
                title_artist_results = self.music_library.search(f"{title} {artist}")
                # Filter only tracks from results
                track_results = [item for item in title_artist_results if hasattr(item, 'title') and hasattr(item, 'grandparentTitle')]
                logger.info(f"  Combined search returned {len(track_results)} track results")
                for track in track_results:
                    score = self.calculate_enhanced_similarity(spotify_track, track)
                    # Avoid duplicates
                    if not any(existing_track.key == track.key for existing_track, _ in candidates):
                        candidates.append((track, score))
                        logger.debug(f"Combined search candidate: {getattr(track, 'title', 'Unknown')} (score: {score:.1f})")
            except Exception as e:
                logger.warning(f"Combined search failed: {e}")
            
            # Strategy 3: Original simple search as fallback
            try:
                from plex_utils import find_plex_match
                simple_match = find_plex_match(self.music_library, spotify_track)
                if simple_match:
                    score = self.calculate_enhanced_similarity(spotify_track, simple_match)
                    # Avoid duplicates
                    if not any(existing_track.key == simple_match.key for existing_track, _ in candidates):
                        candidates.append((simple_match, score))
                        logger.info(f"  Original search found: {getattr(simple_match, 'title', 'Unknown')} (score: {score:.1f})")
            except Exception as e:
                logger.warning(f"Original search fallback failed: {e}")
            
            # Strategy 4: Search by artist name (using general search, then filter)
            try:
                artist_results = self.music_library.search(artist)
                # Filter only tracks from results and match artist
                track_results = []
                for item in artist_results:
                    if hasattr(item, 'title') and hasattr(item, 'grandparentTitle'):
                        # Check if this track's artist matches
                        if fuzz.ratio(self.normalize_string(artist), 
                                    self.normalize_string(getattr(item, 'grandparentTitle', ''))) >= 70:
                            track_results.append(item)
                
                logger.info(f"  Artist search returned {len(track_results)} matching track results")
                for track in track_results:
                    # Quick title similarity check before expensive full calculation
                    quick_title_score = fuzz.ratio(
                        self.normalize_string(title),
                        self.normalize_string(getattr(track, 'title', ''))
                    )
                    if quick_title_score >= 60:  # Lower threshold for artist search
                        score = self.calculate_enhanced_similarity(spotify_track, track)
                        # Avoid duplicates
                        if not any(existing_track.key == track.key for existing_track, _ in candidates):
                            candidates.append((track, score))
                            logger.debug(f"Artist search candidate: {getattr(track, 'title', 'Unknown')} (score: {score:.1f})")
            except Exception as e:
                logger.warning(f"Artist search failed: {e}")
            
            # Strategy 5: Broad title search with lower threshold
            try:
                title_results = self.music_library.search(title)
                # Filter only tracks from results
                track_results = [item for item in title_results if hasattr(item, 'title') and hasattr(item, 'grandparentTitle')][:30]
                
                logger.info(f"  Broad title search returned {len(track_results)} track results")
                for track in track_results:
                    # Quick pre-filter
                    quick_title_score = fuzz.ratio(
                        self.normalize_string(title),
                        self.normalize_string(getattr(track, 'title', ''))
                    )
                    if quick_title_score >= 70:  # Lower threshold for title search
                        score = self.calculate_enhanced_similarity(spotify_track, track)
                        # Avoid duplicates
                        if not any(existing_track.key == track.key for existing_track, _ in candidates):
                            candidates.append((track, score))
                            logger.debug(f"Broad title search candidate: {getattr(track, 'title', 'Unknown')} (score: {score:.1f})")
            except Exception as e:
                logger.warning(f"Broad title search failed: {e}")
            
            # Sort by score descending
            candidates.sort(key=lambda x: x[1], reverse=True)
            
            logger.info(f"  Total candidates found: {len(candidates)}")
            if candidates:
                best_score = candidates[0][1]
                logger.info(f"  Best candidate score: {best_score:.1f}")
            
            return candidates[:10]  # Return top 10 candidates
            
        except Exception as e:
            logger.error(f"Smart Plex search failed for '{title}' by '{artist}': {e}")
            return []
    
    def find_best_plex_match(self, spotify_track: Dict, min_score: float = 75.0) -> Optional[any]:
        """Find the best Plex match for a Spotify track"""
        title = spotify_track.get('title', 'Unknown')
        artist = spotify_track.get('artist', 'Unknown')
        
        try:
            logger.info(f"🔍 Searching Plex for: {artist} - {title}")
            
            # Get all candidates with scores
            candidates = self.smart_plex_search(spotify_track)
            
            if not candidates:
                logger.warning(f"❌ No Plex candidates found for: {artist} - {title}")
                return None
            
            # Get the best candidate
            best_track, best_score = candidates[0]
            
            logger.info(f"  Best candidate: {getattr(best_track, 'grandparentTitle', 'Unknown')} - {getattr(best_track, 'title', 'Unknown')} (score: {best_score:.1f})")
            
            if best_score >= min_score:
                plex_title = getattr(best_track, 'title', 'Unknown')
                plex_artist = getattr(best_track, 'grandparentTitle', 'Unknown')
                logger.info(f"✅ Plex match found (score: {best_score:.1f}): {plex_artist} - {plex_title}")
                return best_track
            else:
                logger.warning(f"⚠️  Best Plex candidate has low score ({best_score:.1f}): {artist} - {title}")
                # For debugging - show if we're close
                if best_score >= 60:
                    logger.info(f"  Close match available but below threshold ({min_score})")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error finding Plex match for '{title}' by '{artist}': {e}")
            return None
    
    def batch_find_matches(self, spotify_tracks: List[Dict], min_score: float = 75.0) -> Tuple[List[any], List[Dict]]:
        """Find matches for a batch of Spotify tracks"""
        found_tracks = []
        missing_tracks = []
        
        total_tracks = len(spotify_tracks)
        logger.info(f"🔍 Performing enhanced Plex search for {total_tracks} tracks...")
        
        for i, track in enumerate(spotify_tracks, 1):
            logger.info(f"🎵 [{i}/{total_tracks}] Searching: {track.get('artist', 'Unknown')} - {track.get('title', 'Unknown')}")
            
            plex_match = self.find_best_plex_match(track, min_score)
            
            if plex_match:
                found_tracks.append(plex_match)
            else:
                missing_tracks.append(track)
            
            # Progress indicator
            if i % 10 == 0 or i == total_tracks:
                found_count = len(found_tracks)
                missing_count = len(missing_tracks)
                logger.info(f"📊 Progress: {i}/{total_tracks} processed. Found: {found_count}, Missing: {missing_count}")
        
        logger.info(f"✅ Enhanced Plex search complete!")
        logger.info(f"  📁 Found in Plex: {len(found_tracks)}")
        logger.info(f"  📥 Need to download: {len(missing_tracks)}")
        
        return found_tracks, missing_tracks


def enhanced_plex_matching(plex_client, music_library, spotify_tracks: List[Dict], min_score: float = 75.0) -> Tuple[List[any], List[Dict]]:
    """Main function for enhanced Plex matching"""
    matcher = EnhancedPlexMatcher(plex_client, music_library)
    return matcher.batch_find_matches(spotify_tracks, min_score)