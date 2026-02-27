#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from ui_components import show_artifacts, show_key_value, show_metrics_cards, show_prompt_copy_area
from ui_data_access import (
    compare_result_vs_baseline,
    format_mtime,
    get_baseline,
    get_latest_ledger_row,
    get_status,
    get_ui_paths,
    latest_prompt_path,
    list_log_files,
    list_prompt_files,
    load_experiment_result,
    load_ledger_df,
    read_text_file,
    read_text_head,
    safe_read_json,
    tail_text_file,
)


st.set_page_config(page_title="Experiments Monitor", layout="wide")
st.title("Freqtrade Experiments Monitor")


@st.cache_data(show_spinner=False)
def cached_ledger() -> pd.DataFrame:
    return load_ledger_df(get_ui_paths(Path.cwd()))


@st.cache_data(show_spinner=False)
def cached_json(path_str: str):
    return safe_read_json(Path(path_str))


@st.cache_data(show_spinner=False)
def cached_text(path_str: str) -> str:
    return read_text_file(Path(path_str))


paths = get_ui_paths(Path.cwd())

with st.sidebar:
    st.header("Controls")
    if st.button("Refresh"):
        st.cache_data.clear()
        st.rerun()

    status = get_status(paths)
    st.subheader("Live Status")
    show_key_value("state", status.get("state", "idle"))
    show_key_value("current_task", status.get("current_task", "-"))
    show_key_value("progress", status.get("progress", 0))
    show_key_value("updated_at", status.get("updated_at", "-"))


tab_overview, tab_experiments, tab_compare, tab_prompts, tab_logs = st.tabs(
    ["Overview", "Experiments", "Compare", "Prompts", "Logs"]
)

with tab_overview:
    baseline_ref = get_baseline(paths)
    ledger_df = cached_ledger()
    latest_row = get_latest_ledger_row(ledger_df)
    prompt_path = latest_prompt_path(paths)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("Baseline")
        if baseline_ref:
            show_key_value("experiment_id", baseline_ref.get("experiment_id"))
            show_key_value("strategy", baseline_ref.get("strategy_name"))
            show_key_value("timeframe", baseline_ref.get("timeframe"))
            show_key_value("universe", baseline_ref.get("universe_label"))
        else:
            st.info("No baseline marcado todavía.")

    with col_b:
        st.subheader("Último experimento")
        if latest_row:
            show_key_value("experiment_id", latest_row.get("experiment_id"))
            show_key_value("strategy", latest_row.get("strategy_name"))
            show_key_value("timeframe", latest_row.get("timeframe"))
            show_key_value("universe", latest_row.get("universe_label"))
            show_key_value("status", latest_row.get("status"))
            show_key_value("notes", latest_row.get("notes_short", ""))
        else:
            st.info("Ledger vacío.")

    with col_c:
        st.subheader("Último prompt")
        if prompt_path:
            show_key_value("path", str(prompt_path))
            show_key_value("generated", format_mtime(prompt_path))
        else:
            st.info("No hay prompts generados aún.")

    st.markdown("---")

    if prompt_path:
        st.subheader("Preview último prompt")
        preview = read_text_head(prompt_path, lines=20)
        st.code(preview)
        show_prompt_copy_area(cached_text(str(prompt_path)), key="overview_prompt_copy")
    else:
        st.info("No se encontró prompt para mostrar preview.")

