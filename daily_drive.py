#!/usr/bin/env python3
"""
My Daily Drive — Spotify Playlist Builder
==========================================
Automatically creates a personalised "My Daily Drive" playlist each morning,
mixing Australian news podcast episodes with music tracks from your library.

How it works:
  1. Connects to your Spotify account using saved login credentials
  2. Fetches the latest episode from each of your priority news podcasts
     (ABC News Daily, SBS News Headlines, The Quicky) — always in that order
  3. Checks your other followed podcasts for any episode released today
  4. Grabs a random selection of songs from your liked songs library
     (starts at a different position each day so you always hear different songs)
  5. Grabs a selection from your personal top tracks (recent + all-time)
  6. Interleaves the podcast episodes and music tracks together
     (e.g. 3 songs → episode → 3 songs → episode → ...)
  7. Creates or overwrites a playlist called "My Daily Drive" in your account

Run manually:  python3 daily_drive.py
Scheduled:     runs automatically at 5:00 AM daily via cron
Log file:      daily_drive.log (in this folder — check here if something goes wrong)
"""

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# Edit the values in this section to customise your playlist.
# Everything else in the file can be left as-is.
# ══════════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Priority podcasts
# These shows are ALWAYS included, ALWAYS at the front of the playlist,
# in the order listed below — regardless of when their episode was released.
#
# To find a show's Spotify ID:
#   1. Open the show in the Spotify app
#   2. Click the three-dot menu → Share → Copy link to show
#   3. The link looks like: https://open.spotify.com/show/1D4A4NKKF0axPvAS7h31Lu
#   4. The ID is the long string at the end (after "/show/")
#
# To add a new show: paste its ID as a new line inside the list below.
# To remove a show: delete its line.
# To reorder:       move the lines around — top of the list = first in playlist.
# ---------------------------------------------------------------------------
PRIORITY_PODCAST_IDS = [
    "1D4A4NKKF0axPvAS7h31Lu",  # ABC News Daily       — always first
    "0jg3AfXsIV2WBvw4oGgFFW",  # SBS News Headlines   — always second
    "4omeoOVsGWXhhFObFWGTvT",  # The Quicky           — always third
]

# Friendly display names for each priority podcast.
# These are only used in log messages so you can see what's happening.
# Keep this in sync with PRIORITY_PODCAST_IDS above.
PRIORITY_PODCAST_NAMES = {
    "1D4A4NKKF0axPvAS7h31Lu": "ABC News Daily",
    "0jg3AfXsIV2WBvw4oGgFFW": "SBS News Headlines",
    "4omeoOVsGWXhhFObFWGTvT": "The Quicky",
}

# ---------------------------------------------------------------------------
# Other followed podcasts
# If True, the script also checks ALL other podcasts you follow on Spotify
# and adds any episode that was released TODAY (excluding the priority shows
# above, which are always included separately).
# Set to False if you only want the priority podcasts above.
# ---------------------------------------------------------------------------
INCLUDE_FOLLOWED_PODCASTS = True

# How many of your followed podcasts to scan each morning.
# Higher = more thorough but takes longer. 15 is a good balance.
MAX_FOLLOWED_PODCASTS = 15

# ---------------------------------------------------------------------------
# Music tracks
# ---------------------------------------------------------------------------

# Total number of music tracks to include in the playlist each day.
MUSIC_TRACK_COUNT = 50

# How to split the music between your liked songs and your top tracks.
# LIKED_SONGS_PERCENT = songs from your saved/liked songs library
# ARTIST_TRACKS_PERCENT = songs from your personal Spotify top tracks
# These two numbers MUST add up to 100.
LIKED_SONGS_PERCENT = 50
ARTIST_TRACKS_PERCENT = 50

# ---------------------------------------------------------------------------
# Playlist layout
# ---------------------------------------------------------------------------

# The name of the Spotify playlist to create (or overwrite) each day.
# If a playlist with this exact name already exists in your account,
# its contents will be replaced. If not, a new one will be created.
PLAYLIST_NAME = "My Daily Drive"

