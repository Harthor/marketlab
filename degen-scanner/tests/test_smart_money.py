"""Tests for smart money wallet tracking module."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from degen_scanner.smart_money.features import (
    compute_accumulation_signal,
    compute_smart_money_features,
    detect_first_buys,
)
from degen_scanner.smart_money.parser import (
    ParsedTransaction,
    parse_evm_normal_transactions,
    parse_evm_token_transfers,
    parse_solana_signatures,
    parse_solana_transaction,
)
from degen_scanner.smart_money.registry import TrackedWallet, WalletRegistry
from degen_scanner.smart_money.storage import SmartMoneyStorage


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------
class TestWalletRegistry:
    def test_load_from_yaml(self, tmp_path: Path):
        yaml_content = """
schema_version: 1
kind: wallet_registry
wallets:
  - address: "ABC123"
    chain: solana
    label: "test_wallet"
    tier: A
    tags: [whale, early_buyer]
    notes: "Test wallet"
  - address: "0xDEF456"
    chain: base
    label: "evm_wallet"
    tier: B
    tags: [degen_farmer]
"""
        config_file = tmp_path / "wallet_registry.yaml"
        config_file.write_text(yaml_content)

        registry = WalletRegistry(config_path=config_file)
        assert len(registry.wallets) == 2

    def test_by_chain(self, tmp_path: Path):
        yaml_content = """
wallets:
  - address: "SOL1"
    chain: solana
    label: "sol1"
    tier: A
    tags: []
  - address: "0xEVM1"
    chain: base
    label: "evm1"
    tier: B
    tags: []
  - address: "SOL2"
    chain: solana
    label: "sol2"
    tier: C
    tags: []
"""
        config_file = tmp_path / "wallet_registry.yaml"
        config_file.write_text(yaml_content)
        registry = WalletRegistry(config_path=config_file)

        assert len(registry.by_chain("solana")) == 2
        assert len(registry.by_chain("base")) == 1
        assert len(registry.by_chain("bsc")) == 0

    def test_by_tier(self, tmp_path: Path):
        yaml_content = """
wallets:
  - address: "W1"
    chain: solana
    label: "w1"
    tier: A
    tags: []
  - address: "W2"
    chain: base
    label: "w2"
    tier: A
    tags: []
  - address: "W3"
    chain: bsc
    label: "w3"
    tier: B
    tags: []
"""
        config_file = tmp_path / "wallet_registry.yaml"
        config_file.write_text(yaml_content)
        registry = WalletRegistry(config_path=config_file)

        assert len(registry.by_tier("A")) == 2
        assert len(registry.by_tier("B")) == 1

    def test_by_tag(self, tmp_path: Path):
        yaml_content = """
wallets:
  - address: "W1"
    chain: solana
    label: "w1"
    tier: A
    tags: [whale, early_buyer]
  - address: "W2"
    chain: base
    label: "w2"
    tier: B
    tags: [whale]
"""
        config_file = tmp_path / "wallet_registry.yaml"
        config_file.write_text(yaml_content)
        registry = WalletRegistry(config_path=config_file)

        assert len(registry.by_tag("whale")) == 2
        assert len(registry.by_tag("early_buyer")) == 1

    def test_get_wallet(self, tmp_path: Path):
        yaml_content = """
wallets:
  - address: "0xAbCdEf"
    chain: base
    label: "test"
    tier: A
    tags: []
