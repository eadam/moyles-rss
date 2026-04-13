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

The repo lives in a local folder (not iCloud — background processes can't reliably access iCloud Drive):

```bash
mkdir -p ~/Developer/chrismoylespodcast
cd ~/Developer/chrismoylespodcast
git clone https://github.com/eadam/moyles-rss.git
```

The script (`rss_proxy.py`) lives inside the repo and runs directly from there.

---

## Step 2 — Set Git Identity in the Repo

```bash
cd ~/Developer/chrismoylespodcast/moyles-rss
git config --local user.name "Your Name"
git config --local user.email "your@email.com"
```

---

## Step 3 — Test the Script Once Manually

```bash
cd ~/Developer/chrismoylespodcast/moyles-rss
python3 rss_proxy.py
```

Expected output:
- Fetches upstream feed
- Saves a snapshot to `snapshots/`
- Probes duration for any uncached episodes (slow on first run — ~1-2 min for 25+ episodes)
- Writes `feed.xml`
- Commits and pushes to GitHub

Check the output: all items fixed, 0 title parse warnings.

---

## Step 4 — Create the AppleScript App Wrapper

macOS Full Disk Access can't be granted to Python (it's a symlink chain). The workaround is a `.app` bundle that wraps the script — `.app` bundles are recognised by macOS FDA. Even though the repo is now on a local path, the `.app` wrapper is still needed for launchd to run the script reliably.

```bash
mkdir -p ~/Applications

cat > /tmp/moyles_proxy.applescript << 'APPLESCRIPT'
do shell script "/opt/homebrew/bin/python3 'HOMEDIR/Developer/chrismoylespodcast/moyles-rss/rss_proxy.py' >> HOMEDIR/Library/Logs/moyles-rss.log 2>&1"
APPLESCRIPT

# Substitute the real home directory path
sed -i '' "s|HOMEDIR|$HOME|g" /tmp/moyles_proxy.applescript

osacompile -o ~/Applications/MoylesRSSProxy.app /tmp/moyles_proxy.applescript
```

---

## Step 5 — Install the launchd Plist

The plist schedules the script to run every 2 hours:

```bash
cd ~/Developer/chrismoylespodcast/moyles-rss
sed "s|__HOME__|$HOME|g" net.chrismoyles.rssproxy.plist > ~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist
launchctl load ~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist
```

Verify it loaded:
```bash
launchctl list | grep chrismoyles
# Should show: -  0  net.chrismoyles.rssproxy
```

---

## Step 6 — Grant Full Disk Access to the App

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click **+**
3. Press **Cmd + Shift + G** and type `~/Applications`
4. Select **MoylesRSSProxy.app** and click Open

---

## Step 7 — Verify the Job is Firing

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

## Step 8 — Subscribe Apple Podcasts

In Apple Podcasts on iPhone:
1. Remove any existing subscription to `https://chrismoyles.net/shows/shows.rss`
2. Add: `https://eadam.github.io/moyles-rss/feed.xml`

Note: GitHub Pages can take a few minutes to serve a newly pushed file. If the feed doesn't load immediately, wait 5 minutes and try again.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Operation not permitted` in log | FDA not granted | Re-do Step 6; make sure to select the `.app` not a folder |
| `can't push to GitHub` | `gh` not authenticated | Run `gh auth login` |
| Episodes out of order in Apple Podcasts | Old subscription still active | Remove old feed, re-add GitHub Pages URL |
| Duration shows 0:00 | `ffprobe` not found | Run `brew install ffmpeg` |
| No new episodes appearing | Feed stale or script not running | Check log; run `python3 rss_proxy.py` manually |

---

## Useful Commands

```bash
# Run the script manually
cd ~/Developer/chrismoylespodcast/moyles-rss && python3 rss_proxy.py

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
| Repo + script + feed | `~/Developer/chrismoylespodcast/moyles-rss/` |
| Duration cache | `~/Developer/chrismoylespodcast/moyles-rss/duration_cache.json` (gitignored, auto-regenerates) |
| launchd plist (source) | `moyles-rss/net.chrismoyles.rssproxy.plist` (contains `__HOME__` placeholder) |
| launchd plist (installed) | `~/Library/LaunchAgents/net.chrismoyles.rssproxy.plist` |
| AppleScript app | `~/Applications/MoylesRSSProxy.app` |
| Log file | `~/Library/Logs/moyles-rss.log` |
