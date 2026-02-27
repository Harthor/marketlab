from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

@dataclass
class WorkspacePaths:
    workspace_dir: Path
    notes_file: Path
    sentiment_file: Path
    backtest_file: Path

def _ensure(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("", encoding="utf-8")

def append_section(path: Path, title: str, body: str) -> None:
    _ensure(path)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    chunk = f"\n\n## {title}\n\n_{stamp}_\n\n{body.strip()}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(chunk)

def write_snapshot(path: Path, body: str) -> None:
    _ensure(path)
    path.write_text(body.strip() + "\n", encoding="utf-8")
