"""Solana wallet tracker — fetches recent transactions via RPC."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Public Solana RPC endpoints (free, rate-limited)
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


class SolanaTracker:
    """Fetch recent Solana transactions for tracked wallets."""

    def __init__(self, rpc_url: str = DEFAULT_RPC_URL, timeout: float = 30.0):
        self.rpc_url = rpc_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _rpc_call(self, method: str, params: list[Any]) -> dict[str, Any]:
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        resp = await client.post(self.rpc_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            logger.error("Solana RPC error: %s", data["error"])
            return {}
        return data.get("result", {})

    async def get_recent_signatures(
        self, address: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent transaction signatures for a wallet.

        Returns list of dicts with: signature, slot, blockTime, err, memo.
        """
        result = await self._rpc_call(
            "getSignaturesForAddress",
            [address, {"limit": limit}],
        )
        if not isinstance(result, list):
            return []
        return result

    async def get_transaction(self, signature: str) -> dict[str, Any]:
        """Get full transaction details by signature."""
        result = await self._rpc_call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        return result if isinstance(result, dict) else {}

    async def get_token_accounts(self, address: str) -> list[dict[str, Any]]:
        """Get all SPL token accounts for a wallet."""
        result = await self._rpc_call(
            "getTokenAccountsByOwner",
            [
                address,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"},
            ],
        )
        if not isinstance(result, dict):
            return []
        accounts = result.get("value", [])
        parsed = []
        for acct in accounts:
            info = (
                acct.get("account", {})
                .get("data", {})
                .get("parsed", {})
                .get("info", {})
            )
            token_amount = info.get("tokenAmount", {})
            parsed.append({
                "mint": info.get("mint", ""),
                "owner": info.get("owner", ""),
                "amount": float(token_amount.get("uiAmount", 0) or 0),
                "decimals": token_amount.get("decimals", 0),
            })
        return [p for p in parsed if p["amount"] > 0]

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
