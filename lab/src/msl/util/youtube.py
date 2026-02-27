from __future__ import annotations
import os, re, subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from dateutil import parser as dtp
import feedparser

@dataclass(frozen=True)
class Video:
    video_id: str
    url: str
    title: str
    published_at: datetime
    channel: str

def _yt_dlp_bin() -> str:
    for p in [os.path.expanduser("~/.local/bin/yt-dlp"), "yt-dlp"]:
        try:
            subprocess.run([p, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return p
        except FileNotFoundError:
            continue
    return "yt-dlp"

def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr.strip()}")
    return p.stdout.strip()

def resolve_channel_id(youtube_url: str) -> str:
    ytdlp = _yt_dlp_bin()
    cmd = [ytdlp, "--flat-playlist", "--skip-download"]

    cookies = os.path.expanduser("~/.config/youtube_cookies.txt")
    if os.path.exists(cookies):
        cmd += ["--cookies", cookies]

    deno = os.path.expanduser("~/.deno/bin/deno")
    if os.path.exists(deno):
        cmd += ["--js-runtimes", "deno"]

    cmd += ["--print", "channel_id", youtube_url]
    return _run(cmd).splitlines()[0].strip()

def feed_url_from_channel_id(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

def parse_video_id(url: str) -> str:
    m = re.search(r"[?&]v=([^&]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([^?&/]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"youtube\.com/shorts/([^?&/]+)", url)
    if m:
        return m.group(1)
    raise ValueError(f"Could not parse video_id from url: {url}")

def fetch_recent_videos(feed_url: str, channel_name: str, max_videos: int) -> list[Video]:
    feed = feedparser.parse(feed_url)
    out: list[Video] = []
    for e in (feed.entries or [])[:max_videos]:
        url = e.get("link") or ""
        title = e.get("title") or "(no title)"
        published = e.get("published") or e.get("updated")
        if not url or not published:
            continue
        dt = dtp.parse(published)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        out.append(Video(
            video_id=parse_video_id(url),
            url=url,
            title=title,
            published_at=dt.astimezone(timezone.utc),
            channel=channel_name
        ))
    return out
