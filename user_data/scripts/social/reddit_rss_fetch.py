#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def get_child_text(node: ET.Element, candidates: list[str]) -> str:
    wanted = {c.lower() for c in candidates}
    for child in list(node):
        if local_name(child.tag).lower() in wanted:
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def parse_time_to_utc(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""

    # RFC822 (RSS) and ISO8601 (Atom) tolerant parsing.
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass

    try:
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return raw


def find_feed_items(root: ET.Element) -> list[ET.Element]:
    items: list[ET.Element] = []
    for node in root.iter():
        name = local_name(node.tag).lower()
        if name in {"item", "entry"}:
            items.append(node)
    return items


def extract_link(node: ET.Element) -> str:
    direct = get_child_text(node, ["link"])
    if direct:
        return direct

    # Atom feeds commonly store link in href attributes.
    for child in list(node):
        if local_name(child.tag).lower() == "link":
            href = (child.attrib.get("href") or "").strip()
            if href:
                return href
    return ""


def extract_author(node: ET.Element) -> str:
    direct = get_child_text(node, ["author", "dc:creator", "creator"])
    if direct:
        return direct

    for child in list(node):
        if local_name(child.tag).lower() == "author":
            name = get_child_text(child, ["name"])
            if name:
                return name
            txt = (child.text or "").strip()
            if txt:
                return txt
    return ""


def extract_summary(node: ET.Element) -> str:
    return get_child_text(node, ["summary", "description", "content", "content:encoded"])


def load_sources(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("sources config must be a JSON list")
    out: list[dict[str, Any]] = []
    for src in data:
        if not isinstance(src, dict):
            continue
        if not src.get("enabled", False):
            continue
        if not src.get("url"):
            continue
        out.append(src)
    out.sort(key=lambda s: (int(s.get("priority", 0)), str(s.get("id", ""))), reverse=True)
    return out


def fetch_xml(url: str, timeout: float, user_agent: str) -> bytes:
    req = Request(url=url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_source(source: dict[str, Any], payload: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    items = find_feed_items(root)
    out: list[dict[str, Any]] = []
    subreddit = str(source.get("subreddit", "") or "").strip()

    for item in items:
        title = get_child_text(item, ["title"])
        link = extract_link(item)
        published_raw = get_child_text(item, ["published", "updated", "pubdate", "dc:date"])
        author = extract_author(item)
        summary = extract_summary(item)
        guid = get_child_text(item, ["guid", "id"])

        out.append(
            {
                "source": "reddit_rss",
                "subreddit": subreddit,
                "title": title,
                "link": link,
                "published_utc": parse_time_to_utc(published_raw) if published_raw else "",
                "author": author,
                "summary": summary,
                "guid": guid,
            }
        )
    return out


def dedupe_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    dupes = 0
    for row in rows:
        key = (row.get("guid") or row.get("link") or "").strip()
        if not key:
            key = f"{row.get('subreddit','')}::{row.get('title','')}::{row.get('published_utc','')}"
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        out.append(row)
    return out, dupes


def setup_logger(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir / f"reddit_rss_fetch_{ts}.log"

    logger = logging.getLogger("reddit_rss_fetch")
    logger.setLevel(logging.INFO)
    logger.handlers = []

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger, log_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch enabled Reddit RSS feeds for social research.")
    parser.add_argument(
        "--sources-config",
        default="user_data/configs/reddit_rss_sources.json",
        help="Path to RSS sources JSON config.",
    )
    parser.add_argument(
        "--output-json",
        default="user_data/research/out/reddit_rss_latest.json",
        help="Output JSON path for normalized RSS items.",
    )
    parser.add_argument(
        "--log-dir",
        default="user_data/logs",
        help="Directory where fetch logs are written.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="Per-feed timeout in seconds.")
    parser.add_argument(
        "--user-agent",
        default="market-sentiment-lab/1.0 (+https://github.com/Harthor/market-sentiment-lab)",
        help="HTTP User-Agent for RSS requests.",
    )
    args = parser.parse_args()

    sources_path = Path(args.sources_config)
    output_path = Path(args.output_json)
    log_dir = Path(args.log_dir)

    logger, log_path = setup_logger(log_dir)
    logger.info("rss_fetch_start sources_config=%s output_json=%s", sources_path, output_path)

    if not sources_path.exists():
        logger.error("sources config not found: %s", sources_path)
        return 2

    try:
        sources = load_sources(sources_path)
    except Exception as exc:
        logger.error("failed to load sources config: %s", exc)
        return 2

    rows_all: list[dict[str, Any]] = []
    feed_errors: list[dict[str, str]] = []
    processed = 0

    for source in sources:
        src_id = str(source.get("id", ""))
        url = str(source.get("url", ""))
        try:
            payload = fetch_xml(url=url, timeout=args.timeout, user_agent=args.user_agent)
            rows = parse_source(source, payload)
            rows_all.extend(rows)
            processed += 1
            logger.info("feed_ok id=%s rows=%d url=%s", src_id, len(rows), url)
        except (HTTPError, URLError, TimeoutError, ET.ParseError, OSError) as exc:
            feed_errors.append({"id": src_id, "url": url, "error": str(exc)})
            logger.warning("feed_error id=%s url=%s error=%s", src_id, url, exc)
        except Exception as exc:  # Keep fetch resilient.
            feed_errors.append({"id": src_id, "url": url, "error": str(exc)})
            logger.warning("feed_error id=%s url=%s error=%s", src_id, url, exc)

    deduped, duplicates_removed = dedupe_rows(rows_all)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at_utc": utc_now_iso(),
        "source": "reddit_rss",
        "sources_total": len(sources),
        "sources_ok": processed,
        "sources_failed": len(feed_errors),
        "rows_total": len(rows_all),
        "rows_deduped": len(deduped),
        "duplicates_removed": duplicates_removed,
        "items": deduped,
        "errors": feed_errors,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logger.info(
        "rss_fetch_done sources_ok=%d sources_failed=%d rows_out=%d output_json=%s log_path=%s",
        processed,
        len(feed_errors),
        len(deduped),
        output_path,
        log_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
