import os
import re
import tempfile
import subprocess
from pathlib import Path


def _clean_vtt(content: str) -> str:
    lines = []
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if s == "WEBVTT":
            continue
        if "-->" in s:
            continue
        if s.isdigit():
            continue
        s = re.sub(r"<[^>]+>", "", s)
        lines.append(s)

    # de-dup líneas consecutivas
    out = []
    prev = None
    for l in lines:
        if l != prev:
            out.append(l)
        prev = l

    return "\n".join(out).strip()


def _fetch_with_ytdlp(video_id: str, languages=None):
    languages = languages or ["en", "es"]
    url = f"https://www.youtube.com/watch?v={video_id}"

    env = os.environ.copy()
    env["PATH"] = f"{Path.home()}/.deno/bin:{Path.home()}/.local/bin:" + env.get("PATH", "")

    cookies = Path.home() / ".config" / "youtube_cookies.txt"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        outtmpl = str(td_path / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs",
            "--write-subs",
            "--sub-format", "vtt",
            "--sub-langs", ",".join(languages),
            "--output", outtmpl,
            "--no-playlist",
            "--sleep-requests", "2",
            "--sleep-interval", "1",
            "--max-sleep-interval", "3",
            url,
        ]

        if cookies.exists():
            cmd[1:1] = ["--cookies", str(cookies)]

        # solver JS (te ayudó antes)
        if (Path.home() / ".deno" / "bin" / "deno").exists():
            cmd[1:1] = ["--js-runtimes", "deno", "--remote-components", "ejs:github"]

        p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip() or "yt-dlp failed")

        vtts = sorted(td_path.glob("*.vtt"))
        if not vtts:
            raise RuntimeError("yt-dlp no subtitle files found")

        chosen = None
        for lang in languages:
            for f in vtts:
                if f".{lang}." in f.name or f".{lang}-" in f.name:
                    chosen = f
                    break
            if chosen:
                break
        if not chosen:
            chosen = vtts[0]

        text = _clean_vtt(chosen.read_text(encoding="utf-8", errors="ignore"))
        if not text:
            raise RuntimeError("empty transcript after cleaning")

        mode = "yt-dlp:auto" if "auto" in chosen.name.lower() else "yt-dlp:subs"
        return text, mode


def _fetch_manual_file(video_id: str):
    # carpeta para transcripts manuales que subas vos
    base = Path.home() / "projects" / "market-sentiment-lab" / "user_data" / "research" / "social" / "manual_transcripts"
    txt = base / f"{video_id}.txt"
    if txt.exists():
        content = txt.read_text(encoding="utf-8", errors="ignore").strip()
        if content:
            return content, "manual-upload"
    raise FileNotFoundError(
        f"No transcript for {video_id}. "
        f"Subí un archivo manual a: {txt}"
    )


def fetch_transcript_text(video_id: str, languages=None):
    """
    VPS-safe:
    1) yt-dlp + cookies + deno
    2) transcript manual (archivo .txt subido por vos)
    """
    languages = languages or ["en", "es"]

    try:
        return _fetch_with_ytdlp(video_id, languages)
    except Exception as e_ytdlp:
        try:
            return _fetch_manual_file(video_id)
        except Exception as e_manual:
            raise RuntimeError(
                f"Transcript failed for {video_id}\n"
                f"- yt-dlp: {e_ytdlp}\n"
                f"- manual: {e_manual}"
            )
