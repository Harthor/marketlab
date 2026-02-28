"""EVM wallet tracker — fetches recent transactions via Etherscan V2 API."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Etherscan V2 supports multiple chains via chainid parameter
ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"

# Chain IDs for supported networks
CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "base": 8453,
    "bsc": 56,
    "arbitrum": 42161,
    "polygon": 137,
}


class EVMTracker:
    """Fetch recent EVM transactions using Etherscan V2 multi-chain API."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("ETHERSCAN_API_KEY", "")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _api_call(
        self, chain: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        chain_id = CHAIN_IDS.get(chain)
        if chain_id is None:
            logger.warning("Unsupported EVM chain: %s", chain)
            return []

        params = {
            **params,
            "chainid": chain_id,
            "apikey": self.api_key,
        }
        client = await self._get_client()
        resp = await client.get(ETHERSCAN_V2_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "1":
            msg = data.get("message", "Unknown error")
            if "No transactions found" in msg:
                return []
            logger.warning("Etherscan error for %s: %s", chain, msg)
            return []

        return data.get("result", [])

    async def get_normal_transactions(
        self,
        address: str,
        chain: str,
        start_block: int = 0,
        end_block: int = 99999999,
        page: int = 1,
        offset: int = 20,
        sort: str = "desc",
    ) -> list[dict[str, Any]]:
        """Get normal (ETH/native) transactions for a wallet."""
        return await self._api_call(chain, {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
        })

    async def get_token_transfers(
        self,
        address: str,
        chain: str,
        start_block: int = 0,
        end_block: int = 99999999,
        page: int = 1,
        offset: int = 50,
        sort: str = "desc",
    ) -> list[dict[str, Any]]:
        """Get ERC-20 token transfers for a wallet."""
        return await self._api_call(chain, {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
        })

    async def get_token_balance(
        self, address: str, contract_address: str, chain: str
    ) -> float:
        """Get ERC-20 token balance for a wallet."""
        result = await self._api_call(chain, {
            "module": "account",
            "action": "tokenbalance",
            "address": address,
            "contractaddress": contract_address,
        })
        if isinstance(result, str):
            try:
                return float(result)
            except ValueError:
                return 0.0
        return 0.0

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
