"""Storage for smart money data — transaction logs, features, snapshots."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SmartMoneyStorage:
    """Manage persistent storage for smart money tracking data."""

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = (
                Path(__file__).resolve().parent.parent.parent.parent
                / "src"
                / "degen_scanner"
                / "storage"
                / "smart_money"
            )
        self.base_dir = base_dir
        self.tx_dir = base_dir / "transactions"
        self.features_dir = base_dir / "features"
        self.snapshots_dir = base_dir / "snapshots"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in (self.tx_dir, self.features_dir, self.snapshots_dir):
            d.mkdir(parents=True, exist_ok=True)

    def save_transactions(
        self, wallet_address: str, chain: str, transactions: list[dict[str, Any]]
    ) -> Path:
        """Save parsed transactions for a wallet."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        filename = f"{chain}_{wallet_address[:12]}_{ts}.json"
        path = self.tx_dir / filename
        path.write_text(json.dumps(transactions, indent=2, default=str))
        return path

    def save_features(self, features: dict[str, dict[str, Any]]) -> Path:
        """Save computed smart money features."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        filename = f"sm_features_{ts}.json"
        path = self.features_dir / filename
        path.write_text(json.dumps(features, indent=2, default=str))
        return path

    def load_latest_features(self) -> dict[str, dict[str, Any]]:
        """Load the most recent features snapshot."""
        files = sorted(self.features_dir.glob("sm_features_*.json"), reverse=True)
        if not files:
            return {}
        return json.loads(files[0].read_text())

    def save_snapshot(self, snapshot: dict[str, Any]) -> Path:
        """Save a full smart money snapshot (features + metadata)."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        filename = f"sm_snapshot_{ts}.json"
        path = self.snapshots_dir / filename
        path.write_text(json.dumps(snapshot, indent=2, default=str))
        return path

    def load_wallet_history(self, wallet_address: str) -> set[str]:
        """Load historical asset_uids a wallet has traded.

        Scans saved transaction files to build the set.
        """
        asset_uids: set[str] = set()
        prefix = wallet_address[:12]
        for f in self.tx_dir.glob(f"*_{prefix}_*.json"):
            try:
                data = json.loads(f.read_text())
                for tx in data:
                    uid = tx.get("asset_uid", "")
                    if uid:
                        asset_uids.add(uid)
            except (json.JSONDecodeError, OSError):
                continue
        return asset_uids
