#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

import streamlit as st


def show_key_value(title: str, value: Any) -> None:
    st.markdown(f"**{title}:** {value}")


def show_metrics_cards(metrics: dict[str, Any]) -> None:
    cols = st.columns(6)
    cols[0].metric("Trades", int(metrics.get("trades", 0) or 0))
    cols[1].metric("Trades/day", f"{float(metrics.get('trades_per_day', 0.0)):.2f}")
    cols[2].metric("Profit %", f"{float(metrics.get('profit_total_pct', 0.0)):.2f}")
    cols[3].metric("Winrate %", f"{float(metrics.get('winrate_pct', 0.0)):.2f}")
    pf = metrics.get("profit_factor")
    cols[4].metric("Profit Factor", "n/a" if pf is None else f"{float(pf):.3f}")
    cols[5].metric("Max DD %", f"{float(metrics.get('max_drawdown_pct', 0.0)):.2f}")


def show_artifacts(artifacts: dict[str, Any]) -> None:
    st.markdown("**Artifacts**")
    for key in ["backtest_meta_json", "backtest_export_json", "summary_md"]:
        st.code(f"{key}: {artifacts.get(key)}")
    extra = artifacts.get("extra_files", []) or []
    if extra:
        st.markdown("**Extra files**")
        for p in extra:
            st.code(p)


def show_prompt_copy_area(content: str, key: str) -> None:
    st.text_area("Prompt (copy/pegar)", value=content, height=320, key=key)
