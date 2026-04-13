#!/usr/bin/env python3
"""
Chris Moyles RSS Proxy
======================
Fetches the upstream feed, fixes broken pubDate and unstable GUID values,
writes a corrected feed.xml, saves a raw snapshot, and pushes to GitHub
so Apple Podcasts (iPhone) gets a stable, correctly-ordered feed.

Public feed URL: https://eadam.github.io/moyles-rss/feed.xml
"""

import json
import re
import sys
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Configuration ──────────────────────────────────────────────────────────────

UPSTREAM_URL    = "https://chrismoyles.net/shows/shows.rss"
SCRIPT_DIR      = Path(__file__).parent.resolve()
REPO_DIR        = SCRIPT_DIR
FEED_OUT        = REPO_DIR / "feed.xml"
SNAPSHOT_DIR    = REPO_DIR / "snapshots"
DURATION_CACHE  = REPO_DIR / "duration_cache.json"
FFPROBE_PATH    = "/opt/homebrew/bin/ffprobe"
LOG_PREFIX      = "[moyles-rss]"
MAX_SNAPSHOTS   = 14         # ~7 days at 2 runs/day
STALE_DAYS      = 7          # alert if newest episode is older than this
FETCH_TIMEOUT   = 30         # seconds
FFPROBE_TIMEOUT = 30         # seconds per episode

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"

# RFC 2822 weekday/month maps for output formatting
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS   = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Regex to pull a date out of titles like:
#   "Saturday, 11th April 2026"
#   "Friday, 10th April 2026 - Saturday Show"
TITLE_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(\d{1,2})(?:st|nd|rd|th)\s+"
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+"
    r"(\d{4})",
    re.IGNORECASE,
)

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3,    "april": 4,
    "may": 5,     "june": 6,     "july": 7,     "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{LOG_PREFIX} {ts}  {msg}", flush=True)


def notify(title: str, message: str) -> None:
    """Send a macOS notification (shows on Mac and iPhone via iCloud)."""
    script = (
        f'display notification "{message}" '
        f'with title "{title}" '
        f'sound name "Basso"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True,
                       capture_output=True, timeout=10)
    except Exception as e:
        log(f"WARNING: could not send notification: {e}")


def notify_error(message: str) -> None:
    log(f"ERROR: {message}")
    notify("Moyles RSS Proxy Error", message)


def to_rfc2822(dt: datetime) -> str:
    """Format a datetime as RFC 2822, e.g. 'Sat, 11 Apr 2026 06:00:00 +0000'"""
    wd  = WEEKDAYS[dt.weekday()]
    mon = MONTHS[dt.month - 1]
    return f"{wd}, {dt.day:02d} {mon} {dt.year} 06:00:00 +0000"


def parse_title_date(title: str) -> Optional[datetime]:
    """Extract the air date from an episode title, or return None."""
    m = TITLE_DATE_RE.search(title)
    if not m:
        return None
    day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    month = MONTH_NAMES.get(month_name)
    if not month:
        return None
    try:
        return datetime(year, month, day, 6, 0, 0, tzinfo=timezone.utc)
    except ValueError:
        return None


def stable_guid(dt: datetime) -> str:
    return f"cm-radiox-{dt.strftime('%Y%m%d')}"