# How many music tracks to play between each podcast episode.
# For example, 3 means: song, song, song, episode, song, song, song, episode ...
MUSIC_TRACKS_BETWEEN_EPISODES = 3


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS
# These lines load the Python libraries the script needs.
# They are installed automatically when you run: pip install -r requirements.txt
# ══════════════════════════════════════════════════════════════════════════════

import os           # Reads environment variables (SPOTIPY_CLIENT_ID etc.)
import sys          # Lets us exit the script early if something goes wrong
import random       # Used to shuffle songs and pick random starting positions
import logging      # Writes timestamped log messages to the console / log file
from datetime import datetime  # Used to get today's date and format timestamps

import spotipy                      # The main Spotify API library
from spotipy.oauth2 import SpotifyOAuth  # Handles the Spotify login / token flow
from dotenv import load_dotenv      # Reads our credentials from the .env file


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# Configures how log messages look. Each message gets a timestamp and
# a level label (INFO, WARNING, ERROR).
#
# When run manually:   messages print to the Terminal window
# When run via cron:   messages are written to daily_drive.log
#
# Example log line:
#   2026-06-28 07:00:01  INFO      Authenticated as: Jeffrey Mahoney
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,                            # Show INFO and above (not DEBUG)
    format="%(asctime)s  %(levelname)-8s  %(message)s",  # Timestamp + level + message
    datefmt="%Y-%m-%d %H:%M:%S",                  # e.g. 2026-06-28 07:00:01
)
log = logging.getLogger(__name__)  # Creates a logger named after this file


# ══════════════════════════════════════════════════════════════════════════════
# LOAD CREDENTIALS
# The script reads your Spotify app credentials from environment variables.
# These are set in the .env file in this folder (never committed to GitHub).
#
# Required variables:
#   SPOTIPY_CLIENT_ID      — from your Spotify Developer Dashboard
#   SPOTIPY_CLIENT_SECRET  — from your Spotify Developer Dashboard
#   SPOTIPY_REDIRECT_URI   — must be http://127.0.0.1:8888/callback
#
# See README.md → Step 3 for setup instructions.
# ══════════════════════════════════════════════════════════════════════════════

# load_dotenv() reads the .env file and sets its values as environment variables.
# It's safe to call even if no .env file exists — it just does nothing.
load_dotenv()

# Check that all three required credentials are present before going any further.
# If any are missing, print a clear error message and exit.
REQUIRED_ENV_VARS = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"]
missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
if missing:
    log.error(
        "Missing required environment variables: %s\n"
        "Copy .env.example to .env and fill in your Spotify credentials.",
        ", ".join(missing),
    )
    sys.exit(1)  # Stop the script — it can't do anything without credentials


# ══════════════════════════════════════════════════════════════════════════════
# SPOTIFY PERMISSION SCOPES
# When you log in for the first time, Spotify asks which parts of your account
# the app is allowed to access. Each "scope" below grants one specific permission.
# If you add a new scope, delete the .cache file to trigger a fresh login.
# ══════════════════════════════════════════════════════════════════════════════

SCOPES = " ".join([
    "user-library-read",     # Read your saved/liked songs library
    "user-follow-read",      # Read the podcasts and artists you follow
    "user-top-read",         # Read your personal top tracks (used for music selection)
    "playlist-read-private", # Read your existing playlists (to find "My Daily Drive")
    "playlist-modify-public",  # Create or edit public playlists
    "playlist-modify-private", # Create or edit private playlists
])


# ══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════

