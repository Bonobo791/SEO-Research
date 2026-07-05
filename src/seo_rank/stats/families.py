"""Declarative signal-family registry for Phase 5 stats."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


VALID_SIGNAL_FAMILY_KINDS = frozenset(
    {
        "similarity",
        "backlinks_metric",
        "onpage_metric",
        "textrazor_scalar",
        "textrazor_structural",
    }
)

SOURCE_MART_BY_KIND = {
    "similarity": "analysis_mart",
    "backlinks_metric": "backlinks_analysis",
    "onpage_metric": "onpage_features",
    "textrazor_scalar": "textrazor_page_metrics",
    "textrazor_structural": "textrazor_page_metrics",
}

# Family-level Plackett-Luce runs one optimizer fit per signal × rank depth.
FAMILY_PLACKETT_LUCE_KINDS = frozenset(
    {
        "similarity",
        "backlinks_metric",
        "onpage_metric",
        "textrazor_scalar",
        "textrazor_structural",
    }
)


@dataclass(frozen=True)
class SignalFamily:
    """One ordered signal family in the Phase 5 registry."""

    key: str
    kind: str
    signal_columns: tuple[str, ...]


@dataclass(frozen=True)
class SignalFamilyRegistry:
    """Ordered signal-family taxonomy at the analysis panel grain."""

    panel_grain: tuple[str, ...]
    families: tuple[SignalFamily, ...]
    _families_by_key: Mapping[str, SignalFamily] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        families_by_key = {family.key: family for family in self.families}
        object.__setattr__(self, "_families_by_key", MappingProxyType(families_by_key))

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(family.key for family in self.families)

    @property
    def similarity_keys(self) -> tuple[str, ...]:
        return tuple(
            family.key
            for family in self.families
            if family.kind == "similarity"
        )

    @property
    def textrazor_keys(self) -> tuple[str, ...]:
        return tuple(
            family.key
            for family in self.families
            if family.kind.startswith("textrazor_")
        )

    def family(self, key: str) -> SignalFamily:
        try:
            return self._families_by_key[key]
        except KeyError as error:
            raise KeyError(f"unknown signal family: {key}") from error

    def families_by_kind(self, kind: str) -> tuple[SignalFamily, ...]:
        return tuple(family for family in self.families if family.kind == kind)

    def source_mart_for_family(self, key: str) -> str:
        family = self.family(key)
        return source_mart_for_family(family)


def load_signal_family_registry(
    *,
    panel_grain: Sequence[str],
    raw_spec: Mapping[str, Any],
) -> SignalFamilyRegistry:
    """Validate and load the declarative signal-family registry."""

    registry_panel_grain = _normalize_string_tuple(
        raw_spec.get("panel_grain"),
        field_name="signal_families.panel_grain",
    )
    requested_panel_grain = _normalize_string_tuple(
        panel_grain,
        field_name="panel.grain",
    )
    if registry_panel_grain != requested_panel_grain:
        raise ValueError(
            "signal_families.panel_grain must match panel.grain"
        )

    raw_families = raw_spec.get("families")
    if not isinstance(raw_families, Sequence) or isinstance(raw_families, (str, bytes)):
        raise ValueError("signal_families.families must be a sequence")
    if not raw_families:
        raise ValueError("signal_families.families must not be empty")

    families: list[SignalFamily] = []
    seen_keys: set[str] = set()
    for index, raw_family in enumerate(raw_families):
        family = _load_signal_family(raw_family, index=index)
        if family.key in seen_keys:
            raise ValueError(f"duplicate signal family key: {family.key}")
        seen_keys.add(family.key)
        families.append(family)

    _assert_unique_signal_columns_across_families(families)

    registry = SignalFamilyRegistry(
        panel_grain=requested_panel_grain,
        families=tuple(families),
    )
    return registry


def source_mart_for_family(family: SignalFamily) -> str:
    try:
        return SOURCE_MART_BY_KIND[family.kind]
    except KeyError as error:
        raise ValueError(f"unsupported signal family kind: {family.kind}") from error


def plackett_luce_enabled_for_family(family: SignalFamily) -> bool:
    """Return whether the family-level PL path should run for this family."""

    return family.kind in FAMILY_PLACKETT_LUCE_KINDS


def _load_signal_family(raw_family: Any, *, index: int) -> SignalFamily:
    if not isinstance(raw_family, Mapping):
        raise ValueError(f"signal_families.families[{index}] must be a mapping")

    key = _require_string(raw_family, "key", index=index)
    kind = _require_string(raw_family, "kind", index=index)
    if kind not in VALID_SIGNAL_FAMILY_KINDS:
        raise ValueError(f"signal family {key!r} has unsupported kind: {kind}")

    raw_columns = raw_family.get("signal_columns")
    signal_columns = _normalize_string_tuple(
        raw_columns,
        field_name=f"signal_families.families[{index}].signal_columns",
    )
    if not signal_columns:
        raise ValueError(f"signal family {key!r} must define signal_columns")

    return SignalFamily(
        key=key,
        kind=kind,
        signal_columns=signal_columns,
    )


def _assert_unique_signal_columns_across_families(
    families: Sequence[SignalFamily],
) -> None:
    seen: dict[str, str] = {}
    for family in families:
        for column in family.signal_columns:
            if column in seen:
                raise ValueError(
                    f"duplicate signal column {column!r}: "
                    f"used by {seen[column]!r} and {family.key!r}"
                )
            seen[column] = family.key


def _normalize_string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = tuple(part.strip() for part in value.replace("×", " x ").split(" x "))
        normalized = tuple(part for part in normalized if part)
    elif isinstance(value, Sequence) and not isinstance(value, bytes):
        normalized = tuple(str(item).strip() for item in value)
    else:
        raise ValueError(f"{field_name} must be a sequence of strings")
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(not item for item in normalized):
        raise ValueError(f"{field_name} must not contain blank values")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _require_string(raw_family: Mapping[str, Any], key: str, *, index: int) -> str:
    value = raw_family.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"signal_families.families[{index}].{key} must be a string")
    return value.strip()
