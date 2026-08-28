"""Load and validate the district configuration YAML.

The YAML file at `config/district_composition.yaml` is the single source of
truth for all district-level numbers (income mix, area targets, PV acceptance,
height tiers, site coordinates). Code reads from a `DistrictConfig` instance
loaded once at startup and never edits the dataclass after that - so swapping
in real data is a YAML edit, not a code change.

Validation rules:
  * Land-use target shares must sum to 1.0 within +/- 0.01.
  * Income shares must sum to 1.0 within +/- 0.01.
  * Every land-use named in `land_use_targets` must match a LandUse enum.
  * Every category named in `pv_acceptance` must match a built-cell category.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .land_use import CATEGORY_CATALOGUE, LandUse


DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent / "config" / "district_composition.yaml"
)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class DistrictConfig:
    """All district-level parameters loaded from YAML."""

    site: Dict[str, Any] = field(default_factory=dict)
    land_use_targets: Dict[LandUse, float] = field(default_factory=dict)
    income_shares: Dict[str, float] = field(default_factory=dict)
    household_floor_area_m2: Dict[str, float] = field(default_factory=dict)
    height_tiers: Dict[str, float] = field(default_factory=dict)
    height_multipliers: Dict[str, float] = field(default_factory=dict)
    floor_area_per_cell_m2: Dict[str, float] = field(default_factory=dict)
    floor_to_floor_m: float = 3.0
    pv_acceptance: Dict[str, float] = field(default_factory=dict)
    # PV module efficiency (kWp per m^2 of panel area at STC).
    # refactor: replaces the hardcoded "/6.0" rule in Building.deployable_pv_kwp
    # so the panel-efficiency assumption is explicit and tunable. Orthogonal
    # to pv_acceptance (usable-roof fraction) and pv_capacity_factor (yield).
    #: default realigned 0.20 -> 0.1930 to match the live
    # `rooftop_module_efficiency` in district_composition.yaml. The 0.20 here
    # silently encoded the PRE- value, so any construction that skipped
    # the YAML got PV capacity 3.6% high with no warning. The YAML remains the
    # single source of truth; this default only applies when it is absent.
    rooftop_module_efficiency: float = 0.1930
    permeability: Dict[str, str] = field(default_factory=dict)
    optimisation: Dict[str, Any] = field(default_factory=dict)
    # (Claude 2 critical-review #4): catchment radii (m) and
    # the per-quadrant park-cell minimum, all moved from hardcoded Python
    # constants in `layout/constraints.py` to YAML. Anchoring document:
    # URDPFI 2014 §8.2 Table 2. Loaders in `layout/constraints.py` consume
    # these via the function-default values; old constants now wrap these
    # for back-compat.
    constraint_catchments_m: Dict[str, float] = field(default_factory=dict)
    park_cells_per_quadrant_min: int = 4

    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "DistrictConfig":
        """Load from a YAML file. If `path` is None, use the default location.

        Returns
        -------
        DistrictConfig
            Parsed and validated district configuration.
        """
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not path.exists():
            raise FileNotFoundError(f"Config not found at {path}")

        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        # convert land_use_targets keys (strings) to LandUse enums
        lu_targets_raw = raw.get("land_use_targets", {})
        lu_targets: Dict[LandUse, float] = {}
        for name, share in lu_targets_raw.items():
            try:
                lu = LandUse(name)
            except ValueError as e:
                raise ValueError(
                    f"land_use_targets contains unknown LandUse {name!r}"
                ) from e
            lu_targets[lu] = float(share)

        cfg = cls(
            site=raw.get("site", {}),
            land_use_targets=lu_targets,
            income_shares=raw.get("income_shares", {}),
            household_floor_area_m2=raw.get("household_floor_area_m2", {}),
            height_tiers=raw.get("height_tiers", {}),
            height_multipliers=raw.get("height_multipliers", {
                "short": 0.67, "medium": 1.0, "tall": 1.5,
            }),
            floor_area_per_cell_m2=raw.get("floor_area_per_cell_m2", {}),
            floor_to_floor_m=float(raw.get("floor_to_floor_m", 3.0)),
            pv_acceptance=raw.get("pv_acceptance", {}),
            rooftop_module_efficiency=float(
                raw.get("rooftop_module_efficiency", 0.20)
            ),
            permeability=raw.get("permeability", {}),
            optimisation=raw.get("optimisation", {}),
            constraint_catchments_m=raw.get("constraint_catchments_m", {}),
            park_cells_per_quadrant_min=int(
                raw.get("park_cells_per_quadrant_min", 4)
            ),
        )
        cfg.validate()
        return cfg

    # ---- validation -----------------------------------------------------
    def validate(self) -> None:
        """Raise ValueError on any inconsistency.

        Returns
        -------
        None
        """
        # land-use shares
        total_lu = sum(self.land_use_targets.values())
        if abs(total_lu - 1.0) > 0.01:
            raise ValueError(
                f"land_use_targets sum to {total_lu:.4f}, expected 1.0"
            )
        # income shares
        total_inc = sum(self.income_shares.values())
        if abs(total_inc - 1.0) > 0.01:
            raise ValueError(
                f"income_shares sum to {total_inc:.4f}, expected 1.0"
            )
        # pv_acceptance keys must match BuildingCategory.name for built cells
        built_category_names = {
            cat.name for cat in CATEGORY_CATALOGUE.values() if cat is not None
        }
        for name in self.pv_acceptance:
            if name not in built_category_names:
                raise ValueError(
                    f"pv_acceptance contains unknown category {name!r}. "
                    f"Known: {sorted(built_category_names)}"
                )
        # income share keys
        for name in self.income_shares:
            if name not in {"low", "mid", "high"}:
                raise ValueError(
                    f"income_shares uses unknown class {name!r}; "
                    f"expected one of low / mid / high"
                )
        # height tier keys ("ground": the Baseline 2 v7
        # G+1/G+2 solo-house tier - see core.grid.HeightTier.GROUND)
        for name in self.height_tiers:
            if name not in {"ground", "short", "medium", "tall"}:
                raise ValueError(
                    f"height_tiers uses unknown name {name!r}; "
                    f"expected one of ground / short / medium / tall"
                )

    # ---- convenience accessors -----------------------------------------
    def height_for(self, tier: str) -> float:
        """Return the height in metres for a tier name.

        Returns
        -------
        float
            Height in metres for the requested tier.
        """
        if tier not in self.height_tiers:
            raise KeyError(f"unknown height tier {tier!r}")
        return self.height_tiers[tier]

    def height_multiplier_for(self, tier: str) -> float:
        """Return the floor-area multiplier for a height tier (vs medium).

        Returns
        -------
        float
            Floor-area multiplier for the requested tier.
        """
        return float(self.height_multipliers.get(tier, 1.0))

    def floor_area_for_category(self, category_name: str) -> float:
        """Return medium-tier floor area per cell for a category (m^2).
        Returns 0 if the category is not listed.

        Returns
        -------
        float
            Medium-tier floor area per cell, in square metres.
        """
        return float(self.floor_area_per_cell_m2.get(category_name, 0.0))

    def household_floor_area_for(self, income_class: str) -> float:
        """Return per-household gross floor area in m^2 for an income class.

        Returns
        -------
        float
            Gross floor area per household, in square metres.
        """
        return float(self.household_floor_area_m2.get(income_class, 0.0))

    def acceptance_for(self, category_name: str) -> float:
        """Return PV acceptance fraction for a category. Defaults to 0.5
        if the category is not listed.

        Returns
        -------
        float
            PV acceptance fraction for the category.
        """
        return float(self.pv_acceptance.get(category_name, 0.5))


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_cached: Optional[DistrictConfig] = None


def load_config(path: Optional[Path] = None,
                force_reload: bool = False) -> DistrictConfig:
    """Get the cached DistrictConfig; load it on first call.

    Returns
    -------
    DistrictConfig
        Cached or freshly loaded district configuration.
    """
    global _cached
    if _cached is None or force_reload:
        _cached = DistrictConfig.from_yaml(path)
    return _cached


if __name__ == "__main__":
    cfg = load_config()
    print(f"loaded config from {DEFAULT_CONFIG_PATH.name}")
    print(f"  site: {cfg.site.get('name')!r}")
    print(f"  population: {cfg.site.get('total_population'):,}")
    print(f"  households: {cfg.site.get('total_households'):,}")
    print(f"  area: {cfg.site.get('area_km2')} km^2")
    print(f"  land-use targets: {len(cfg.land_use_targets)} entries, "
          f"sum {sum(cfg.land_use_targets.values()):.3f}")
    print(f"  income shares: {cfg.income_shares}")
    print(f"  height tiers: {cfg.height_tiers}")
    print(f"  pv acceptance entries: {len(cfg.pv_acceptance)}")
    print(f"  permeability: {cfg.permeability}")
