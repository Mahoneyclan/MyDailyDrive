#!/usr/bin/env python3
"""
My Daily Drive — Spotify Playlist Builder
==========================================
Automatically creates a personalised "My Daily Drive" playlist each morning,
mixing Australian news podcast episodes with music tracks from your library
and followed artists.

Run manually:  python3 daily_drive.py
Schedule:      add to cron (see README.md for instructions)
"""

# ── CONFIGURATION ─────────────────────────────────────────────────────────────
# Edit the values below to customise your Daily Drive playlist.

# Spotify show ID for the primary podcast (default: ABC News Daily)
PRIMARY_PODCAST_ID = "1D4A4NKKF0axPvAS7h31Lu"

# Set to True to also include new episodes from other podcasts you follow
INCLUDE_FOLLOWED_PODCASTS = True

# Maximum number of followed podcasts to scan (keeps API calls reasonable)
MAX_FOLLOWED_PODCASTS = 15

# Total number of music tracks to add to the playlist
MUSIC_TRACK_COUNT = 25

# How to split music tracks: liked songs vs. followed-artist tracks.
# Both numbers must add up to 100.
LIKED_SONGS_PERCENT = 50
ARTIST_TRACKS_PERCENT = 50

# Name of the Spotify playlist that will be created or overwritten each day
PLAYLIST_NAME = "My Daily Drive"

# How many music tracks to play between each podcast episode
MUSIC_TRACKS_BETWEEN_EPISODES = 3

# ── IMPORTS ───────────────────────────────────────────────────────────────────

import os           # For reading environment variables
import sys          # For exiting the script on fatal errors
import random       # For shuffling tracks so they don't repeat in the same order
import logging      # For writing informative log messages
from datetime import datetime, timezone  # For checking if an episode was released today

import spotipy                                     # The Spotify API wrapper library
from spotipy.oauth2 import SpotifyOAuth            # Handles OAuth 2.0 login flow
from dotenv import load_dotenv                     # Reads credentials from a .env file

# ── LOGGING SETUP ─────────────────────────────────────────────────────────────
# Writes messages to the console (and to a log file if redirected by cron).

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── LOAD CREDENTIALS ──────────────────────────────────────────────────────────
# Reads SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI
# from environment variables (or from a .env file in the same folder).

load_dotenv()  # Loads a .env file if one exists (safe to call even if it doesn't)

REQUIRED_ENV_VARS = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"]
missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
if missing:
    log.error(
        "Missing required environment variables: %s\n"
        "Copy .env.example to .env and fill in your Spotify credentials.",
        ", ".join(missing),
    )
    sys.exit(1)

# ── SPOTIFY SCOPES ────────────────────────────────────────────────────────────
# Each scope grants permission to a different part of the Spotify API.

SCOPES = " ".join([
    "user-library-read",          # Read your liked/saved songs
    "user-follow-read",           # Read your followed artists and podcasts
    "playlist-read-private",      # Read your existing private playlists
    "playlist-modify-public",     # Create/edit public playlists
    "playlist-modify-private",    # Create/edit private playlists
])

# ── AUTHENTICATION ────────────────────────────────────────────────────────────

