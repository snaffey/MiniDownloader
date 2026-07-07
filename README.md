# MiniDownloader

A universal music downloader with a modern dark/light GUI. Takes track, album, or playlist links from major streaming services, scrapes track metadata without requiring API keys, downloads audio via YouTube/YT Music, and automatically embeds ID3 tags and high-resolution cover art.

## Features & Technical Mechanics

- **Multi-Platform Metadata Scraping**: Extracts track metadata without requiring API keys or user authentication:
  - **Spotify**: Uses public oEmbed API endpoints.
  - **Deezer**: Uses unauthenticated public REST APIs.
  - **Apple Music, Tidal, Amazon Music, SoundCloud**: Parses OpenGraph and HTML meta tags via lightweight DOM extraction.
- **Advanced Audio Extraction**:
  - Uses `yt-dlp` and `ytmusicapi` with configurable output formats (**FLAC**, **MP3**, **M4A/ALAC**) and concurrent fragment downloading (`concurrent_fragments: 4`).
  - **Anti-Rate-Limiting**: Configures request sleep intervals to avoid YouTube HTTP 429 (Too Many Requests) errors.
  - **Client Cycling & Challenge Solver**: Defaults to robust YouTube player clients (`android`, `ios`, `web`, `web_music`) and enables remote EJS challenge solvers (`remote_components: ejs:github`) for YouTube signature decryption to prevent HTTP 403 Forbidden errors.
- **Automated ID3v2 Tagging**:
  - Uses `mutagen` and `Pillow` to convert scraped artwork to standard JPEG formats and embed high-resolution `APIC` (cover art), title, artist, album, and duration frames directly into the audio file.
- **DJ & Rekordbox Integration**: Dedicated playlist checking engine that scans local folders to prevent downloading duplicates and audits existing DJ libraries.
- **Automation & GUI**:
  - **CustomTkinter UI**: Customizable appearance modes (dark/light) with UI scaling and high-contrast support.
  - **Smart Folders**: Automatically structures downloaded files by source platform, publication date (`%Y/%m`), or audio format.
  - **Background Monitoring**: Optional clipboard link monitoring, folder watch polling (`watch_folder_enabled`), and cron-style scheduled downloads.
  - **System Integration**: System tray support (`pystray`) for background operation and native desktop notifications (`plyer`).

## DJ Features & Duplicate Prevention (Rekordbox / Local Library Checker)

For DJs preparing sets in **Rekordbox**, **Serato**, **Traktor**, or **Engine DJ**, importing new streaming playlists often leads to duplicate files—cluttering hard drives, wasting storage, and polluting software libraries. MiniDownloader includes a built-in **Rekordbox & Playlist Library Checker** designed specifically to solve this.

### The Playlist Checker Workflow
1. **Local Library Scanning**: Select any local directory (your Rekordbox library folder, external USB drive, or master music archive). The engine recursively indexes all supported audio files (`.mp3`, `.flac`, `.wav`, `.m4a`, `.aac`, `.aiff`, `.ogg`, etc.).
2. **Intelligent Token Normalization**: To compare clean metadata against messy filenames, the checker strips standard music and DJ qualifiers (e.g., `(Official Video)`, `(Radio Edit)`, `(Remastered)`, `[Live]`, `[Deluxe]`, `[Acoustic]`) and removes trailing `feat.` / `ft.` credits and stop words (`vs`, `pres`, `dj`, `mc`).
3. **4-Stage Fuzzy Matching Algorithm**:
   - **Stage 1 (ID3v2 Metadata Overlap)**: Calculates a Sørensen–Dice similarity coefficient on embedded Title and Artist tags (`0.6 * title_sim + 0.4 * artist_sim`).
   - **Stage 2 (Directory & Filename Analysis)**: When tags are missing or stripped, it evaluates directory names and file paths against combined token pools.
   - **Stage 3 (Exact Substring Containment)**: Fallback check for unformatted filenames containing the title and artist string.
   - **Stage 4 (Duration Precision Verification)**: Cross-references audio duration against playlist metadata (precision within ±4 seconds boosts confidence, while >15 second mismatches penalize different mixes or live cuts).
4. **Zero-Duplicate Queue & CSV Reporting**:
   - Categorizes every playlist track into **✅ In Rekordbox** (showing the existing local file path and match reason) or **❌ Missing**.
   - **1-Click Missing Download**: Click **⬇️ Download All Missing Tracks to Queue** to send *only the tracks you don't already own* directly to `yt-dlp`.
   - **Audit Reports**: Click **📋 Export Report (CSV)** to generate a complete synchronization spreadsheet for your DJ records.

