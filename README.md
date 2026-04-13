# moyles-rss

Stable RSS proxy for **The Chris Moyles Show on Radio X**.

Fixes two defects in the upstream feed (`https://chrismoyles.net/shows/shows.rss`):
- All episodes share one `pubDate` → Apple Podcasts can't sort them
- GUIDs are mutable archive.org URLs → Apple Podcasts re-downloads episodes when URLs shift

This repo is updated automatically every 2 hours by `rss_proxy.py` running on a Mac via launchd.

## Subscribe

**Apple Podcasts feed URL:**
```
https://eadam.github.io/moyles-rss/feed.xml
```

## How it works

1. Fetches the upstream RSS feed
2. Extracts the real air date from each episode title (`"Saturday, 11th April 2026"`)
3. Sets a correct per-episode `pubDate` in RFC 2822 format
4. Replaces each GUID with a stable `cm-radiox-YYYYMMDD` identifier
5. Probes each episode's duration via `ffprobe` (cached — only new episodes are probed)
6. Commits `feed.xml` + a raw snapshot to this repo
7. GitHub Pages serves the corrected feed publicly

## Docs

- [SPEC.md](SPEC.md) — Full technical specification: problem statement, architecture, decisions and rationale
- [SETUP.md](SETUP.md) — Step-by-step guide to recreate this on a new Mac
