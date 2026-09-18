"""
YouTube audio fetcher for track analysis.

Searches YouTube for audio matching track metadata,
downloads the best match, and validates the audio file.

AGPL-3.0 License - See LICENSE file for details.
"""
import structlog
import os
import glob
import re
import yt_dlp
import difflib


class AudioFetcher:
    """
    Fetches audio from YouTube for analysis.

    Uses yt-dlp to search and download audio files.
    Implements intelligent matching based on title, artist, and duration.
    """

    def __init__(self, temp_dir="./temp_audio"):
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)
        self.log = structlog.get_logger()
        self._expected_duration_ms = None
        self._track_title = None
        self._artist_name = None

    def _normalize_title(self, title: str) -> str:
        """
        Normalize a title for comparison by removing common variations.
        """
        title = title.lower()
        # Remove content in parentheses/brackets (feat., remix info, etc.)
        title = re.sub(r'\([^)]*\)', '', title)
        title = re.sub(r'\[[^\]]*\]', '', title)
        # Remove common suffixes
        title = re.sub(r'\s*[-\u2013\u2014]\s*(official|audio|video|lyric|lyrics|hd|hq|4k|visualizer|visualiser).*$', '', title, flags=re.IGNORECASE)
        # Remove special characters and extra whitespace
        title = re.sub(r'[^\w\s]', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    def fetch_track_audio(self, track_id: str, query: str, expected_duration_ms: int = None,
                          track_title: str = None, artist_name: str = None,
                          direct_video_id: str = None) -> dict | None:
        """
        Fetch audio from YouTube.

        1. If direct_video_id is provided, downloads that video directly.
        2. Otherwise, searches YouTube for the top 20 results.
        3. Scores candidates based on duration match and title similarity.
        4. Downloads the best scoring match if confidence is above threshold.

        Args:
            track_id: Unique identifier for the track
            query: Search query string
            expected_duration_ms: Expected track duration in milliseconds
            track_title: The exact track title (for accurate matching)
            artist_name: The artist name (for accurate matching)
            direct_video_id: If provided, skip search and download this video directly

        Returns:
            dict with file_path, youtube_id, youtube_title, verified, actual_duration_ms
            or None if no suitable audio found
        """
        self.cleanup(track_id)

        # Store for use in matching
        self._track_title = track_title
        self._artist_name = artist_name
        self._expected_duration_ms = expected_duration_ms

        # Download Options
        dl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{self.temp_dir}/{track_id}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'quiet': True,
            'noplaylist': True,
        }

        try:
            # --- DIRECT DOWNLOAD PATH (User-provided link) ---
            if direct_video_id:
                self.log.info("direct_download", video_id=direct_video_id)
                video_url = f"https://www.youtube.com/watch?v={direct_video_id}"

                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    youtube_id = info.get('id')
                    youtube_title = info.get('title')

                expected_file = f"{self.temp_dir}/{track_id}.mp3"

                # Verify downloaded audio
                verification = self._verify_downloaded_audio(expected_file)
                if not verification["valid"]:
                    self.log.warn("direct_download_verification_failed", reason=verification['reason'])

                if os.path.exists(expected_file):
                    return {
                        "file_path": expected_file,
                        "youtube_id": youtube_id,
                        "youtube_title": youtube_title,
                        "verified": verification["valid"],
                        "actual_duration_ms": verification["actual_duration_ms"]
                    }
                return None

            # --- SEARCH PATH (No direct link provided) ---
            search_opts = {
                'quiet': True,
                'noplaylist': True,
                'extract_flat': True,
            }

            with yt_dlp.YoutubeDL(search_opts) as ydl:
                self.log.info("youtube_search", query=query, result_count=20)

                search_query = f"ytsearch20:{query}"
                info = ydl.extract_info(search_query, download=False)
                entries = info.get('entries', [])

                if not entries:
                    self.log.warn("search_no_results", query=query)
                    return None

                best_match = self._find_best_match(entries, expected_duration_ms)

                if not best_match:
                    self.log.warn("all_candidates_rejected")
                    return None

                # Get full info and download
                full_info = ydl.extract_info(best_match['url'], download=False)
                youtube_id = full_info.get('id')
                youtube_title = full_info.get('title')
                webpage_url = full_info.get('webpage_url')

            # Download the verified video
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                self.log.info("downloading_match", title=youtube_title)
                ydl.download([webpage_url])

            expected_file = f"{self.temp_dir}/{track_id}.mp3"

            if os.path.exists(expected_file):
                verification = self._verify_downloaded_audio(expected_file)

                if not verification["valid"]:
                    self.log.warn("post_download_verification_failed", reason=verification['reason'])
                    self.cleanup(track_id)
                    return None

                self.log.info("audio_verified", reason=verification['reason'])
                return {
                    "file_path": expected_file,
                    "youtube_id": youtube_id,
                    "youtube_title": youtube_title,
                    "verified": True,
                    "actual_duration_ms": verification["actual_duration_ms"]
                }

        except Exception as e:
            self.log.error("download_failed", track_id=track_id, error=str(e))
            return None

        return None

    def _find_best_match(self, entries: list, expected_duration_ms: int) -> dict | None:
        """
        Score candidates based on title, artist, and duration match.

        Returns the best matching entry dictionary, or None.
        """
        candidates = []

        TITLE_WEIGHT = 0.4
        ARTIST_WEIGHT = 0.2
        DURATION_WEIGHT = 0.4
        MIN_CONFIDENCE = 0.65
        MIN_TITLE_SIMILARITY = 0.5

        track_title = self._track_title or ""
        artist_name = self._artist_name or ""

        normalized_track_title = self._normalize_title(track_title)
        normalized_artist = self._normalize_title(artist_name)

        for video_data in entries:
            score = 0

            video_title = video_data.get('title', '')
            normalized_video_title = self._normalize_title(video_title)
            video_channel = video_data.get('channel', '').lower() if video_data.get('channel') else ''

            # Basic validation
            if not self._passes_basic_filters(video_data, track_title):
                continue

            # Title score
            title_similarity = 0
            if normalized_track_title:
                if normalized_track_title in normalized_video_title:
                    title_similarity = 1.0
                else:
                    title_similarity = difflib.SequenceMatcher(
                        None, normalized_track_title, normalized_video_title
                    ).ratio()

                    track_words = set(normalized_track_title.split())
                    video_words = set(normalized_video_title.split())
                    if track_words and track_words.issubset(video_words):
                        title_similarity = max(title_similarity, 0.9)

            if normalized_track_title and title_similarity < MIN_TITLE_SIMILARITY:
                self.log.debug("candidate_rejected_low_title_similarity", video_title=video_title, title_similarity=round(title_similarity, 2))
                continue

            score += title_similarity * TITLE_WEIGHT

            # Artist score
            artist_similarity = 0
            if normalized_artist:
                if normalized_artist in normalized_video_title:
                    artist_similarity = 1.0
                elif normalized_artist in video_channel:
                    artist_similarity = 0.9
                else:
                    artist_similarity = max(
                        difflib.SequenceMatcher(None, normalized_artist, normalized_video_title).ratio(),
                        difflib.SequenceMatcher(None, normalized_artist, video_channel).ratio()
                    )
            else:
                artist_similarity = 0.5

            score += artist_similarity * ARTIST_WEIGHT

            # Duration score
            yt_duration_sec = video_data.get('duration', 0)
            expected_sec = expected_duration_ms / 1000 if expected_duration_ms else 0

            if expected_sec > 0 and yt_duration_sec > 0:
                max_diff = 15
                duration_diff = abs(yt_duration_sec - expected_sec)
                duration_score = max(0, 1 - (duration_diff / max_diff))
                score += duration_score * DURATION_WEIGHT
            else:
                score += 0.3 * DURATION_WEIGHT

            # Bonus for official channels
            if "topic" in video_channel or "- topic" in video_channel:
                score += 0.05

            candidates.append({
                'video': video_data,
                'score': score,
                'url': video_data.get('webpage_url'),
                'title_sim': title_similarity,
                'artist_sim': artist_similarity
            })

            self.log.debug("candidate_scored", video_title=video_title, score=round(score, 2))

        candidates.sort(key=lambda x: x['score'], reverse=True)

        if candidates:
            best = candidates[0]
            self.log.info("best_match_found", title=best['video'].get('title'), score=round(best['score'], 2))

            if best['score'] >= MIN_CONFIDENCE:
                return best['video']
            else:
                self.log.warn("best_score_below_threshold", score=round(best['score'], 2), threshold=MIN_CONFIDENCE)

        return None

    def _passes_basic_filters(self, video_data: dict, track_title: str) -> bool:
        """
        Check for obvious mismatches (karaoke, live, covers, etc.).
        """
        video_title = video_data.get('title', '').lower()
        track_title_lower = track_title.lower() if track_title else ""

        # Forbidden keywords
        forbidden_keywords = ['live', 'cover', 'karaoke', 'remix', 'mix', 'tutorial',
                              'instrumental', 'acoustic', 'slowed', 'reverb', 'sped up', '8d']

        for word in forbidden_keywords:
            if word in video_title and word not in track_title_lower:
                return False

        # Reject very short or very long videos
        duration = video_data.get('duration', 0)
        if duration > 0 and (duration < 60 or duration > 600):
            return False

        return True

    def cleanup(self, track_id: str):
        """Remove temporary audio files for a track."""
        files = glob.glob(f"{self.temp_dir}/{track_id}.*")
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass

    def _verify_downloaded_audio(self, file_path: str) -> dict:
        """
        Verify the downloaded audio file.

        Returns: {"valid": bool, "actual_duration_ms": int, "reason": str}
        """
        if not os.path.exists(file_path):
            return {"valid": False, "actual_duration_ms": 0, "reason": "File not found"}

        try:
            from mutagen.mp3 import MP3

            audio = MP3(file_path)
            actual_duration_ms = int(audio.info.length * 1000)

            if not self._expected_duration_ms:
                return {"valid": True, "actual_duration_ms": actual_duration_ms, "reason": "No expected duration to compare"}

            diff_ms = abs(actual_duration_ms - self._expected_duration_ms)
            diff_seconds = diff_ms / 1000

            # 10 second tolerance
            if diff_seconds <= 10:
                return {
                    "valid": True,
                    "actual_duration_ms": actual_duration_ms,
                    "reason": f"Duration match (diff: {diff_seconds:.1f}s)"
                }
            else:
                return {
                    "valid": False,
                    "actual_duration_ms": actual_duration_ms,
                    "reason": f"Duration mismatch: expected {self._expected_duration_ms/1000:.0f}s, got {actual_duration_ms/1000:.0f}s"
                }

        except Exception as e:
            self.log.error("audio_verification_failed", error=str(e))
            return {"valid": False, "actual_duration_ms": 0, "reason": f"Verification error: {e}"}
