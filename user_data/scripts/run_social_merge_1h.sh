#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-user_data/tmp/social_test}"
NORM_JSONL="$OUT_DIR/social_events.normalized.jsonl"
FEATURES_JSONL="$OUT_DIR/social_features_1h.jsonl"
FEATURES_CSV="$OUT_DIR/social_features_1h.csv"
CANDLES_CSV="$OUT_DIR/candles_1h.csv"
MERGED_CSV="$OUT_DIR/candles_1h.social_merged.csv"

python3 -m user_data.scripts.social.social_cli features-1h \
  --input-jsonl "$NORM_JSONL" \
  --output-jsonl "$FEATURES_JSONL" \
  --output-csv "$FEATURES_CSV"

python3 -m user_data.scripts.social.social_cli merge-with-candles \
  --candles-csv "$CANDLES_CSV" \
  --social-features-csv "$FEATURES_CSV" \
  --output-csv "$MERGED_CSV"

test -f "$FEATURES_JSONL"
test -f "$FEATURES_CSV"
test -f "$MERGED_CSV"

head -n 3 "$MERGED_CSV"
ls -lh "$OUT_DIR"

