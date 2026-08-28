"""Load demographic and demand-norm YAMLs.

Two configs feed this module:

  * config/demographics.yaml  - WHO lives in the district (population counts,
                                income mix, age structure, employment mix).
  * config/demand_norms.yaml  - WHAT each person/worker needs (URDPFI per-capita
                                norms for schools, healthcare, retail, office,
                                industry, hospitality, open space).

The pair is validated and exposed as `Demographics` and `DemandNorms` dataclass
instances. Anything downstream (`requirements.py`, the optimiser) reads these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_DEMOGRAPHICS_PATH = (
    Path(__file__).parent.parent / "config" / "demographics.yaml"
)
DEFAULT_DEMAND_NORMS_PATH = (
    Path(__file__).parent.parent / "config" / "demand_norms.yaml"
)


# ---------------------------------------------------------------------------
# Demographics
# ---------------------------------------------------------------------------
@dataclass
class Demographics:
    """Population, income, age, and employment of the district."""

    total_population: int = 0
    income_shares: Dict[str, float] = field(default_factory=dict)
    household_size_by_income: Dict[str, float] = field(default_factory=dict)
    age_structure: Dict[str, float] = field(default_factory=dict)
    worker_share_of_population: float = 0.36
    employment_mix: Dict[str, float] = field(default_factory=dict)
    school_enrolment_rate: float = 0.92

    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "Demographics":
        """Load demographic inputs from YAML.

        Returns
        -------
        Demographics
            Parsed and validated demographic inputs.
        """
        path = Path(path) if path else DEFAULT_DEMOGRAPHICS_PATH
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        d = cls(
            total_population=int(raw.get("population", {}).get("total", 0)),
            income_shares=raw.get("income_shares", {}),
            household_size_by_income=raw.get("household_size_by_income", {}),
            age_structure=raw.get("age_structure", {}),
            worker_share_of_population=float(
                raw.get("worker_share_of_population", 0.36)
            ),
            employment_mix=raw.get("employment_mix", {}),
            school_enrolment_rate=float(raw.get("school_enrolment_rate", 0.92)),
        )
        d.validate()
        return d

    def validate(self) -> None:
        """Validate demographic shares and population counts.

        Returns
        -------
        None
        """
        if self.total_population <= 0:
            raise ValueError("demographics: total_population must be > 0")
        for name, shares in (
            ("income_shares", self.income_shares),
            ("age_structure", self.age_structure),
            ("employment_mix", self.employment_mix),
        ):
            s = sum(shares.values())
            if abs(s - 1.0) > 0.01:
                raise ValueError(f"demographics.{name} sums to {s:.3f}, expected 1.0")

    # ----- derived counts ---------------------------------------------
    def households_by_income(self) -> Dict[str, int]:
        """Compute household counts per income class.

        pop_in_class = population × income_share[class]
        households   = pop_in_class / household_size[class]

        Returns
        -------
        Dict[str, int]
            Household count by income class.
        """
        out: Dict[str, int] = {}
        for cls, share in self.income_shares.items():
            pop = self.total_population * share
            hh_size = self.household_size_by_income.get(cls, 4.0)
            out[cls] = int(round(pop / hh_size))
        return out

    def total_households(self) -> int:
        """Return the total household count across all income classes.

        Returns
        -------
        int
            Total households in the district.
        """
        return sum(self.households_by_income().values())

    def children_count(self) -> int:
        """Return the estimated under-18 population.

        Returns
        -------
        int
            Count of children in the district.
        """
        return int(round(self.total_population
                         * self.age_structure.get("under_18", 0.30)))

    def working_age_count(self) -> int:
        """Return the estimated working-age population.

        Returns
        -------
        int
            Count of people aged 18 to 64.
        """
        return int(round(self.total_population
                         * self.age_structure.get("age_18_to_64", 0.62)))

    def workers_count(self) -> int:
        """Return the estimated worker count.

        Returns
        -------
        int
            Total economically active workers.
        """
        return int(round(self.total_population * self.worker_share_of_population))

    def workers_by_sector(self) -> Dict[str, int]:
        """Return worker counts split by employment sector.

        Returns
        -------
        Dict[str, int]
            Worker count by sector key.
        """
        total = self.workers_count()
        return {sector: int(round(total * share))
                for sector, share in self.employment_mix.items()}


# ---------------------------------------------------------------------------
# DemandNorms
# ---------------------------------------------------------------------------
@dataclass
class DemandNorms:
    """Per-capita / per-worker norms for converting people into floor area."""

    education: Dict[str, Any] = field(default_factory=dict)
    healthcare: Dict[str, Any] = field(default_factory=dict)
    retail: Dict[str, Any] = field(default_factory=dict)
    office: Dict[str, Any] = field(default_factory=dict)
    industry: Dict[str, Any] = field(default_factory=dict)
    hospitality: Dict[str, Any] = field(default_factory=dict)
    open_space: Dict[str, Any] = field(default_factory=dict)
    blue_space: Dict[str, Any] = field(default_factory=dict)
    religious: Dict[str, Any] = field(default_factory=dict)
    solar: Dict[str, Any] = field(default_factory=dict)
    public_services: Dict[str, Any] = field(default_factory=dict)
    parking: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "DemandNorms":
        """Load per-capita and per-worker demand norms from YAML.

        Returns
        -------
        DemandNorms
            Parsed demand-norm tables.
        """
        path = Path(path) if path else DEFAULT_DEMAND_NORMS_PATH
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls(
            education=raw.get("education", {}),
            healthcare=raw.get("healthcare", {}),
            retail=raw.get("retail", {}),
            office=raw.get("office", {}),
            industry=raw.get("industry", {}),
            hospitality=raw.get("hospitality", {}),
            open_space=raw.get("open_space", {}),
            blue_space=raw.get("blue_space", {}),
            religious=raw.get("religious", {}),
            solar=raw.get("solar", {}),
            public_services=raw.get("public_services", {}),
            parking=raw.get("parking", {}),
        )


# ---------------------------------------------------------------------------
# Cached singletons
# ---------------------------------------------------------------------------
_cached_demo: Optional[Demographics] = None
_cached_norms: Optional[DemandNorms] = None


def load_demographics(force_reload: bool = False) -> Demographics:
    """Get cached demographics, loading the YAML on first use.

    Returns
    -------
    Demographics
        Cached or freshly loaded demographic inputs.
    """
    global _cached_demo
    if _cached_demo is None or force_reload:
        _cached_demo = Demographics.from_yaml()
    return _cached_demo


def load_demand_norms(force_reload: bool = False) -> DemandNorms:
    """Get cached demand norms, loading the YAML on first use.

    Returns
    -------
    DemandNorms
        Cached or freshly loaded demand-norm inputs.
    """
    global _cached_norms
    if _cached_norms is None or force_reload:
        _cached_norms = DemandNorms.from_yaml()
    return _cached_norms


if __name__ == "__main__":
    demo = load_demographics()
    norms = load_demand_norms()

    print(f"loaded demographics for {demo.total_population:,} people")
    print(f"  households: {demo.total_households():,}")
    for cls, n in demo.households_by_income().items():
        print(f"    {cls:<6}: {n:>6,} hh")
    print(f"  children:    {demo.children_count():>6,}")
    print(f"  working age: {demo.working_age_count():>6,}")
    print(f"  workers:     {demo.workers_count():>6,}")
    for s, n in demo.workers_by_sector().items():
        print(f"    {s:<22}: {n:>6,}")

    print(f"\nloaded demand norms")
    print(f"  retail:      {norms.retail.get('m2_per_capita')} m²/person")
    print(f"  office:      "
          f"{norms.office.get('m2_per_professional_worker')} m²/professional")
    print(f"  healthcare:  "
          f"{norms.healthcare.get('beds_per_1000_population')} beds/1000")
    print(f"  open space:  {norms.open_space.get('m2_per_capita_total')} m²/person")