"""
        config_file = tmp_path / "wallet_registry.yaml"
        config_file.write_text(yaml_content)
        registry = WalletRegistry(config_path=config_file)

        # Case-insensitive lookup
        w = registry.get("0xabcdef")
        assert w is not None
        assert w.label == "test"

        assert registry.get("nonexistent") is None

    def test_missing_file(self, tmp_path: Path):
        registry = WalletRegistry(config_path=tmp_path / "missing.yaml")
        assert len(registry.wallets) == 0

    def test_tracked_wallet_properties(self):
        w = TrackedWallet(
            address="0x123", chain="base", label="test", tier="A", tags=["whale"]
        )
        assert w.poll_interval_seconds == 300
        assert w.is_evm is True

        w_sol = TrackedWallet(
            address="SOL1", chain="solana", label="sol", tier="C"
        )
        assert w_sol.poll_interval_seconds == 3600
        assert w_sol.is_evm is False


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------
class TestParser:
    def test_parse_solana_signatures(self):
        sigs = [
            {
                "signature": "sig1",
                "slot": 100,
                "blockTime": 1700000000,
                "err": None,
            },
            {
                "signature": "sig2",
                "slot": 101,
                "blockTime": 1700000100,
                "err": {"InstructionError": [0, "Custom"]},
            },
        ]
        result = parse_solana_signatures(sigs, "WALLET_ADDR", "test_label")
        assert len(result) == 1  # sig2 skipped due to error
        assert result[0].tx_hash == "sig1"
        assert result[0].chain == "solana"
        assert result[0].wallet_label == "test_label"

    def test_parse_solana_transaction_buy(self):
        tx_data = {
            "slot": 200,
            "blockTime": 1700000000,
            "transaction": {"signatures": ["sig_buy"]},
            "meta": {
                "err": None,
                "preTokenBalances": [],
                "postTokenBalances": [
                    {
                        "owner": "WALLET",
                        "mint": "TOKEN_MINT",
                        "uiTokenAmount": {"uiAmount": 1000.0, "decimals": 6},
                    }
                ],
            },
        }
        result = parse_solana_transaction(tx_data, "WALLET", "label")
        assert result is not None
        assert result.direction == "buy"
        assert result.token_address == "TOKEN_MINT"
        assert result.amount_tokens == 1000.0

    def test_parse_solana_transaction_failed(self):
        tx_data = {
            "meta": {"err": {"InstructionError": [0, "Custom"]}},
        }
        result = parse_solana_transaction(tx_data, "WALLET")
        assert result is None

    def test_parse_evm_token_transfers(self):
        transfers = [
            {
                "hash": "0xabc",
                "from": "0xwallet",
                "to": "0xdex",
                "value": "1000000000000000000",
                "tokenDecimal": "18",
                "tokenSymbol": "TEST",
                "contractAddress": "0xtoken",
                "timeStamp": "1700000000",
                "blockNumber": "100",
            },
            {
                "hash": "0xdef",
                "from": "0xdex",
                "to": "0xwallet",
                "value": "500000000",
                "tokenDecimal": "6",
                "tokenSymbol": "USDC",
                "contractAddress": "0xusdc",
                "timeStamp": "1700000100",
                "blockNumber": "101",
            },
        ]
        result = parse_evm_token_transfers(transfers, "0xwallet", "label", "base")
        assert len(result) == 2
        assert result[0].direction == "sell"
        assert result[0].amount_tokens == 1.0
        assert result[1].direction == "buy"
        assert result[1].amount_tokens == 500.0

    def test_parse_evm_normal_transactions(self):
        txs = [
            {
                "hash": "0x111",
                "from": "0xwallet",
                "to": "0xother",
                "value": "2000000000000000000",
                "timeStamp": "1700000000",
                "blockNumber": "50",
            },
        ]
        result = parse_evm_normal_transactions(txs, "0xwallet", "label", "base")
        assert len(result) == 1
        assert result[0].direction == "transfer_out"
        assert result[0].amount_tokens == 2.0

    def test_parsed_transaction_asset_uid(self):
        tx = ParsedTransaction(
            tx_hash="test",
            wallet_address="W1",
            chain="solana",
            block_time=datetime.now(UTC),
            direction="buy",
            token_address="TOKEN123",
        )
        assert tx.asset_uid == "solana:TOKEN123"

        tx_empty = ParsedTransaction(
            tx_hash="test2",
            wallet_address="W1",
            chain="solana",
            block_time=datetime.now(UTC),
            direction="buy",
        )
        assert tx_empty.asset_uid == ""


# ---------------------------------------------------------------------------
# Features tests
# ---------------------------------------------------------------------------
class TestFeatures:
    def _make_wallets(self) -> list[TrackedWallet]:
        return [
            TrackedWallet(address="W1", chain="solana", label="w1", tier="A", tags=["whale"]),
            TrackedWallet(address="W2", chain="solana", label="w2", tier="B", tags=["early_buyer"]),
            TrackedWallet(address="W3", chain="base", label="w3", tier="A", tags=["whale"]),
        ]

    def _make_buy_tx(
        self, wallet: str, token: str, chain: str = "solana", hours_ago: float = 1
    ) -> ParsedTransaction:
        return ParsedTransaction(
            tx_hash=f"tx_{wallet}_{token}",
            wallet_address=wallet,
            chain=chain,
            block_time=datetime.now(UTC) - timedelta(hours=hours_ago),
            direction="buy",
            token_address=token,
            amount_tokens=100.0,
            amount_usd=500.0,
        )

    def test_consensus_accumulate(self):
        wallets = self._make_wallets()
        txs = [
            self._make_buy_tx("W1", "TOKEN_A"),
            self._make_buy_tx("W2", "TOKEN_A"),
            self._make_buy_tx("W3", "TOKEN_A", chain="base"),
        ]
        features = compute_smart_money_features(txs, wallets)
        assert "solana:TOKEN_A" in features
        feat = features["solana:TOKEN_A"]
        assert feat["consensus_direction"] == "accumulate"
        assert feat["unique_wallets_buying"] >= 2
        assert feat["tier_a_active"] is True

    def test_consensus_distribute(self):
        wallets = self._make_wallets()
        txs = [
            ParsedTransaction(
                tx_hash="sell1", wallet_address="W1", chain="solana",
                block_time=datetime.now(UTC) - timedelta(hours=1),
                direction="sell", token_address="TOKEN_B", amount_tokens=50.0,
            ),
            ParsedTransaction(
                tx_hash="sell2", wallet_address="W2", chain="solana",
                block_time=datetime.now(UTC) - timedelta(hours=1),
                direction="sell", token_address="TOKEN_B", amount_tokens=30.0,
            ),
        ]
        features = compute_smart_money_features(txs, wallets)
        feat = features["solana:TOKEN_B"]
        assert feat["consensus_direction"] == "distribute"

    def test_old_transactions_excluded(self):
        wallets = self._make_wallets()
        txs = [self._make_buy_tx("W1", "OLD_TOKEN", hours_ago=100)]
        features = compute_smart_money_features(txs, wallets, lookback_hours=72)
        assert len(features) == 0

    def test_whale_buy_count(self):
        wallets = self._make_wallets()
        txs = [
            self._make_buy_tx("W1", "TOKEN_C"),
            self._make_buy_tx("W3", "TOKEN_C", chain="base"),
        ]
        features = compute_smart_money_features(txs, wallets)
        # W1 and W3 are tagged "whale"
        assert features["solana:TOKEN_C"]["whale_buy_count"] >= 1

    def test_detect_first_buys(self):
        txs = [
            ParsedTransaction(
                tx_hash="first", wallet_address="W1", chain="solana",
                block_time=datetime.now(UTC), direction="buy",
                token_address="NEW_TOKEN",
            ),
            ParsedTransaction(
                tx_hash="repeat", wallet_address="W1", chain="solana",
                block_time=datetime.now(UTC), direction="buy",
                token_address="OLD_TOKEN",
            ),
        ]
        history = {"w1": {"solana:OLD_TOKEN"}}
        first = detect_first_buys(txs, history)
        assert "solana:NEW_TOKEN" in first
        assert "solana:OLD_TOKEN" not in first

    def test_accumulation_signal(self):
        features = {
            "solana:STRONG": {
                "consensus_direction": "accumulate",
                "consensus_score": 80.0,
                "unique_wallets_buying": 3,
                "tier_a_active": True,
                "accumulation_net_usd": 1500.0,
            },
            "solana:WEAK": {
                "consensus_direction": "accumulate",
                "consensus_score": 30.0,
                "unique_wallets_buying": 1,
                "tier_a_active": False,
                "accumulation_net_usd": 100.0,
            },
        }
        signals = compute_accumulation_signal(features, min_wallets=2, min_consensus=50.0)
        assert len(signals) == 1
        assert signals[0]["asset_uid"] == "solana:STRONG"


# ---------------------------------------------------------------------------
# Storage tests
# ---------------------------------------------------------------------------
class TestStorage:
    def test_save_and_load_features(self, tmp_path: Path):
        storage = SmartMoneyStorage(base_dir=tmp_path)
        features = {
            "solana:TOKEN": {
                "consensus_score": 75.0,
                "consensus_direction": "accumulate",
            }
        }
        path = storage.save_features(features)
        assert path.exists()

        loaded = storage.load_latest_features()
        assert loaded["solana:TOKEN"]["consensus_score"] == 75.0

    def test_save_transactions(self, tmp_path: Path):
        storage = SmartMoneyStorage(base_dir=tmp_path)
        txs = [{"tx_hash": "abc", "direction": "buy", "asset_uid": "solana:X"}]
        path = storage.save_transactions("WALLET_ADDR", "solana", txs)
        assert path.exists()

    def test_load_wallet_history(self, tmp_path: Path):
        storage = SmartMoneyStorage(base_dir=tmp_path)
        txs = [
            {"tx_hash": "t1", "asset_uid": "solana:A"},
            {"tx_hash": "t2", "asset_uid": "solana:B"},
        ]
        storage.save_transactions("WALLET_12345", "solana", txs)

        history = storage.load_wallet_history("WALLET_12345")
        assert "solana:A" in history
        assert "solana:B" in history

    def test_empty_features(self, tmp_path: Path):
        storage = SmartMoneyStorage(base_dir=tmp_path)
        assert storage.load_latest_features() == {}

    def test_directory_creation(self, tmp_path: Path):
        base = tmp_path / "new_dir"
        storage = SmartMoneyStorage(base_dir=base)
        assert storage.tx_dir.exists()
        assert storage.features_dir.exists()
        assert storage.snapshots_dir.exists()
