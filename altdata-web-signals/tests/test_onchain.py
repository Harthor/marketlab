"""Tests for on-chain signal builder (Mempool.space + DeFiLlama)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from altdata_web_signals.fetchers.onchain import (
    PREFIX,
    build_btc_fee_rate,
    build_btc_mempool,
    build_eth_defi_tvl,
    build_eth_l2_tvl,
    build_eth_stablecoin_supply,
    fetch_onchain_signals,
    run_quality_checks,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Adapter tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestEthDefiTvl:
    def test_parse_defillama_tvl(self):
        fixture = json.loads((FIXTURES / "defillama_eth_tvl_sample.json").read_text())
        client = MagicMock()
        client.get_json.return_value = fixture

        start = datetime(2020, 1, 1, tzinfo=UTC)
        end = datetime(2020, 2, 1, tzinfo=UTC)
        df = build_eth_defi_tvl(client, start, end)

        assert df.shape[0] > 0
        assert "ts_utc" in df.columns
        col = f"{PREFIX}_eth_defi_tvl_total"
        assert col in df.columns
        assert f"{col}_pct_change_7d" in df.columns
        assert f"{col}_zscore_90d" in df.columns
        assert "asof_utc" in df.columns

    def test_empty_response(self):
        client = MagicMock()
        client.get_json.return_value = []

        start = datetime(2020, 1, 1, tzinfo=UTC)
        end = datetime(2020, 2, 1, tzinfo=UTC)
        df = build_eth_defi_tvl(client, start, end)
        assert df.is_empty()


class TestEthL2Tvl:
    def test_combines_three_chains(self):
        fixture = json.loads((FIXTURES / "defillama_eth_tvl_sample.json").read_text())
        client = MagicMock()
        client.get_json.return_value = fixture  # Same data for all 3 chains

        start = datetime(2020, 1, 1, tzinfo=UTC)
        end = datetime(2020, 2, 1, tzinfo=UTC)
        df = build_eth_l2_tvl(client, start, end)

        assert df.shape[0] > 0
        col = f"{PREFIX}_eth_l2_tvl_total"
        assert col in df.columns
        # TVL should be 3x because all 3 chains return same data
        first_val = df[col][0]
        single_chain_df = build_eth_defi_tvl(client, start, end)
        single_first = single_chain_df[f"{PREFIX}_eth_defi_tvl_total"][0]
        assert abs(first_val - single_first * 3) < 1.0


class TestStablecoinSupply:
    def test_parse_stablecoin(self):
        fixture = json.loads((FIXTURES / "stablecoin_usdt_sample.json").read_text())
        client = MagicMock()
        client.get_json.return_value = fixture

        start = datetime(2020, 1, 1, tzinfo=UTC)
        end = datetime(2020, 2, 1, tzinfo=UTC)
        df = build_eth_stablecoin_supply(client, start, end)

        assert df.shape[0] > 0
        col = f"{PREFIX}_eth_stablecoin_supply"
        assert col in df.columns
        # Both USDT and USDC mocked with same fixture → supply = 2× USDT
        assert df[col][0] == pytest.approx(40_000_000_000.0)


class TestBtcMempool:
    def test_parse_mempool_snapshot(self):
        fixture = json.loads((FIXTURES / "mempool_sample.json").read_text())
        client = MagicMock()
        client.get_json.return_value = fixture

        df = build_btc_mempool(client)
        assert df.shape[0] == 1
        col = f"{PREFIX}_btc_mempool_vbytes"
        assert col in df.columns
        assert df[col][0] == 125_000_000.0

    def test_error_returns_empty(self):
        client = MagicMock()
        client.get_json.side_effect = RuntimeError("Network error")

        df = build_btc_mempool(client)
        assert df.is_empty()


class TestBtcFeeRate:
    def test_parse_fee_blocks(self):
        fixture = json.loads((FIXTURES / "mempool_fee_blocks_sample.json").read_text())
        client = MagicMock()
        client.get_json.return_value = fixture

        df = build_btc_fee_rate(client)
        assert df.shape[0] == 1
        col = f"{PREFIX}_btc_median_fee_rate"
        assert col in df.columns
        assert df[col][0] == 15.5  # medianFee from first block


# ---------------------------------------------------------------------------
# Quality checks tests
# ---------------------------------------------------------------------------


class TestQualityChecks:
    def _make_df(self, values: list[float], *, dates_start: str = "2024-01-01") -> tuple[pl.DataFrame, str]:
        col = f"{PREFIX}_test_signal"
        start = datetime.fromisoformat(dates_start).replace(tzinfo=UTC)
        df = pl.DataFrame({
            "ts_utc": [start + __import__("datetime").timedelta(days=i) for i in range(len(values))],
            col: values,
        })
        return df, col

    def test_oc001_no_duplicates_pass(self):
        df, col = self._make_df([1.0, 2.0, 3.0])
        report = run_quality_checks(df, col, "test")
        assert any(n.check_id == "OC001" and n.level == "pass" for n in report.notes)

    def test_oc001_duplicates_fail(self):
        col = f"{PREFIX}_test_signal"
        ts = datetime(2024, 1, 1, tzinfo=UTC)
        df = pl.DataFrame({
            "ts_utc": [ts, ts, ts + __import__("datetime").timedelta(days=1)],
            col: [1.0, 2.0, 3.0],
        })
        report = run_quality_checks(df, col, "test")
        assert any(n.check_id == "OC001" and n.level == "fail" for n in report.notes)

    def test_oc003_flatline_warn(self):
        # 10 identical values → should trigger flatline warning
        df, col = self._make_df([5.0] * 10)
        report = run_quality_checks(df, col, "test")
        assert any(n.check_id == "OC003" and n.level == "warn" for n in report.notes)

    def test_oc004_negative_warn(self):
        df, col = self._make_df([-1.0, 2.0, 3.0])
        report = run_quality_checks(df, col, "test")
        assert any(n.check_id == "OC004" and n.level == "warn" for n in report.notes)

    def test_oc004_empty_fail(self):
        col = f"{PREFIX}_test_signal"
        df = pl.DataFrame({"ts_utc": [], col: []}).cast(
            {"ts_utc": pl.Datetime("us", "UTC"), col: pl.Float64}
        )
        report = run_quality_checks(df, col, "test")
        assert report.status == "fail"

    def test_overall_status_pass(self):
        df, col = self._make_df(list(range(1, 32)))
        report = run_quality_checks(df, col, "test")
        assert report.status == "pass"


# ---------------------------------------------------------------------------
# Builder integration test
# ---------------------------------------------------------------------------


class TestFetchOnchainSignals:
    @patch("altdata_web_signals.fetchers.onchain.ApiClient")
    def test_builder_writes_parquets(self, MockClient, tmp_path):
        """Test the full builder pipeline with mocked HTTP."""
        fixture = json.loads((FIXTURES / "defillama_eth_tvl_sample.json").read_text())

        mock_client = MagicMock()
        mock_client.get_json.return_value = fixture
        MockClient.return_value = mock_client

        outputs = fetch_onchain_signals(
            start="2020-01-01",
            end="2020-02-01",
            signals_root=str(tmp_path / "signals"),
            freq="1d",
            cache_dir=str(tmp_path / "cache"),
        )

        # Should have written at least some DeFiLlama parquets
        assert len(outputs) > 0

        # Check manifest exists
        manifest_path = tmp_path / "signals" / "onchain" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["run_type"] == "onchain_builder"
        assert manifest["status"] in ("success", "partial")
