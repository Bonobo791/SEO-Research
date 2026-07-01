"""Load the Phase 5 analysis spec."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml


ANALYSIS_SPEC_FILENAME = "analysis_spec.v1.yaml"


@dataclass(frozen=True)
class AnalysisSpec:
    """Parsed Phase 5 analysis specification."""

    path: Path
    source_path: Path
    data: Mapping[str, Any]

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
        backend_order = self.data["decision"]["backend_order"]
        return tuple(str(backend) for backend in backend_order)

    @property
    def estimand(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self.data["estimand"]))


def load_analysis_spec(path: Path | str | None = None) -> AnalysisSpec:
    """Load the committed analysis spec from disk."""

    requested_path = Path(path) if path is not None else Path(ANALYSIS_SPEC_FILENAME)
    source_path = _resolve_analysis_spec_path(requested_path)
    with source_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("analysis spec must load as a mapping")
    return AnalysisSpec(
        path=requested_path,
        source_path=source_path,
        data=MappingProxyType(dict(loaded)),
    )


def _resolve_analysis_spec_path(requested_path: Path) -> Path:
    if requested_path.exists():
        return requested_path

    for parent in Path(__file__).resolve().parents:
        candidate = parent / requested_path
        if candidate.exists():
            return candidate

    raise FileNotFoundError(requested_path)