def seconds_to_hhmmss(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s   = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def load_duration_cache() -> dict:
    if DURATION_CACHE.exists():
        try:
            return json.loads(DURATION_CACHE.read_text())
        except Exception:
            pass
    return {}


def save_duration_cache(cache: dict) -> None:
    DURATION_CACHE.write_text(json.dumps(cache, indent=2))


def probe_duration(url: str) -> Optional[float]:
    """Use ffprobe to get duration (seconds) of an audio file at a URL."""
    try:
        result = subprocess.run(
            [
                FFPROBE_PATH,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                url,
            ],
            capture_output=True, text=True, timeout=FFPROBE_TIMEOUT
        )
        val = result.stdout.strip()
        if val:
            return float(val)
    except Exception as e:
        log(f"WARNING: ffprobe failed for {url}: {e}")
    return None


# ── Core logic ─────────────────────────────────────────────────────────────────

def fetch_feed() -> bytes:
    log(f"Fetching {UPSTREAM_URL}")
    req = urllib.request.Request(
        UPSTREAM_URL,
        headers={"User-Agent": "MoylesRSSProxy/1.0 (+https://github.com/eadam/moyles-rss)"},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return resp.read()


def save_snapshot(raw: bytes) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = SNAPSHOT_DIR / f"{ts}-raw.xml"
    path.write_bytes(raw)
    log(f"Snapshot saved: {path.name}")

    # Purge oldest snapshots beyond MAX_SNAPSHOTS
    snapshots = sorted(SNAPSHOT_DIR.glob("*-raw.xml"))
    excess = len(snapshots) - MAX_SNAPSHOTS
    for old in snapshots[:excess]:
        old.unlink()
        log(f"Purged old snapshot: {old.name}")


def transform_feed(raw: bytes) -> tuple[str, list[str]]:
    """
    Parse raw RSS, fix pubDate, guid, and itunes:duration for every item.
    Returns (transformed_xml_string, list_of_warnings).
    """
    root = ET.fromstring(raw)

    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("atom",   "http://www.w3.org/2005/Atom")
    ET.register_namespace("",       "")

    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("No <channel> element found in feed")

    warnings      = []
    items_fixed   = 0
    latest_date: Optional[datetime] = None
    dur_cache     = load_duration_cache()
    dur_tag       = f"{{{ITUNES_NS}}}duration"
    cache_updated = False

    for item in channel.findall("item"):
        title_el = item.find("title")
        title    = title_el.text.strip() if title_el is not None and title_el.text else ""

        air_date = parse_title_date(title)

        if air_date is None:
            warnings.append(f"Could not parse date from title: {title!r}")
            continue

        # Fix pubDate
        pub_el = item.find("pubDate")
        if pub_el is None:
            pub_el = ET.SubElement(item, "pubDate")
        pub_el.text = to_rfc2822(air_date)

        # Fix guid
        guid      = stable_guid(air_date)
        guid_el   = item.find("guid")
        if guid_el is None:
            guid_el = ET.SubElement(item, "guid")
        guid_el.text = guid
        guid_el.set("isPermaLink", "false")

        # Fix itunes:duration — use cache, probe if missing
        if guid not in dur_cache:
            enclosure = item.find("enclosure")
            url = enclosure.get("url") if enclosure is not None else None
            if url:
                log(f"Probing duration for {guid} …")
                secs = probe_duration(url)
                if secs is not None:
                    dur_cache[guid] = secs
                    cache_updated = True
                    log(f"  → {seconds_to_hhmmss(secs)}")
                else:
                    log(f"  → probe failed, skipping duration for {guid}")

        if guid in dur_cache:
            dur_el = item.find(dur_tag)
            if dur_el is None:
                dur_el = ET.SubElement(item, dur_tag)
            dur_el.text = seconds_to_hhmmss(dur_cache[guid])

        if latest_date is None or air_date > latest_date:
            latest_date = air_date

        items_fixed += 1

    if cache_updated:
        save_duration_cache(dur_cache)
        log(f"Duration cache saved ({len(dur_cache)} entries)")

    # Update channel lastBuildDate
    now_str = to_rfc2822(datetime.now(timezone.utc))
    lbd = channel.find("lastBuildDate")
    if lbd is None:
        lbd = ET.SubElement(channel, "lastBuildDate")
    lbd.text = now_str

    log(f"Fixed {items_fixed} items; {len(warnings)} title parse warnings")

    # Staleness check
    if latest_date is not None:
        age_days = (datetime.now(timezone.utc) - latest_date).days
        if age_days > STALE_DAYS:
            warnings.append(
                f"Feed looks stale: newest episode is {age_days} days old "
                f"(threshold: {STALE_DAYS} days)"
            )

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode", xml_declaration=False
    )
    return xml_str, warnings


def write_feed(xml_str: str) -> None:
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    FEED_OUT.write_text(xml_str, encoding="utf-8")
    log(f"Feed written: {FEED_OUT}")


def git_push() -> None:
    """Commit feed.xml + snapshots and push to GitHub."""
    def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, cwd=REPO_DIR, check=True,
                              capture_output=True, text=True, **kwargs)

    run(["git", "pull", "--rebase", "--autostash"])

    run(["git", "add", "feed.xml"])
    # Add snapshots dir if it exists
    if SNAPSHOT_DIR.exists():
        run(["git", "add", "snapshots/"])

    # Only commit if there are staged changes
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=REPO_DIR, capture_output=True
    )
    if diff.returncode == 0:
        log("No changes to commit — feed unchanged since last run")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run(["git", "commit", "-m", f"feed: refresh {ts}"])
    run(["git", "push"])
    log("Pushed to GitHub")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    log("=== Run started ===")

    # 1. Fetch
    try:
        raw = fetch_feed()
    except Exception as e:
        notify_error(f"Failed to fetch upstream feed: {e}")
        return 1

    # 2. Snapshot
    try:
        save_snapshot(raw)
    except Exception as e:
        log(f"WARNING: snapshot failed (non-fatal): {e}")

    # 3. Transform
    try:
        xml_str, warnings = transform_feed(raw)
    except Exception as e:
        notify_error(f"Feed parsing/transform failed: {e}")
        return 1

    if not xml_str:
        notify_error("Transform produced empty feed — upstream format may have changed")
        return 1

    # Report warnings (and notify on bad ones)
    parse_failures = [w for w in warnings if "Could not parse" in w]
    stale_warnings = [w for w in warnings if "stale" in w]

    for w in warnings:
        log(f"WARNING: {w}")

    if parse_failures:
        notify_error(
            f"{len(parse_failures)} episode(s) had unparseable titles — "
            "upstream feed format may have changed"
        )

    if stale_warnings:
        notify_error(stale_warnings[0])

    # 4. Write
    try:
        write_feed(xml_str)
    except Exception as e:
        notify_error(f"Failed to write feed.xml: {e}")
        return 1

    # 5. Push
    try:
        git_push()
    except subprocess.CalledProcessError as e:
        notify_error(f"Git push failed: {e.stderr.strip() or str(e)}")
        return 1

    log("=== Run complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