## Prerequisites

- **Python**: 3.10 or higher.
- **ffmpeg**: Required for audio conversion and muxing. Must be installed and accessible in system PATH:
  - **Windows**: `winget install ffmpeg`
  - **macOS**: `brew install ffmpeg`
  - **Linux**: `sudo apt install ffmpeg`

## Quick Start

1. **Clone or enter the repository**:
   ```bash
   cd MiniDownloader
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the application**:
   ```bash
   python main.py
   ```

## Advanced Cookie Management (Bypassing YouTube Restrictions)

YouTube frequently restricts access to age-gated tracks, members-only releases, or flags frequent requests with HTTP 403/429 errors. Providing authentication cookies allows MiniDownloader to bypass these restrictions.

### Method 1: Automatic Browser Extraction (One-Click)
In MiniDownloader, go to **Settings > YouTube** and click **Auto Setup**, or manually select your browser from the dropdown (`brave`, `chrome`, `edge`, `firefox`, `vivaldi`, `opera`, `chromium`).
- **Important**: Close all running browser windows before running extraction so `yt-dlp` can access the browser's SQLite cookie database without file lock errors.
- *Note on Windows Chromium*: Windows DPAPI encryption can sometimes block automatic Chromium cookie extraction. If this happens, use Firefox or fall back to Method 2.

### Method 2: Manually Exporting `cookies.txt` (Recommended)
If automatic extraction fails or you want an isolated authentication file without browser locking issues, export a Netscape format `cookies.txt` file manually:

1. **Install a Cookie Export Extension** in your browser:
   - **Chrome / Edge / Brave / Vivaldi**: Install [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/ccfejmblifdcfgnocgbbkoaeoelddfed).
   - **Firefox**: Install [Export Cookies](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/).
2. **Log into YouTube**:
   - Open [youtube.com](https://www.youtube.com) in your browser and ensure you are logged into your account.
3. **Export the Cookies**:
   - Click the extension icon in your browser toolbar while on `youtube.com`.
   - Click **Export** to download the `cookies.txt` file (must be in **Netscape HTTP Cookie File** format).
4. **Configure in MiniDownloader**:
   - Open MiniDownloader and navigate to **Settings > YouTube**.
   - Under **Cookies file**, click **Browse** and select your saved `cookies.txt` file (or save it directly as `cookies.txt` in the project root directory).
   - Click **Test** to verify authentication, then click **Save**.

## Project Structure

```text
MiniDownloader/
├── main.py                # Application entry point and ffmpeg validation
├── requirements.txt       # Project dependencies
├── cookies.txt            # Optional Netscape cookie file for authentication
└── src/
    ├── core/              # Core backend logic
    │   ├── downloader.py  # Audio downloading and yt-dlp execution engine
    │   ├── scraper.py     # Multi-platform DOM/oEmbed metadata scraper
    │   ├── searcher.py    # YouTube / YT Music audio matching
    │   ├── tagger.py      # ID3v2 tagging and artwork embedding
    │   ├── checker.py     # Rekordbox 4-stage fuzzy matching engine
    │   ├── yt_dlp_config.py # Anti-rate-limit, EJS solver, and cookie rules
    │   ├── config.py      # App configuration persistence
    │   └── models.py      # Data dataclasses and enums
    ├── ui/                # Graphical user interface (CustomTkinter)
    │   ├── app.py         # Main application window and tabs
    │   ├── settings.py    # Configuration, cookie setup, and preferences UI
    │   ├── history.py     # Download history viewer
    │   └── checker.py     # Rekordbox & playlist validation UI
    └── utils/             # Helper utilities
        ├── constants.py   # Regex URL patterns and platform identification
        ├── paths.py       # OS-specific directory resolvers
        └── sanitizer.py   # Filename string cleanup
```

## Configuration & Storage

By default, downloaded tracks are saved to `~/Music/MiniDownloader`. App settings (`config.json`), download history (`history.json`), and download queues (`queue.json`) are persisted automatically in:
- **Windows**: `%APPDATA%/MiniDownloader/`
- **macOS / Linux**: `~/.config/MiniDownloader/`

<!-- ponytail: omitted standard enterprise boilerplate (TOC, Code of Conduct, verbose contributing guidelines) in favor of direct, high-signal technical documentation -->
