# Spec: Chris Moyles RSS Proxy — Stable Feed for Apple Podcasts

## Problem Statement

The RSS feed at `https://chrismoyles.net/shows/shows.rss` has two critical defects that cause Apple Podcasts (iPhone) to misbehave:

| Defect | Symptom | Root Cause |
|--------|---------|------------|
| All episodes share one pubDate | Episodes appear out of order; order shifts on each feed rebuild | Feed is regenerated from scratch periodically; all episodes stamped with today's date |
| GUIDs are mutable archive.org URLs | Episodes re-download as duplicates; playback position resets | Archive.org URLs can change; Apple Podcasts treats a changed GUID as a new episode |

**Secondary issue (fixed):** `itunes:duration` was 0 for all episodes.

---

## Solution Architecture

```
Original Feed                 Always-On Mac                 Public URL
chrismoyles.net/shows/ ──▶  rss_proxy.py (runs on cron) ──▶  GitHub Pages
shows.rss                    • fixes pubDate                   eadam.github.io/
                             • stabilises GUIDs                moyles-rss/feed.xml
                             • fetches/caches durations                │
                             • snapshots raw feed                       ▼
                             • git commit + push             Apple Podcasts (iPhone)
```

No open router ports. No persistent server process. Free hosting with version history.

---

## How the Fix Works

### pubDate
Each episode title contains its real air date in the format `"Saturday, 11th April 2026"`. The script parses this and sets a correct per-episode `pubDate` in RFC 2822 format (`Sat, 11 Apr 2026 06:00:00 +0000`). This gives Apple Podcasts the information it needs to sort episodes correctly.

### GUIDs
Each episode GUID is replaced with a stable date-based identifier: `cm-radiox-YYYYMMDD` (e.g. `cm-radiox-20260411`), marked `isPermaLink="false"`. This never changes regardless of what archive.org does to its URLs.

### Duration
On first encounter, `ffprobe` probes each episode's archive.org URL to get the real duration. Results are cached in `duration_cache.json` (not committed) so subsequent runs only probe new episodes.

---

## Files in This Repo

| File | Purpose |
|------|---------|
| `feed.xml` | The corrected public RSS feed, updated every 2 hours |
| `rss_proxy.py` | The transformer script — run this on the Mac |
| `net.chrismoyles.rssproxy.plist` | launchd plist for scheduling (copy to `~/Library/LaunchAgents/`) |
| `snapshots/` | Timestamped raw copies of the upstream feed (14 max) |
| `SETUP.md` | Full instructions for recreating this on a new Mac |
| `SPEC.md` | This file |

`duration_cache.json` lives next to `rss_proxy.py` in the iCloud folder (not committed — auto-regenerated on first run).

---

## Public Feed URL

```
https://eadam.github.io/moyles-rss/feed.xml
```

Subscribe Apple Podcasts to this URL instead of the upstream feed.

---

## Scheduling

A launchd agent (`net.chrismoyles.rssproxy`) runs every 2 hours via `StartInterval: 7200`. It fires immediately on load and runs silently in the background. Logs go to `~/Library/Logs/moyles-rss.log`.

---

## Error Alerts

The script sends macOS notifications (appear on Mac and iPhone via iCloud) when:
- Fetching the upstream feed fails (HTTP error, network down)
- Zero episodes parsed from the feed (feed format changed)
- Any episode title can't be parsed for a date (upstream format changed)
- The newest episode is more than 7 days old (feed stale — 7 days accounts for holiday weeks)
- Git push fails

It does NOT notify on new episodes (you'll see those in Apple Podcasts naturally).

---

## Snapshot Retention

Raw upstream feed snapshots are committed to `snapshots/` and capped at 14 files (~7 days at 2 runs/day). Older files are deleted automatically before each commit.

---

## Decisions & Rationale

| Decision | Choice | Reason |
|----------|--------|--------|
| Hosting | GitHub Pages | Free, stable URL, version history, no open ports, no server process |
| Scheduling | launchd | Native macOS, runs without user interaction, survives reboots |
| FDA workaround | AppleScript `.app` wrapper | Python symlinks can't be added to macOS Full Disk Access; `.app` bundles can |
| Snapshot retention | 14 files | Enough to diagnose any upstream change pattern without unbounded growth |
| Stale alert threshold | 7 days | Accounts for holiday weeks; Christmas may produce one false alarm/year |
| Duration caching | Local JSON | Avoids re-probing 25+ episodes every 2 hours; only new episodes are probed |
