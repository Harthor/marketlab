#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.deno/bin:$HOME/.local/bin:$PATH"

cd ~/projects/market-sentiment-lab
SCRIPT="$(find ~/skills/youtube-watcher -name get_transcript.py | head -n1)"

if [ -z "${SCRIPT:-}" ]; then
  echo "No encontré get_transcript.py en ~/skills/youtube-watcher"
  exit 1
fi

mkdir -p tmp/transcripts
: > /tmp/youtube_ids_all.txt

# === Canales (editables) ===
# Formato: "Nombre|URL"
cat > /tmp/youtube_channels.txt <<'EOF'
MoonDev|https://www.youtube.com/channel/UCN7D80fY9xMYu5mHhUhXEFw/videos
Coin Bureau|https://www.youtube.com/@CoinBureau/videos
Benjamin Cowen|https://www.youtube.com/@BenjaminCowen/videos
DataDash|https://www.youtube.com/@DataDash/videos
Bankless|https://www.youtube.com/@Bankless/videos
EOF

while IFS='|' read -r CH_NAME CH_URL; do
  [ -z "$CH_NAME" ] && continue
  echo "===== CHANNEL: $CH_NAME ====="
  yt-dlp --cookies ~/.config/youtube_cookies.txt \
    --flat-playlist --playlist-end 3 \
    --print "%(id)s|$CH_NAME|%(title)s" "$CH_URL" >> /tmp/youtube_ids_all.txt || true
done < /tmp/youtube_channels.txt

# dedupe por video id
awk -F'|' '!seen[$1]++' /tmp/youtube_ids_all.txt > /tmp/youtube_ids_unique.txt

while IFS='|' read -r VID CH_NAME TITLE; do
  [ -z "$VID" ] && continue
  OUT="tmp/transcripts/${VID}.txt"
  if [ -s "$OUT" ]; then
    echo "SKIP (exists): $VID"
    continue
  fi
  echo "==> $VID | $CH_NAME | $TITLE"
  {
    echo "CHANNEL: $CH_NAME"
    echo "TITLE: $TITLE"
    echo "VIDEO_ID: $VID"
    echo
    python3 "$SCRIPT" "https://www.youtube.com/watch?v=$VID"
  } > "$OUT" || true
done < /tmp/youtube_ids_unique.txt

python3 - <<'PY' > /tmp/openclaw_research_append.txt
from pathlib import Path
import re
from datetime import datetime, UTC

tx_dir = Path("tmp/transcripts")

# ticker aliases
ALIASES = {
    "BITCOIN":"BTC", "BTC":"BTC",
    "ETHEREUM":"ETH", "ETH":"ETH",
    "SOLANA":"SOL", "SOL":"SOL",
    "HYPERLIQUID":"HYPE", "HYPE":"HYPE",
    "DOGE":"DOGE", "DOGECOIN":"DOGE",
    "XRP":"XRP", "BNB":"BNB",
    "ARBITRUM":"ARB", "ARB":"ARB",
    "OPTIMISM":"OP", "OP":"OP",
    "CHAINLINK":"LINK", "LINK":"LINK",
    "WIF":"WIF", "PEPE":"PEPE"
}
token_re = re.compile(r'\b(' + '|'.join(map(re.escape, ALIASES.keys())) + r')\b', re.I)

def sentiment_guess(text: str):
    t = text.lower()
    pos_words = ["bullish","long","buy","breakout","upside","strong","higher","bid","accumulate"]
    neg_words = ["bearish","short","sell","breakdown","downside","weak","lower","risk-off","distribution"]
    pos = sum(t.count(w) for w in pos_words)
    neg = sum(t.count(w) for w in neg_words)
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"

files = sorted(tx_dir.glob("*.txt"))
stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

notes = [f"\n## {stamp} YouTube batch\n"]
sent = [f"\n## {stamp} Snapshot\n"]
todo = [f"\n## {stamp} Hypotheses (draft)\n"]

source_count = {}

for f in files:
    raw = f.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw:
        continue

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    ch = next((ln.replace("CHANNEL:","").strip() for ln in lines if ln.startswith("CHANNEL:")), "unknown")
    title = next((ln.replace("TITLE:","").strip() for ln in lines if ln.startswith("TITLE:")), f.stem)
    vid = next((ln.replace("VIDEO_ID:","").strip() for ln in lines if ln.startswith("VIDEO_ID:")), f.stem)

    body_lines = [ln for ln in lines if not ln.startswith(("CHANNEL:","TITLE:","VIDEO_ID:"))]
    text = "\n".join(body_lines)
    excerpt = " ".join(body_lines[:16])[:500] if body_lines else "(no transcript text)"

    tickers = sorted({ALIASES[m.group(1).upper()] for m in token_re.finditer(text)})
    s = sentiment_guess(text)

    notes += [
        f"- channel: {ch}",
        f"  - title: {title}",
        f"  - video_id: {vid}",
        f"  - summary_seed: {excerpt}",
        f"  - tickers: {', '.join(tickers) if tickers else 'none detected'}",
        f"  - sentiment: {s}",
    ]

    if tickers:
        for tk in tickers:
            source_count[tk] = source_count.get(tk, 0) + 1
            sent.append(f"- {tk}: {s} | confidence: low | independent_sources: {source_count[tk]} | source_channel: {ch} | source_video: {vid}")
            todo += [
                f"- hypothesis: If YouTube sentiment remains {s} on {tk}, test momentum continuation",
                f"  entry trigger: 1h breakout above prior 24h high with volume confirmation",
                f"  invalidation logic: close back below breakout level",
                f"  timeframe: 1h",
                f"  asset(s): {tk}",
            ]
    else:
        todo += [
            f"- hypothesis: Video {vid} is narrative/infrastructure (no clear ticker call)",
            f"  entry trigger: n/a",
            f"  invalidation logic: n/a",
            f"  timeframe: 1h",
            f"  asset(s): n/a",
        ]

print("###NOTES###")
print("\n".join(notes))
print("###SENTIMENT###")
print("\n".join(sent))
print("###BACKTEST###")
print("\n".join(todo))
PY

cd ~/apps/openclaw 2>/dev/null || cd /docker/openclaw-4arj

docker compose exec -T openclaw sh -lc '
mkdir -p /data/.openclaw/workspace
touch /data/.openclaw/workspace/NOTES.md /data/.openclaw/workspace/SENTIMENT.md /data/.openclaw/workspace/BACKTEST_TODO.md
'

awk '/^###NOTES###/{f=1;next}/^###SENTIMENT###/{f=0}f' /tmp/openclaw_research_append.txt \
| docker compose exec -T openclaw sh -lc 'cat >> /data/.openclaw/workspace/NOTES.md'

awk '/^###SENTIMENT###/{f=1;next}/^###BACKTEST###/{f=0}f' /tmp/openclaw_research_append.txt \
| docker compose exec -T openclaw sh -lc 'cat >> /data/.openclaw/workspace/SENTIMENT.md'

awk '/^###BACKTEST###/{f=1;next}f' /tmp/openclaw_research_append.txt \
| docker compose exec -T openclaw sh -lc 'cat >> /data/.openclaw/workspace/BACKTEST_TODO.md'

echo "DONE $(date -u +'%F %T UTC')"
docker compose exec -T openclaw sh -lc 'tail -n 25 /data/.openclaw/workspace/BACKTEST_TODO.md'
