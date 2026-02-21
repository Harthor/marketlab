#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any

INFRA_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"could not contact dns servers", re.IGNORECASE), "dns_unreachable"),
    (re.compile(r"temporary failure in name resolution", re.IGNORECASE), "dns_temporary_failure"),
    (re.compile(r"name or service not known", re.IGNORECASE), "dns_name_not_known"),
    (re.compile(r"network is unreachable", re.IGNORECASE), "network_unreachable"),
    (re.compile(r"connection reset", re.IGNORECASE), "connection_reset"),
    (re.compile(r"connection aborted", re.IGNORECASE), "connection_aborted"),
    (re.compile(r"requesttimeout", re.IGNORECASE), "request_timeout"),
    (re.compile(r"\btimed out\b", re.IGNORECASE), "network_timeout"),
    (re.compile(r"exchangenotavailable", re.IGNORECASE), "exchange_not_available"),
    (re.compile(r"networkerror", re.IGNORECASE), "network_error"),
    (re.compile(r"temporaryerror: error in reload_markets", re.IGNORECASE), "reload_markets_error"),
    (re.compile(r"could not load markets", re.IGNORECASE), "load_markets_error"),
    (re.compile(r"exchangeinfo", re.IGNORECASE), "exchange_info_error"),
    (re.compile(r"ccxt", re.IGNORECASE), "ccxt_network_error"),
]


def detect_infra_failure(output_text: str, returncode: int) -> dict[str, Any]:
    if returncode == 0:
        return {"is_infra": False, "reason": None, "pattern": None}
    for pattern, reason in INFRA_PATTERNS:
        if pattern.search(output_text):
            return {"is_infra": True, "reason": reason, "pattern": pattern.pattern}
    return {"is_infra": False, "reason": None, "pattern": None}


def run_cmd(cmd: list[str], cwd: Path | None = None, output_tail_chars: int = 4000) -> dict[str, Any]:
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    out = (res.stdout or "") + "\n" + (res.stderr or "")
    infra = detect_infra_failure(out, res.returncode)
    return {
        "cmd": " ".join(cmd),
        "returncode": res.returncode,
        "output_tail": out[-output_tail_chars:],
        "is_infra": infra["is_infra"],
        "infra_reason": infra["reason"],
        "infra_pattern": infra["pattern"],
    }


def run_with_retries(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    attempts: int = 3,
    base_delay_sec: float = 2.0,
    backoff_mult: float = 2.0,
    output_tail_chars: int = 4000,
) -> dict[str, Any]:
    attempts = max(1, int(attempts))
    delay = max(0.0, float(base_delay_sec))
    backoff = max(1.0, float(backoff_mult))

    attempt_rows: list[dict[str, Any]] = []
    final_detail: dict[str, Any] | None = None

    for idx in range(1, attempts + 1):
        detail = run_cmd(cmd, cwd=cwd, output_tail_chars=output_tail_chars)
        detail["attempt"] = idx
        attempt_rows.append(detail)
        final_detail = detail

        if detail["returncode"] == 0:
            break

        if not detail["is_infra"]:
            break

        if idx < attempts and delay > 0:
            detail["sleep_before_next_sec"] = round(delay * (backoff ** (idx - 1)), 3)
            time.sleep(detail["sleep_before_next_sec"])

    if final_detail is None:
        return {
            "status": "fail",
            "retryable": False,
            "attempts": attempt_rows,
            "final": None,
        }

    if final_detail["returncode"] == 0:
        status = "ok"
        retryable = False
    elif final_detail["is_infra"]:
        status = "infra_fail"
        retryable = True
    else:
        status = "fail"
        retryable = False

    return {
        "status": status,
        "retryable": retryable,
        "attempts": attempt_rows,
        "final": final_detail,
    }