def authenticate() -> spotipy.Spotify:
    """
    Log in to Spotify and return an authenticated client object.

    How it works:
    - On the FIRST run: opens a browser window so you can log in to Spotify
      and grant the app permission. After you approve, the token is saved to
      a file called .cache in this folder.
    - On SUBSEQUENT runs (including cron): reads the token from .cache and
      refreshes it automatically. No browser needed.

    If authentication fails, the script prints an error message and exits.
    """
    log.info("Authenticating with Spotify …")
    try:
        # SpotifyOAuth manages the entire login flow and token refresh cycle.
        auth_manager = SpotifyOAuth(
            scope=SCOPES,
            # Store the auth token next to this script file
            cache_path=os.path.join(os.path.dirname(__file__), ".cache"),
            open_browser=True,  # Automatically open the browser on first login
        )

        # Create the Spotify client using the auth manager above
        sp = spotipy.Spotify(auth_manager=auth_manager)

        # Make a test API call to confirm the token is working
        user = sp.current_user()
        log.info("Authenticated as: %s (%s)", user["display_name"], user["id"])
        return sp

    except Exception as exc:
        # Catch any error during auth and print a helpful message before exiting
        log.error("Authentication failed: %s", exc)
        log.error(
            "Check that SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and "
            "SPOTIPY_REDIRECT_URI are set correctly in your .env file, and that "
            "the redirect URI is registered in your Spotify Developer Dashboard."
        )
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# PODCAST HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_latest_episode(sp: spotipy.Spotify, show_id: str, show_name: str = "") -> dict | None:
    """
    Fetch and return the single most recent episode of a podcast.

    Parameters:
        sp        — the authenticated Spotify client
        show_id   — the Spotify show ID (the alphanumeric string in the show URL)
        show_name — a human-readable label used only for log messages

    Returns:
        A dictionary containing episode details (name, URI, release date, etc.),
        or None if the episode could not be fetched.

    The 'market="AU"' parameter tells Spotify to return content available
    in Australia. Remove or change this if you're in a different country.
    """
    label = show_name or show_id  # Fall back to the ID if no name was provided

    try:
        # limit=1 means "give me only the most recent episode"
        results = sp.show_episodes(show_id, limit=1, market="AU")
        episodes = results.get("items", [])

        if not episodes:
            log.warning("No episodes found for: %s", label)
            return None

        episode = episodes[0]  # The first (and only) result is the latest episode
        log.info('Latest episode of %s: "%s"', label, episode["name"])
        return episode

    except spotipy.SpotifyException as exc:
        # This catches API errors (e.g. wrong show ID, network timeout)
        log.warning("Could not fetch episodes for %s: %s", label, exc)
        return None


def released_today(episode: dict) -> bool:
    """
    Return True if a podcast episode was published today.

    Spotify stores release dates as simple "YYYY-MM-DD" strings (e.g. "2026-06-28").
    We compare that against today's local date to decide if the episode is new.

    This is used when scanning followed podcasts — we only add those episodes
    if they were released today. Priority podcasts are always added regardless.
    """
    release_date = episode.get("release_date", "")       # e.g. "2026-06-28"
    today_str = datetime.now().strftime("%Y-%m-%d")       # e.g. "2026-06-28"
    return release_date == today_str


