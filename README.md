# My Daily Drive

Automatically builds a personalised **My Daily Drive** playlist in your Spotify account each morning, mixing Australian news podcast episodes with music from your library.

Default behaviour:
- Fetches the latest **ABC News Daily** episode
- Checks your other followed podcasts for any episode released today
- Pulls 25 tracks from your liked songs and followed artists (50/50 split)
- Interleaves episodes and music (3 songs → 1 episode → 3 songs → …)
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
| `PRIMARY_PODCAST_ID` | ABC News Daily | Spotify show ID of your main podcast |
| `INCLUDE_FOLLOWED_PODCASTS` | `True` | Also add today's episodes from other followed shows |
| `MAX_FOLLOWED_PODCASTS` | `15` | How many followed shows to check |
| `MUSIC_TRACK_COUNT` | `25` | Total music tracks in the playlist |
| `LIKED_SONGS_PERCENT` | `50` | % of music from your liked songs |
| `ARTIST_TRACKS_PERCENT` | `50` | % of music from your followed artists |
| `PLAYLIST_NAME` | `"My Daily Drive"` | Name of the Spotify playlist |
| `MUSIC_TRACKS_BETWEEN_EPISODES` | `3` | Songs between each podcast episode |

---

## Step 6 — Schedule with cron (runs automatically every morning)

### Find the full path to your Python interpreter

```bash
cd /Volumes/GDrive/Github/MyDailyDrive
source .venv/bin/activate
which python3
```

Copy the output — it will look like:
```
/Volumes/GDrive/Github/MyDailyDrive/.venv/bin/python3
```

### Open your crontab

```bash
crontab -e
```

This opens a text editor (usually `vi` — press `i` to start typing).

### Add this line

Replace `<python_path>` with what you copied above:

```
0 7 * * * <python_path> /Volumes/GDrive/Github/MyDailyDrive/daily_drive.py >> /Volumes/GDrive/Github/MyDailyDrive/daily_drive.log 2>&1
```

This runs the script at **7:00 AM every day**. Change `7` to any hour you prefer.

Save and exit (`Escape` then `:wq` then `Enter` in vi).

Verify it was saved:
```bash
crontab -l
```

### Allow cron to run on macOS

macOS may block cron from accessing files. If the script doesn't run:

1. Go to **System Settings → Privacy & Security → Full Disk Access**
2. Click **+** and add `/usr/sbin/cron`

---

## Step 7 — Create the GitHub repository and push

```bash
cd /Volumes/GDrive/Github/MyDailyDrive

# Initialize the git repo (already done if you cloned this)
git init
git add daily_drive.py requirements.txt .env.example .gitignore README.md
git commit -m "Initial commit: My Daily Drive playlist builder"
```

Then create a new **public** or **private** repository called `MyDailyDrive` on GitHub (via the GitHub website), and push:

```bash
git remote add origin https://github.com/YOUR_USERNAME/MyDailyDrive.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `Missing required environment variables` | `.env` not set up | Follow Step 3 |
| `Authentication failed` | Wrong credentials or redirect URI | Double-check `.env` and the Spotify Dashboard redirect URI |
| Browser opens but token isn't saved | Copied the wrong URL | Paste the full `http://127.0.0.1:8888/callback?code=…` URL |
| `No episodes found for ABC News Daily` | Show ID changed | Find the new ID in the Spotify app and update `PRIMARY_PODCAST_ID` |
| Cron job doesn't run | macOS privacy block | Grant Full Disk Access to `/usr/sbin/cron` (see Step 6) |
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
