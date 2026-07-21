"""Load the Phase 5 analysis spec."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from seo_rank.stats.families import SignalFamily, SignalFamilyRegistry
from seo_rank.stats.families import load_signal_family_registry

logger = logging.getLogger(__name__)

ANALYSIS_SPEC_FILENAME = "analysis_spec.v1.2.yaml"


@dataclass(frozen=True)
class AnalysisSpec:
    """Parsed Phase 5 analysis specification."""

    path: Path
    source_path: Path
    data: Mapping[str, Any]
    _signal_families: SignalFamilyRegistry

    @property
    def version(self) -> str:
        return str(self.data["version"])

    @property
    def estimand_version(self) -> str:
        return self.version

    @property
    def primary_backend(self) -> str:
        return str(self.data["decision"]["primary_backend"])

    @property
    def backend_order(self) -> tuple[str, ...]:
        return self.signal_families.similarity_keys

    @property
    def panel_grain(self) -> tuple[str, ...]:
        return self.signal_families.panel_grain

    @property
    def signal_families(self) -> SignalFamilyRegistry:
        return self._signal_families

    @property
    def signal_family_keys(self) -> tuple[str, ...]:
        return self.signal_families.keys

    def signal_family(self, family_key: str) -> SignalFamily:
        return self.signal_families.family(family_key)

    @property
    def estimand(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self.data["estimand"]))

    @property
    def multivariate_vif_threshold(self) -> float:
        return float(self.data["sensitivity"]["multivariate_vif_threshold"])

    @property
    def backend_drop_order(self) -> tuple[str, ...]:
        return tuple(str(backend) for backend in self.data["sensitivity"]["backend_drop_order"])

    @property
    def primary_rank_depth(self) -> str:
        return str(self.data["rank_depths"]["primary"])

    @property
    def confirmatory_rank_depths(self) -> tuple[str, ...]:
        depth_order = self.data["rank_depths"]["confirmatory_order"]
        return tuple(str(depth_key) for depth_key in depth_order)

    def rank_depth_limit(self, depth_key: str) -> int:
        limits = self.data["rank_depths"]["limits"]
        return int(limits[depth_key])

    def limitation_key_for_rank_depth(self, depth_key: str) -> str:
        limitations_by_depth = self.data["limitations_by_depth"]
        return str(limitations_by_depth[depth_key])

    @property
    def entity_signal_policy(self) -> Mapping[str, int | float]:
        configured = self.data.get("entity_signals", {})
        if not isinstance(configured, Mapping):
            raise ValueError("entity_signals must be a mapping")
        defaults: dict[str, int | float] = {
            "min_present_pages": 10,
            "min_present_keywords": 3,
            "min_inference_keywords": 10,
            "bh_q": 0.05,
        }
        return MappingProxyType({**defaults, **configured})


def load_analysis_spec(path: Path | str | None = None) -> AnalysisSpec:
    """Load the committed analysis spec from disk."""

    requested_path = Path(path) if path is not None else Path(ANALYSIS_SPEC_FILENAME)
    source_path = _resolve_analysis_spec_path(requested_path)
    with source_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("analysis spec must load as a mapping")
    signal_families = _load_signal_families(loaded)
    backend_order = tuple(str(backend) for backend in loaded["decision"]["backend_order"])
    if backend_order != signal_families.similarity_keys:
        raise ValueError("decision.backend_order must match similarity signal families")
    primary_backend = str(loaded["decision"]["primary_backend"])
    if primary_backend != signal_families.similarity_keys[0]:
        raise ValueError("decision.primary_backend must match the first similarity signal family")
    backend_drop_order = tuple(str(backend) for backend in loaded["sensitivity"]["backend_drop_order"])
    if backend_drop_order[-1] != primary_backend:
        raise ValueError("sensitivity.backend_drop_order must keep the primary backend last")
    expected_drop_order = tuple(reversed(signal_families.similarity_keys))
    if backend_drop_order != expected_drop_order:
        raise ValueError("sensitivity.backend_drop_order must match the reverse similarity backend order")
    analysis_spec = AnalysisSpec(
        path=requested_path,
        source_path=source_path,
        data=MappingProxyType(dict(loaded)),
        _signal_families=signal_families,
    )
    logger.info(
        "loaded analysis spec version=%s source=%s primary_rank_depth=%s depths=%s",
        analysis_spec.version,
        source_path,
        analysis_spec.primary_rank_depth,
        list(analysis_spec.confirmatory_rank_depths),
    )
    return analysis_spec


def _load_signal_families(loaded: Mapping[str, Any]) -> SignalFamilyRegistry:
    panel = loaded.get("panel")
    if not isinstance(panel, Mapping):
        raise ValueError("analysis spec panel must be a mapping")
    panel_grain = panel.get("grain")
    signal_families = loaded.get("signal_families")
    if not isinstance(signal_families, Mapping):
        raise ValueError("analysis spec must define signal_families")
    registry = load_signal_family_registry(
        panel_grain=panel_grain,
        raw_spec=signal_families,
    )
    return registry


def _resolve_analysis_spec_path(requested_path: Path) -> Path:
    if requested_path.exists():
        return requested_path

    for parent in Path(__file__).resolve().parents:
        candidate = parent / requested_path
        if candidate.exists():
            return candidate

    raise FileNotFoundError(requested_path)
