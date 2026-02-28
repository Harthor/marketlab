"""Transaction parser — normalizes raw Solana & EVM transactions into unified format."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ParsedTransaction(BaseModel):
    """Unified transaction representation across chains."""

    tx_hash: str
    wallet_address: str
    wallet_label: str = ""
    chain: str
    block_time: datetime
    direction: str  # "buy" | "sell" | "transfer_in" | "transfer_out"
    token_address: str = ""
    token_symbol: str = ""
    amount_tokens: float = 0.0
    amount_usd: float | None = None
    counterparty: str = ""
    dex_id: str = ""
    is_swap: bool = False
    raw_data: dict[str, Any] = Field(default_factory=dict)

    @property
    def asset_uid(self) -> str:
        if self.token_address:
            return f"{self.chain}:{self.token_address}"
        return ""


def parse_solana_signatures(
    signatures: list[dict[str, Any]],
    wallet_address: str,
    wallet_label: str = "",
) -> list[ParsedTransaction]:
    """Parse Solana getSignaturesForAddress results into ParsedTransactions.

    Note: This parses signature metadata only (no full tx details).
    For full parsing, get_transaction() is needed per signature.
    """
    parsed = []
    for sig_info in signatures:
        sig = sig_info.get("signature", "")
        block_time = sig_info.get("blockTime")
        err = sig_info.get("err")

        if err is not None:
            continue  # skip failed txs

        ts = datetime.fromtimestamp(block_time, tz=UTC) if block_time else datetime.now(UTC)

        parsed.append(ParsedTransaction(
            tx_hash=sig,
            wallet_address=wallet_address,
            wallet_label=wallet_label,
            chain="solana",
            block_time=ts,
            direction="transfer_out",  # placeholder — needs full tx parse
            raw_data=sig_info,
        ))
    return parsed


def parse_solana_transaction(
    tx_data: dict[str, Any],
    wallet_address: str,
    wallet_label: str = "",
) -> ParsedTransaction | None:
    """Parse a full Solana transaction (jsonParsed) into a ParsedTransaction."""
    if not tx_data:
        return None

    meta = tx_data.get("meta", {})
    if meta.get("err") is not None:
        return None

    block_time = tx_data.get("blockTime")
    ts = datetime.fromtimestamp(block_time, tz=UTC) if block_time else datetime.now(UTC)
    sig = tx_data.get("transaction", {}).get("signatures", [""])[0]

    # Analyze token balance changes to determine direction
    pre_balances = meta.get("preTokenBalances", [])
    post_balances = meta.get("postTokenBalances", [])

    direction = "transfer_out"
    token_address = ""
    amount = 0.0

    # Build map of owner -> mint -> balance change
    wallet_lower = wallet_address.lower()
    for post in post_balances:
        owner = (post.get("owner") or "").lower()
        if owner != wallet_lower:
            continue
        mint = post.get("mint", "")
        post_amount = float(post.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)

        # Find matching pre-balance
        pre_amount = 0.0
        for pre in pre_balances:
            if (pre.get("owner") or "").lower() == wallet_lower and pre.get("mint") == mint:
                pre_amount = float(pre.get("uiTokenAmount", {}).get("uiAmount", 0) or 0)
                break

        delta = post_amount - pre_amount
        if abs(delta) > abs(amount):
            amount = delta
            token_address = mint

    if amount > 0:
        direction = "buy"
    elif amount < 0:
        direction = "sell"

    return ParsedTransaction(
        tx_hash=sig,
        wallet_address=wallet_address,
        wallet_label=wallet_label,
        chain="solana",
        block_time=ts,
        direction=direction,
        token_address=token_address,
        amount_tokens=abs(amount),
        is_swap=len(pre_balances) > 0 or len(post_balances) > 0,
        raw_data={"slot": tx_data.get("slot")},
    )


def parse_evm_token_transfers(
    transfers: list[dict[str, Any]],
    wallet_address: str,
    wallet_label: str = "",
    chain: str = "base",
) -> list[ParsedTransaction]:
    """Parse Etherscan ERC-20 token transfer results into ParsedTransactions."""
    parsed = []
    wallet_lower = wallet_address.lower()

    for tx in transfers:
        from_addr = (tx.get("from") or "").lower()
        to_addr = (tx.get("to") or "").lower()

        if from_addr == wallet_lower:
            direction = "sell"
        elif to_addr == wallet_lower:
            direction = "buy"
        else:
            continue

        # Parse amount with decimals
        raw_value = tx.get("value", "0")
        decimals = int(tx.get("tokenDecimal", 18))
        try:
            amount = float(raw_value) / (10**decimals)
        except (ValueError, OverflowError):
            amount = 0.0

        block_time = tx.get("timeStamp", "0")
        try:
            ts = datetime.fromtimestamp(int(block_time), tz=UTC)
        except (ValueError, OSError):
            ts = datetime.now(UTC)

        parsed.append(ParsedTransaction(
            tx_hash=tx.get("hash", ""),
            wallet_address=wallet_address,
            wallet_label=wallet_label,
            chain=chain,
            block_time=ts,
            direction=direction,
            token_address=tx.get("contractAddress", ""),
            token_symbol=tx.get("tokenSymbol", ""),
            amount_tokens=amount,
            counterparty=to_addr if direction == "sell" else from_addr,
            raw_data={"blockNumber": tx.get("blockNumber")},
        ))

    return parsed


def parse_evm_normal_transactions(
    transactions: list[dict[str, Any]],
    wallet_address: str,
    wallet_label: str = "",
    chain: str = "base",
) -> list[ParsedTransaction]:
    """Parse Etherscan normal transaction results."""
    parsed = []
    wallet_lower = wallet_address.lower()

    for tx in transactions:
        from_addr = (tx.get("from") or "").lower()
        to_addr = (tx.get("to") or "").lower()

        if from_addr == wallet_lower:
            direction = "transfer_out"
        elif to_addr == wallet_lower:
            direction = "transfer_in"
        else:
            continue

        raw_value = tx.get("value", "0")
        try:
            amount = float(raw_value) / 1e18  # native token (18 decimals)
        except (ValueError, OverflowError):
            amount = 0.0

        block_time = tx.get("timeStamp", "0")
        try:
            ts = datetime.fromtimestamp(int(block_time), tz=UTC)
        except (ValueError, OSError):
            ts = datetime.now(UTC)

        parsed.append(ParsedTransaction(
            tx_hash=tx.get("hash", ""),
            wallet_address=wallet_address,
            wallet_label=wallet_label,
            chain=chain,
            block_time=ts,
            direction=direction,
            amount_tokens=amount,
            counterparty=to_addr if direction == "transfer_out" else from_addr,
            raw_data={"blockNumber": tx.get("blockNumber")},
        ))

    return parsed