def authenticate() -> spotipy.Spotify:
    """
    Authenticate with Spotify using OAuth 2.0.

    The first time you run this script a browser window will open asking you
    to log in and authorise the app. After that, the token is cached in a
    file called .cache so you don't need to log in again.
    """
    log.info("Authenticating with Spotify …")
    try:
        auth_manager = SpotifyOAuth(
            scope=SCOPES,
            # The .cache file is written next to this script
            cache_path=os.path.join(os.path.dirname(__file__), ".cache"),
            open_browser=True,   # Opens the browser automatically on first run
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        # Make a simple API call to confirm the token works
        user = sp.current_user()
        log.info("Authenticated as: %s (%s)", user["display_name"], user["id"])
        return sp
    except Exception as exc:
        log.error("Authentication failed: %s", exc)
        log.error(
            "Check that SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and "
            "SPOTIPY_REDIRECT_URI are set correctly, and that the redirect URI "
            "is registered in your Spotify Developer Dashboard."
        )
        sys.exit(1)

# ── PODCAST HELPERS ───────────────────────────────────────────────────────────

def get_latest_episode(sp: spotipy.Spotify, show_id: str, show_name: str = "") -> dict | None:
    """
    Return the most recent episode of a podcast show, or None on failure.

    sp        — authenticated Spotify client
    show_id   — Spotify show ID (the long string in the show's URL)
    show_name — human-readable name used only for log messages
    """
    label = show_name or show_id
    try:
        results = sp.show_episodes(show_id, limit=1, market="AU")
        episodes = results.get("items", [])
        if not episodes:
            log.warning("No episodes found for: %s", label)
            return None
        episode = episodes[0]
        log.info("Latest episode of %s: "%s"", label, episode["name"])
        return episode
    except spotipy.SpotifyException as exc:
        log.warning("Could not fetch episodes for %s: %s", label, exc)
        return None


def released_today(episode: dict) -> bool:
    """
    Return True if an episode was published today (in the local timezone).

    Spotify stores release dates as "YYYY-MM-DD" strings.
    """
    release_date = episode.get("release_date", "")
    today_str = datetime.now().strftime("%Y-%m-%d")
    return release_date == today_str


def get_followed_podcast_episodes(sp: spotipy.Spotify) -> list[dict]:
    """
    Scan all followed podcasts and return today's new episodes (if any).

    Returns a list of episode objects (may be empty).
    """
    log.info("Checking followed podcasts for new episodes today …")
    today_episodes: list[dict] = []
    after = None          # Cursor for pagination
    checked = 0

    while checked < MAX_FOLLOWED_PODCASTS:
        try:
            # Fetch a page of followed shows (up to 50 per page)
            results = sp.current_user_followed_shows(limit=50, after=after)
        except spotipy.SpotifyException as exc:
            log.warning("Could not fetch followed shows: %s", exc)
            break

        shows = results.get("shows", {})
        items = shows.get("items", [])
        if not items:
            break  # No more shows

        for item in items:
            if checked >= MAX_FOLLOWED_PODCASTS:
                break
            show = item.get("show", item)   # API returns nested structure
            show_id = show.get("id")
            show_name = show.get("name", show_id)

            # Skip the primary podcast — we already handle it separately
            if show_id == PRIMARY_PODCAST_ID:
                checked += 1
                continue

            episode = get_latest_episode(sp, show_id, show_name)
            if episode and released_today(episode):
                log.info("  → New today from %s: "%s"", show_name, episode["name"])
                today_episodes.append(episode)

            checked += 1

        # Move to the next page of results
        after = shows.get("cursors", {}).get("after")
        if not after:
            break  # No more pages

    log.info("Found %d new episode(s) from followed podcasts today.", len(today_episodes))
    return today_episodes

# ── MUSIC TRACK HELPERS ───────────────────────────────────────────────────────

def get_liked_songs(sp: spotipy.Spotify, count: int) -> list[str]:
    """
    Fetch up to `count` track URIs from the user's liked/saved songs.

    Retrieves a larger pool first, then picks randomly so the playlist
    feels fresh each day.
    """
    log.info("Fetching liked songs …")
    pool_size = min(count * 4, 200)   # Fetch 4× what we need, up to 200
    uris: list[str] = []
    offset = 0

    while len(uris) < pool_size:
        try:
            results = sp.current_user_saved_tracks(limit=50, offset=offset)
        except spotipy.SpotifyException as exc:
            log.warning("Could not fetch liked songs: %s", exc)
            break

        items = results.get("items", [])
        if not items:
            break

        for item in items:
            track = item.get("track")
            if track and track.get("uri"):
                uris.append(track["uri"])

        offset += len(items)
        if not results.get("next"):
            break  # No more pages

    log.info("Fetched %d liked songs (pool).", len(uris))
    random.shuffle(uris)
    return uris[:count]


def get_artist_tracks(sp: spotipy.Spotify, count: int) -> list[str]:
    """
    Fetch up to `count` track URIs from the top tracks of followed artists.

    Picks a few artists at random so you get variety each day.
    """
    log.info("Fetching tracks from followed artists …")
    # Collect followed artists
    artist_ids: list[str] = []
    after = None

    while True:
        try:
            results = sp.current_user_followed_artists(limit=50, after=after)
        except spotipy.SpotifyException as exc:
            log.warning("Could not fetch followed artists: %s", exc)
            break

        artists = results.get("artists", {})
        items = artists.get("items", [])
        if not items:
            break

        for artist in items:
            if artist.get("id"):
                artist_ids.append(artist["id"])

        after = artists.get("cursors", {}).get("after")
        if not after:
            break

    if not artist_ids:
        log.warning("No followed artists found — skipping artist tracks.")
        return []

    log.info("You follow %d artists.", len(artist_ids))

    # Randomly sample artists to keep the playlist varied
    sample_size = min(len(artist_ids), count * 2)
    sampled_artists = random.sample(artist_ids, sample_size)

    uris: list[str] = []
    for artist_id in sampled_artists:
        if len(uris) >= count * 3:   # Collect a pool, then trim
            break
        try:
            results = sp.artist_top_tracks(artist_id, country="AU")
            tracks = results.get("tracks", [])
            for track in tracks[:3]:   # Take up to 3 tracks per artist
                if track.get("uri"):
                    uris.append(track["uri"])
        except spotipy.SpotifyException as exc:
            log.warning("Could not fetch tracks for artist %s: %s", artist_id, exc)

    log.info("Collected %d tracks from followed artists (pool).", len(uris))
    random.shuffle(uris)
    return uris[:count]


def build_music_tracks(sp: spotipy.Spotify) -> list[str]:
    """
    Build the final list of music track URIs using the configured
    liked-songs / artist-tracks ratio.
    """
    # Validate ratio (must sum to 100)
    if LIKED_SONGS_PERCENT + ARTIST_TRACKS_PERCENT != 100:
        log.error(
            "LIKED_SONGS_PERCENT (%d) + ARTIST_TRACKS_PERCENT (%d) must equal 100.",
            LIKED_SONGS_PERCENT, ARTIST_TRACKS_PERCENT,
        )
        sys.exit(1)

    liked_count = round(MUSIC_TRACK_COUNT * LIKED_SONGS_PERCENT / 100)
    artist_count = MUSIC_TRACK_COUNT - liked_count

    liked_uris = get_liked_songs(sp, liked_count) if liked_count > 0 else []
    artist_uris = get_artist_tracks(sp, artist_count) if artist_count > 0 else []

    combined = liked_uris + artist_uris
    random.shuffle(combined)   # Mix liked and artist tracks together
    log.info(
        "Music tracks: %d liked + %d from artists = %d total.",
        len(liked_uris), len(artist_uris), len(combined),
    )
    return combined

# ── PLAYLIST BUILDER ──────────────────────────────────────────────────────────

def interleave(episode_uris: list[str], track_uris: list[str]) -> list[str]:
    """
    Interleave podcast episodes and music tracks into one ordered list.

    Pattern: [music × N] → [episode] → [music × N] → [episode] → …
    Any leftover music tracks are appended at the end.

    episode_uris — Spotify URIs for podcast episodes
    track_uris   — Spotify URIs for music tracks
    """
    result: list[str] = []
    music = list(track_uris)    # Work on a copy
    episodes = list(episode_uris)

    while episodes or music:
        # Add a block of music tracks
        for _ in range(MUSIC_TRACKS_BETWEEN_EPISODES):
            if music:
                result.append(music.pop(0))

        # Add one podcast episode
        if episodes:
            result.append(episodes.pop(0))

    return result


def find_existing_playlist(sp: spotipy.Spotify, user_id: str) -> str | None:
    """
    Search the user's playlists for one matching PLAYLIST_NAME.
    Returns the playlist ID if found, otherwise None.
    """
    offset = 0
    while True:
        results = sp.current_user_playlists(limit=50, offset=offset)
        items = results.get("items", [])
        if not items:
            return None

        for pl in items:
            if pl.get("name") == PLAYLIST_NAME and pl.get("owner", {}).get("id") == user_id:
                return pl["id"]

        if not results.get("next"):
            return None
        offset += len(items)


def create_or_overwrite_playlist(
    sp: spotipy.Spotify,
    user_id: str,
    uris: list[str],
) -> str:
    """
    Create the 'My Daily Drive' playlist (or clear it if it already exists),
    then fill it with `uris`. Returns the playlist URL.

    Spotify limits playlist additions to 100 items per call, so we batch
    large lists automatically.
    """
    playlist_id = find_existing_playlist(sp, user_id)

    if playlist_id:
        log.info("Found existing playlist "%s" — clearing it.", PLAYLIST_NAME)
        # Replace all tracks with an empty list to clear the playlist
        sp.playlist_replace_items(playlist_id, [])
    else:
        log.info("Creating new playlist "%s" …", PLAYLIST_NAME)
        pl = sp.user_playlist_create(
            user=user_id,
            name=PLAYLIST_NAME,
            public=False,   # Set to True if you want it visible on your profile
            description=f"Auto-generated by My Daily Drive on {datetime.now().strftime('%d %b %Y')}",
        )
        playlist_id = pl["id"]

    # Add tracks in batches of 100 (Spotify API limit)
    for i in range(0, len(uris), 100):
        batch = uris[i : i + 100]
        sp.playlist_add_items(playlist_id, batch)
        log.info("Added items %d–%d to playlist.", i + 1, i + len(batch))

    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    log.info("Playlist ready: %s", playlist_url)
    return playlist_url

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    log.info("=== My Daily Drive starting — %s ===", datetime.now().strftime("%A %d %b %Y"))

    # 1. Authenticate
    sp = authenticate()
    user_id = sp.current_user()["id"]

    # 2. Fetch podcast episodes
    episode_uris: list[str] = []

    # Primary podcast (ABC News Daily)
    primary_episode = get_latest_episode(sp, PRIMARY_PODCAST_ID, "ABC News Daily")
    if primary_episode:
        uri = primary_episode.get("uri")
        if uri:
            episode_uris.append(uri)
    else:
        log.warning(
            "Could not fetch ABC News Daily episode — continuing without it. "
            "Check the show ID in the CONFIG section at the top of this script."
        )

    # Other followed podcasts (today's new episodes only)
    if INCLUDE_FOLLOWED_PODCASTS:
        followed_episodes = get_followed_podcast_episodes(sp)
        for ep in followed_episodes:
            uri = ep.get("uri")
            if uri:
                episode_uris.append(uri)

    if not episode_uris:
        log.warning("No podcast episodes found today — playlist will be music only.")

    # 3. Fetch music tracks
    track_uris = build_music_tracks(sp)

    if not track_uris and not episode_uris:
        log.error(
            "No content found (no episodes, no music tracks). "
            "Check your Spotify account has liked songs and/or followed artists."
        )
        sys.exit(1)

    # 4. Interleave episodes and tracks
    ordered_uris = interleave(episode_uris, track_uris)
    log.info(
        "Playlist will contain %d item(s): %d episode(s) + %d track(s).",
        len(ordered_uris), len(episode_uris), len(track_uris),
    )

    # 5. Create or update the playlist
    playlist_url = create_or_overwrite_playlist(sp, user_id, ordered_uris)

    log.info("=== Done! Open your playlist: %s ===", playlist_url)


if __name__ == "__main__":
    main()
