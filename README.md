# My Daily Drive

Automatically builds a personalised **My Daily Drive** playlist in your Spotify account each morning, mixing Australian news podcast episodes with music from your library.

Default behaviour:
- Fetches the latest episode from 5 priority Australian news podcasts (always included, always in order); episodes older than 2 days are dropped
- Checks your other followed podcasts for any episode released within the last 2 days (handles timezone lag between Spotify's UTC dates and AEST)
- Pulls 50 tracks — 25 from your liked songs, 25 from your personal top tracks
- Interleaves episodes and music (1 episode → 3 songs → 1 episode → 3 songs → …)
- Creates or overwrites a private playlist called **My Daily Drive**

---

## Prerequisites

- macOS (tested on Mac Mini M1)
- Python 3.11 or later — check with `python3 --version`
- A free [Spotify Developer account](https://developer.spotify.com/)

---

## Step 1 — Create a Spotify Developer App

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in.
2. Click **Create app**.
3. Fill in any **App name** and **App description** (e.g. "My Daily Drive").
4. In the **Redirect URIs** field enter exactly:
   ```
   http://127.0.0.1:8888/callback
   ```
   Click **Add** so it appears in the list, then click **Save**.
5. Open your new app and go to **Settings**. Copy the **Client ID** and **Client Secret** — you will need them in Step 3.

> **Why this URI?** The script runs locally, so we use localhost. The port `8888` is arbitrary; just make sure it matches what you put in `.env`.

---

## Step 2 — Install Python dependencies

Open **Terminal** and run:

```bash
cd /Volumes/GDrive/Github/MyDailyDrive

# Create a virtual environment so dependencies don't affect other projects
python3 -m venv .venv
source .venv/bin/activate

# Install the required libraries
pip install -r requirements.txt
```

---

## Step 3 — Set up your credentials

```bash
# Still inside the MyDailyDrive folder:
cp .env.example .env
open -e .env      # Opens the file in TextEdit
```

Replace the placeholder values with your real credentials:

```
SPOTIPY_CLIENT_ID=abc123...        ← paste your Client ID
SPOTIPY_CLIENT_SECRET=xyz789...    ← paste your Client Secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

Save and close TextEdit.

> **Your `.env` file is listed in `.gitignore`** and will never be committed to GitHub. Never share it.

### Alternative — set environment variables permanently in your shell

If you prefer not to use a `.env` file, add these lines to your `~/.zshrc`:

```bash
export SPOTIPY_CLIENT_ID="your_client_id"
export SPOTIPY_CLIENT_SECRET="your_client_secret"
export SPOTIPY_REDIRECT_URI="http://127.0.0.1:8888/callback"
```

Then run `source ~/.zshrc` to reload.

---

## Step 4 — First run (authorize the app)

```bash
cd /Volumes/GDrive/Github/MyDailyDrive
source .venv/bin/activate
python3 daily_drive.py
```

**What happens on first run:**
1. A browser window opens asking you to log in to Spotify and authorize the app.
2. After clicking **Agree**, your browser is redirected to `http://127.0.0.1:8888/callback?code=…`
3. The page will look blank or show an error — **that's expected**. Copy the full URL from the browser address bar and paste it back into the Terminal when prompted.
4. The script saves a `.cache` token file so future runs skip the browser step.

If everything works you will see log lines ending with:
```
=== Done! Open your playlist: https://open.spotify.com/playlist/... ===
```

---

## Step 5 — Customise the playlist (optional)

Open `daily_drive.py` in any text editor and edit the **CONFIGURATION** block near the top of the file:

| Variable | Default | What it does |
|---|---|---|
| `PRIORITY_PODCAST_IDS` | 5 Australian news shows | Spotify show IDs always included, always first, in order |
| `INCLUDE_FOLLOWED_PODCASTS` | `True` | Also add today's episodes from other followed shows |
| `MAX_FOLLOWED_PODCASTS` | `15` | How many followed shows to check |
| `MUSIC_TRACK_COUNT` | `50` | Total music tracks in the playlist |
| `LIKED_SONGS_PERCENT` | `50` | % of music from your liked songs |
| `ARTIST_TRACKS_PERCENT` | `50` | % of music from your personal top tracks |
| `PLAYLIST_NAME` | `"My Daily Drive"` | Name of the Spotify playlist |
| `MUSIC_TRACKS_BETWEEN_EPISODES` | `3` | Songs between each podcast episode |

### Priority podcasts

The default priority podcasts (in order) are:

1. Squiz Today
2. 7News Just In
3. ABC News Daily
4. SBS News Headlines
5. The Quicky

To add, remove, or reorder them, edit `PRIORITY_PODCAST_IDS` at the top of `daily_drive.py`. See **Finding a Spotify Show ID** below.

---

## Step 6 — Schedule with LaunchAgent (runs automatically every morning)

A LaunchAgent is the recommended way to schedule the script on macOS. Unlike cron, it runs in your user session so network drives (like Google Drive) are guaranteed to be mounted.

### 6a — Create the wrapper script

```bash
mkdir -p ~/.local/bin
```

Create `~/.local/bin/daily_drive_run.sh` with this content:

```bash
#!/bin/bash
# Wait up to 2 minutes for GDrive to mount
for i in $(seq 1 24); do
    if [ -d "/Volumes/GDrive/Github/MyDailyDrive" ]; then
        break
    fi
    sleep 5
done

if [ ! -d "/Volumes/GDrive/Github/MyDailyDrive" ]; then
    echo "$(date): GDrive not mounted after 2 minutes, aborting" >> /tmp/daily_drive_error.log
    exit 1
fi

exec /Volumes/GDrive/Github/MyDailyDrive/.venv/bin/python3 /Volumes/GDrive/Github/MyDailyDrive/daily_drive.py \
    >> /Volumes/GDrive/Github/MyDailyDrive/daily_drive.log 2>&1
```

Make it executable:

```bash
chmod +x ~/.local/bin/daily_drive_run.sh
```

### 6b — Create the LaunchAgent plist

Create `~/Library/LaunchAgents/com.mahoney.dailydrive.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mahoney.dailydrive</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/mahoney/.local/bin/daily_drive_run.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>5</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/daily_drive_launchagent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/daily_drive_error.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

### 6c — Load the LaunchAgent

```bash
launchctl load ~/Library/LaunchAgents/com.mahoney.dailydrive.plist
```

Verify it loaded:

```bash
launchctl list | grep mahoney.dailydrive
```

### 6d — Schedule a wake (if your Mac sleeps overnight)

```bash
sudo pmset repeat wakeorpoweron MTWRFSU 04:55:00
```

This wakes the Mac at 4:55 AM — 5 minutes before the script fires. Verify with:

```bash
pmset -g sched
```

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `Missing required environment variables` | `.env` not set up | Follow Step 3 |
| `Authentication failed` | Wrong credentials or redirect URI | Double-check `.env` and the Spotify Dashboard redirect URI |
| Browser opens but token isn't saved | Copied the wrong URL | Paste the full `http://127.0.0.1:8888/callback?code=…` URL |
| `No episodes found for …` | Show ID changed or show is inactive | Find the new ID in the Spotify app and update `PRIORITY_PODCAST_IDS` |
| Script doesn't run at 5 AM | Mac was asleep | Set a scheduled wake with `pmset` (see Step 6d) |
| GDrive not mounted when script runs | Drive mounted after script fires | The wrapper script waits up to 2 minutes; check `/tmp/daily_drive_error.log` |
| Playlist not visible in Spotify | Created as private | Change `public=True` in `create_or_overwrite_playlist()` in the script |

---

## File structure

```
MyDailyDrive/
├── daily_drive.py      ← Main script
├── requirements.txt    ← Python dependencies
├── .env.example        ← Template for your credentials (safe to commit)
├── .env                ← Your actual credentials (never committed)
├── .gitignore          ← Excludes .env, .cache, logs, etc.
├── .cache              ← Spotipy auth token (auto-generated, never committed)
└── README.md           ← This file
```

---

## Finding a Spotify Show ID

1. Open Spotify and navigate to any podcast.
2. Click the three-dot menu → **Share** → **Copy link to show**.
3. The link looks like `https://open.spotify.com/show/1D4A4NKKF0axPvAS7h31Lu` — the ID is the last part.
