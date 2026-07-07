"""
Music Library & Playlist Checker for Rekordbox / Local Folders.

Scans a local directory for audio files and compares them against tracks
from a Spotify (or other supported platform) playlist to identify existing
and missing songs.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Set

import mutagen

from src.core.models import TrackInfo
from src.core.scraper import scrape_playlist, scrape_metadata

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".m4a", ".aac", ".aiff", ".aif",
    ".ogg", ".opus", ".alac", ".wma"
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by",
    "for", "with", "vs", "pres", "presents", "dj", "mc", "part", "pt"
}


@dataclass
class LocalAudioFile:
    """Represents a local music file found during folder scanning."""
    file_path: str
    rel_path: str
    filename_clean: str
    tag_title: str = ""
    tag_artist: str = ""
    tag_album: str = ""
    duration_s: Optional[float] = None
    title_tokens: Set[str] = field(default_factory=set)
    artist_tokens: Set[str] = field(default_factory=set)
    all_tokens: Set[str] = field(default_factory=set)


@dataclass
class TrackMatchResult:
    """Result of comparing a playlist track against the local library."""
    track: TrackInfo
    exists: bool = False
    matched_file_path: Optional[str] = None
    matched_rel_path: Optional[str] = None
    matched_by: Optional[str] = None  # e.g., "ID3 Tags" or "Filename / Path"
    similarity_score: float = 0.0
    matched_duration_s: Optional[float] = None


class LibraryChecker:
    """
    Compares a music platform playlist/album against a local folder (e.g. Rekordbox library).
    """

    @staticmethod
    def _normalize_to_tokens(text: str) -> Set[str]:
        """
        Normalize string and extract significant alphanumeric tokens for fuzzy matching.
        Strips common music qualifiers like (Official Video), (Remastered), etc.
        """
        if not text:
            return set()

        # Unicode normalize
        norm = unicodedata.normalize("NFC", text)

        # Strip parenthesized or bracketed qualifiers (e.g., [Official Audio], (Radio Edit))
        norm = re.sub(
            r'[\(\[].*?(official|video|audio|remaster|edit|mix|remix|feat|ft|live|bonus|deluxe|version|akustik|acoustic).*?[\)\]]',
            ' ',
            norm,
            flags=re.IGNORECASE,
        )

        # Strip trailing featuring info not in parens
        norm = re.sub(r'\b(feat|ft|featuring)\b.*$', ' ', norm, flags=re.IGNORECASE)

        # Replace non-alphanumeric with spaces and lowercase
        norm = re.sub(r'[^a-z0-9\s]', ' ', norm.lower())
        words = norm.split()

        # Filter out stop words and single characters (unless digit)
        tokens = {
            w for w in words
            if (len(w) > 1 or w.isdigit()) and w not in STOP_WORDS
        }

        # Fallback if filtering removed everything (e.g., song named "The" or "1")
        if not tokens and words:
            tokens = set(words)

        return tokens

    @staticmethod
    def _overlap_ratio(set_a: Set[str], set_b: Set[str]) -> float:
        """Calculate overlap ratio (Sørensen–Dice coefficient variant)."""
        if not set_a or not set_b:
            return 0.0
        intersection = set_a.intersection(set_b)
        return len(intersection) / min(len(set_a), len(set_b))

    def scan_folder(
        self,
        folder_path: str,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> List[LocalAudioFile]:
        """
        Recursively scan folder for audio files and extract metadata/tokens.
        """
        local_files: List[LocalAudioFile] = []
        folder_path = os.path.abspath(os.path.expanduser(folder_path))

        if not os.path.exists(folder_path):
            logger.warning("Folder does not exist: %s", folder_path)
            return local_files

        # First pass: collect all audio file paths
        all_paths: List[str] = []
        for root, _, files in os.walk(folder_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in AUDIO_EXTENSIONS:
                    all_paths.append(os.path.join(root, f))

        total_files = len(all_paths)
        logger.info("Found %d audio files in %s", total_files, folder_path)

        if progress_cb:
            progress_cb(f"Scanning {total_files} local audio files...", 10.0)

        for idx, filepath in enumerate(all_paths):
            if progress_cb and idx % 25 == 0 and total_files > 0:
                pct = 10.0 + (idx / total_files) * 40.0
                progress_cb(f"Reading file metadata ({idx}/{total_files})...", pct)

            try:
                rel_path = os.path.relpath(filepath, folder_path)
            except ValueError:
                rel_path = filepath

            filename_clean = Path(filepath).stem
            file_obj = LocalAudioFile(
                file_path=filepath,
                rel_path=rel_path,
                filename_clean=filename_clean,
            )

            # Tokens from path (parent folder name + filename)
            parent_dir = os.path.basename(os.path.dirname(filepath))
            path_str = f"{parent_dir} {filename_clean}"
            file_obj.path_tokens = self._normalize_to_tokens(path_str)

            # Attempt to read ID3 / audio tags via mutagen
            try:
                audio = mutagen.File(filepath, easy=True)
                if audio is not None:
                    file_obj.tag_title = str((audio.get("title") or [""])[0]).strip()
                    file_obj.tag_artist = str((audio.get("artist") or [""])[0]).strip()
                    file_obj.tag_album = str((audio.get("album") or [""])[0]).strip()
                    
                    if hasattr(audio, "info") and audio.info and hasattr(audio.info, "length"):
                        file_obj.duration_s = float(audio.info.length)
            except Exception as e:
                logger.debug("Failed reading tags for %s: %s", filepath, e)

            file_obj.title_tokens = self._normalize_to_tokens(file_obj.tag_title)
            file_obj.artist_tokens = self._normalize_to_tokens(file_obj.tag_artist)

            # Combined token pool for matching
            file_obj.all_tokens = (
                file_obj.path_tokens | file_obj.title_tokens | file_obj.artist_tokens
            )

            local_files.append(file_obj)

        if progress_cb:
            progress_cb(f"Indexed {len(local_files)} local tracks.", 50.0)

        return local_files

    def match_track(
        self, track: TrackInfo, local_files: List[LocalAudioFile]
    ) -> TrackMatchResult:
        """
        Find the best matching local file for a playlist track.
        """
        result = TrackMatchResult(track=track)
        if not local_files:
            return result

        track_title_tokens = self._normalize_to_tokens(track.title)
        track_artist_tokens = self._normalize_to_tokens(track.artist)

        best_score = 0.0
        best_file: Optional[LocalAudioFile] = None
        best_match_type = ""

        for lf in local_files:
            score = 0.0
            match_type = ""

            # 1. Check ID3 Tag Match (if both title and artist tags exist on the file)
            if lf.title_tokens and lf.artist_tokens and track_title_tokens and track_artist_tokens:
                title_sim = self._overlap_ratio(track_title_tokens, lf.title_tokens)
                artist_sim = self._overlap_ratio(track_artist_tokens, lf.artist_tokens)

                if title_sim >= 0.75 and artist_sim >= 0.5:
                    score = 0.6 * title_sim + 0.4 * artist_sim
                    match_type = "ID3 Tags"

            # 2. Check Filename & Path Match (if tag match wasn't strong enough)
            if score < 0.75 and track_title_tokens and track_artist_tokens:
                title_in_path = self._overlap_ratio(track_title_tokens, lf.all_tokens)
                artist_in_path = self._overlap_ratio(track_artist_tokens, lf.all_tokens)

                if title_in_path >= 0.8 and artist_in_path >= 0.5:
                    path_score = 0.6 * title_in_path + 0.4 * artist_in_path
                    if path_score > score:
                        score = path_score
                        match_type = "Filename / Path"

            # 3. Check Exact String Containment (for simple filenames without clean tokenization)
            if score < 0.75:
                clean_t = self._normalize_to_tokens(track.title)
                clean_a = self._normalize_to_tokens(track.artist)
                if clean_t and clean_a and clean_t.issubset(lf.all_tokens) and clean_a.intersection(lf.all_tokens):
                    score = 0.78
                    match_type = "Filename Containment"

            # Apply duration modifier if both durations are known
            if score >= 0.70 and track.duration_s and lf.duration_s:
                diff = abs(track.duration_s - lf.duration_s)
                if diff <= 4.0:
                    score += 0.05  # Slight boost for exact duration
                elif diff > 15.0:
                    score -= 0.15  # Penalty for significant duration mismatch

            if score > best_score:
                best_score = score
                best_file = lf
                best_match_type = match_type

        # Consider it existing if score >= 0.75
        if best_score >= 0.75 and best_file is not None:
            result.exists = True
            result.matched_file_path = best_file.file_path
            result.matched_rel_path = best_file.rel_path
            result.matched_by = best_match_type
            result.similarity_score = round(best_score, 2)
            result.matched_duration_s = best_file.duration_s

        return result

    def scan_and_compare(
        self,
        url: str,
        folder_path: str,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> List[TrackMatchResult]:
        """
        Scrape playlist from URL and compare all tracks against local folder.
        """
        if progress_cb:
            progress_cb("Scraping playlist / track metadata from URL...", 2.0)

        tracks: List[TrackInfo] = []
        try:
            tracks = scrape_playlist(url)
        except ValueError:
            # Fallback: maybe it's a single track URL rather than a playlist/album
            logger.info("URL not recognized as collection, trying single track scrape: %s", url)
            try:
                single_track = scrape_metadata(url)
                tracks = [single_track]
            except Exception as e:
                raise ValueError(f"Could not scrape tracks from URL: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to scrape URL: {e}") from e

        if not tracks:
            raise ValueError("No tracks could be found at the provided URL.")

        logger.info("Scraped %d tracks from %s", len(tracks), url)
        if progress_cb:
            progress_cb(f"Scraped {len(tracks)} tracks. Indexing local library...", 10.0)

        # Scan local folder
        local_files = self.scan_folder(folder_path, progress_cb=progress_cb)

        # Match tracks
        results: List[TrackMatchResult] = []
        total_tracks = len(tracks)

        for idx, track in enumerate(tracks):
            if progress_cb and idx % 5 == 0 and total_tracks > 0:
                pct = 50.0 + (idx / total_tracks) * 50.0
                progress_cb(f"Comparing tracks ({idx + 1}/{total_tracks})...", pct)

            match_res = self.match_track(track, local_files)
            results.append(match_res)

        if progress_cb:
            progress_cb("Comparison complete!", 100.0)

        return results
