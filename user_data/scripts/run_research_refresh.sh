#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

mkdir -p user_data/research/out user_data/logs

TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_PATH="user_data/logs/research_refresh_${TS_UTC}.log"
CANDIDATES_OUT="user_data/research/out/candidates_latest.csv"
FEATURES_CSV="user_data/tmp/social_test/social_features_1h.csv"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] research_refresh start"

  if [ -x user_data/scripts/run_social_merge_1h.sh ]; then
    echo "Running user_data/scripts/run_social_merge_1h.sh user_data/tmp/social_test"
    user_data/scripts/run_social_merge_1h.sh user_data/tmp/social_test
  else
    echo "run_social_merge_1h.sh not found or not executable, skipping social merge step"
  fi

  if [ -f "$FEATURES_CSV" ]; then
    echo "Generating candidates CSV from $FEATURES_CSV"
    .env/bin/python - <<'PY'
import csv
from datetime import datetime, timezone
from pathlib import Path

features = Path("user_data/tmp/social_test/social_features_1h.csv")
out = Path("user_data/research/out/candidates_latest.csv")
out.parent.mkdir(parents=True, exist_ok=True)

rows_out = []
with features.open("r", encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        symbol = str(row.get("symbol", "") or "").strip().upper()
        if not symbol:
            continue
        score_raw = row.get("avg_engagement_score", 0.0)
        mentions_raw = row.get("mentions_count", 0)
        bucket_start = str(row.get("bucket_start", "") or "").strip()
        try:
            score = float(score_raw if score_raw not in (None, "") else 0.0)
        except Exception:
            score = 0.0
        try:
            mentions = int(float(mentions_raw if mentions_raw not in (None, "") else 0))
        except Exception:
            mentions = 0
        ts = bucket_start or datetime.now(timezone.utc).isoformat()
        rows_out.append(
            {
                "symbol": symbol,
                "score": score,
                "mentions": mentions,
                "source": "social_1h",
                "timestamp_utc": ts,
            }
        )

rows_out.sort(key=lambda r: (float(r["score"]), int(r["mentions"])), reverse=True)
with out.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["symbol", "score", "mentions", "source", "timestamp_utc"])
    writer.writeheader()
    writer.writerows(rows_out)

print(f"wrote_candidates={out} rows={len(rows_out)}")
PY
  else
    echo "Features CSV not found at $FEATURES_CSV"
    if [ ! -f "$CANDIDATES_OUT" ]; then
      printf 'symbol,score,mentions,source,timestamp_utc\n' > "$CANDIDATES_OUT"
      echo "Created empty candidates file at $CANDIDATES_OUT"
    fi
  fi

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] research_refresh done"
} 2>&1 | tee -a "$LOG_PATH"

echo "research_log=$LOG_PATH"
echo "candidates_csv=$CANDIDATES_OUT"

