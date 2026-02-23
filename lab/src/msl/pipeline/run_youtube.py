from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml

from msl.util.youtube import resolve_channel_id, feed_url_from_channel_id, fetch_recent_videos
from msl.util.transcripts import fetch_transcript_text
from msl.llm.openai_client import OpenAIClient
from msl.io.workspace_writer import append_section, write_snapshot

FAST_SYSTEM = """You are a crypto research assistant.
Return ONLY valid JSON.
Extract: themes, tickers (uppercase), sentiment, confidence, thesis, invalidation.
No financial advice. Be factual about what the speaker claims."""
FINAL_SYSTEM = """You are a crypto research lead.
Create a concise daily research memo from extracted video facts.
No financial advice. Focus on narratives + hypotheses for backtesting."""

def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", default="lab/configs/channels.yaml")
    ap.add_argument("--config", default="lab/configs/pipeline.yaml")
    args = ap.parse_args()

    repo_root = Path.cwd()
    ch_cfg = load_yaml(repo_root / args.channels)
    cfg = load_yaml(repo_root / args.config)

    lookback = timedelta(hours=int(cfg.get("lookback_hours", 72)))
    cutoff = datetime.now(timezone.utc) - lookback
    max_videos = int(cfg.get("max_videos_per_channel", 3))
    langs = list(cfg.get("language_priority", ["es","en"]))
    model_fast = cfg["models"]["fast"]
    model_final = cfg["models"]["final"]

    out = cfg["output"]
    ws = repo_root / out["workspace_dir"]
    notes = ws / out["notes_file"]
    sent = ws / out["sentiment_file"]
    back = ws / out["backtest_file"]

    client = OpenAIClient()

    extracted = []
    for ch in ch_cfg.get("channels", []):
        name = ch["name"]
        url = ch["youtube_url"]
        channel_id = ch.get("channel_id") or resolve_channel_id(url)
        feed_url = ch.get("rss") or feed_url_from_channel_id(channel_id)

        videos = fetch_recent_videos(feed_url, name, max_videos=max_videos)
        for v in videos:
            print(f"[run_youtube] video: {v.video_id} | {v.title[:80]}", flush=True)
            if v.published_at < cutoff:
                continue
            try:
                print(f"[run_youtube] transcript fetch: {v.video_id}", flush=True)
                text, mode = fetch_transcript_text(v.video_id, langs)
                print(f"[run_youtube] transcript ok: {v.video_id} mode={mode}", flush=True)
            except Exception as e:
                text, mode = "", "no-transcript"
                print(f"[run_youtube] transcript fail: {v.video_id} err={type(e).__name__}", flush=True)
                # Si preferís saltear el video (no guardarlo vacío), descomentá:
                # continue
            if not text:
                append_section(notes, f"YouTube: {v.channel} (no transcript)",
                              f"- {v.title}\n- {v.url}\n- transcript: none\n")

            # recorte defensivo para no explotar tokens (v1)
            clip = text[:8000]

            print(f"[run_youtube] llm extract: {v.video_id}", flush=True)
            payload = client.call_json(
                model_fast,
                FAST_SYSTEM,
                f"""Video:
- channel: {v.channel}
- title: {v.title}
- url: {v.url}
- published_utc: {v.published_at.isoformat()}
Transcript_mode: {mode}

Transcript (clipped):
{clip}
"""
            )
            extracted.append(payload)

    if not extracted:
        append_section(notes, "Daily research", "HEARTBEAT_OK\n")
        return

    # Snapshot simple de tickers (v1)
    ticker_rows = []
    for item in extracted:
        for t in item.get("tickers", []):
            t = {"ticker": t} if isinstance(t, str) else (t or {})
            ticker_rows.append({
                "ticker": (str(t).upper() if isinstance(t, str) else str(t.get("ticker","")).upper()),
                "sentiment": t.get("sentiment",""),
                "confidence": t.get("confidence",""),
                "thesis": t.get("thesis",""),
                "invalidates_if": t.get("invalidates_if",""),
            })

        # Memo final (safe: nunca bloquea el pipeline)
    brief = []
    for item in extracted[:12]:
        brief.append({
            "themes": item.get("themes", [])[:10],
            "tickers": item.get("tickers", [])[:25],
            "sentiment": item.get("sentiment", ""),
            "confidence": item.get("confidence", ""),
            "thesis": item.get("thesis", ""),
            "invalidation": item.get("invalidation", item.get("invalidates_if", "")),
        })

    memo_user = "Extracted facts (JSON-ish):\n" + yaml.safe_dump(
        brief,
        sort_keys=False,
        allow_unicode=True
    )[:12000]

    memo = client.call_text_safe(
        model_final,
        FINAL_SYSTEM,
        memo_user,
        max_tries=2,
        fallback="(memo final unavailable: LLM timeout/error)"
    )

    append_section(notes, "Daily research", memo)

    # SENTIMENT snapshot (markdown simple)
    snap = ["# SENTIMENT snapshot\n"]
    for r in ticker_rows[:200]:
        snap.append(f"- **{r['ticker']}** | {r['sentiment']} | {r['confidence']} | {r['thesis']} | invalidation: {r['invalidates_if']}")
    write_snapshot(sent, "\n".join(snap))

    # BACKTEST TODO seed (markdown)
    bt = ["# BACKTEST_TODO\n", "## Hypotheses (auto)\n", memo]
    append_section(back, "Auto hypotheses", "\n".join(bt))
    print("[run_youtube] DONE", flush=True)

if __name__ == "__main__":
    main()