def get_followed_podcast_episodes(sp: spotipy.Spotify) -> list[dict]:
    """
    Scan the user's followed podcasts and return any episodes released today.

    This function handles the "bonus" podcasts — the ones beyond the fixed
    priority list. It only adds an episode if:
      - The show is in your Spotify saved shows list
      - The show is NOT already in PRIORITY_PODCAST_IDS (those are handled separately)
      - The show released a new episode TODAY

    The scan stops after MAX_FOLLOWED_PODCASTS shows to keep things fast.

    Returns a list of episode dictionaries (may be empty if nothing new today).
    """
    log.info("Checking followed podcasts for new episodes today …")
    today_episodes: list[dict] = []

    # 'offset' tracks our position in the paginated list of followed shows.
    # Spotify returns shows in pages of up to 50; we step through each page.
    offset = 0

    # 'checked' counts how many shows we've looked at so far.
    # We stop when we reach MAX_FOLLOWED_PODCASTS.
    checked = 0

    while checked < MAX_FOLLOWED_PODCASTS:
        try:
            # Request one page of followed/saved shows from Spotify
            # limit=50 means "give me up to 50 shows per page"
            results = sp.current_user_saved_shows(limit=50, offset=offset)
        except spotipy.SpotifyException as exc:
            log.warning("Could not fetch followed shows: %s", exc)
            break  # Stop trying if the API call fails

        items = results.get("items", [])
        if not items:
            break  # No more shows — we've reached the end of the list

        # Loop through each show in this page of results
        for item in items:
            if checked >= MAX_FOLLOWED_PODCASTS:
                break  # We've checked enough shows for today

            # Each item from the API has a nested "show" object containing the details
            show = item.get("show", item)
            show_id = show.get("id")
            show_name = show.get("name", show_id)

            # Skip priority podcasts — they are fetched separately in main()
            # and always appear at the front of the playlist
            if show_id in PRIORITY_PODCAST_IDS:
                checked += 1
                continue  # Move on to the next show without fetching an episode

            # Check if this show has a new episode out today
            episode = get_latest_episode(sp, show_id, show_name)
            if episode and released_today(episode):
                log.info('  -> New today from %s: "%s"', show_name, episode["name"])
                today_episodes.append(episode)

            checked += 1  # Count this show as checked

        # Advance to the next page of results
        offset += len(items)
        if not results.get("next"):
            break  # "next" is None when we've reached the last page

    log.info("Found %d new episode(s) from followed podcasts today.", len(today_episodes))
    return today_episodes


# ══════════════════════════════════════════════════════════════════════════════
# MUSIC TRACK HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_liked_songs(sp: spotipy.Spotify, count: int) -> list[str]:
    """
    Fetch a random selection of track URIs from the user's liked/saved songs.

    The key to keeping the playlist fresh is the RANDOM STARTING POSITION:
    - We first ask Spotify how many liked songs you have in total (e.g. 532)
    - Then we pick a random position to start from (e.g. position 210)
    - We fetch songs starting from that position
    - This means every day we pull from a DIFFERENT part of your library

    Without this, we'd always get the same 200 most-recently-liked songs.

    Parameters:
        sp    — the authenticated Spotify client
        count — how many track URIs to return

    Returns a shuffled list of Spotify track URIs (e.g. "spotify:track:abc123").
    """
    log.info("Fetching liked songs …")

    # We fetch 4× as many songs as we need, then pick randomly from that pool.
    # This gives a better shuffle. Cap at 200 to avoid too many API calls.
    pool_size = min(count * 4, 200)

    # Step 1: Find out how many liked songs the user has in total.
    # We request just 1 song — we only care about the "total" number in the response.
    try:
        total = sp.current_user_saved_tracks(limit=1).get("total", 0)
    except spotipy.SpotifyException as exc:
        log.warning("Could not determine liked-songs library size: %s", exc)
        total = 0  # If the call fails, start from position 0 as a fallback

    # Step 2: Choose a random starting position within the library.
    # We subtract pool_size so we always have enough songs to fetch from that point.
    # Example: 532 total songs, pool_size=100 → random start between 0 and 432
    if total > pool_size:
        start_offset = random.randint(0, total - pool_size)
    else:
        start_offset = 0  # Library is small — start from the beginning

    log.info("Liked songs library: %d tracks — starting from position %d.", total, start_offset)

    # Step 3: Fetch songs starting from the random position.
    uris: list[str] = []
    offset = start_offset

    while len(uris) < pool_size:
        try:
            # Fetch up to 50 songs at a time (Spotify API limit per request)
            results = sp.current_user_saved_tracks(limit=50, offset=offset)
        except spotipy.SpotifyException as exc:
            log.warning("Could not fetch liked songs: %s", exc)
            break

        items = results.get("items", [])
        if not items:
            break  # No songs returned — stop fetching

        # Extract the Spotify URI from each song
        # A URI looks like: "spotify:track:4uLU6hMCjMI75M1A2tKUQC"
        for item in items:
            track = item.get("track")
            if track and track.get("uri"):
                uris.append(track["uri"])

        # Move to the next page of results
        offset += len(items)
        if not results.get("next"):
            break  # We've reached the end of the library — stop

    log.info("Fetched %d liked songs (pool).", len(uris))

    # Step 4: Shuffle the pool, then return only as many as we need
    random.shuffle(uris)
    return uris[:count]


