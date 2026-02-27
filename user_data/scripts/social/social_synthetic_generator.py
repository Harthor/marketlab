from __future__ import annotations

from datetime import datetime, timedelta, timezone


def generate_synthetic_events(n: int = 12, now_utc: datetime | None = None) -> list[dict]:
    now = now_utc or datetime.now(timezone.utc)
    symbols = ["BTC", "ETH", "SOL", "ARB", "XRP", "BNB"]
    rows: list[dict] = []
    for i in range(max(0, n)):
        sym = symbols[i % len(symbols)]
        ts = now - timedelta(minutes=i * 7)
        rows.append(
            {
                "event_id": f"mock-{i:04d}",
                "source": "mock",
                "ts_utc": ts.isoformat(),
                "text": f"{sym} momentum sample event {i}",
                "author": f"mock_user_{i % 5}",
                "channel_or_subreddit": "mock_feed",
                "url": "",
                "engagement_score": float((i % 9) + 1),
                "metadata": {"symbols_detected": [sym]},
            }
        )
    return rows

