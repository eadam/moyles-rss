# SETUP.md — Recreating the Moyles RSS Proxy on a New Mac

This is a complete guide for recreating the Chris Moyles RSS proxy from scratch on a new machine. It's written so another Claude Code session can implement it end-to-end.

**What this does:** Runs a Python script every 2 hours that fetches the Chris Moyles Radio X podcast feed, fixes broken dates and unstable episode IDs, and publishes the corrected feed to GitHub Pages so Apple Podcasts on iPhone gets a stable, correctly-ordered feed.

**Public feed URL (already live):** `https://eadam.github.io/moyles-rss/feed.xml`

---

## Prerequisites

Install the following if not already present:

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ffmpeg (provides ffprobe for duration detection) + python3
brew install ffmpeg python3

# GitHub CLI (for pushing the feed)
brew install gh

# Authenticate gh with GitHub account eadam
gh auth login
```

---

## Step 1 — Clone the Repo

The script and config files live in the same iCloud developer folder as the git repo clone:

```bash
mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/Developer/chrismoylespodcast
cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Developer/chrismoylespodcast
git clone https://github.com/eadam/moyles-rss.git
```

---

## Step 2 — Copy the Script Out of the Repo

The script needs to live in the parent folder (one level above the git repo), not inside it — this keeps `rss_proxy.py` out of git's working tree so it doesn't get committed on every run:

```bash
cp moyles-rss/rss_proxy.py .
```

The script auto-detects its own location and sets `REPO_DIR` relative to itself, so no path changes are needed as long as `rss_proxy.py` is in:
```
.../chrismoylespodcast/rss_proxy.py          ← script here
.../chrismoylespodcast/moyles-rss/           ← repo here
```

---

## Step 3 — Set Git Identity in the Repo

```bash
cd moyles-rss
git config --local user.name "Your Name"
git config --local user.email "your@email.com"
cd ..
```

---

## Step 4 — Test the Script Once Manually

```bash
python3 rss_proxy.py
```

Expected output:
- Fetches upstream feed
- Saves a snapshot to `moyles-rss/snapshots/`
- Probes duration for any uncached episodes (slow on first run — ~1-2 min for 25 episodes)
- Writes `moyles-rss/feed.xml`
- Commits and pushes to GitHub

Check the log: all 25 (or however many) items fixed, 0 title parse warnings.

---

## Step 5 — Create the AppleScript App Wrapper

macOS Full Disk Access can't be granted to Python (it's a symlink). The workaround is a `.app` bundle that wraps the script — `.app` bundles are recognised by macOS FDA.

```bash
mkdir -p ~/Applications

cat > /tmp/moyles_proxy.applescript << 'EOF'
do shell script "/opt/homebrew/bin/python3 '/Users/YOUR_USERNAME/Library/Mobile Documents/com~apple~CloudDocs/Developer/chrismoylespodcast/rss_proxy.py' >> /Users/YOUR_USERNAME/Library/Logs/moyles-rss.log 2>&1"
EOF

# Replace YOUR_USERNAME with the actual macOS username
sed -i '' "s/YOUR_USERNAME/$(whoami)/g" /tmp/moyles_proxy.applescript

osacompile -o ~/Applications/MoylesRSSProxy.app /tmp/moyles_proxy.applescript
```

---

## Step 6 — Install the launchd Plist

The plist schedules the script to run every 2 hours:

```bash
# Substitute __HOME__ with your actual home directory path, then install
sed "s|__HOME__|$HOME|g" moyles-rss/net.chrismoyles.rssproxy.plist > ~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist
launchctl load ~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist
```

Verify it loaded:
```bash
launchctl list | grep chrismoyles
# Should show: -  0  net.chrismoyles.rssproxy
```

---

## Step 7 — Grant Full Disk Access to the App

The launchd job calls `~/Applications/MoylesRSSProxy.app` which needs FDA to access iCloud Drive files.

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click **+**
3. Press **Cmd + Shift + G** and type `~/Applications`
4. Select **MoylesRSSProxy.app** and click Open

---

## Step 8 — Verify the Job is Firing

Wait a few minutes (the job runs on load), then check the log:

```bash
cat ~/Library/Logs/moyles-rss.log
```

A successful run looks like:
```
[moyles-rss] 2026-04-13T07:55:46Z  === Run started ===
[moyles-rss] 2026-04-13T07:55:47Z  Fetching https://chrismoyles.net/shows/shows.rss
[moyles-rss] 2026-04-13T07:55:47Z  Snapshot saved: 20260413-075547-raw.xml
[moyles-rss] 2026-04-13T07:55:47Z  Fixed 25 items; 0 title parse warnings
[moyles-rss] 2026-04-13T07:55:47Z  Feed written: ...
[moyles-rss] 2026-04-13T07:55:48Z  Pushed to GitHub
[moyles-rss] 2026-04-13T07:55:48Z  === Run complete ===
```

If you see `Operation not permitted`, the FDA grant didn't take — try reloading the plist:
```bash
launchctl unload ~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist
launchctl load ~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist
```

---

## Step 9 — Subscribe Apple Podcasts

In Apple Podcasts on iPhone:
1. Remove any existing subscription to `https://chrismoyles.net/shows/shows.rss`
2. Add: `https://eadam.github.io/moyles-rss/feed.xml`

Note: GitHub Pages can take a few minutes to serve a newly pushed file. If the feed doesn't load immediately, wait 5 minutes and try again.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Operation not permitted` in log | FDA not granted | Re-do Step 7; make sure to select the `.app` not a folder |
| `can't push to GitHub` | `gh` not authenticated | Run `gh auth login` |
| Episodes out of order in Apple Podcasts | Old subscription still active | Remove old feed, re-add GitHub Pages URL |
| Duration shows 0:00 | `ffprobe` not found | Run `brew install ffmpeg` |
| No new episodes appearing | Feed stale or script not running | Check log; run `python3 rss_proxy.py` manually |

---

## Useful Commands

```bash
# Run the script manually
python3 ~/Library/Mobile\ Documents/com~apple~CloudDocs/Developer/chrismoylespodcast/rss_proxy.py

# Watch the log live
tail -f ~/Library/Logs/moyles-rss.log

# Reload the scheduler (e.g. after a reboot if it didn't auto-start)
launchctl load ~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist

# Check job status
launchctl list | grep chrismoyles

# Check GitHub Pages is serving the feed
curl -s https://eadam.github.io/moyles-rss/feed.xml | head -5
```

---

## File Locations Summary

| File | Location |
|------|---------|
| Transformer script | `~/Library/Mobile Documents/.../chrismoylespodcast/rss_proxy.py` |
| Git repo + feed | `~/Library/Mobile Documents/.../chrismoylespodcast/moyles-rss/` |
| Duration cache | `~/Library/Mobile Documents/.../chrismoylespodcast/duration_cache.json` |
| launchd plist (source) | `moyles-rss/net.chrismoyles.rssproxy.plist` |
| launchd plist (installed) | `~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist` |
| AppleScript app | `~/Applications/MoylesRSSProxy.app` |
| Log file | `~/Library/Logs/moyles-rss.log` |