def get_artist_tracks(sp: spotipy.Spotify, count: int) -> list[str]:
    """
    Fetch a selection of track URIs from the user's personal top tracks.

    Spotify tracks which songs you listen to most. This function pulls from
    three different time windows to get a varied mix:
      - short_term:  songs you've listened to a lot in the past ~4 weeks
      - medium_term: songs you've listened to a lot in the past ~6 months
      - long_term:   your all-time most-played songs

    Note: We originally used "artist top tracks" (most popular songs by artists
    you follow), but Spotify blocks that endpoint for new developer apps.
    This approach — using YOUR personal listening history — is actually better
    because it's personalised to your taste.

    Parameters:
        sp    — the authenticated Spotify client
        count — how many track URIs to return

    Returns a shuffled, deduplicated list of Spotify track URIs.
    """
    log.info("Fetching your personal top tracks …")
    uris: list[str] = []

    # Fetch up to 50 tracks from each time window
    # Stop early if we already have enough for a good shuffle pool (count × 3)
    for time_range in ("short_term", "medium_term", "long_term"):
        if len(uris) >= count * 3:
            break  # We have a big enough pool — no need to fetch more
        try:
            results = sp.current_user_top_tracks(limit=50, time_range=time_range)
            for track in results.get("items", []):
                if track.get("uri"):
                    uris.append(track["uri"])
        except spotipy.SpotifyException as exc:
            log.warning("Could not fetch top tracks (%s): %s", time_range, exc)

    if not uris:
        log.warning("No personal top tracks found — skipping this music slot.")
        return []

    log.info("Collected %d personal top tracks (pool).", len(uris))

    # Remove duplicates — the same song can appear across multiple time windows.
    # We use a 'seen' set to track which URIs we've already added.
    seen: set[str] = set()
    unique = [u for u in uris if not (u in seen or seen.add(u))]  # type: ignore[func-returns-value]

    # Shuffle and return the requested number of tracks
    random.shuffle(unique)
    return unique[:count]


def build_music_tracks(sp: spotipy.Spotify) -> list[str]:
    """
    Assemble the full list of music tracks for today's playlist.

    Splits the total track count between liked songs and top tracks according
    to the LIKED_SONGS_PERCENT / ARTIST_TRACKS_PERCENT ratio in the config,
    then combines and shuffles them together.

    Example with defaults (50/50, 50 total tracks):
      - 25 tracks from liked songs (random position in your library)
      - 25 tracks from your personal top tracks
      - All 50 shuffled together

    Returns a shuffled list of Spotify track URIs.
    """
    # Safety check: the two percentages must always add up to 100
    if LIKED_SONGS_PERCENT + ARTIST_TRACKS_PERCENT != 100:
        log.error(
            "LIKED_SONGS_PERCENT (%d) + ARTIST_TRACKS_PERCENT (%d) must equal 100. "
            "Please fix the configuration at the top of this script.",
            LIKED_SONGS_PERCENT, ARTIST_TRACKS_PERCENT,
        )
        sys.exit(1)

    # Calculate how many tracks to get from each source
    liked_count = round(MUSIC_TRACK_COUNT * LIKED_SONGS_PERCENT / 100)
    artist_count = MUSIC_TRACK_COUNT - liked_count  # Use subtraction to avoid rounding issues

    # Fetch tracks from each source (skip if the percentage is 0)
    liked_uris = get_liked_songs(sp, liked_count) if liked_count > 0 else []
    artist_uris = get_artist_tracks(sp, artist_count) if artist_count > 0 else []

    # Combine both lists and shuffle so liked songs and top tracks are mixed together
    combined = liked_uris + artist_uris
    random.shuffle(combined)

    log.info(
        "Music tracks: %d liked + %d from top tracks = %d total.",
        len(liked_uris), len(artist_uris), len(combined),
    )
    return combined


