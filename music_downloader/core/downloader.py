from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, AsyncIterator, Dict

import yt_dlp
import aiohttp
import musicbrainzngs
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3._util import ID3NoHeaderError
from .content_filter import ContentFilter
from .config import ConfigManager

logger = logging.getLogger(__name__)

@dataclass
class TrackMetadata:
    """Metadata for a music track."""
    title: str
    artist: str
    album: str = ""
    year: str = ""
    genre: str = ""

class ProgressCallback(Protocol):
    """Protocol for progress callbacks."""
    def __call__(self, status: str, progress: float = 0) -> None: ...

class MusicDownloader:
    """Core downloader class with async support."""
    
    def __init__(self, music_dir: Path):
        """Initialize the downloader with a music directory."""
        self.music_dir = music_dir
        self.music_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize content filter
        self.content_filter = ContentFilter()
        
        # Configure yt-dlp options
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'no_warnings': False,
            'extract_flat': True,
            'progress_hooks': [self.progress_hook],
            'postprocessor_hooks': [self.postprocessor_hook],
            'post_hooks': [self._post_process, self._clean_output_file],
            'paths': {'home': str(self.music_dir)},
            'ffmpeg_location': str(Path(__file__).parent.parent.parent / 'bin' / 'ffmpeg.exe'),
            'verbose': True,
            'logger': logger,
            'writethumbnail': False,
            'writeinfojson': False,
            'outtmpl': {
                'default': '%(title)s.%(ext)s'
            }
        }
        
        # Configure musicbrainz
        musicbrainzngs.set_useragent(
            "MP3 Player Genie",
            "2.0.0",
            "https://github.com/yourusername/mp3-player-genie"
        )
        
        self._current_callback = None
        self._cancelled = False

    async def _get_output_path(self, info: dict) -> Path:
        """Get the output path for a track based on MusicBrainz metadata."""
        # Get clean title for searching
        title = self._clean_title(info.get('title', ''))
        channel = info.get('channel', '')
        
        # Try to get MusicBrainz metadata
        try:
            result = await asyncio.to_thread(
                musicbrainzngs.search_recordings,
                query=f'recording:"{title}"',
                limit=5
            )
            
            if recordings := result.get('recording-list', []):
                # Score each result
                scored_results = []
                for recording in recordings:
                    score = self._score_metadata_match(recording, channel, title)
                    scored_results.append((score, recording))
                
                # Use the best match if score is above threshold
                if scored_results and scored_results[0][0] >= 0.7:
                    best_match = scored_results[0][1]
                    artist = best_match.get('artist-credit-phrase', channel)
                    title = best_match.get('title', title)
                    album = best_match.get('release-list', [{}])[0].get('title', '')
                    
                    # Clean filenames
                    artist = self.content_filter.clean_filename(artist)
                    title = self.content_filter.clean_filename(title)
                    
                    # Create artist directory
                    artist_dir = self.music_dir / artist
                    if album:
                        artist_dir = artist_dir / self.content_filter.clean_filename(album)
                    artist_dir.mkdir(parents=True, exist_ok=True)
                    
                    return artist_dir / f"{title}.mp3"
        
        except Exception as e:
            logger.warning(f"Failed to get MusicBrainz metadata for path: {e}")
        
        # Fallback: Use cleaned up video title and channel
        artist = self.content_filter.clean_filename(channel)
        title = self.content_filter.clean_filename(title)
        
        # Create artist directory
        artist_dir = self.music_dir / artist
        artist_dir.mkdir(parents=True, exist_ok=True)
        
        return artist_dir / f"{title}.mp3"

    async def search_track(self, query: str) -> AsyncIterator[dict]:
        """Search for tracks matching the query."""
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            try:
                # Search for videos
                results = await asyncio.to_thread(
                    ydl.extract_info,
                    f"ytsearch10:{query}",
                    download=False
                )
                
                if not results or 'entries' not in results:
                    return
                
                for entry in results['entries']:
                    if not entry:
                        continue
                        
                    # Score the result
                    score = self._score_result(entry, query)
                    
                    yield {
                        'id': entry['id'],
                        'title': entry['title'],
                        'channel': entry.get('channel', ''),
                        'duration': entry.get('duration', 0),
                        'score': score,
                    }
                    
            except Exception as e:
                logger.exception("Search failed")
                if isinstance(e, yt_dlp.utils.DownloadError):
                    if "HTTP Error 403" in str(e):
                        raise RuntimeError(
                            "YouTube is blocking our requests. Please try again later or update yt-dlp."
                        ) from e
                raise

    def _score_result(self, entry: dict, query: str) -> float:
        """Score a search result based on various factors."""
        score = 0.0
        
        # Convert to lowercase for comparison
        title = entry['title'].lower()
        channel = entry.get('channel', '').lower()
        query = query.lower()
        
        # Check for profanity if filter enabled
        if self.content_filter.enabled:
            if (self.content_filter.contains_profanity(title) or 
                self.content_filter.contains_profanity(channel)):
                return -100.0  # Effectively exclude profane content
        
        # Direct matches (case insensitive)
        if query in title:
            score += 10.0
            
        # Duration scoring (prefer typical song lengths)
        duration = entry.get('duration', 0)
        if 180 <= duration <= 360:  # 3-6 minutes
            score += 5.0
        elif 120 <= duration <= 480:  # 2-8 minutes
            score += 3.0
        elif duration > 480:  # Longer than 8 minutes
            score -= 5.0  # Likely a mix or compilation
            
        # Title format scoring - prioritize official audio and lyric videos
        lower_title = title.lower()
        
        # Highest priority: Official audio
        if "official audio" in lower_title:
            score += 25.0  # Increased from 15.0
        elif "audio" in lower_title:
            score += 15.0  # Increased from 8.0
            
        # Second priority: Lyric videos
        if "lyric video" in lower_title or "lyrics" in lower_title:
            score += 20.0  # Increased from 3.0
            
        # Third priority: Radio edits
        if "radio edit" in lower_title or "radio version" in lower_title:
            score += 12.0
            
        # Fourth priority: Official content
        if "official" in lower_title:
            score += 10.0  # Increased from 5.0
            
        # Penalize music videos more strongly
        if "official video" in lower_title or "music video" in lower_title:
            score -= 5.0  # Increased penalty from -2.0
            
        # Penalize unwanted versions
        penalties = [
            "live", "cover", "remix", "instrumental", "karaoke",
            "extended", "concert", "performance", "rehearsal", "demo",
            "acoustic", "remake", "remaster", "mix", "mashup"
        ]
        for term in penalties:
            if term in lower_title:
                score -= 8.0
                
        # Channel verification
        if entry.get('channel_verified', False):
            score += 5.0
            
        # View count scoring (log scale, max 5 points)
        view_count = entry.get('view_count', 0)
        if view_count > 0:
            score += min(5.0, (view_count / 1_000_000))
            
        # Like ratio scoring (if available)
        if 'like_count' in entry and 'dislike_count' in entry:
            likes = entry['like_count'] or 0
            dislikes = entry['dislike_count'] or 0
            total = likes + dislikes
            if total > 0:
                ratio = likes / total
                score += ratio * 3.0  # Max 3 points for perfect like ratio
                
        return score

    async def download_track(
        self,
        video_id: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Path:
        """Download a track by video ID."""
        self._current_callback = progress_callback
        self._cancelled = False
        output_path = None
        
        if progress_callback:
            progress_callback("Starting download...", 0)
            
        try:
            # Get video info first
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                if progress_callback:
                    progress_callback("Fetching video info...", 0.1)
                    
                if self._cancelled:
                    raise RuntimeError("Download cancelled")
                    
                info = await asyncio.to_thread(
                    ydl.extract_info,
                    f"https://youtube.com/watch?v={video_id}",
                    download=False
                )
                
                if not info:
                    raise ValueError("Failed to get video info")
                
                # Get final output path
                output_path = await self._get_output_path(info)
                
                # Download the track
                if self._cancelled:
                    raise RuntimeError("Download cancelled")
                    
                try:
                    # Create a new options dict with the output template
                    opts = dict(self.ydl_opts)
                    opts['outtmpl'] = {
                        'default': str(output_path.with_suffix('').with_suffix('.%(ext)s'))
                    }
                    
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        await asyncio.to_thread(
                            ydl.download,
                            [f"https://youtube.com/watch?v={video_id}"]
                        )
                except yt_dlp.utils.DownloadError as e:
                    error_msg = str(e)
                    if "HTTP Error 403" in error_msg:
                        raise RuntimeError(
                            "YouTube is blocking our requests. Please try again later."
                        ) from e
                    elif "Video unavailable" in error_msg:
                        raise RuntimeError(
                            "This video is not available. It might be private or deleted."
                        ) from e
                    elif "Sign in" in error_msg:
                        raise RuntimeError(
                            "This video requires age verification or sign in."
                        ) from e
                    else:
                        raise RuntimeError(f"Download failed: {error_msg}") from e
                
                if self._cancelled:
                    if output_path.exists():
                        output_path.unlink()
                    raise RuntimeError("Download cancelled")
                
                # Wait a moment for ffmpeg to finish conversion
                await asyncio.sleep(0.5)
                
                # Verify the MP3 file exists
                mp3_path = output_path.with_suffix('.mp3')
                if not mp3_path.exists():
                    logger.error(f"Expected file not found at: {mp3_path}")
                    logger.error(f"Directory contents: {list(output_path.parent.glob('*'))}")
                    raise FileNotFoundError("Converted MP3 file not found")
                
                # Format metadata from video info
                metadata = {
                    'title': self._clean_title(info.get('title', '')),
                    'artist': info.get('channel', ''),
                    'album': info.get('album', ''),
                    'date': info.get('upload_date', '')[:4] if info.get('upload_date') else '',
                    'genre': info.get('genre', '')
                }
                
                # Update metadata
                if progress_callback:
                    progress_callback("Finalizing metadata...", 0.95)
                    
                if not self._cancelled:
                    try:
                        metadata = await asyncio.to_thread(self._update_metadata, mp3_path, metadata)
                        logger.info("Updated metadata: %s", metadata)
                    except Exception as e:
                        logger.error("Failed to update metadata: %s", e)
                        if progress_callback:
                            progress_callback("Warning: Metadata update failed, but download succeeded", 0.95)
                
                # Check if we should update progress and verify file
                if progress_callback and not self._cancelled:
                    if not mp3_path.exists():
                        raise FileNotFoundError("Downloaded file not found at expected location")
                    progress_callback("Download complete!", 1.0)
                
                # Return the path to the downloaded file
                return mp3_path
                
        except Exception as e:
            logger.exception("Download failed")
            # Clean up partial downloads
            if output_path:
                try:
                    # Clean up any partial downloads with any extension
                    for file in output_path.parent.glob(f"{output_path.stem}.*"):
                        file.unlink()
                except Exception as cleanup_error:
                    logger.error("Failed to clean up partial download: %s", cleanup_error)
            
            if progress_callback:
                if isinstance(e, RuntimeError):
                    progress_callback(str(e), 0)
                else:
                    progress_callback(f"Download failed: {str(e)}", 0)
            raise
        finally:
            self._current_callback = None
            self._cancelled = False

    def progress_hook(self, d: dict) -> None:
        """Progress hook for yt-dlp."""
        if not self._current_callback:
            return
            
        if d['status'] == 'downloading':
            try:
                if '_percent_str' in d:
                    p = d.get('_percent_str', '0%').replace('%', '')
                    speed = d.get('_speed_str', '')
                    eta = d.get('_eta_str', '')
                    self._current_callback(
                        f"Downloading: {p}% @ {speed} (ETA: {eta})", 
                        float(p) / 100 * 0.7
                    )
                else:
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes', 0)
                    if total > 0:
                        progress = downloaded / total
                        self._current_callback(
                            f"Downloading: {progress:.1%}", 
                            progress * 0.7
                        )
            except (ValueError, ZeroDivisionError):
                self._current_callback("Downloading...", 0.1)
        elif d['status'] == 'finished':
            self._current_callback("Download complete, starting conversion...", 0.75)
                
    def postprocessor_hook(self, d: dict) -> None:
        """Post-processor hook for yt-dlp."""
        if not self._current_callback:
            return
            
        if d['status'] == 'started':
            if d['postprocessor'] == 'FFmpegExtractAudio':
                self._current_callback("Converting audio to MP3...", 0.8)
            elif d['postprocessor'] == 'FFmpegMetadata':
                self._current_callback("Adding metadata tags...", 0.9)
            elif d['postprocessor'] == 'EmbedThumbnail':
                self._current_callback("Adding album artwork...", 0.85)
        elif d['status'] == 'finished':
            if d['postprocessor'] == 'FFmpegExtractAudio':
                self._current_callback("Audio conversion complete", 0.85)
            elif d['postprocessor'] == 'FFmpegMetadata':
                self._current_callback("Metadata added successfully", 0.95)
            elif d['postprocessor'] == 'EmbedThumbnail':
                self._current_callback("Album artwork added", 0.9)

    def _post_process(self, d: dict | str) -> None:
        """Post-processor hook to handle cleanup."""
        if not self._current_callback:
            return

        if isinstance(d, dict):
            if d.get('status') == 'started':
                self._current_callback("Starting post-processing...", 0.75)
            elif d.get('status') == 'finished':
                filename = d.get('filename', 'unknown file')
                logger.debug("Post-processing finished for %s", filename)
                self._current_callback("Post-processing complete", 0.9)
        elif isinstance(d, str):
            logger.debug("Post-processing finished for %s", d)
            self._current_callback("Post-processing complete", 0.9)
            
    def _clean_output_file(self, d: dict | str) -> None:
        """Clean up the output file name and any temporary files."""
        if not self._current_callback:
            return

        if isinstance(d, dict) and d.get('status') == 'finished':
            filename = d.get('filename')
            if filename:
                logger.debug("Cleaning output file: %s", filename)
                self._current_callback("Cleaning up file...", 0.95)
                
                # Clean up any temporary files (webp, jpg, etc)
                try:
                    base_path = Path(filename).with_suffix('')
                    for ext in ['.webp', '.jpg', '.jpeg', '.png']:
                        temp_file = base_path.with_suffix(ext)
                        if temp_file.exists():
                            try:
                                # Force close any open handles
                                import gc
                                gc.collect()
                                
                                # Try to delete the file
                                logger.debug("Removing temporary file: %s", temp_file)
                                temp_file.unlink(missing_ok=True)
                            except PermissionError:
                                logger.warning("Permission denied when deleting %s - will try again later", temp_file)
                            except Exception as e:
                                logger.error("Failed to delete temporary file %s: %s", temp_file, e)
                except Exception as e:
                    logger.error("Failed to clean up temporary files: %s", e)
                    
        elif isinstance(d, str):
            logger.debug("Cleaning output file: %s", d)
            self._current_callback("Cleaning up file...", 0.95)

    def _update_metadata(self, file_path: Path, metadata: dict) -> dict:
        """Update the metadata of an MP3 file."""
        audio = None
        tags = None
        written_metadata = {}
        
        try:
            # Load audio file
            audio = MP3(file_path)
            
            # Get or create ID3 tags
            try:
                tags = EasyID3(file_path)
            except ID3NoHeaderError:
                logger.debug("No ID3 header found, creating one")
                tags = EasyID3()
                tags.save(file_path)
            
            # Map metadata to ID3 tags
            if 'title' in metadata:
                tags['title'] = metadata['title']
            if 'artist' in metadata:
                tags['artist'] = metadata['artist']
            if 'album' in metadata:
                tags['album'] = metadata['album']
            if 'date' in metadata:
                tags['date'] = metadata['date']
            if 'genre' in metadata:
                tags['genre'] = metadata['genre']
            
            # Save tags
            tags.save()
            logger.info("Successfully wrote metadata to file")
            
            # Return the metadata that was written
            written_metadata = {
                'title': metadata.get('title', ''),
                'artist': metadata.get('artist', ''),
                'album': metadata.get('album', ''),
                'date': metadata.get('date', ''),
                'genre': metadata.get('genre', ''),
                'file_path': str(file_path),
                'format': 'MP3',
                'size': file_path.stat().st_size,
                'duration': int(audio.info.length) if audio else 0
            }
            
        except Exception as e:
            logger.error("Failed to update metadata: %s", e)
        
        finally:
            # Clean up
            if audio:
                audio.tags = None
                audio = None
            if tags:
                tags = None
            
        return written_metadata

    def _has_better_metadata(self, new_recording: dict, existing_recording: dict) -> bool:
        """Check if new_recording has more complete metadata than existing_recording."""
        score = 0
        
        # Prefer recordings with releases
        if 'release-list' in new_recording:
            score += 1
            
        # Prefer recordings with ISRC
        if 'isrc-list' in new_recording:
            score += 1
            
        # Prefer recordings with tags
        if 'tag-list' in new_recording:
            score += 1
            
        existing_score = 0
        if 'release-list' in existing_recording:
            existing_score += 1
        if 'isrc-list' in existing_recording:
            existing_score += 1
        if 'tag-list' in existing_recording:
            existing_score += 1
            
        return score > existing_score

    def _get_best_release(self, releases: list) -> Optional[dict]:
        """Find the best release from a list of releases."""
        if not releases:
            return None
            
        # Score each release
        scored_releases = []
        for release in releases:
            score = 0
            
            # Prefer albums over compilations
            release_group = release.get('release-group', {})
            if release_group.get('type') == 'Album':
                score += 2
            elif release_group.get('type') in ['EP', 'Single']:
                score += 1
            elif release_group.get('type') == 'Compilation':
                score -= 1
                
            # Prefer releases with complete date
            if release.get('date', '').count('-') == 2:
                score += 1
                
            # Prefer releases with cover art
            if release.get('cover-art-archive', {}).get('front', False):
                score += 1
                
            scored_releases.append((score, release))
            
        # Sort by score and return the best
        scored_releases.sort(key=lambda x: x[0], reverse=True)
        return scored_releases[0][1] if scored_releases else releases[0]

    def _score_metadata_match(self, recording: dict, artist: str, title: str) -> float:
        """Score how well a metadata match fits the artist and title."""
        score = 0.0
        
        # Get recording info
        rec_title = recording.get('title', '').lower()
        rec_artist = recording.get('artist-credit-phrase', '').lower()
        
        # Clean up input
        artist = artist.lower()
        title = title.lower()
        
        # Title matching (50% of score)
        if rec_title == title:
            score += 0.5
        else:
            # Partial title match
            title_words = set(title.split())
            rec_title_words = set(rec_title.split())
            common_words = title_words & rec_title_words
            if common_words:
                score += 0.5 * (len(common_words) / max(len(title_words), len(rec_title_words)))
        
        # Artist matching (50% of score)
        if rec_artist == artist:
            score += 0.5
        else:
            # Partial artist match
            artist_words = set(artist.split())
            rec_artist_words = set(rec_artist.split())
            common_words = artist_words & rec_artist_words
            if common_words:
                score += 0.5 * (len(common_words) / max(len(artist_words), len(rec_artist_words)))
        
        # Bonus points for additional metadata
        if recording.get('release-list'):
            score += 0.05  # Bonus for having album info
        if recording.get('isrc-list'):
            score += 0.05  # Bonus for having ISRC
                
        return min(1.0, score)  # Cap at 1.0

    async def fetch_metadata(self, artist: str, title: str) -> Optional[TrackMetadata]:
        """Fetch metadata from multiple sources and combine results."""
        # Clean up the title and artist first
        title = self._clean_title(title)
        artist = artist.strip()
        
        metadata = None
        
        # Try MusicBrainz with multiple search strategies
        try:
            # Strategy 1: Exact artist + title match
            result = await asyncio.to_thread(
                musicbrainzngs.search_recordings,
                query=f'artistname:"{artist}" AND recording:"{title}"',
                limit=5
            )
            
            if recordings := result.get('recording-list', []):
                # Score each result
                scored_results = []
                for recording in recordings:
                    score = self._score_metadata_match(recording, artist, title)
                    scored_results.append((score, recording))
                
                # Use the best match if score is above threshold
                if scored_results and scored_results[0][0] >= 0.7:
                    best_match = scored_results[0][1]
                    metadata = TrackMetadata(
                        title=best_match.get('title', title),
                        artist=best_match.get('artist-credit-phrase', artist),
                        album=best_match.get('release-list', [{}])[0].get('title', ''),
                        year=best_match.get('release-list', [{}])[0].get('date', '')[:4],
                        genre=best_match.get('tag-list', [{}])[0].get('name', '')
                    )
            
            # Strategy 2: If no good match, try just the title
            if not metadata:
                result = await asyncio.to_thread(
                    musicbrainzngs.search_recordings,
                    query=f'recording:"{title}"',
                    limit=10
                )
                
                if recordings := result.get('recording-list', []):
                    # Score each result
                    scored_results = []
                    for recording in recordings:
                        score = self._score_metadata_match(recording, artist, title)
                        scored_results.append((score, recording))
                    
                    # Use the best match if score is above threshold
                    if scored_results and scored_results[0][0] >= 0.8:  # Higher threshold for title-only search
                        best_match = scored_results[0][1]
                        metadata = TrackMetadata(
                            title=best_match.get('title', title),
                            artist=best_match.get('artist-credit-phrase', artist),
                            album=best_match.get('release-list', [{}])[0].get('title', ''),
                            year=best_match.get('release-list', [{}])[0].get('date', '')[:4],
                            genre=best_match.get('tag-list', [{}])[0].get('name', '')
                        )
                
        except Exception as e:
            logger.warning(f"Failed to fetch MusicBrainz metadata: {e}")
        
        # If no metadata found, create basic metadata from video info
        if not metadata:
            metadata = TrackMetadata(title=title, artist=artist)
            
        return metadata

    def _clean_title(self, title: str) -> str:
        """Clean up the title for better metadata matching."""
        title = title.strip()
        
        # Remove artist prefix if present (e.g., "Artist - Title" -> "Title")
        if " - " in title:
            parts = title.split(" - ", 1)
            if len(parts) == 2:
                title = parts[1].strip()
        
        # Remove common suffixes
        suffixes = [
            '(Official Music Video)',
            '(Official Video)',
            '(Official Audio)',
            '(Lyric Video)',
            '(Music Video)',
            '[Official Music Video]',
            '[Official Video]',
            '[Official Audio]',
            '[Lyric Video]',
            '[Music Video]',
            '(HD)',
            '(HQ)',
            '(4K)',
            '(1080p)',
            '(720p)',
            '(Official)',
            '(Audio)',
            '(Lyrics)',
            'Official Video',
            'Official Audio',
            'Lyric Video',
            'Music Video',
            'Official Music Video'
        ]
        
        for suffix in suffixes:
            if title.lower().endswith(suffix.lower()):
                title = title[:-len(suffix)].strip()
            if title.lower().startswith(suffix.lower()):
                title = title[len(suffix):].strip()
                
        # Remove featuring artists for better matching
        feat_indicators = ['ft.', 'feat.', 'featuring', 'ft', 'feat']
        lower_title = title.lower()
        for indicator in feat_indicators:
            if indicator in lower_title:
                feat_index = lower_title.find(indicator)
                if feat_index > 0:
                    title = title[:feat_index].strip()
                    
        # Remove anything in parentheses or brackets at the end
        while title.endswith(')') and '(' in title:
            title = title[:title.rindex('(')].strip()
        while title.endswith(']') and '[' in title:
            title = title[:title.rindex('[')].strip()
            
        return title.strip()

    async def apply_metadata(
        self,
        file_path: Path,
        metadata: TrackMetadata,
        progress_callback: Optional[ProgressCallback] = None
    ) -> bool:
        """Apply metadata to the downloaded file."""
        try:
            if progress_callback:
                progress_callback("Applying metadata...", 0)
                
            # Load the file
            audio = MP3(file_path, ID3=EasyID3)
            
            # Ensure tags exist
            if not audio.tags:
                audio.add_tags()
                
            # Apply metadata - now we know tags exist
            tags = audio.tags
            if tags is not None:  # Extra safety check for type checker
                tags['title'] = metadata.title
                tags['artist'] = metadata.artist
                if metadata.album:
                    tags['album'] = metadata.album
                if metadata.year:
                    tags['date'] = metadata.year
                if metadata.genre:
                    tags['genre'] = metadata.genre
                
                # Save changes
                audio.save()
                
                if progress_callback:
                    progress_callback("Metadata applied!", 1.0)
                    
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to apply metadata: {e}")
            return False 

    def cancel_download(self):
        """Cancel the current download."""
        logger.info("Cancelling download...")
        self._cancelled = True 