with tab_experiments:
    ledger_df = cached_ledger()
    if ledger_df.empty:
        st.warning("No se encontró ledger o está vacío.")
    else:
        st.subheader("Historial (ledger.csv)")

        c1, c2, c3, c4 = st.columns(4)
        strategies = sorted(x for x in ledger_df.get("strategy_name", pd.Series(dtype=str)).dropna().unique())
        timeframes = sorted(x for x in ledger_df.get("timeframe", pd.Series(dtype=str)).dropna().unique())
        universes = sorted(x for x in ledger_df.get("universe_label", pd.Series(dtype=str)).dropna().unique())
        statuses = sorted(x for x in ledger_df.get("status", pd.Series(dtype=str)).dropna().unique())

        selected_strategy = c1.multiselect("strategy_name", options=strategies, default=[])
        selected_timeframe = c2.multiselect("timeframe", options=timeframes, default=[])
        selected_universe = c3.multiselect("universe_label", options=universes, default=[])
        selected_status = c4.multiselect("status", options=statuses, default=[])

        c5, c6 = st.columns(2)
        min_trades = c5.number_input("min trades", min_value=0, value=0, step=1)

        has_created = "created_at" in ledger_df.columns and ledger_df["created_at"].notna().any()
        if has_created:
            min_date = ledger_df["created_at"].min().date()
            max_date = ledger_df["created_at"].max().date()
            date_range = c6.date_input("date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        else:
            date_range = None
            c6.info("Sin fecha parseable en ledger.")

        filtered = ledger_df.copy()
        if selected_strategy:
            filtered = filtered[filtered["strategy_name"].isin(selected_strategy)]
        if selected_timeframe:
            filtered = filtered[filtered["timeframe"].isin(selected_timeframe)]
        if selected_universe:
            filtered = filtered[filtered["universe_label"].isin(selected_universe)]
        if selected_status:
            filtered = filtered[filtered["status"].isin(selected_status)]
        if "trades" in filtered.columns:
            filtered = filtered[filtered["trades"].fillna(0) >= min_trades]
        if date_range and has_created and len(date_range) == 2:
            start_date, end_date = date_range
            mask = (filtered["created_at"].dt.date >= start_date) & (filtered["created_at"].dt.date <= end_date)
            filtered = filtered[mask]

        filtered = filtered.sort_values("created_at", ascending=False, na_position="last")
        st.dataframe(filtered, use_container_width=True)

        ids = filtered["experiment_id"].dropna().tolist() if "experiment_id" in filtered.columns else []
        if ids:
            selected_id = st.selectbox("Seleccionar experimento", options=ids)
            result = load_experiment_result(paths, selected_id)
            baseline_ref = get_baseline(paths)
            baseline_result = None
            if baseline_ref and baseline_ref.get("experiment_id"):
                baseline_result = load_experiment_result(paths, baseline_ref["experiment_id"])

            if not result:
                st.error("No se pudo cargar JSON del experimento seleccionado.")
            else:
                st.subheader("Detalle experimento")
                meta_cols = st.columns(4)
                meta_cols[0].metric("Strategy", result.get("strategy_name", "-"))
                meta_cols[1].metric("Timeframe", result.get("timeframe", "-"))
                meta_cols[2].metric("Universe", result.get("universe_label", "-"))
                meta_cols[3].metric("Status", result.get("status", "-"))

                show_metrics_cards(result.get("metrics", {}))

                delta = compare_result_vs_baseline(result, baseline_result)
                if delta:
                    st.info(
                        f"Vs baseline: delta PF {delta['delta_pf']:+.3f}, "
                        f"delta DD {delta['delta_dd_pct']:+.3f}pp"
                    )
                elif baseline_ref:
                    st.info("No se pudo calcular comparación contra baseline (datos incompletos).")

                show_artifacts(result.get("artifacts", {}))

                summary_path = result.get("artifacts", {}).get("summary_md")
                if summary_path and Path(summary_path).exists():
                    st.markdown("### Summary.md")
                    st.markdown(cached_text(summary_path))

                st.markdown("### JSON completo")
                st.json(result)
        else:
            st.info("No hay filas después de aplicar filtros.")

with tab_compare:
    ledger_df = cached_ledger()
    if ledger_df.empty or "experiment_id" not in ledger_df.columns:
        st.info("No hay experimentos para comparar.")
    else:
        options = ledger_df["experiment_id"].dropna().tolist()
        selected_ids = st.multiselect("experiment_id", options=options)
        if selected_ids:
            rows = []
            for exp_id in selected_ids:
                result = load_experiment_result(paths, exp_id)
                if not result:
                    continue
                m = result.get("metrics", {})
                rows.append(
                    {
                        "experiment_id": exp_id,
                        "strategy": result.get("strategy_name"),
                        "timeframe": result.get("timeframe"),
                        "universe": result.get("universe_label"),
                        "trades": m.get("trades"),
                        "trades_per_day": m.get("trades_per_day"),
                        "profit_total_pct": m.get("profit_total_pct"),
                        "winrate_pct": m.get("winrate_pct"),
                        "profit_factor": m.get("profit_factor"),
                        "max_drawdown_pct": m.get("max_drawdown_pct"),
                    }
                )

            cdf = pd.DataFrame(rows)
            if cdf.empty:
                st.warning("No se pudieron cargar detalles de los experimentos seleccionados.")
            else:
                best_pf = cdf["profit_factor"].max(skipna=True)
                best_dd = cdf["max_drawdown_pct"].min(skipna=True)

                def _style_row(row: pd.Series):
                    styles = ["" for _ in row.index]
                    if pd.notna(row.get("profit_factor")) and row["profit_factor"] == best_pf:
                        styles[row.index.get_loc("profit_factor")] = "background-color: #d1fae5"
                    if pd.notna(row.get("max_drawdown_pct")) and row["max_drawdown_pct"] == best_dd:
                        styles[row.index.get_loc("max_drawdown_pct")] = "background-color: #dbeafe"
                    return styles

                st.dataframe(cdf.style.apply(_style_row, axis=1), use_container_width=True)
                st.caption("Verde: mejor PF. Azul: menor DD.")

with tab_prompts:
    prompt_files = list_prompt_files(paths)
    if not prompt_files:
        st.info("No hay prompts generados.")
    else:
        selected_prompt = st.selectbox("Prompt file", options=prompt_files, format_func=lambda p: p.name)
        st.markdown(f"**Generated:** {format_mtime(selected_prompt)}")
        content = cached_text(str(selected_prompt))
        st.code(content)
        show_prompt_copy_area(content, key="prompt_copy_tab")

with tab_logs:
    log_files = list_log_files(paths)
    if not log_files:
        st.info("No hay logs del orquestador.")
    else:
        left, right = st.columns([2, 1])
        selected_log = left.selectbox("Log file", options=log_files, format_func=lambda p: p.name)
        tail_lines = right.slider("Tail lines", min_value=20, max_value=1000, value=200, step=20)

        auto_refresh = st.checkbox("Auto-refresh (if streamlit-autorefresh installed)", value=False)
        interval_sec = st.slider("Refresh interval (sec)", min_value=2, max_value=5, value=3)
        if auto_refresh:
            try:
                from streamlit_autorefresh import st_autorefresh

                st_autorefresh(interval=interval_sec * 1000, key="logs_refresh")
            except Exception:
                st.info("Install optional package for auto-refresh: pip install streamlit-autorefresh")

        st.code(tail_text_file(selected_log, lines=tail_lines))