# ══════════════════════════════════════════════════════════════════════════════
# PLAYLIST BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def interleave(episode_uris: list[str], track_uris: list[str]) -> list[str]:
    """
    Mix podcast episodes and music tracks into one ordered playlist.

    Pattern (with MUSIC_TRACKS_BETWEEN_EPISODES = 3):
      song → song → song → episode → song → song → song → episode → song → ...

    Any music tracks left over after all episodes have been placed are
    appended at the end of the playlist.

    Parameters:
        episode_uris — Spotify URIs for podcast episodes (in priority order)
        track_uris   — Spotify URIs for music tracks (already shuffled)

    Returns a single ordered list of URIs ready to be added to Spotify.
    """
    result: list[str] = []
    music = list(track_uris)    # Make a copy so we don't modify the original list
    episodes = list(episode_uris)

    # Keep going until we've placed all episodes and all music tracks
    while episodes or music:

        # Add a block of N music tracks before each episode
        for _ in range(MUSIC_TRACKS_BETWEEN_EPISODES):
            if music:
                result.append(music.pop(0))  # Take the next song from the front of the list

        # Add the next podcast episode (if any remain)
        if episodes:
            result.append(episodes.pop(0))  # Take the next episode from the front of the list

    return result


def find_existing_playlist(sp: spotipy.Spotify, user_id: str) -> str | None:
    """
    Look through the user's playlists for one named PLAYLIST_NAME that they own.

    Returns the playlist ID (a string) if found, or None if it doesn't exist yet.

    We check that the playlist is owned by this user (not just shared with them)
    to avoid accidentally overwriting a playlist with the same name made by someone else.
    """
    offset = 0  # Start at the first page of playlists

    while True:
        # Fetch a page of playlists (up to 50 at a time)
        results = sp.current_user_playlists(limit=50, offset=offset)
        items = results.get("items", [])

        if not items:
            return None  # No more playlists to check — not found

        # Check each playlist on this page
        for pl in items:
            # Match on name AND owner to be safe
            if pl.get("name") == PLAYLIST_NAME and pl.get("owner", {}).get("id") == user_id:
                return pl["id"]  # Found it — return the playlist ID

        # If there are more pages, move to the next one
        if not results.get("next"):
            return None  # Last page reached and no match found
        offset += len(items)


