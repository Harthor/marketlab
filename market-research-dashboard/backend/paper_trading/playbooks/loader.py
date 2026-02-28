"""Playbook YAML loader with Pydantic validation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs" / "playbooks"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ConditionConfig(BaseModel):
    """A single condition: field + operator + value."""

    field: str
    operator: str = "gte"
    value: Any = None

    @field_validator("operator")
    @classmethod
    def valid_operator(cls, v: str) -> str:
        allowed = {"gt", "gte", "lt", "lte", "eq", "neq", "in", "not_in", "between"}
        if v not in allowed:
            msg = f"operator must be one of {allowed}, got '{v}'"
            raise ValueError(msg)
        return v


class ConfidenceComponent(BaseModel):
    """One weighted component of the confidence score."""

    field: str
    weight: float = 1.0
    func: str = "ramp"
    lo: float = 0.0
    hi: float = 100.0

    @field_validator("func")
    @classmethod
    def valid_func(cls, v: str) -> str:
        allowed = {"ramp", "inv_ramp", "boolf", "clip01", "raw"}
        if v not in allowed:
            msg = f"func must be one of {allowed}, got '{v}'"
            raise ValueError(msg)
        return v


class PlaybookConfig(BaseModel):
    """Full playbook configuration loaded from YAML."""

    name: str
    slug: str
    description: str = ""
    version: str = "1.0"
    enabled: bool = True

    # Signal evaluation
    required: list[ConditionConfig] = Field(default_factory=list)
    confirmations: list[ConditionConfig] = Field(default_factory=list)
    vetos: list[ConditionConfig] = Field(default_factory=list)

    # Confidence scoring
    base_confidence: float = 0.5
    confidence_components: list[ConfidenceComponent] = Field(default_factory=list)

    # Priority inputs
    edge_prior: float = 1.0

    # Regime fit — maps regime name → multiplier [0, 1]
    regime_fit: dict[str, float] = Field(default_factory=dict)

    # Filters
    chains: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    min_age_hours: float = 0
    max_age_hours: float = 0
    min_liquidity_usd: float = 0
    min_volume_24h_usd: float = 0
    min_market_cap_usd: float = 0


class PortfolioRiskConfig(BaseModel):
    """Global portfolio risk limits."""

    max_positions: int = 10
    max_per_chain: int = 5
    max_per_bucket: int = 3
    max_daily_trades: int = 20
    circuit_breaker_drawdown_pct: float = 25.0
    circuit_breaker_loss_streak: int = 5
    max_correlated_exposure_pct: float = 30.0


class GlobalConfig(BaseModel):
    """Global configuration loaded from _global.yml."""

    vetos: list[ConditionConfig] = Field(default_factory=list)
    filters: list[ConditionConfig] = Field(default_factory=list)
    portfolio_risk: PortfolioRiskConfig = Field(
        default_factory=PortfolioRiskConfig,
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class PlaybookLoader:
    """Load and cache playbook configs from YAML files."""

    def __init__(self, configs_dir: Path | None = None) -> None:
        self.configs_dir = configs_dir or CONFIGS_DIR
        self._playbooks: dict[str, PlaybookConfig] = {}
        self._global: GlobalConfig | None = None
        self._loaded = False

    def load(self) -> None:
        """Load all playbooks and global config from disk."""
        self._playbooks.clear()
        self._global = None

        if not self.configs_dir.exists():
            logger.warning("Playbook configs dir not found: %s", self.configs_dir)
            self._loaded = True
            return

        # Load _global.yml
        global_path = self.configs_dir / "_global.yml"
        if global_path.exists():
            raw = yaml.safe_load(global_path.read_text()) or {}
            self._global = GlobalConfig(**raw)
        else:
            self._global = GlobalConfig()

        # Load playbook files
        for path in sorted(self.configs_dir.glob("*.yml")):
            if path.name.startswith("_"):
                continue
            try:
                raw = yaml.safe_load(path.read_text()) or {}
                pb = PlaybookConfig(**raw)
                self._playbooks[pb.slug] = pb
                logger.debug("Loaded playbook: %s", pb.slug)
            except Exception:
                logger.exception("Failed to load playbook %s", path.name)

        self._loaded = True
        logger.info(
            "Loaded %d playbooks + global config", len(self._playbooks),
        )

    def get_playbooks(self) -> list[PlaybookConfig]:
        """Return all enabled playbooks."""
        if not self._loaded:
            self.load()
        return [p for p in self._playbooks.values() if p.enabled]

    def get_playbook(self, slug: str) -> PlaybookConfig | None:
        """Return a specific playbook by slug."""
        if not self._loaded:
            self.load()
        return self._playbooks.get(slug)

    def get_global(self) -> GlobalConfig:
        """Return global config."""
        if not self._loaded:
            self.load()
        return self._global or GlobalConfig()

    def reload(self) -> None:
        """Force reload all configs."""
        self._loaded = False
        self.load()