def create_or_overwrite_playlist(
    sp: spotipy.Spotify,
    user_id: str,
    uris: list[str],
) -> str:
    """
    Create "My Daily Drive" if it doesn't exist, then fill it with today's content.
    If the playlist already exists (from a previous day), clear it and refill it.

    Spotify's API only allows adding 100 items per request, so we split large
    playlists into batches of 100 automatically.

    Parameters:
        sp      — the authenticated Spotify client
        user_id — the Spotify user ID of the authenticated user
        uris    — the ordered list of track/episode URIs to add

    Returns the URL of the finished playlist (e.g. https://open.spotify.com/playlist/...)
    """
    # Check if the playlist already exists from a previous run
    playlist_id = find_existing_playlist(sp, user_id)

    if playlist_id:
        # Playlist exists — clear its current contents so we can refill it
        log.info('Found existing playlist "%s" — clearing it.', PLAYLIST_NAME)
        sp.playlist_replace_items(playlist_id, [])  # Replace with empty list = clear
    else:
        # Playlist doesn't exist yet — create a new one
        log.info('Creating new playlist "%s" …', PLAYLIST_NAME)

        # We use the /me/playlists API endpoint here instead of /users/{id}/playlists.
        # Both do the same thing, but /me/playlists works for new Spotify developer apps
        # that haven't gone through extended quota approval.
        pl = sp._post(
            "me/playlists",
            payload={
                "name": PLAYLIST_NAME,
                "public": False,  # Set to True if you want it visible on your profile
                "description": f"Auto-generated by My Daily Drive on {datetime.now().strftime('%d %b %Y')}",
            },
        )
        playlist_id = pl["id"]

    # Add the content to the playlist in batches of 100
    # (Spotify rejects any single request with more than 100 items)
    for i in range(0, len(uris), 100):
        batch = uris[i : i + 100]  # Slice out 100 items at a time
        sp.playlist_add_items(playlist_id, batch)
        log.info("Added items %d–%d to playlist.", i + 1, i + len(batch))

    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    log.info("Playlist ready: %s", playlist_url)
    return playlist_url


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — ties everything together
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Entry point — runs all the steps in order to build today's playlist.

    Steps:
      1. Authenticate with Spotify
      2. Fetch priority podcast episodes (ABC News Daily, SBS News, The Quicky)
      3. Optionally fetch new episodes from other followed podcasts
      4. Fetch music tracks (random liked songs + personal top tracks)
      5. Interleave episodes and music into one ordered list
      6. Create or overwrite the "My Daily Drive" playlist with that content
    """
    log.info("=== My Daily Drive starting — %s ===", datetime.now().strftime("%A %d %b %Y"))

    # ── Step 1: Authenticate ──────────────────────────────────────────────────
    # This reads the cached token from .cache (no browser needed after first run).
    sp = authenticate()
    user_id = sp.current_user()["id"]  # We need the user ID to create/find playlists

    # ── Step 2: Fetch priority podcast episodes ───────────────────────────────
    # These are always included and always in the same order (as configured above).
    # We fetch the latest episode from each show, regardless of when it was released.
    episode_uris: list[str] = []

    for show_id in PRIORITY_PODCAST_IDS:
        show_name = PRIORITY_PODCAST_NAMES.get(show_id, show_id)
        episode = get_latest_episode(sp, show_id, show_name)

        if episode:
            uri = episode.get("uri")
            if uri:
                episode_uris.append(uri)  # Add to our ordered list
        else:
            # Log a warning but keep going — a missing episode won't stop the script
            log.warning(
                "Could not fetch episode for %s — skipping. "
                "Check the show ID in PRIORITY_PODCAST_IDS at the top of this script.",
                show_name,
            )

    # ── Step 3: Fetch today's episodes from other followed podcasts ───────────
    # Only runs if INCLUDE_FOLLOWED_PODCASTS is True.
    # These come AFTER the priority shows in the playlist.
    if INCLUDE_FOLLOWED_PODCASTS:
        followed_episodes = get_followed_podcast_episodes(sp)
        for ep in followed_episodes:
            uri = ep.get("uri")
            if uri:
                episode_uris.append(uri)

    if not episode_uris:
        # This shouldn't happen if your priority shows are set up correctly,
        # but we log a warning just in case
        log.warning("No podcast episodes found today — playlist will be music only.")

    # ── Step 4: Fetch music tracks ────────────────────────────────────────────
    # Random selection from liked songs + personal top tracks, shuffled together.
    track_uris = build_music_tracks(sp)

    # If we have neither episodes nor music, something has gone wrong — exit cleanly
    if not track_uris and not episode_uris:
        log.error(
            "No content found at all (no podcast episodes, no music tracks). "
            "Check your Spotify account has liked songs and that your credentials are correct."
        )
        sys.exit(1)

    # ── Step 5: Interleave episodes and music ─────────────────────────────────
    # Produces an ordered list: music, music, music, episode, music, music, music, episode ...
    ordered_uris = interleave(episode_uris, track_uris)
    log.info(
        "Playlist will contain %d item(s): %d episode(s) + %d track(s).",
        len(ordered_uris), len(episode_uris), len(track_uris),
    )

    # ── Step 6: Create or overwrite the Spotify playlist ─────────────────────
    playlist_url = create_or_overwrite_playlist(sp, user_id, ordered_uris)

    log.info("=== Done! Open your playlist: %s ===", playlist_url)


# ── Script entry point ────────────────────────────────────────────────────────
# This block only runs when the script is executed directly (e.g. python3 daily_drive.py).
# It does NOT run when the file is imported by another Python script.
if __name__ == "__main__":
    main()
