"""Stage B economics: load `config/economics.yaml` and expose INR cost
helpers used by the MILP and the merit-order fallback.

Path-1 refactor: 16 → 144 representative slices, 3 → 5 tariff
bands, 1 → 5 actor-tier discount rates, 2030-real INR base year, heating +
EV demand, day-type weighted profiles, microclimate coupling parameters,
inverter clipping. The legacy 16-slice / 3-band / single-discount-rate
API is no longer supported; older callers should use the new per-actor
helpers below.

Everything in this module is currency-pure INR. No GBP / USD conversions
appear anywhere. Energy is always kWh, capacity is kWp (PV nameplate),
kWh (battery usable) or "units" (V2G charger).

The headline outputs are:

  * `Economics`               - typed wrapper over `economics.yaml`
  * `crf(rate, n_years)`      - capital recovery factor
  * `annualised_capex(...)`   - levelised CAPEX in INR / yr
  * `TimeSlice`               - one of the 144 representative time slices
                                 (synthesized from dayparts × months)
  * `DesignDay`               - extreme-day feasibility slice (not in cost
                                 objective; constrains capacity)
  * `Scenario`                - which technologies are switched on
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


DEFAULT_ECONOMICS_PATH = (
    Path(__file__).parent.parent / "config" / "economics.yaml"
)

# Hours in a year used as the duration normaliser for the MILP. The 144
# representative slices in `economics.yaml` should sum to this.
HOURS_PER_YEAR = 8760

# Canonical month order used everywhere.
MONTHS: Tuple[str, ...] = (
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
)

# Days per month used by the A19 fog multiplier (non-leap year).
DAYS_IN_MONTH: Dict[str, int] = {
    "jan": 31, "feb": 28, "mar": 31, "apr": 30, "may": 31, "jun": 30,
    "jul": 31, "aug": 31, "sep": 30, "oct": 31, "nov": 30, "dec": 31,
}

# A19 PV soiling + fog multiplier calibration constants.
# `PV_SOILING_PER_PM25_UGM3` — fractional yield loss per µg/m³ of monthly
# PM2.5. Default 0.0006 ⇒ at PM2.5 = 100 µg/m³ the LP sees a 6 % monthly
# soiling penalty before rain recovery. Anchored to CSIR-CEERI Pilani /
# IIT Roorkee field measurements showing 5-8 % dry-season soiling for
# Punjab / Haryana plain.
# `PV_SOILING_RAIN_RECOVERY_PER_DAY` — fraction of accumulated soiling
# that one rain day "washes off". Default 0.005 ⇒ 1 rain day recovers
# 0.5 % yield. CALIBRATION CHECK: the 0.005 rate
# is INTENTIONAL, not a typo. Worked examples on Zirakpur climate.yaml:
#   * May (PM2.5 ~120 µg/m³, 2.2 rain days): gross 7.2 % - recovery 1.1 %
#     = 6.1 % net loss → multiplier 0.939. In CSIR-CEERI 5-8 % anchor.
#   * July (PM2.5 ~60 µg/m³, 9.8 rain days): gross 3.6 % - recovery 4.9 %
#     = -1.3 % → clamped to 0 → multiplier 1.0 (fully washed).
# A higher rate (e.g. 0.015) would push May below 4 % net, below the
# literature anchor. Keep 0.005 unless field data says otherwise.
# `PV_SOILING_FLOOR` — clamp on the worst monthly multiplier. Default
# 0.80 (matches the brief's [0.80, 1.00] envelope).
# `PV_FOG_DIFFUSE_YIELD_FRACTION` — yield retained on a fog day (direct
# beam ≈ 0, diffuse component still works at reduced intensity). Default
# 0.30 per the brief. CONSERVATIVENESS NOTE: IMD `fog_days` come from
# the 08:30 IST synoptic observation; fog typically lifts by 10-11 AM.
# Applying 0.30 across the WHOLE day is an upper bound on the loss.
# A finer model (Stage D / Stage F) could weight by hours-of-fog or
# split into early-morning + clear hours.
PV_SOILING_PER_PM25_UGM3: float = 0.0006
PV_SOILING_RAIN_RECOVERY_PER_DAY: float = 0.005
PV_SOILING_FLOOR: float = 0.80
PV_FOG_DIFFUSE_YIELD_FRACTION: float = 0.30

# (Bullet 4 dust-storm A19 wiring, Claude 2):
# `PV_SOILING_PER_DUST_STORM_DAY` — fractional yield loss contribution per
# IMD dust-storm day in the month (synoptic codes 30-35, sustained
# visibility reduction). Default 0.05 -> each dust event adds 5 %
# gross soiling that month before rain recovery. Anchored to CSIR-CEERI
# Pilani + IIT Roorkee NW-India dust-deposition studies showing a
# single significant dust event deposits ~10-20x the daily PM2.5
# baseline, equating to ~5-10 % gross soiling per event. Rain on
# subsequent days washes it via the existing recovery term, so the
# annual contribution for Chandigarh (~0.94 dust days/yr summed
# across months) is ~0.5 % extra yield loss — small but non-zero.
# Mostly bites pre-monsoon Apr/May (0.10 dust-days each, near-zero
# rain) where each event sits on dry panels until June rains arrive.
PV_SOILING_PER_DUST_STORM_DAY: float = 0.05

# Canonical daypart ids (must match `dayparts` in YAML).
DAYPARTS: Tuple[str, ...] = (
    "00_02", "02_04", "04_06", "06_08", "08_10", "10_12",
    "12_14", "14_16", "16_18", "18_20", "20_22", "22_24",
)

# Canonical actor tiers (must match keys in YAML `discount_rates`).
# (Opus 4.8): added `social_ews` — government-assisted EWS housing
# cost of capital (PMAY-U CLSS ~6%), the baseline financing actor for the EWS
# tier; `private_ews` (microfinance ~12.5%) retained as the self-financed
# sensitivity.
ACTOR_TIERS: Tuple[str, ...] = (
    "social_planner", "utility", "rwa_pooled",
    "private_high_income", "private_ews", "social_ews",
)


# ---------------------------------------------------------------------------
# Capital recovery factor
# ---------------------------------------------------------------------------
def crf(rate: float, n_years: int) -> float:
    """Capital recovery factor for `rate` discount over `n_years`.

    crf = r * (1+r)^n / ((1+r)^n - 1)

    Returns
    -------
    float
        Annuity factor in 1/year. Multiply a CAPEX by this to get an
        annualised cost (INR/yr).
    """
    if rate <= 0:
        return 1.0 / n_years
    factor = (1.0 + rate) ** n_years
    return rate * factor / (factor - 1.0)


def annualised_capex(
    capex_inr: float,
    rate: float,
    lifetime_years: int,
    eol_cost_fraction: float = 0.0,
) -> float:
    """Return the levelised annual cost in INR / yr of one CAPEX outlay.

    Parameters
    ----------
    capex_inr : float
        Up-front capital expenditure in INR.
    rate : float
        Real discount rate (e.g. 0.085 for RWA-pooled tier).
    lifetime_years : int
        Technology lifetime in years.
    eol_cost_fraction : float, default 0.0
 audit addition: fraction of original CAPEX that is
        spent at end-of-life on decommissioning, disposal, recycling, or
        replacement. Sources: CPCB PV-disposal norms ~3-5 % of new-panel
        cost; Li-ion recycling ~5-10 % of new-cell cost; biomass plant
        demolition ~3-5 %. Currently applied as a straight-line accrual
        (`capex * eol_fraction / lifetime`) -- no NPV discounting because
        the rounding-error vs CAPEX × CRF is < 0.5 %. Pass 0.0 (default)
        for back-compat with tests that pin the old CRF-only number.

    Returns
    -------
    float
        Annualised CAPEX in INR / yr including straight-line EOL accrual.
    """
    base = capex_inr * crf(rate, lifetime_years)
    if eol_cost_fraction > 0 and lifetime_years > 0:
        return base + capex_inr * eol_cost_fraction / lifetime_years
    return base


# ---------------------------------------------------------------------------
# TimeSlice
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TimeSlice:
    """One representative slice in the annual model.

    The 144-slice scheme (legacy, still the production default) bundles
    a daypart-of-month: ``jan_18_20`` = the 18:00-20:00 window across all
    31 days of January = 62 hours/year, with `weekday_share` /
    `weekend_share` / `festival_share` capturing the day-type
    distribution INSIDE that bundle.

    The 864-slice scheme ( refactor, opt-in via
    ``slices_per_year: 864`` in economics.yaml) unbundles into
    month × day_type × hour: ``jan_wd_18`` = 18:00-19:00 on weekdays of
    January only = 22 hours/year. Each 864-scheme slice carries its
    explicit `day_type` ("weekday" / "weekend" / "festival") and `hour`
    (0-23). The legacy fields are still populated for back-compat:
    `daypart` derived from hour, and `weekday_share` / `weekend_share` /
    `festival_share` = (1, 0, 0) for a weekday slice, (0, 1, 0) for a
    weekend slice, (0, 0, 1) for a festival slice. This lets existing
    daypart-keyed lookups (`pv_daypart_shape[s.daypart]`,
    `base_mult = wd*wd_share + we*we_share + fest*fest_share`) keep
    working without modification in the 864-slice path.

    Attributes
    ----------
    id : str
        Stable id, e.g. ``jan_18_20`` (144-slice) or ``jan_wd_18``
        (864-slice).
    month : str
        One of ``jan``... ``dec``.
    daypart : str
        One of ``00_02``... ``22_24``. In 864-slice mode, derived from
        ``hour`` via the standard 2-hour bin map.
    hours_per_year : int
        Annual duration of this slice in hours. 144-slice mode:
        2 × days_in_month. 864-slice mode: 1 × days_of_that_day_type.
    tariff_band : str
        ``solar`` / ``off_peak`` / ``shoulder`` / ``peak`` / ``super_peak``.
        Indexes the import tariff. this list used to name
        ``super_off_peak``, the model's own invented 02-04 sub-band, which was
        deleted when the bands were re-derived from PSERC. It did not name
        ``solar``, which MoP rule 8A requires. A docstring that contradicts
        the config is the Tier 2 defect class this audit swept for, so it is
        corrected here rather than left to drift further.)
    weekday_share : float
        144-slice: fraction of the month's days that are weekdays.
        864-slice: 1.0 if day_type == "weekday" else 0.0.
    weekend_share : float
        Analogous to weekday_share.
    festival_share : float
        Analogous to weekday_share.
    day_type : str
        ``"weekday"`` / ``"weekend"`` / ``"festival"``. In 144-slice mode,
        always ``"mixed"``. In 864-slice mode, the explicit day type.
    hour : int
        Hour-of-day in [0, 23]. In 144-slice mode, set to the daypart
        midpoint (e.g. ``18_20`` → 19). In 864-slice mode, the explicit
        hour of the slice.
    """

    id: str
    month: str
    daypart: str
    hours_per_year: int
    tariff_band: str
    weekday_share: float
    weekend_share: float
    festival_share: float
    # (864-slice refactor, Claude 2): explicit day type and
    # hour. Defaulted to back-compat values for the 144-slice path.
    day_type: str = "mixed"
    hour: int = 12


# ---------------------------------------------------------------------------
# DesignDay
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DesignDay:
    """An extreme-day feasibility slice (capacity sizing only).

    DesignDays are NOT in the cost objective; they impose feasibility
    constraints on the worst-case slices (peak demand × demand_uplift
    must be servable; PV × pv_factor caps low-resource sizing).
    """

    id: str
    month: str
    daypart: str
    demand_uplift: float
    pv_factor: float


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Scenario:
    """Which technologies are switched on for a MILP solve.

    Used to run BAU vs PV-only vs PV+battery vs full-stack comparisons in
    Stage B / C acceptance criteria.
    """

    name: str
    allow_rooftop_pv: bool
    allow_solar_farm: bool
    allow_battery: bool
    allow_v2g: bool
    allow_biomass_chp: bool = False     # Stage C
    allow_tracked_pv: bool = False      # Stage C
    allow_wte: bool = False             # Stage C round 2
    allow_biogas: bool = False          # Stage C round 2
    allow_thermal_storage: bool = False # Stage C round 2
    # Stage C round 3 - Claude 2 additions
    allow_panel_orientation_choice: bool = False
    allow_dsr: bool = False
    allow_solshare: bool = False
    allow_biosolar: bool = False
    allow_bipv: bool = False
    allow_carport: bool = False
    allow_floating_pv: bool = False        # Stage C round 5
    # REV-2: managed EV charging (bounded charge-shift within
    # plug-in windows). Pyomo builders only; the heuristic ignores it.
    allow_ev_smart_charging: bool = False
    # B21: buy-side green open-access purchase - design-package
    # scenarios only (BAU/pv_* counterfactuals stay grid-only).
    allow_green_purchase: bool = False
    # solar water heating. Defaults OFF, and the technology is
    # ALSO gated on `technologies.solar_thermal.enabled` in economics.yaml,
    # so it takes two switches to reach the LP. Both are off in production.
    allow_solar_thermal: bool = False
    battery_coupling_mode: str = "ac_traditional"


# ---------------------------------------------------------------------------
# Slice synthesis (144 legacy / 864 representative-days refactor)
# ---------------------------------------------------------------------------
def _daypart_for_hour(hour: int, dayparts_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the daypart dict whose [start_h, end_h) bracket includes hour.

    Used by the 864-slice synthesis to back-fill the legacy ``daypart``
    and ``tariff_band`` attributes from the explicit hour. Falls back
    to the last daypart if no match (shouldn't happen with the standard
    12 × 2-hour partition covering 0-24).
    """
    for dp in dayparts_raw:
        if int(dp["start_h"]) <= hour < int(dp["end_h"]):
            return dp
    return dayparts_raw[-1]


def _synthesize_slices(slices_per_year: int,
                        calendar: Dict[str, Any],
                        dayparts_raw: List[Dict[str, Any]],
                        seasonal_tod: Optional[Dict[str, Any]] = None,
                        ) -> List["TimeSlice"]:
    """Construct the per-year slice list.

    144-slice mode (legacy): one slice per (month, daypart). Each slice
    bundles all day types into a weighted shape, with weekday_share +
    weekend_share + festival_share summing to 1.

    864-slice mode: one slice per
    (month, day_type, hour). Day type ∈ {weekday, weekend, festival}.
    Hour ∈ [0, 23]. hours_per_year = days_of_that_type. Back-compat:
    weekday_share=(1,0,0)/(0,1,0)/(0,0,1) so legacy code paths that
    blend the three shares still resolve to the correct single shape.

    FX-4: when ``seasonal_tod.enabled`` is
    true, ``seasonal_tod.overrides_by_month[month][daypart_id]`` replaces
    the daypart's default ``tariff_band`` for that month's slices (both
    modes). Months/dayparts absent from the table keep the year-round
    default, so a missing or disabled block is byte-identical to the
    pre-FX-4 behaviour. Source: PSPCL/PSERC ToD schedule (see
    economics.yaml ``seasonal_tod`` block).
    """
    slices: List["TimeSlice"] = []

    tod_overrides: Dict[str, Dict[str, str]] = {}
    if seasonal_tod and bool(seasonal_tod.get("enabled", False)):
        tod_overrides = {
            str(m): {str(k): str(v) for k, v in (bands or {}).items()}
            for m, bands in (seasonal_tod.get("overrides_by_month", {}) or {}).items()
        }

    if slices_per_year == 144:
        for month in MONTHS:
            if month not in calendar:
                raise ValueError(f"calendar.months missing {month!r}")
            month_info = calendar[month]
            days = int(month_info["days"])
            wd = int(month_info["weekday"])
            we = int(month_info["weekend"])
            fest = int(month_info["festival"])
            if wd + we + fest != days:
                raise ValueError(
                    f"calendar.months.{month} day breakdown "
                    f"{wd}+{we}+{fest}={wd+we+fest} != {days}"
                )
            for dp_entry in dayparts_raw:
                dp_id = dp_entry["id"]
                sid = f"{month}_{dp_id}"
                hours = 2 * days
                # midpoint hour for the daypart (for s.hour back-compat)
                mid_hour = (int(dp_entry["start_h"])
                            + int(dp_entry["end_h"])) // 2
                slices.append(TimeSlice(
                    id=sid,
                    month=month,
                    daypart=dp_id,
                    hours_per_year=hours,
                    tariff_band=str(tod_overrides.get(month, {}).get(
                        dp_id, dp_entry["tariff_band"])),
                    weekday_share=wd / days,
                    weekend_share=we / days,
                    festival_share=fest / days,
                    day_type="mixed",
                    hour=mid_hour,
                ))
        return slices

    # 864-slice mode: month × day_type × hour.
    DAY_TYPES = (("weekday", "wd"), ("weekend", "we"), ("festival", "fs"))
    for month in MONTHS:
        if month not in calendar:
            raise ValueError(f"calendar.months missing {month!r}")
        month_info = calendar[month]
        days = int(month_info["days"])
        day_counts = {
            "weekday":  int(month_info["weekday"]),
            "weekend":  int(month_info["weekend"]),
            "festival": int(month_info["festival"]),
        }
        if sum(day_counts.values()) != days:
            raise ValueError(
                f"calendar.months.{month} day breakdown "
                f"{day_counts['weekday']}+{day_counts['weekend']}"
                f"+{day_counts['festival']} != {days}"
            )
        for day_type, abbrev in DAY_TYPES:
            n_days = day_counts[day_type]
            wd_share = 1.0 if day_type == "weekday" else 0.0
            we_share = 1.0 if day_type == "weekend" else 0.0
            fs_share = 1.0 if day_type == "festival" else 0.0
            for hour in range(24):
                dp = _daypart_for_hour(hour, dayparts_raw)
                sid = f"{month}_{abbrev}_{hour:02d}"
                # hours_per_year = days_of_that_type × 1h/day. For zero-
                # festival months this gives 0 for festival slices, which
                # the LP correctly weights out of the cost objective.
                slices.append(TimeSlice(
                    id=sid,
                    month=month,
                    daypart=str(dp["id"]),
                    hours_per_year=n_days,
                    tariff_band=str(tod_overrides.get(month, {}).get(
                        str(dp["id"]), dp["tariff_band"])),
                    weekday_share=wd_share,
                    weekend_share=we_share,
                    festival_share=fs_share,
                    day_type=day_type,
                    hour=hour,
                ))
    return slices


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------
@dataclass
class Economics:
    """Typed view of `config/economics.yaml`."""

    # Identity
    currency: str = "INR"
    base_year: int = 2030
    inflation_assumption_annual: float = 0.04
    tariff_escalation_real_annual: float = 0.025

    # Discount rates per actor tier (real, inflation-stripped).
    discount_rates: Dict[str, float] = field(default_factory=dict)
    discount_rate: float = 0.08    # legacy default

    # (ownership correction): rooftop-PV financing blend. Each owner
    # class's share of the rooftop ceiling -> its actor tier. Empty => legacy flat
    # rwa_pooled rate (back-compat: single-bus path byte-exact without this config).
    rooftop_owner_weights: Dict[str, float] = field(default_factory=dict)
    rooftop_owner_actors: Dict[str, str] = field(default_factory=dict)

    # Tech cost tables (one entry per tech).
    technologies: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Grid tariffs + emission factor + capacity caps.
    grid: Dict[str, Any] = field(default_factory=dict)

    # Calendar (month-day-count + day-type weights).
    calendar: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Daypart schedule + tariff bands.
    dayparts: List[Dict[str, Any]] = field(default_factory=list)

    # Synthesized 144 representative slices.
    slices: List[TimeSlice] = field(default_factory=list)

    # Extreme-day feasibility slices (not weighted in cost).
    design_days: List[DesignDay] = field(default_factory=list)

    # PV capacity factor table (monthly × daypart compositional).
    pv_monthly_modifier: Dict[str, float] = field(default_factory=dict)
    pv_daypart_shape: Dict[str, float] = field(default_factory=dict)
    # (GSA v5): optional PER-MONTH daypart shapes (month ->
    # daypart -> value) derived from the GSA report's hourly tables.
    # When a month is present here it takes precedence over the flat
    # `pv_daypart_shape` (which remains the back-compat fallback).
    pv_daypart_shape_by_month: Dict[str, Dict[str, float]] = field(
        default_factory=dict)

    # Cooling tech catalogue + per-category mix.
    cooling_technologies: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # B1 audit: per-month Punjab climate data (IMD Chandigarh
    # proxy) loaded from `config/climate.yaml`. Used by
    # `_desert_cooler_effectiveness_for_month` to replace the binary
    # `monsoon_effectiveness` flag with a humidity-driven curve. Falls
    # back to empty dict (legacy binary behaviour) if the YAML is missing.
    climate: Dict[str, Dict[str, float]] = field(default_factory=dict)
    cooling_tech_mix_by_category: Dict[str, Dict[str, float]] = field(default_factory=dict)
    #: per-category correction where a technology's W/m2
    # was derived at a reference dwelling size that differs from the actual.
    # Empty -> every category scales at 1.0 (byte-stable for old fixtures).
    cooling_intensity_dwelling_correction: Dict[str, float] = field(default_factory=dict)

    # Heating + cooling factor tables.
    heating_loads: Dict[str, Any] = field(default_factory=dict)
    cooling_factors: Dict[str, Any] = field(default_factory=dict)

    # Day-type base demand profile (per category, weekday / weekend / festival × daypart).
    base_demand_profile: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    # FX-4: per-(category, month) occupancy scaler on base +
    # cooling demand (school summer vacation etc.). Missing = 1.0.
    occupancy_monthly_modifier_table: Dict[str, Dict[str, float]] = field(default_factory=dict)
    #: indoor-lighting daylength seasonality on the 18-20
    # daypart. See the `lighting_seasonal` block in economics.yaml.
    lighting_seasonal: Dict[str, Any] = field(default_factory=dict)

    # EV adoption + EV charging shapes.
    ev_adoption: Dict[str, Any] = field(default_factory=dict)
    ev_vehicle_ownership: Dict[str, Any] = field(default_factory=dict)

    # Microclimate coupling parameters (consumed by energy.network).
    microclimate: Dict[str, float] = field(default_factory=dict)

    # Street-lighting daypart shape (Task 5; consumed by energy.network).
    street_lighting: Dict[str, Any] = field(default_factory=dict)

    # PV realism (clipping + curtailment).
    pv_inverter: Dict[str, float] = field(default_factory=dict)
    curtailment_enabled: bool = True

    # (Claude 2 864-slice refactor Phase 5): hourly behavioural
    # patches that only apply in 864-slice mode. Three sub-blocks (lighting
    # evening-peak, WFH day-of-week split, festival Diwali evening) with
    # explicit `enabled` switches in YAML.
    behavioural_864: Dict[str, Any] = field(default_factory=dict)
    # (Item 2): per-FAITH festival-day demand bumps for
    # tagged RELIGIOUS cells. Keys: "enabled" (bool) + one block per
    # faith (sikh / hindu / muslim / christian) with months + hours +
    # multiplier. See config/economics.yaml `religious_festival_bumps:`
    # for the schema.
    religious_festival_bumps: Dict[str, Any] = field(default_factory=dict)

    # Scenarios.
    scenarios: Dict[str, Scenario] = field(default_factory=dict)

    # ----- loader ------------------------------------------------------
    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "Economics":
        """Load and validate economics from YAML, synthesizing the 144 slices.

        Returns
        -------
        Economics
            Parsed economics inputs with the 12 × 12 = 144 slice grid.
        """
        path = Path(path) if path else DEFAULT_ECONOMICS_PATH
        if not path.exists():
            raise FileNotFoundError(f"Economics config not found at {path}")
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        # B1 audit: load Punjab climate normals from a sibling
        # YAML if present (config/climate.yaml). Used by the desert-cooler
        # humidity-driven effectiveness curve. Failure to find the file is
        # OK -- model falls back to the legacy binary `monsoon_effectiveness`.
        climate_path = path.parent / "climate.yaml"
        climate_data: Dict[str, Dict[str, float]] = {}
        # FX-5/B5: lifetime ambient-PM2.5 decline table (top-level
        # key in climate.yaml, sibling of `climate:`). {} = off (back-compat).
        pm25_scale_by_period: Dict[str, float] = {}
        if climate_path.exists():
            with climate_path.open("r", encoding="utf-8") as cf:
                climate_raw = yaml.safe_load(cf) or {}
            climate_data = climate_raw.get("climate", {}) or {}
            pm25_scale_by_period = (
                climate_raw.get("pm25_ambient_scale_by_period", {}) or {}
            )

        # A21: load price + grid-EF trajectory scenarios from a
        # sibling YAML if present (config/price_trajectories.yaml). Active
        # scenario keys + payload are then surfaced via
        # `Economics.active_price_scenario` / `.tariff_escalation_real_annual` /
        # `.emission_factor_trajectory_average` -- the legacy single
        # escalation + trajectory remain the fallback.
        price_traj_path = path.parent / "price_trajectories.yaml"
        price_traj_data: Dict[str, object] = {}
        if price_traj_path.exists():
            with price_traj_path.open("r", encoding="utf-8") as pf:
                price_traj_raw = yaml.safe_load(pf) or {}
            price_traj_data = price_traj_raw.get("price_trajectories", {}) or {}

        currency = raw.get("currency", "INR")
        if currency != "INR":
            raise ValueError(
                f"economics.yaml currency must be INR, got {currency!r}"
            )

        calendar = raw.get("calendar", {}).get("months", {})
        dayparts_raw = raw.get("dayparts", [])

        # (864-slice refactor, Claude 2): pick synthesis mode
        # from top-level YAML key `slices_per_year` (default 144 for
        # production back-compat; 864 unlocks day-type × hour resolution).
        slices_per_year = int(raw.get("slices_per_year", 144))
        if slices_per_year not in (144, 864):
            raise ValueError(
                f"slices_per_year must be 144 or 864 (got {slices_per_year})"
            )

        slices = _synthesize_slices(
            slices_per_year=slices_per_year,
            calendar=calendar,
            dayparts_raw=dayparts_raw,
            seasonal_tod=raw.get("seasonal_tod", {}) or {},
        )

        # Design days.
        design_days = [
            DesignDay(
                id=d["id"],
                month=d["month"],
                daypart=d["daypart"],
                demand_uplift=float(d["demand_uplift"]),
                pv_factor=float(d["pv_factor"]),
            )
            for d in raw.get("design_days", [])
        ]

        # Scenarios.
        scenarios_raw = raw.get("scenarios", {})
        scenarios = {
            name: Scenario(
                name=name,
                allow_rooftop_pv=bool(v.get("allow_rooftop_pv", False)),
                allow_solar_farm=bool(v.get("allow_solar_farm", False)),
                allow_battery=bool(v.get("allow_battery", False)),
                allow_v2g=bool(v.get("allow_v2g", False)),
                allow_biomass_chp=bool(v.get("allow_biomass_chp", False)),
                allow_tracked_pv=bool(v.get("allow_tracked_pv", False)),
                allow_wte=bool(v.get("allow_wte", False)),
                allow_biogas=bool(v.get("allow_biogas", False)),
                allow_thermal_storage=bool(v.get("allow_thermal_storage", False)),
                allow_solar_thermal=bool(v.get("allow_solar_thermal", False)),
                # Stage C round 3 flags
                allow_panel_orientation_choice=bool(
                    v.get("allow_panel_orientation_choice", False)
                ),
                allow_dsr=bool(v.get("allow_dsr", False)),
                allow_solshare=bool(v.get("allow_solshare", False)),
                allow_biosolar=bool(v.get("allow_biosolar", False)),
                allow_bipv=bool(v.get("allow_bipv", False)),
                allow_carport=bool(v.get("allow_carport", False)),
                allow_floating_pv=bool(v.get("allow_floating_pv", False)),
                allow_ev_smart_charging=bool(
                    v.get("allow_ev_smart_charging", False)
                ),
                allow_green_purchase=bool(
                    v.get("allow_green_purchase", False)
                ),
                battery_coupling_mode=str(
                    v.get("battery_coupling_mode", "ac_traditional")
                ),
            )
            for name, v in scenarios_raw.items()
        }

        pv_cf = raw.get("pv_capacity_factor", {})
        carbon_objective_raw = raw.get("carbon_objective", {})
        embodied_carbon_raw = raw.get("embodied_carbon", {})
        reliability_raw = raw.get("reliability", {})

        econ = cls(
            currency=currency,
            base_year=int(raw.get("base_year", 2030)),
            inflation_assumption_annual=float(
                raw.get("inflation_assumption_annual", 0.04)
            ),
            tariff_escalation_real_annual=float(
                raw.get("tariff_escalation_real_annual", 0.025)
            ),
            discount_rates=raw.get("discount_rates", {}),
            discount_rate=float(raw.get("discount_rate", 0.08)),
            rooftop_owner_weights=raw.get("rooftop_owner_weights", {}),
            rooftop_owner_actors=raw.get("rooftop_owner_actors", {}),
            technologies=raw.get("technologies", {}),
            grid=raw.get("grid", {}),
            calendar=calendar,
            dayparts=dayparts_raw,
            slices=slices,
            design_days=design_days,
            pv_monthly_modifier=pv_cf.get("monthly_modifier", {}),
            pv_daypart_shape=pv_cf.get("daypart_shape", {}),
            pv_daypart_shape_by_month=pv_cf.get("daypart_shape_by_month", {}),
            cooling_technologies=raw.get("cooling_technologies", {}),
            cooling_intensity_dwelling_correction=raw.get(
                "cooling_intensity_dwelling_correction", {}
            ),
            cooling_tech_mix_by_category=raw.get(
                "cooling_tech_mix_by_category", {}
            ),
            climate=climate_data,
            heating_loads=raw.get("heating_loads", {}),
            cooling_factors=raw.get("cooling_factors", {}),
            base_demand_profile=raw.get("base_demand_profile", {}),
            occupancy_monthly_modifier_table=(
                raw.get("occupancy_monthly_modifier", {}) or {}
            ),
            #: indoor-lighting daylength seasonality.
            lighting_seasonal=raw.get("lighting_seasonal", {}) or {},
            ev_adoption=raw.get("ev_adoption", {}),
            ev_vehicle_ownership=raw.get("ev_vehicle_ownership", {}),
            microclimate=raw.get("microclimate", {}),
            street_lighting=raw.get("street_lighting", {}),
            pv_inverter=raw.get("pv_inverter", {}),
            curtailment_enabled=bool(raw.get("curtailment", {}).get("enabled", True)),
            scenarios=scenarios,
            behavioural_864=raw.get("behavioural_864", {}) or {},
            religious_festival_bumps=(
                raw.get("religious_festival_bumps", {}) or {}
            ),
        )
        econ.__dict__["carbon_objective_raw"] = carbon_objective_raw
        econ.__dict__["embodied_carbon_raw"] = embodied_carbon_raw
        econ.__dict__["reliability_raw"] = reliability_raw
        # FX-5/B5: lifetime ambient-PM2.5 decline table from
        # config/climate.yaml (top-level key, sibling of `climate:`).
        # Consumed by `pm25_period_soiling_relief`. {} = off (back-compat).
        econ.__dict__["pm25_ambient_scale_by_period_raw"] = pm25_scale_by_period
        # audit: top-level end-of-life decommissioning cost
        # fraction (defaults 0.0 = back-compat). Read by
        # `Economics.end_of_life_cost_fraction` and threaded through
        # every `_annualised` / `_generic_dispatchable_annualised` /
        # `thermal_storage_annualised_inr_per_kwh` / `biomass_chp_annualised_inr_per_kw_e`.
        econ.__dict__["end_of_life_cost_fraction_raw"] = float(
            raw.get("end_of_life_cost_fraction", 0.0)
        )
        # audit A12: electrical losses on the single-bus model.
        # `dc_loss_fraction` -- multiplicative penalty on every PV-yield
        # builder (inverter conversion + DC string + module mismatch).
        # `ac_loss_fraction` -- multiplicative penalty on AC-bus
        # deliveries (grid_import + V2G discharge + battery_discharge).
        # Both default to 0.0 so legacy fixtures + tests stay back-compat.
        eloss_raw = raw.get("electrical_losses") or {}
        econ.__dict__["dc_loss_fraction_raw"] = float(
            eloss_raw.get("dc_loss_fraction", 0.0)
        )
        econ.__dict__["ac_loss_fraction_raw"] = float(
            eloss_raw.get("ac_loss_fraction", 0.0)
        )
        # (Phase 1A —: upstream PSPCL
        # grid loss fraction (transmission + distribution physical losses
        # OUTSIDE the district bus). Defaults 0.0 for back-compat. Anchor:
        # PSPCL FY 2023-24 audit reports 10.73 % T&D physical loss (the
        # AT&C 34.5 % spike is collection-side, transient subsidy issue).
        # Applied to GRID_IMPORT only (not V2G/battery/biomass — those
        # are local-bus). Stacks multiplicatively with last-mile ac_loss.
        econ.__dict__["pspcl_grid_loss_fraction_raw"] = float(
            eloss_raw.get("pspcl_grid_loss_fraction", 0.0)
        )
        #: per-period technical-loss trajectory. Absent =
        # flat, which reproduces every pre-fix result byte-exactly.
        econ.__dict__["pspcl_grid_loss_by_period_raw"] = dict(
            eloss_raw.get("pspcl_grid_loss_by_period", {}) or {}
        )
        # A21: price + grid-EF trajectory scenarios. Stored as
        # raw dict; accessed via `active_price_scenario` /
        # `tariff_escalation_real_annual` / `emission_factor_trajectory_average`.
        econ.__dict__["price_trajectories_raw"] = price_traj_data
        # Stage C round 3 blocks (kept off the typed Economics surface to
        # avoid a schema cascade; accessors below read them via __dict__).
        econ.__dict__["pv_orientations_raw"] = raw.get("pv_orientations", {})
        econ.__dict__["pv_orientation_defaults_raw"] = raw.get(
            "pv_orientation_defaults_by_category", {}
        )
        econ.__dict__["dsr_raw"] = raw.get("demand_side_response", {})
        econ.__dict__["solshare_raw"] = raw.get("allume_solshare", {})
        econ.__dict__["biosolar_raw"] = raw.get("biosolar_roof", {})
        econ.__dict__["bipv_raw"] = raw.get("bipv_facade", {})
        econ.__dict__["carport_raw"] = raw.get("solar_carport", {})
        econ.__dict__["floating_pv_raw"] = raw.get("floating_pv", {})
        econ.__dict__["battery_coupling_raw"] = raw.get("battery_coupling", {})
        econ.__dict__["multi_period_raw"] = raw.get("multi_period", {})
        # (soiling double-count fix): the pv_capacity_factor block
        # is needed whole so `pv_soiling_yield_multiplier_for_month` can read
        # its renormalisation flag. The individual keys above stay as they are.
        econ.__dict__["pv_capacity_factor_raw"] = pv_cf
        # Trajectory batch: A/B scenario hooks (DEM-3 duck
        # curve, DEM-8 carbon price, REV-3 reserve margin). All default
        # to enabled:false -> production path byte-identical.
        econ.__dict__["scenario_hooks_raw"] = raw.get("scenario_hooks", {}) or {}
        # (Stage D scaffold): per-cell/multi-bus block stays
        # disabled-by-default until the per-cell LP lands + validates.
        econ.__dict__["stage_d_raw"] = raw.get("stage_d", {}) or {}
        # (Stage D electrical-asset build, Phases B-E): network
        # capex + substation + voltage tiers + transformers + I2R losses.
        # `enabled: false` by default -> production headline byte-exact.
        econ.__dict__["electrical_network_raw"] = (
            raw.get("electrical_network", {}) or {}
        )
        # (Phase 4 — equity + P2P REPORT): per-tier retail tariffs,
        # EWS social tariff, P2P participation, PMSGY per-tier attribution.
        # REPORT-ONLY (consumed by energy/equity_report.py); a transfer, not a
        # system cost, so it is NEVER read by the LP -> headline byte-exact.
        econ.__dict__["equity_report_raw"] = raw.get("equity_report", {}) or {}
        # (PPA scaffold): YAML block loaded; LP wiring is
        # Stage E. `enabled: false` by default → no headline change.
        econ.__dict__["ppa_raw"] = raw.get("ppa", {}) or {}
        # (IEX-Agile dynamic tariff): opt-in per-slice market-pegged
        # retail price; `enabled_default: false` keeps the fixed-ToU path default.
        econ.__dict__["dynamic_tariff_raw"] = raw.get("dynamic_tariff", {}) or {}
        econ.__dict__["_force_dynamic_tariff"] = None  # None=use YAML default; True/False override
        # (N21 — Stage E PPA LP wiring): per-instance override of the
        # `ppa:` master switch, mirroring `_force_dynamic_tariff`, so a scenario
        # / test can A/B the data-centre PPA on the same network.
        econ.__dict__["_force_ppa_enabled"] = None  # None=use YAML default; True/False override
        # B21: regional-integration blocks - buy-side
        # green open access + boundary opex + interconnection capex + TRJ-7 farm
        # land rent. ALL default enabled: false = byte-exact production until
        econ.__dict__["green_purchase_raw"] = raw.get("green_purchase", {}) or {}
        econ.__dict__["boundary_opex_raw"] = raw.get("boundary_opex", {}) or {}
        econ.__dict__["interconnection_raw"] = raw.get("interconnection", {}) or {}
        econ.__dict__["farm_land_rent_raw"] = raw.get("farm_land_rent", {}) or {}
        econ.__dict__["_force_green_purchase_enabled"] = None  # test A/B override
        econ.validate()
        return econ

    # ----- validation -------------------------------------------------
    def validate(self) -> None:
        """Raise ValueError on any inconsistency.

        Returns
        -------
        None
        """
        if not self.slices:
            raise ValueError("economics.yaml: no slices synthesized")
        # (864-slice refactor): accept both schemes.
        # 144 = 12 months × 12 dayparts.
        # 864 = 12 months × 3 day types × 24 hours.
        n = len(self.slices)
        if n not in (144, 864):
            raise ValueError(
                f"economics.yaml: expected 144 or 864 slices, got {n}"
            )
        total_hours = sum(s.hours_per_year for s in self.slices)
        if total_hours != HOURS_PER_YEAR:
            raise ValueError(
                f"representative_slices hours sum to {total_hours}, "
                f"expected {HOURS_PER_YEAR}"
            )
        slice_ids = {s.id for s in self.slices}
        if len(slice_ids) != n:
            raise ValueError("duplicate slice ids in synthesized slices")
        for tech in (
            "rooftop_pv", "solar_farm", "li_ion_battery", "v2g_charger",
        ):
            if tech not in self.technologies:
                raise ValueError(f"missing technology entry for {tech!r}")
        # 5 tariff bands. replaced the invented
        # `super_off_peak` 02-04 sub-band with the MoP-mandated `solar`
        # 08-16 band, which moved the daily price valley from 03:00 to
        # midday where rule 8A puts it.
        for band in ("solar", "off_peak", "shoulder",
                      "peak", "super_peak"):
            if band not in self.grid.get("import_tariff_inr_per_kwh", {}):
                raise ValueError(f"missing import tariff band {band!r}")
        for scen in ("bau", "pv_only", "pv_battery", "pv_battery_v2g"):
            if scen not in self.scenarios:
                raise ValueError(f"missing scenario {scen!r}")
        for tier in ACTOR_TIERS:
            if tier not in self.discount_rates:
                raise ValueError(f"missing actor-tier discount rate {tier!r}")
        # Cooling tech mix must sum ~1.0 per category that has it.
        for cat, mix in self.cooling_tech_mix_by_category.items():
            s = sum(mix.values())
            if abs(s - 1.0) > 0.01:
                raise ValueError(
                    f"cooling_tech_mix[{cat}] sums to {s:.3f}, expected 1.0"
                )

    # ----- accessors --------------------------------------------------
    # (864-slice refactor Phase 5, Claude 2): behavioural
    # patch multiplier on base residential / office demand. Applies ONLY
    # in 864-slice mode (`day_type in {weekday, weekend, festival}`); in
    # 144-slice mode all slices have day_type=="mixed" and this returns
    # 1.0 by construction. Patches stack multiplicatively. Each patch
    # has an `enabled` switch in the YAML.
    def is_864_slice_mode(self) -> bool:
        return len(self.slices) == 864

    def occupancy_monthly_modifier(self, category_name: str,
                                    month: str) -> float:
        """Per-(category, month) occupancy scaler on base + cooling demand.

        FX-4: encodes building closure seasons - currently
        school summer vacation (economics.yaml ``occupancy_monthly_modifier``
        block, PSEB calendar). Applied by ``network.demand_by_slice_kw`` to
        BOTH the base/plug term and the cooling term (an empty building
        runs neither). Categories/months absent from the table return 1.0,
        so unconfigured categories are byte-stable.
        """
        tbl = self.occupancy_monthly_modifier_table.get(category_name)
        if not tbl:
            return 1.0
        return float(tbl.get(month, 1.0))

    def lighting_seasonal_multiplier(self, category_name: str, month: str,
                                      daypart: str) -> float:
        """: daylength seasonality on INDOOR lighting.

        The model already scales STREET lighting by daylength
        (`street_lighting.monthly_modifier`, same solar-geometry engine). Indoor
        lighting had no equivalent, so a household's 18:00-20:00 demand was
        identical in July and December - when sunset at this site moves from
        16.94 h to 19.00 h and that daypart goes from fully dark to half dark.

        Only the LIGHTING share of the daypart is reshaped:

            1 - S + S x darkfrac(month) / mean_darkfrac

        S = 0.45, the midpoint of BESCOM 2022's 40-55% lighting share of the
        residential evening peak - the same citation behind
        `lighting_evening_peak`. The dark-fraction term is normalised to its
        own annual mean, so ANNUAL ENERGY IS UNCHANGED; only the seasonal
        distribution moves. Returns 1.0 for any category, month or daypart not
        in the table, and whenever the block is disabled."""
        blk = self.lighting_seasonal or {}
        if not blk or blk.get("enabled") is False:
            return 1.0
        if category_name not in (blk.get("categories") or []):
            return 1.0
        if daypart != "18_20":
            return 1.0
        ratio = (blk.get("dark_fraction_ratio_18_20") or {}).get(month)
        if ratio is None:
            return 1.0
        share = float(blk.get("lighting_share_of_daypart", 0.0) or 0.0)
        return 1.0 - share + share * float(ratio)

    def behavioural_demand_multiplier(self, category_name: str,
                                       slice_obj: "TimeSlice",
                                       faith: Optional[str] = None) -> float:
        if not self.behavioural_864 and not self.religious_festival_bumps:
            return 1.0
        # 144-slice mode safety: day_type is "mixed", so none of the
        # patches (which gate on weekday/weekend/festival) fire.
        if slice_obj.day_type == "mixed":
            return 1.0
        mult = 1.0
        # Lighting evening-peak
        lep = self.behavioural_864.get("lighting_evening_peak") or {}
        if lep.get("enabled") and category_name in (lep.get("categories") or []):
            if int(slice_obj.hour) in (lep.get("hours") or []):
                mult *= float(lep.get("multiplier", 1.0))
        # WFH day-of-week split
        wfh = self.behavioural_864.get("wfh_day_of_week") or {}
        if wfh.get("enabled") and slice_obj.day_type in (wfh.get("day_types") or []):
            if category_name in (wfh.get("office_categories") or []):
                mult *= max(0.0, 1.0 - float(
                    wfh.get("office_reduction_fraction", 0.0)
                ))
            elif (category_name in (wfh.get("residential_categories") or [])
                  and int(slice_obj.hour) in (wfh.get("residential_daytime_hours") or [])):
                mult *= 1.0 + float(
                    wfh.get("residential_daytime_uplift_fraction", 0.0)
                )
        # Festival Diwali evening
        fest = self.behavioural_864.get("festival_diwali_evening") or {}
        if (fest.get("enabled")
                and slice_obj.day_type in (fest.get("day_types") or [])
                and slice_obj.month in (fest.get("months") or [])
                and category_name in (fest.get("categories") or [])
                and int(slice_obj.hour) in (fest.get("hours") or [])):
            mult *= float(fest.get("multiplier", 1.0))
        # (Item 2): per-faith festival-day bump for RELIGIOUS
        # cells (faith != None means the cell is RELIGIOUS and tagged).
        # Multiplier applies only on the `fs` (festival) day_type.
        if (faith is not None
                and category_name == "religious"
                and slice_obj.day_type == "festival"
                and self.religious_festival_bumps.get("enabled")):
            fb = self.religious_festival_bumps.get(faith) or {}
            if fb and slice_obj.month in (fb.get("months") or []):
                hour = int(slice_obj.hour)
                if (hour in (fb.get("evening_hours") or [])
                        or hour in (fb.get("morning_hours") or [])):
                    mult *= float(fb.get("multiplier", 1.0))
        return mult

    def slice_by_id(self, slice_id: str) -> TimeSlice:
        """Return the TimeSlice with the given id.

. THIS WAS A LINEAR SCAN OVER 864 SLICES AND IT WAS
        THE LARGEST SINGLE COST IN THE WHOLE MODEL.

        It is called once per node per slice from inside
        `demand_by_slice_kw` (via `ev_node_kw` -> `ev_kw_per_household`), so a
        2,500-node network costs 2,500 x 864 = 2.16 MILLION calls per demand
        build. Measured on the production config: 160 us average per call
        against 0.59 us for a dict lookup, i.e. **272x**, which works out at
        roughly SIX MINUTES of pure scanning per demand build. And
        `cooling_kwh_by_slice` builds a cooling-stripped clone whose cache is
        fresh, so the cost is paid twice.

        Found by py-spy on a structural-proof run that had been going 45
        minutes; the live stack sat in this function on every sample.

        NOT the same issue as. That entry blames the 320 s geometric
        shading precompute for the 7h39m suite. Shading is real but it is not
        the only cause, and this one is bigger because it scales with nodes x
        slices rather than being paid once per network build.

        BYTE-EXACTNESS IS UNAFFECTED BY CONSTRUCTION. A dict returns the SAME
        TimeSlice OBJECT the scan would have returned, so no arithmetic sees a
        different value; only the lookup path changes. Slice ids are unique
        (they are built as month/day-type/hour keys), so the mapping is
        one-to-one.

        The index is rebuilt whenever `self.slices` changes length, which
        covers the fixture paths that swap a 144-slice list for an 864-slice
        one on the same Economics object. It is stored through __dict__ so it
        works whether or not this class is a frozen dataclass.
        """
        idx = self.__dict__.get("_slice_index")
        if idx is None or len(idx) != len(self.slices):
            idx = {s.id: s for s in self.slices}
            self.__dict__["_slice_index"] = idx
        try:
            return idx[slice_id]
        except KeyError:
            raise KeyError(f"unknown slice {slice_id!r}") from None

    def scenario(self, name: str) -> Scenario:
        return self.scenarios[name]

    def pv_capacity_factor(self, slice_id: str) -> float:
        """Per-slice PV capacity factor (rooftop, output / nameplate).

        Computed as `monthly_modifier × daypart_shape`. The daypart shape
        already encodes the absolute slice CF (peak ≈ 0.65 around solar
        noon, zero at night). Annual sum × 8760 ≈ 1500-1800 kWh/kWp for
        Punjab fixed-tilt.
        """
        s = self.slice_by_id(slice_id)
        mm = float(self.pv_monthly_modifier.get(s.month, 1.0))
        # (GSA v5): per-month daypart shape preferred (winter is
        # midday-squeezed, summer has long tails - from the GSA hourly
        # tables); the flat daypart_shape remains the fixture fallback.
        by_month = self.pv_daypart_shape_by_month.get(s.month)
        if by_month:
            ds = float(by_month.get(s.daypart, 0.0))
        else:
            ds = float(self.pv_daypart_shape.get(s.daypart, 0.0))
        return mm * ds

    def pv_capacity_factor_solar_farm(self, slice_id: str) -> float:
        """Solar-farm capacity factor (rooftop × solar_farm/rooftop ratio).

        Ground-mount is ~10% higher than rooftop (no shading, optimal tilt).
        """
        rooftop_base = float(self.technologies["rooftop_pv"].get(
            "base_annual_capacity_factor", 0.18
        ))
        farm_base = float(self.technologies["solar_farm"].get(
            "base_annual_capacity_factor", 0.20
        ))
        ratio = farm_base / rooftop_base if rooftop_base > 0 else 1.0
        return self.pv_capacity_factor(slice_id) * ratio

    # (Realism audit A2): Per-slice PV temperature derating.
    # Standard c-Si modules lose ~0.4% / C above STC (25 C cell temp).
    # Punjab summer ambient ~34 C plus NOCT uplift ~25 C -> 59 C cell temp
    # -> ~14% summer derating. Winter ambient ~15 C plus NOCT uplift gives
    # 40 C cell -> ~6% derating. Integration with PV yield: multiply the
    # capacity-factor-based yield by `pv_temperature_derating(slice_id)`
    # in the network's pv_yield_per_kwp_kwh* builders.
    def pv_temperature_derating(self, slice_id: str) -> float:
        """Per-slice PV temperature derating multiplier in (0, 1].

        Returns 1.0 when no derating coefficient is configured (legacy), and
        also when ``pv_inverter.apply_absolute_temperature_derate`` is false.

 (param audit: the ABSOLUTE derate is off by default
        because the ``pv_capacity_factor`` annual anchor is GSA
        PVOUT_specific, which is AC output after Solargis's own transient
        thermal model - applying it again double-counted. The coefficient is
        still read here (and by ``pv_warming_period_derate``) because TRJ-5
        needs it for the MARGINAL climate-drift effect, which the historical
        anchor does not contain.
        """
        inv = self.pv_inverter or {}
        if not bool(inv.get("apply_absolute_temperature_derate", True)):
            return 1.0
        coef = float(inv.get("temperature_derating_per_celsius", 0.0))
        if coef <= 0:
            return 1.0
        ambient_table = inv.get("ambient_temperature_c_by_month", {}) or {}
        if not ambient_table:
            return 1.0
        s = self.slice_by_id(slice_id)
        ambient_c = float(ambient_table.get(s.month, 25.0))
        noct_uplift_c = float(inv.get("noct_temperature_uplift_c", 25.0))
        cell_c = ambient_c + noct_uplift_c
        delta = cell_c - 25.0   # STC
        if delta <= 0:
            return 1.0
        return max(0.0, 1.0 - coef * delta)

    # ----- (A19): soiling + fog PV multipliers --------------
    def pv_soiling_multiplier_for_month(self, month: str) -> float:
        """Per-month PV yield multiplier in [PV_SOILING_FLOOR, 1.0].

        Accumulates THREE sources of soiling loss and subtracts rain
        washing:
          (1) PM2.5-driven baseline dust deposition (``pm25_ugm3``)
              -- the dominant urban-aerosol-loading contribution.
          (2) IMD dust-storm event deposition (``dust_storm_days``)
              -- Bullet 4 addition. Each synoptic dust event
              (WMO codes 30-35) deposits ~10-20x daily-PM2.5-baseline
              particulate; modelled as ``PV_SOILING_PER_DUST_STORM_DAY ×
              dust_days`` extra fractional loss for that month.
          (3) Rain washing recovery (``rain_days × PV_SOILING_RAIN_RECOVERY_PER_DAY``)
              -- counter-acts both (1) and (2).
        Net loss is clamped to [0, 1 - PV_SOILING_FLOOR] so the
        multiplier never falls below the floor (default 0.80).

        Back-compat: when climate has no ``pm25_ugm3`` field the function
        returns 1.0 (legacy fixtures pre-A19). If ``dust_storm_days`` is
        absent it contributes 0 (clean back-compat).

        Sources: CSIR-CEERI Pilani field study (Mehrotra et al., 2018);
        IIT Roorkee module-soiling characterisation for Indo-Gangetic
        plain (Yadav et al., 2022). Both report 5-8 % dry-season soiling
        on Punjab/Haryana plain at PM2.5 ~80-120 µg/m³. Dust-storm
        deposition multiplier anchored to the same studies' single-event
        loss observations (5-10 % per event).
        """
        if not self.climate:
            return 1.0
        cm = self.climate.get(month, {}) or {}
        pm25 = cm.get("pm25_ugm3")
        if pm25 is None:
            return 1.0
        rain_days = float(cm.get("rain_days", 0.0) or 0.0)
        # (Bullet 4): dust-storm contribution. Defaults to 0
        # when the field is absent (legacy fixtures).
        dust_days = float(cm.get("dust_storm_days", 0.0) or 0.0)
        pm25_loss = PV_SOILING_PER_PM25_UGM3 * float(pm25)
        dust_loss = PV_SOILING_PER_DUST_STORM_DAY * dust_days
        recovery = PV_SOILING_RAIN_RECOVERY_PER_DAY * rain_days
        net_loss = max(0.0, pm25_loss + dust_loss - recovery)
        return max(PV_SOILING_FLOOR, 1.0 - net_loss)

    def pv_soiling_annual_energy_weighted_mean(self) -> float:
        """Energy-weighted annual mean of ``pv_soiling_multiplier_for_month``.

        Months weighted by PV energy share (``pv_monthly_modifier x days``),
        the same weighting ``pm25_period_soiling_relief`` uses. Returns 1.0
        when there is no climate data (legacy fixtures).
        """
        num = 0.0
        den = 0.0
        for month in MONTHS:
            w = (float(self.pv_monthly_modifier.get(month, 1.0))
                 * DAYS_IN_MONTH.get(month, 30))
            num += w * self.pv_soiling_multiplier_for_month(month)
            den += w
        return (num / den) if den > 0 else 1.0

    def pv_soiling_yield_multiplier_for_month(self, month: str) -> float:
        """Soiling multiplier for the PV YIELD path, renormalised so its
        annual energy-weighted mean is exactly 1.0.

 (SOILING DOUBLE-COUNT FIX). The annual PV anchor is GSA
        ``PVOUT_specific`` 1517.4 kWh/kWp, and the World Bank/ESMAP
        methodology behind it states verbatim: "The simulation assumes a
        loss of 3.5% due to dirt and soiling." The A19 PM2.5/dust
        multiplier was then applied ON TOP, costing a further 2.341%
        energy-weighted, for an effective combined soiling of 5.759%.

        The config justified keeping A19 with "panel-level physics not
        present in irradiance data" - true of IRRADIANCE, but the anchor is
        not irradiance. PVOUT_specific is a simulated PV SYSTEM output that
        Solargis/World Bank have already derated for soiling. This is the
        same reasoning the param audit used to zero
        ``dc_loss_fraction`` and switch off the absolute temperature
        derate; soiling was simply missed.

        A "Punjab is dirtier than the global default" defence does not
        rescue the stack, because the model's own soiling term (2.341%) is
        BELOW GSA's global 3.5% - so the correct treatment is to REPLACE,
        not to add.

        Renormalising rather than deleting keeps the SEASONAL SHAPE, which
        is physically real and is information GSA's flat 3.5% does not
        carry (Jan -6.3%, monsoon 0% after rain washing), while removing
        the double-charged LEVEL.

        ``pv_soiling_multiplier_for_month`` is deliberately left untouched:
        it is unit-tested for its floor and back-compat behaviour, and
        ``pm25_period_soiling_relief`` divides two of its values, so a
        constant rescale there would cancel in the numerator but not the
        denominator. Only the YIELD path consumes this method.

        Off by default (flag absent -> returns the raw multiplier), so any
        config without the key stays byte-exact.
        """
        base = self.pv_soiling_multiplier_for_month(month)
        pvcf = self.__dict__.get("pv_capacity_factor_raw", {}) or {}
        if not bool(pvcf.get("soiling_renormalise_to_gsa_anchor", False)):
            return base
        mean = self.pv_soiling_annual_energy_weighted_mean()
        return (base / mean) if mean > 0 else base

    def pv_fog_multiplier_for_month(self, month: str) -> float:
        """Per-month PV yield multiplier accounting for fog events.

        Fog cuts direct beam to ~0 but the diffuse component still
        contributes (``PV_FOG_DIFFUSE_YIELD_FRACTION`` of nominal yield).
        Multiplier =
            (days - fog_days)/days * 1.0
            + fog_days/days * PV_FOG_DIFFUSE_YIELD_FRACTION.

        Returns 1.0 when ``fog_days`` is missing from the climate block
        (back-compat for legacy fixtures).
        """
        if not self.climate:
            return 1.0
        cm = self.climate.get(month, {}) or {}
        fog_days = cm.get("fog_days")
        if fog_days is None:
            return 1.0
        total = float(DAYS_IN_MONTH.get(month, 30))
        if total <= 0:
            return 1.0
        f = max(0.0, min(total, float(fog_days)))
        clear_share = (total - f) / total
        fog_share = f / total
        return clear_share * 1.0 + fog_share * PV_FOG_DIFFUSE_YIELD_FRACTION

    def daypart_multiplier(self, category: str, slice_id: str) -> float:
        """Composite multiplier for a category in a slice.

        Combines (base × occupancy) + cooling + heating + EV. All multipliers
        of category peak (so output × peak_kw = actual demand kW in this slice).

        Returns
        -------
        float
            Fraction of category peak load active in this slice.
        """
        s = self.slice_by_id(slice_id)
        # Base occupancy (day-type weighted).
        base_prof = self.base_demand_profile.get(category)
        if base_prof is None:
            return 0.5  # fallback flat
        wd = float(base_prof.get("weekday", {}).get(s.daypart, 0.5))
        we = float(base_prof.get("weekend", {}).get(s.daypart, 0.5))
        fest = float(base_prof.get("festival", {}).get(s.daypart, 0.5))
        base_mult = (s.weekday_share * wd
                     + s.weekend_share * we
                     + s.festival_share * fest)

        # Cooling: month × daypart × cooling-tech effectiveness.
        #: derived from climate, not hand-typed.
        cf_month = self.cooling_factor_for_month(s.month)
        #: residential and non-residential cooling now
        # take different daypart curves and different running hours.
        cf_dp = self.cooling_daypart_factor(category, s.daypart, s.month)
        cooling_mult = cf_month * cf_dp * self._cooling_effectiveness(
            category, s.month
        )

        # HEAT-1: the two heating loads have separate
        # seasons and daily curves; heating_split_factor sums them and
        # falls back to the legacy month x daypart product when the split
        # is not configured.
        heating_mult = self.heating_split_factor(category, slice_id)

        #: indoor lighting is seasonal; applies to the BASE term only.
        base_mult *= self.lighting_seasonal_multiplier(
            category, s.month, s.daypart)

        return base_mult + cooling_mult + heating_mult

    # ---- HEAT-1 split -----------------------------------
    # + + + + are one defect in five places:
    # a geyser and a room heater were driven by the same peak, the same
    # season and the same daily curve. They are now two loads. See the
    # heating_loads block in economics.yaml for every citation.

    _HEAT_CLASS = {"low_income_residential": "low",
                   "mid_income_residential": "mid",
                   "high_income_residential": "high"}

    def _heat_class(self, category: str) -> str:
        """Which daypart profile a category uses: its income tier, or
        ``commercial`` for everything non-residential."""
        return self._HEAT_CLASS.get(category, "commercial")

    def _heat_month_table(self, key: str) -> Dict[str, float]:
        """Normalised month factor (coldest month = 1.00) for ``dhw`` or
        ``space_heating``, built from climate.yaml and cached.

        DHW runs on (setpoint - inlet), space heating on HDD(base, mean).
        Both fall back to the legacy single table when climate data is
        absent, which keeps the small-grid tests deterministic."""
        cache = self.__dict__.setdefault("_heat_month_cache", {})
        if key in cache:
            return cache[key]
        block = (self.heating_loads or {}).get(key, {}) or {}
        field = block.get("inlet_temperature_field"
                          if key == "dhw" else "hdd_temperature_field",
                          "t_mean_c")
        if key == "dhw":
            base = float(block.get("setpoint_c", 60.0))
        else:
            base = float(block.get("hdd_baseline_c", 18.0))
        raw: Dict[str, float] = {}
        for m, cm in (self.climate or {}).items():
            if not isinstance(cm, dict):
                continue
            t = cm.get(field)
            if t is None:
                continue
            raw[m] = max(0.0, base - float(t))
        if not raw or max(raw.values()) <= 0:
            # no climate: reuse the legacy hand-coded table for both legs
            raw = dict((self.heating_loads or {})
                       .get("heating_factor_by_month", {}) or {})
            table = {m: float(v) for m, v in raw.items()}
        else:
            mx = max(raw.values())
            table = {m: v / mx for m, v in raw.items()}
        cache[key] = table
        return table

    def dhw_month_factor(self, month: str) -> float:
        """Water-heating month factor. Never zero: the energy is
        proportional to (setpoint - inlet) and inlet never reaches the
        setpoint. This is and - the model used to run a
        hospital's hot water at exactly 0 in July."""
        return float(self._heat_month_table("dhw").get(month, 0.0))

    def space_heating_month_factor(self, month: str) -> float:
        """Space-heating month factor on standard degree days against the
        daily MEAN: base 18 is a mean-temperature construct, and
        applying it to the daily minimum stretched the season ~1.9x)."""
        return float(self._heat_month_table("space_heating").get(month, 0.0))

    def dhw_running_hours(self, category: str) -> float:
        """Daily water-heater running hours in the PEAK month, per unit of
        that category's water-heating peak.

        For residential this is DERIVED, not assumed:

            litres/person/day x people/household x (bath_C - inlet_C)
            x 4.186 kJ/kg.K / 3600  ->  kWh/day, then / appliance kW

        so changing the litres or the appliance changes the load. The
        mixing algebra means the thermostat setpoint cancels out of the
        energy (see the config note), which is why ``bath_temperature_c``
        and not ``setpoint_c`` appears here. Non-residential categories
        have no household count and give their hours directly."""
        cache = self.__dict__.setdefault("_dhw_hours_cache", {})
        if category in cache:
            return cache[category]
        b = (self.heating_loads or {}).get("dhw", {}) or {}
        lpcd = float((b.get("hot_water_lpcd_by_category", {}) or {})
                     .get(category, 0.0))
        if lpcd > 0:
            ppl = float((b.get("people_per_household_by_category", {}) or {})
                        .get(category, 0.0))
            kw = float((b.get("appliance_kw_by_category", {}) or {})
                       .get(category, 0.0))
            t_bath = float(b.get("bath_temperature_c", 40.0))
            field = b.get("inlet_temperature_field", "t_mean_c")
            # peak month = the coldest, i.e. the one the month factor
            # normalises to 1.00
            temps = [float(cm[field]) for cm in (self.climate or {}).values()
                     if isinstance(cm, dict) and cm.get(field) is not None]
            if ppl > 0 and kw > 0 and temps:
                t_in = min(temps)
                kwh = lpcd * ppl * max(0.0, t_bath - t_in) * 4.186 / 3600.0
                cache[category] = kwh / kw
                return cache[category]
        cache[category] = float((b.get("running_hours_by_category", {}) or {})
                                .get(category, 0.0))
        return cache[category]

    def space_heating_running_hours(self, category: str) -> float:
        """Daily room-heater running hours in the peak month. Graded by
        income because running a 2 kW heater is a cost decision, not only
        a comfort one."""
        return float(((self.heating_loads or {}).get("space_heating", {}) or {})
                     .get("running_hours_by_category", {})
                     .get(category, 0.0))

    def _heat_daypart(self, key: str, category: str, daypart: str) -> float:
        """Fraction of the day's running hours that falls in this daypart,
        expressed per HOUR so it can multiply a peak directly.

        The YAML profile says only WHEN; it is normalised by its own sum
        and scaled by the running hours, so the day's delivered energy is
        exactly ``running_hours x peak`` whatever the profile holds."""
        block = (self.heating_loads or {}).get(key, {}) or {}
        prof = ((block.get("daypart_profile_by_class", {}) or {})
                .get(self._heat_class(category), {}) or {})
        total = sum(float(v) for v in prof.values())
        if total <= 0:
            return 0.0
        share = float(prof.get(daypart, 0.0)) / total
        if share <= 0:
            return 0.0
        hours = (self.dhw_running_hours(category) if key == "dhw"
                 else self.space_heating_running_hours(category))
        dp_hours = self.daypart_hours_per_day().get(daypart, 0.0)
        if hours <= 0 or dp_hours <= 0:
            return 0.0
        return hours * share / dp_hours

    def heating_split_factor(self, category: str, slice_id: str) -> float:
        """Fraction of a node's ``peak_heating_kw`` drawn in this slice,
        summed over the two loads.

        Replaces ``heating_factor_for_month(month) x heating_daypart_shape``.
        Falls back to that legacy product when the split is not configured,
        so no-climate and small-grid tests stay byte-exact."""
        hl = self.heating_loads or {}
        shares = hl.get("dhw_share_of_peak_by_category", {}) or {}
        # The split needs climate data: the DHW season comes from monthly
        # inlet temperature and the running hours from the temperature rise
        # over it. Without climate there is nothing to split on, so drop
        # cleanly back to the legacy month x daypart product rather than
        # silently returning a zero heating load (small-grid tests).
        if not shares or "dhw" not in hl or not self.climate:
            s = self.slice_by_id(slice_id)
            return (self.heating_factor_for_month(s.month)
                    * float((hl.get("heating_daypart_shape", {}) or {})
                            .get(s.daypart, 0.0)))
        s = self.slice_by_id(slice_id)
        f = float(shares.get(category, 0.0))
        return (f * self.dhw_month_factor(s.month)
                * self._heat_daypart("dhw", category, s.daypart)
                + (1.0 - f) * self.space_heating_month_factor(s.month)
                * self._heat_daypart("space_heating", category, s.daypart))

    def cooling_daypart_factor(self, category: str, daypart: str,
                                month: str) -> float:
        """Fraction of a node's ``peak_cooling_kw`` drawn in this daypart.

. Residential and non-residential cooling are
        different loads and no longer share a curve.

        RESIDENTIAL takes a measured night-weighted profile scaled to
        BOTTOM-UP running hours. The old shared curve delivered 14.4
        equivalent full-load hours a day; a room air conditioner runs 6.2
        (Ramapragada 2022, metered). At the COINCIDENT peak that becomes
        runtime / coincidence, so the correction is graded by tier: 11.21 h
        low, 10.00 mid, 8.18 high, against 14.40 for all three before.

        The profile is normalised by its own sum, so the day's delivered
        energy is exactly ``hours x peak`` whatever the table holds - the
        same discipline as the HEAT-1 split, and for the same reason: WHEN
        and HOW MUCH must live in different fields or they merge again.

        NON-RESIDENTIAL keeps the existing afternoon-peaked shape and its
        monsoon variant, unchanged and correctly so. An office really does
        peak at 14:00-16:00, and LBNL-6674E confirms the commercial sector
        peaks in summer afternoons. Only the residential half was wrong."""
        cf = self.cooling_factors or {}
        rc = cf.get("residential_cooling") or {}
        hours = float((rc.get("equivalent_full_load_hours") or {})
                      .get(category, 0.0))
        if rc and hours > 0:
            prof = rc.get("daypart_profile") or {}
            total = sum(float(v) for v in prof.values())
            if total > 0:
                share = float(prof.get(daypart, 0.0)) / total
                dp_h = self.daypart_hours_per_day().get(daypart, 0.0)
                if share > 0 and dp_h > 0:
                    return hours * share / dp_h
                return 0.0
        # non-residential: the legacy shape, with its monsoon variant
        monsoon = set(cf.get("monsoon_months") or [])
        mon_tbl = cf.get("cooling_daypart_shape_monsoon") or {}
        if month in monsoon and mon_tbl:
            return float(mon_tbl.get(daypart, 0.0))
        return float((cf.get("cooling_daypart_shape") or {}).get(daypart, 0.0))

    def cooling_factor_for_month(self, month: str) -> float:
        """Per-month cooling-load factor, normalised so the hottest month = 1.0.

. This table scales ~32% of district demand and was
        twelve hand-typed numbers with no source, no URL and no derivation -
        while the HEATING month factor, a load 3.7x smaller, had already been
        upgraded to a climate-derived degree-day proxy in the
        audit. The rigour had been applied to the small load and withheld
        from the big one.

        METHOD. Cooling degree days from daily max and min, the CIBSE TM41 /
        UK Met Office approximation, NOT degree days on the monthly mean.
        This matters and is the reason the audit would not name a direction:
        Zirakpur's March mean is 21.4 C but its mean daily MAX is 28.0 C, and
        October is 25.2 / 32.0. Degree days on the mean call both months zero
        cooling, which is plainly wrong for north India - that is Jensen's
        inequality, flagged as. The triangular form recovers them.

            t_min >= base   ->  t_mean - base
            t_max <= base   ->  0
            t_mean >= base  ->  (t_max - base)/2 - (base - t_min)/4
            otherwise       ->  (t_max - base)/4

        BASE = 24 C, and it is a real Indian regulation rather than a
        modelling choice: the Ministry of Power notification of 30 October
        2019 makes 24 C the mandatory factory-default setpoint for every
        BEE star-labelled room air conditioner sold in India from 1 January
        2020 (Tier 1, https://www.pib.gov.in/PressReleasePage.aspx?PRID=1598508 ).
        It is also the conservative end: a building's cooling BALANCE POINT
        sits below its thermostat because of internal and solar gains, so a
        physically derived base would be lower and would give MORE cooling.

        Falls back to the legacy hand-typed table when climate data or a base
        is absent, which keeps the small-grid tests deterministic."""
        cache = self.__dict__.setdefault("_cooling_cdd_cache", {})
        if month in cache:
            return cache[month]
        legacy = (self.cooling_factors or {}).get("cooling_factor_by_month", {})
        base_c = (self.cooling_factors or {}).get("cooling_base_c")
        if base_c is None or not self.climate:
            return float(legacy.get(month, 0.0))
        base = float(base_c)
        cdd: Dict[str, float] = {}
        for m, cm in self.climate.items():
            if not isinstance(cm, dict):
                continue
            tx, tn, tm = cm.get("t_max_c"), cm.get("t_min_c"), cm.get("t_mean_c")
            if tx is None or tn is None or tm is None:
                continue
            tx, tn, tm = float(tx), float(tn), float(tm)
            if tn >= base:
                v = tm - base
            elif tx <= base:
                v = 0.0
            elif tm >= base:
                v = (tx - base) / 2.0 - (base - tn) / 4.0
            else:
                v = (tx - base) / 4.0
            cdd[m] = max(0.0, v)
        if not cdd or max(cdd.values()) <= 0:
            return float(legacy.get(month, 0.0))
        mx = max(cdd.values())
        for m, v in cdd.items():
            cache[m] = v / mx
        return cache.get(month, 0.0)

    def heating_factor_for_month(self, month: str) -> float:
        """Per-month heating-load factor.

 (Realism audit B3): when `config/climate.yaml` is
        loaded AND `heating_loads.heating_baseline_c` is configured,
        compute the factor from a heating-degree-day (HDD) proxy:
            HDD_m = max(0, baseline_c - climate[m].t_min_c)
            factor_m = HDD_m / max_HDD_across_year (so coldest month = 1.0)
        Otherwise fall back to the legacy
        `heating_loads.heating_factor_by_month` hand-coded table (keeps
        small-grid / no-climate tests deterministic).

        Returns
        -------
        float
            Month-of-year heating factor in [0, 1].
        """
        cache = self.__dict__.setdefault("_heating_hdd_cache", {})
        if month in cache:
            return cache[month]

        baseline_c = self.heating_loads.get("heating_baseline_c")
        if baseline_c is not None and self.climate:
            try:
                base = float(baseline_c)
                hdd_by_month = {}
                for m, cm in self.climate.items():
                    if not isinstance(cm, dict):
                        continue
                    tmin = cm.get("t_min_c")
                    if tmin is None:
                        continue
                    hdd_by_month[m] = max(0.0, base - float(tmin))
                if hdd_by_month and any(v > 0 for v in hdd_by_month.values()):
                    max_hdd = max(hdd_by_month.values())
                    for m, h in hdd_by_month.items():
                        cache[m] = h / max_hdd if max_hdd > 0 else 0.0
                    return cache.get(month, 0.0)
            except (TypeError, ValueError):
                pass  # fall through to legacy

        # Legacy fallback.
        legacy = self.heating_loads.get("heating_factor_by_month", {})
        for m, v in legacy.items():
            cache[m] = float(v)
        return cache.get(month, 0.0)

    def heat_wave_cooling_multiplier(self, month: str) -> float:
        """Per-month heat-wave cooling-load uplift.

: the monthly cooling
        factor + daypart shape capture AVERAGE summer demand but miss
        the consecutive-day heat-wave events that drive transformer
        sizing and AC peak utilization.

 - ATTRIBUTION CORRECTED. This docstring used to
        say "IMD heat-wave definition uses mean daily max > 35 C for plains".
        THAT IS NOT THE IMD DEFINITION. IMD declares a heat wave over the
        plains when the ACTUAL daily maximum reaches 40 C and departs from
        normal by 4.5 C or more (severe at 6.5 C), or when the actual maximum
        reaches 45 C regardless of departure. Two things were wrong: the
        threshold (35 vs 40) and, more seriously, the STATISTIC - IMD's rule
        is about individual DAYS, while this accessor tests a MONTHLY MEAN of
        daily maxima. A month whose mean max is 34 C can still contain a
        week at 43 C. That is Jensen's inequality, and it is the same defect
        the cooling month factor had before.

        THE NUMBER IS KEPT AND THE CLAIM IS CHANGED. 35 C on a monthly mean
        is a defensible proxy for "this month contains sustained heat-wave
        conditions" precisely BECAUSE it sits below IMD's daily threshold -
        a monthly mean of 35 implies many individual days above 40. What was
        indefensible was calling it the IMD definition. It is a Tier 3
        monthly proxy FOR the IMD daily criterion, not the criterion itself.
        (IMD criteria: https://mausam.imd.gov.in/, Heat Wave definitions.)

        Returns a per-month multiplier in [1.0, 1.20] that scales cooling
        demand when the month's mean daily maximum exceeds 35 C:

            multiplier = 1.0                            if t_max <= 35 C
            multiplier = 1.0 + (t_max - 35) * 0.04      if 35 < t_max <= 40 C
            multiplier = 1.20                            if t_max > 40 C

        The 0.04/degree slope is calibrated from CEA load-trend studies
        of North Indian summer peak demand: a 1 C rise above the
        threshold typically drives 4-6 % cooling-load growth on the
        worst days; averaged across the month gives ~4 %/degree net
        because not every day in the month is a heat-wave day. The cap
        at +20 % prevents over-stating any single hot month.

        Returns 1.0 when climate data is unavailable or the month is
        absent (back-compat with no-climate fixtures).
        """
        cache = self.__dict__.setdefault("_heatwave_cache", {})
        if month in cache:
            return cache[month]
        if not self.climate:
            cache[month] = 1.0
            return 1.0
        cm = self.climate.get(month)
        if not isinstance(cm, dict):
            cache[month] = 1.0
            return 1.0
        tmax = cm.get("t_max_c")
        if tmax is None:
            cache[month] = 1.0
            return 1.0
        try:
            t = float(tmax)
        except (TypeError, ValueError):
            cache[month] = 1.0
            return 1.0
        if t <= 35.0:
            mult = 1.0
        elif t > 40.0:
            mult = 1.20
        else:
            mult = 1.0 + (t - 35.0) * 0.04
        cache[month] = mult
        return mult

    def _cooling_effectiveness(self, category: str, month: str) -> float:
        """Weighted cooling effectiveness for a category in a month.

        Combines the cooling-tech mix with each tech's effective-effectiveness
        for the month. A "fan_only" share has effectiveness 1.0 but contributes
        only its W/m² peak which is small (fan ~ 1 W/m²); a desert cooler is
        highly effective at low RH and minimally effective above ~70% RH.

 B1 audit: if `config/climate.yaml` is
        present and the tech has `monsoon_effectiveness` configured, the
        effectiveness becomes a smooth function of the month's afternoon RH
        (linear interpolation between `low_rh_effectiveness` at 30% RH and
        `monsoon_effectiveness` at 75% RH). Falls back to the legacy binary
        Jun-Sep flag when climate data is missing -- so existing tests pass.
        """
        mix = self.cooling_tech_mix_by_category.get(category)
        if mix is None:
            return 1.0  # categories without explicit mix use full cooling
        eff = 0.0
        for tech_name, share in mix.items():
            tech = self.cooling_technologies.get(tech_name, {})
            base_eff = self._tech_effectiveness_for_month(tech, month)
            # Weight by the tech's W/m² peak so a fan-only share counts less.
            w = float(tech.get("w_per_m2_peak", 0.0))
            eff += share * base_eff * w
        # Normalise by the unweighted-mix peak so the resulting multiplier
        # stays comparable with the legacy "fraction of category cooling peak"
        # semantics.
        denom = sum(
            float(self.cooling_technologies.get(t, {}).get("w_per_m2_peak", 0.0))
            * sh
            for t, sh in mix.items()
        )
        return eff / denom if denom > 0 else 0.0

    def _tech_effectiveness_for_month(
        self,
        tech: Dict[str, float],
        month: str,
    ) -> float:
        """Effective effectiveness of a cooling tech for the given month.

        Two pathways:
          (1) **RH-curved** (preferred, B1 audit): if climate.yaml has an
              `rh14_pct` for the month AND the tech declares
              `monsoon_effectiveness`, linearly interpolate between full
              effectiveness (1.0) at low_rh_pct and `monsoon_effectiveness`
              at high_rh_pct. Outside the band, clamp.
          (2) **Legacy binary** (fallback): if climate is missing, use the
              monsoon-month set {jun..sep} as a flat trigger to apply
              `monsoon_effectiveness`; non-monsoon months get 1.0.

        Tech YAML may override the breakpoints via
        `low_rh_pct_full_effectiveness` (default 30) and
        `high_rh_pct_monsoon_effectiveness` (default 75).
        """
        # If tech has no monsoon-effectiveness configured, it's RH-invariant
        # (e.g. compressor ACs, fans). Always return 1.0.
        if "monsoon_effectiveness" not in tech:
            return 1.0

        monsoon_eff = float(tech["monsoon_effectiveness"])
        climate_for_month = self.climate.get(month, {}) if self.climate else {}
        rh = climate_for_month.get("rh14_pct")

        # Pathway (1): RH-curved
        if rh is not None and isinstance(rh, (int, float)):
            low_rh = float(tech.get("low_rh_pct_full_effectiveness", 30.0))
            high_rh = float(tech.get("high_rh_pct_monsoon_effectiveness", 75.0))
            if rh <= low_rh:
                return 1.0
            if rh >= high_rh:
                return monsoon_eff
            # Linear interpolation between 1.0 at low_rh and monsoon_eff at high_rh
            fraction = (float(rh) - low_rh) / (high_rh - low_rh)
            return 1.0 + fraction * (monsoon_eff - 1.0)

        # Pathway (2): legacy binary
        if month in ("jun", "jul", "aug", "sep"):
            return monsoon_eff
        return 1.0

    # ----- tariffs ----------------------------------------------------
    def import_tariff_subsidy_fraction(self) -> float:
        """Punjab AAP free-electricity subsidy fraction.

        Default 0.0 in production (AAP is a 2-year-old state policy with
        no 25-year durability guarantee). Set to 0.175 for the AAP
        sensitivity scenario. WARNING: applying as a flat tariff
        reduction creates an LP arbitrage artifact (subsidised off-peak
        import < export tariff -> LP imports for resale, emissions
        explode). Real-world AAP applies to net residential consumption
        only; the single-bus LP can't model that without per-cell
        tariff differentiation (Stage F).
        """
        return float(self.grid.get("import_tariff_subsidy_fraction", 0.0))

    def rooftop_pv_capex_subsidy_fraction(self) -> float:
        """PM Surya Ghar Muft Bijli Yojana central-govt PV CAPEX subsidy.

        Default 0.30 (~Rs 78k/household subsidy on ~3 kWp system at
        Rs 35k/kWp -- the standard scheme cap). Multi-party central
        ratification, durable through the 25-year model horizon.
        Reduces effective rooftop_pv CAPEX -> LP deploys more rooftop ->
        grid imports drop -> emissions decrease. Set to 0.0 to disable
        in policy sensitivity runs.
        """
        return float(self.grid.get("rooftop_pv_capex_subsidy_fraction", 0.0))

    # ----- (D2 —: PMSGY continuation decay -----
    def effective_pmsgy_lifetime_avg_fraction(self) -> float:
        """Time-averaged PMSGY rooftop-CAPEX subsidy across the project
        horizon (``project_lifetime_years``).

        The 2030 snapshot subsidy (``rooftop_pv_capex_subsidy_fraction``,
        0.30) is what the ANNUAL LP sees. But PMSGY has no formal post-2027
        notification; the D2 decision models it as a
        ``decay_linear_to_2040`` profile: a hold at the 2030 value for the
        first ``hold_years``, a linear fade to ``fraction_2040_onwards`` by
        ``fade_end_year``, then flat thereafter. This method returns the
        trapezoidal time-integral of that profile divided by the lifetime
        (exact for the piecewise-linear shape) -- the effective subsidy the
        LIFETIME-COST projection should assume.

        Returns the 2030 snapshot value (i.e. no decay) when the
        ``grid.pmsgy_continuation_scenario`` block is absent, so legacy
        behaviour and no-subsidy sensitivity runs are byte-for-byte
        unchanged. Defence: MNRE FY27 budget +29 % YoY signals continuation
        through ~2027; BNEF + TERI 2030-2035 PV cost-decline projects
        rooftop grid-parity without subsidy by ~2035 (see
        ``_spec/realism_gaps_plan.md`` Round-3 Item 4 + Round-4).
        """
        snapshot = self.rooftop_pv_capex_subsidy_fraction()
        block = self.grid.get("pmsgy_continuation_scenario") or {}
        if not block:
            return snapshot
        N = float(self.project_lifetime_years())
        if N <= 0:
            return snapshot
        f_hold = float(block.get("fraction_2030_2032", snapshot))
        f_end = float(block.get("fraction_2040_onwards", 0.0))
        fade_start = float(block.get("fade_start_year",
                                     block.get("hold_years", 0.0)))
        fade_end = float(block.get("fade_end_year", fade_start))
        # Clamp the breakpoints to [0, N] so the integral stays well-defined.
        fade_start = max(0.0, min(fade_start, N))
        fade_end = max(fade_start, min(fade_end, N))
        # Region 1 (hold)  : [0, fade_start]            at f_hold
        # Region 2 (fade)  : [fade_start, fade_end]     linear f_hold -> f_end
        # Region 3 (tail)  : [fade_end, N]              at f_end
        area_hold = f_hold * fade_start
        area_fade = 0.5 * (f_hold + f_end) * (fade_end - fade_start)
        area_tail = f_end * (N - fade_end)
        return (area_hold + area_fade + area_tail) / N

    def pmsgy_lifetime_capex_uplift_factor(self) -> float:
        """Multiplicative uplift on the rooftop-PV CAPEX cashflow for the
        LIFETIME-COST projection only.

        The annual LP amortises rooftop CAPEX at ``(1 - snapshot_subsidy)``.
        Over the 25-yr horizon the subsidy fades (see
        ``effective_pmsgy_lifetime_avg_fraction``), so the lifetime
        amortisation should reflect ``(1 - lifetime_avg_subsidy)``. This
        returns the ratio of the two, i.e. how much MORE the rooftop CAPEX
        portion costs across the lifetime than the 2030-snapshot LP assumes:

            (1 - lifetime_avg_subsidy) / (1 - snapshot_subsidy)

        Returns 1.0 when the decay block is absent (lifetime == snapshot) or
        when the snapshot subsidy is a full 100 % (degenerate denominator),
        so the ANNUAL alpha=0 LP is never affected -- only the
        ``lifetime_cost_inr`` report shifts.
        """
        snapshot = self.rooftop_pv_capex_subsidy_fraction()
        denom = 1.0 - snapshot
        if denom <= 0:
            return 1.0
        return (1.0 - self.effective_pmsgy_lifetime_avg_fraction()) / denom

    def pmsgy_subsidy_fraction_at_year(self, year: int) -> float:
        """PMSGY rooftop-CAPEX subsidy at a single ``year`` along the decay
        profile (D1(b) Phase 2).

        Mirrors the piecewise-linear ``decay_linear_to_2040`` block consumed
        by ``effective_pmsgy_lifetime_avg_fraction`` but evaluates the
        profile at one year (for vintage-specific CAPEX in the multi-period
        LP). Returns the 2030 snapshot when the
        ``grid.pmsgy_continuation_scenario`` block is absent so legacy
        behaviour is byte-for-byte unchanged.
        """
        snapshot = self.rooftop_pv_capex_subsidy_fraction()
        block = self.grid.get("pmsgy_continuation_scenario") or {}
        if not block:
            return snapshot
        base_year = self.multi_period_base_year()
        f_hold = float(block.get("fraction_2030_2032", snapshot))
        f_end = float(block.get("fraction_2040_onwards", 0.0))
        fade_start = base_year + float(
            block.get("fade_start_year", block.get("hold_years", 0.0))
        )
        fade_end = base_year + float(block.get("fade_end_year", 0.0))
        if year <= fade_start:
            return f_hold
        if year >= fade_end:
            return f_end
        if fade_end <= fade_start:
            return f_hold
        return (
            f_hold + (f_end - f_hold) * (year - fade_start)
            / (fade_end - fade_start)
        )

    def import_tariff(self, slice_id: str) -> float:
        """Per-slice grid import tariff (INR/kWh).

 applies Punjab AAP free-electricity subsidy as a
        flat reduction. Returns the tariff actually paid by the LP after
        subsidy. Set ``import_tariff_subsidy_fraction: 0.0`` in
        ``economics.yaml`` to disable (returns the published slab
        tariff).
        """
        # IEX-Agile dynamic mode — per-slice market-pegged retail
        # price (no AAP subsidy; the Agile price IS what's paid).
        if self.dynamic_tariff_enabled():
            return self._agile_retail_for_slice(slice_id)
        band = self.slice_by_id(slice_id).tariff_band
        published = float(self.grid["import_tariff_inr_per_kwh"][band])
        sub = self.import_tariff_subsidy_fraction()
        return published * (1.0 - max(0.0, min(1.0, sub)))

    def export_tariff(self, slice_id: Optional[str] = None) -> float:
        """Grid export (feed-in) tariff (INR/kWh). Flat under fixed ToU; under
        IEX-Agile (when ``export_pegged_to_wholesale``) it equals the per-slice
        wholesale price, so a slice_id must be passed to get the dynamic value
        (falls back to the flat ToU export when no slice given)."""
        if (slice_id is not None and self.dynamic_tariff_enabled()
                and bool(self.dynamic_tariff_raw.get("export_pegged_to_wholesale", False))):
            return self._agile_wholesale_for_slice(slice_id)
        return float(self.grid["export_tariff_inr_per_kwh"])

    # ----- IEX-Agile dynamic tariff ----------------------
    def dynamic_tariff_enabled(self) -> bool:
        """True when the per-slice IEX-Agile retail tariff is active. A
        per-instance override (`set_dynamic_tariff`) wins over the YAML default,
        so the dispatch can A/B fixed-ToU vs Agile on the same network."""
        override = self.__dict__.get("_force_dynamic_tariff")
        if override is not None:
            return bool(override)
        return bool((self.dynamic_tariff_raw or {}).get("enabled_default", False))

    def set_dynamic_tariff(self, flag: Optional[bool]) -> None:
        """Force the tariff mode (True=Agile, False=fixed-ToU, None=YAML default).
        Clears the import-tariff cache implicitly (tariffs are recomputed per call)."""
        self.__dict__["_force_dynamic_tariff"] = flag

    def _agile_band_multipliers_normalised(self) -> Dict[str, float]:
        """Intraday band multipliers normalised so the hours-weighted daily mean
        is 1.0 (all dayparts are equal 2-h blocks, so a simple mean). Cached."""
        cached = self.__dict__.get("_agile_band_mult_norm")
        if cached is not None:
            return cached
        raw = (self.dynamic_tariff_raw or {}).get("intraday_band_multiplier", {}) or {}
        mults = {str(k): float(v) for k, v in raw.items()}
        if not mults:
            return {}
        mean = sum(mults.values()) / len(mults)
        norm = {k: (v / mean if mean > 0 else 1.0) for k, v in mults.items()}
        self.__dict__["_agile_band_mult_norm"] = norm
        return norm

    def _agile_wholesale_for_slice(self, slice_id: str) -> float:
        """IEX-DAM wholesale price (INR/kWh) for a slice = monthly RTC level x
        normalised intraday band multiplier. Clamped to the IEX [0, cap] range."""
        dt = self.dynamic_tariff_raw or {}
        s = self.slice_by_id(slice_id)
        monthly = dt.get("monthly_rtc_inr_per_kwh", {}) or {}
        # Normalise month to int 1-12 — 864-slice mode stores month as a name
        # ("jan".."dec"); 144-slice may store an int. YAML keys are ints.
        _MN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
               "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        mon = s.month
        if isinstance(mon, str):
            mon = _MN.get(mon.strip().lower()[:3], None)
        rtc = None
        if mon is not None:
            rtc = monthly.get(int(mon), monthly.get(str(int(mon))))
        rtc = float(rtc) if rtc is not None else 5.0
        mult = self._agile_band_multipliers_normalised().get(s.daypart, 1.0)
        cal = float(dt.get("level_calibration_multiplier", 1.0))
        cap = float(dt.get("retail_cap_inr_per_kwh", 11.0))
        # wholesale floor is 0 (IEX no-negative rule); cap at the wholesale cap (10).
        return max(0.0, min(rtc * mult * cal, max(0.0, cap - 1.0)))

    def _agile_retail_for_slice(self, slice_id: str) -> float:
        """Agile retail = wholesale / (1 - T&D loss) + network + CSS + duty,
        clamped to [floor, cap]. Domestic CSS = 0; duty applied on the energy."""
        dt = self.dynamic_tariff_raw or {}
        w = self._agile_wholesale_for_slice(slice_id)
        loss = float(dt.get("tnd_loss_fraction", 0.07))
        net = float(dt.get("network_charge_inr_per_kwh", 0.70))
        css = float(dt.get("cross_subsidy_inr_per_kwh", 0.0))
        duty = float(dt.get("duty_fraction", 0.05))
        energy = w / max(1e-6, (1.0 - loss))
        retail = energy * (1.0 + duty) + net + css
        floor = float(dt.get("retail_floor_inr_per_kwh", 1.5))
        cap = float(dt.get("retail_cap_inr_per_kwh", 11.0))
        return max(floor, min(retail, cap))

    # ----- (Phase 3C —: -----------
    def industrial_cross_subsidy_inr_per_kwh(self) -> float:
        """Per-kWh cross-subsidy surcharge on Punjab industrial tariff.

        PSPCL embedded cross-subsidy on industrial / warehouse consumers
        recovered through higher slab tariffs than residential. Funds
        the agricultural / domestic subsidy on the other side (43 % of
        PSPCL sales). Anchor: PSERC FY24-25 Chapter 7 ARR + Mercom open
        access surcharge (₹1.29 wheeling distinct from embedded ₹0.86-
        1.22 midpoint ₹1.05).

        Phase 3C: REFERENCE DATA only — the LP is
        district-aggregate, so applying a category-specific tariff
        requires either (a) per-category tariff schedules with
        per-cell dispatch (Stage D / Stage F refactor), or (b) a
        district-weighted average tariff uplift. Stage F task: choose
        the wiring approach + apply.
        """
        return float(self.grid.get("industrial_cross_subsidy_inr_per_kwh", 0.0))

    def industrial_categories(self) -> List[str]:
        """List of category names that pay the industrial cross-subsidy.

        Phase 3C: reference data; not yet consumed by LP.
        """
        return list(self.grid.get("industrial_categories", []) or [])

    def _lifetime_demand_trajectory(self) -> Dict[str, Any]:
        """The ``lifetime_demand_trajectory`` block, read ONCE and cached.

 replaces THREE separate copies of the same file read
        (``lifetime_demand_growth_factor``, ``period_demand_multiplier``,
        ``climate_drift_delta_t_c``), each of which wrapped the read in
        ``except Exception: return 1.0``. That meant a MALFORMED
        district_composition.yaml silently switched off all three demand
        drivers at once and the model reported normal-looking numbers.

        The two cases are now separated, which is the whole point:
          - file ABSENT  -> {} (legitimate; legacy fixtures have no such file)
          - file PRESENT but unparseable -> RAISE, because that is a typo in a
            config that scales district demand, not a reason to return 1.0.
        Returns {} when the block is missing or ``enabled: false``, so all
        three callers keep their existing no-op behaviour byte-exactly.
        """
        cached = self.__dict__.get("_lifetime_traj_cache")
        if cached is not None:
            return cached
        import yaml as _yaml
        from pathlib import Path as _Path
        p = (_Path(__file__).parent.parent
             / "config" / "district_composition.yaml")
        block: Dict[str, Any] = {}
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as fh:
                    raw = _yaml.safe_load(fh) or {}
            except Exception as exc:      # malformed, NOT missing
                raise ValueError(
                    f"district_composition.yaml exists but could not be "
                    f"parsed ({type(exc).__name__}: {exc}). Refusing the old "
                    "silent fallback, which disabled the whole lifetime demand "
                    "trajectory and still returned plausible numbers."
                ) from exc
            traj = raw.get("lifetime_demand_trajectory") or {}
            if traj.get("enabled", False):
                block = traj
        self.__dict__["_lifetime_traj_cache"] = block
        return block

    # ----- (Phases 2A/2B/2C/2D/4): lifetime demand growth -----
    def lifetime_demand_growth_factor(self) -> float:
        """Time-averaged multiplier applied to ``grid_net_annual_inr`` over
        ``project_lifetime_years`` to account for 5 demand drivers:
          - 2A population growth 2030-2055
          - 2B EV adoption ramp
          - 2C climate-drift cooling sensitivity
          - 2D cooking electrification (LPG -> induction)
          - 4  income mobility low->mid->high

        Reads ``lifetime_demand_trajectory`` from
        ``config/district_composition.yaml``. Returns 1.0 (no uplift)
        when the block is absent or `enabled: false` -- back-compat with
        legacy fixtures.

        Sources: PSPCL audit / StatisticsTimes (population), NITI Aayog-
        RMI + IEA Stated Policies (EV), IPCC AR6 + AEEE + CEEW (cooling
        elasticity), CEEW + IEA (electric cooking), PEW + Punjab GVA
        (income mobility). All anchored to Tier 1-3 published sources.

        2030 ANNUAL ALPHA=0 LP IS UNAFFECTED — this factor only enters
        the lifetime_cost_inr report. Capacity sizing remains 2030-based
        per the simple lifetime-projection semantics (option D1(a) per
        Claude 2's plan).
        """
        # one cached read, and a malformed file now raises
        # instead of silently disabling every driver. See
        # `_lifetime_demand_trajectory`.
        block = self._lifetime_demand_trajectory()
        if not block:
            return 1.0
        # COMPLETION. `climate_drift_cooling` is NO LONGER
        # in this list, matching `period_demand_multiplier` (costs.py ~3329).
        # established that warming raises COOLING and lowers heating, so
        # it must not scale all demand: as a flat multiplier here it raised
        # January 2055 demand as much as July's. fixed the multi-period
        # path and left this one, so the two methods disagreed about how
        # warming enters - that half-applied state is what is corrected here.
        # CONSEQUENCE, stated rather than hidden: this factor feeds ONLY the
        # SINGLE-PERIOD post-hoc lifetime projection (dispatch.py ~817, ~5263).
        # Production runs multi-period, where the uplift is applied per-period
        # to the cooling term via `cooling_warming_multiplier`, so the headline
        # is unaffected. The single-period lifetime figure now carries NO
        # warming uplift, which UNDERSTATES late-horizon demand and is
        # therefore conservative.
        # NOT fixed by scaling `cooling_share_of_demand` (0.25) instead,
        # because that field is stale: the model's real cooling share is
        # 32.9% (184.21 of 559.33 GWh,. Inventing a
        # share here would put a third warming convention in the codebase.
        keys = ("population_growth", "ev_adoption_ramp",
                "cooking_electrification",
                "income_mobility",
                # AI/datacentre uplift on OFFICE +
                # LIGHT_INDUSTRY base demand (IEA Electricity 2024 +
                # CBRE India Data Center Update Q3 2024).
                "ai_demand_uplift")
        mult = 1.0
        for key in keys:
            sub = block.get(key) or {}
            m = float(sub.get("lifetime_avg_multiplier", 1.0) or 1.0)
            if m > 0:
                mult *= m
        return mult

    def pspcl_ef_premium_factor(self) -> float:
        """B1/FX-5: PSPCL-vs-national grid-EF premium.

        The EF tables (static + trajectories) are national CEA figures;
        Punjab's supply mix is ~7% more thermal-heavy, so grid-import
        emissions were slightly understated (register B1). Applied
        multiplicatively at ALL THREE EF resolution points
        (``emission_factor``, ``period_emission_factor``,
        ``emission_factor_trajectory_average``) so every consumer (BAU,
        single-period, multi-period, exports) sees a consistent EF.
        Default 1.0 = off (byte-stable back-compat).
        """
        return float(self.grid.get("pspcl_premium_factor", 1.0))

    def emission_factor(self) -> float:
        # FX-5/B1: x PSPCL premium (1.0 when unset).
        return (float(self.grid["emission_factor_kgco2_per_kwh"])
                * self.pspcl_ef_premium_factor())

    def import_capacity_limit_kw(self) -> float:
        return float(self.grid.get("import_capacity_limit_kw", 1e9))

    def export_capacity_limit_kw(self) -> float:
        return float(self.grid.get("export_capacity_limit_kw", 1e9))

    # ----- annualised CAPEX (per actor tier) --------------------------
    def actor_discount_rate(self, actor: str) -> float:
        """Return the real discount rate for an actor tier.

        Accepts any of ``social_planner`` / ``utility`` / ``rwa_pooled`` /
        ``private_high_income`` / ``private_ews``. Falls back to the legacy
        ``discount_rate`` if the actor key is missing.

        Returns
        -------
        float
            Real discount rate.
        """
        return float(self.discount_rates.get(actor, self.discount_rate))

    def _annualised(self, tech: str, capex_key: str,
                     actor: str = "social_planner") -> float:
        tech_cfg = self.technologies[tech]
        capex = float(tech_cfg[capex_key])
        lifetime = int(tech_cfg["lifetime_years"])
        rate = self.actor_discount_rate(actor)
        return annualised_capex(
            capex, rate, lifetime,
            eol_cost_fraction=self.end_of_life_cost_fraction(),
        )

    def end_of_life_cost_fraction(self) -> float:
        """ audit: fraction of original CAPEX accrued each year
        as end-of-life decommissioning / disposal / recycling cost.

        Read from top-level ``end_of_life_cost_fraction`` in
        ``economics.yaml`` (default 0.05 if absent). Applied uniformly
        across all techs; per-tech overrides can be added later via a
        ``tech[\"end_of_life_cost_fraction\"]`` field if the audit demands
        finer granularity.
        """
        return float(self.__dict__.get("end_of_life_cost_fraction_raw", 0.0))

    # ----- (A12): electrical loss accessors ----------------
    def dc_loss_fraction(self) -> float:
        """Multiplicative penalty on every PV-yield builder.

        Represents inverter conversion + DC string + module mismatch
        losses. Read from ``electrical_losses.dc_loss_fraction`` in
        ``economics.yaml`` (default 0.0 so legacy fixtures stay flat).
        """
        return float(self.__dict__.get("dc_loss_fraction_raw", 0.0))

    # ----- (Phase 1B): learning-curve + degradation accessors -
    def tech_degradation_per_year(self, tech: str) -> float:
        """Per-year fractional output degradation for a given tech.

        Phase 1B: currently REFERENCE DATA only — not yet
        consumed by the LP / dispatch. Stage F task: wire into a
        time-averaged lifetime yield factor for `lifetime_cost_inr`.
        Anchored to Dubey 2017 India composite-climate field study
        (1.42 %/yr for rooftop hot-zone; 1.0 %/yr for utility ground-mount
        with better maintenance).
        """
        techs = self.technologies or {}
        return float((techs.get(tech) or {}).get("degradation_per_year", 0.0))

    def tech_capex_real_decline_per_year(self, tech: str) -> float:
        """Per-year real CAPEX decline rate for a given tech (2030 onward).

        Phase 1B: currently REFERENCE DATA only — not yet
        consumed by the LP. Stage F task: apply a time-averaged decline
        factor to the lifetime CAPEX recovery so late-deployed kWp
        receives the learning discount. Sources: TERI ETC (rooftop PV 1.2
        %/yr 2030-2050), BNEF + India BESS auction data (battery 3.0
        %/yr 2030-2050).
        """
        techs = self.technologies or {}
        return float((techs.get(tech) or {}).get("capex_real_decline_per_year", 0.0))

    def lifetime_averaged_capex_factor(self, tech: str,
                                        lifetime_yrs: Optional[int] = None) -> float:
        """Time-averaged CAPEX multiplier over a deployment horizon.

        Integral of (1 - d)^t dt / T = (1 - (1-d)^T) / (d * T), where d
        is the real annual decline rate and T is the lifetime. Returns
        1.0 when decline rate is zero (no learning effect).

        Useful for thesis sensitivity calculations even before the LP
        wiring lands: multiply a tech's annualised CAPEX by this factor
        to estimate what late-horizon kWp would have cost.
        """
        d = self.tech_capex_real_decline_per_year(tech)
        if d <= 0:
            return 1.0
        if lifetime_yrs is None:
            techs = self.technologies or {}
            lifetime_yrs = int((techs.get(tech) or {}).get("lifetime_years", 25))
        if lifetime_yrs <= 0:
            return 1.0
        return (1.0 - (1.0 - d) ** lifetime_yrs) / (d * lifetime_yrs)

    def pspcl_grid_loss_fraction(self, year: Optional[int] = None) -> float:
        """Upstream PSPCL transmission + distribution loss fraction.

 (Phase 1A — the author realism-gap audit): the A12 last-mile
        ac/dc losses capture losses INSIDE the district receiving bus.
        PSPCL's UPSTREAM grid (long-haul transmission + LV/MV distribution
        from generating station to district substation) loses an additional
        10.73 % per the FY 2023-24 PSPCL audit (T&D physical only — the
        AT&C 34.5 % spike is the collection-side subsidy delay, transient,
        not modelled).

        Applied to ``grid_import_kwh`` SOURCE-SIDE only. V2G / battery /
        biomass / WTE / biogas all sit ON the district bus alongside the
        load — they only pay the last-mile ac_loss, not this. Exports
        leave the district at the load bus (net-metering convention) so
        PSPCL T&D is on PSPCL's side, not the prosumer's.

        Stacks MULTIPLICATIVELY with ``ac_loss_fraction``:
            effective_grid_delivery = (1 - pspcl_loss) × (1 - ac_loss)
            source_grid_kWh = load_kWh / effective_grid_delivery.

: when ``year`` is given AND a
        ``pspcl_grid_loss_by_period`` trajectory is configured, return the
        interpolated technical loss for that year. The counterfactual grid
        decarbonises 69% across the horizon (``period_emission_factor``
        0.5106 -> 0.1605); holding its NETWORK losses flat over the same 25
        years was inconsistent, and asymmetric in the district's favour
        because BAU imports everything. The trajectory is deliberately
        shallow - RDSS targets AT&C, which is mostly a billing improvement,
        while this figure is physical loss only. See economics.yaml.

        ``year=None`` returns the flat 2030 value, so the single-period and
        heuristic paths stay byte-exact.

        Defaults to 0.0 for back-compat with legacy fixtures + tests.
        """
        flat = float(self.__dict__.get("pspcl_grid_loss_fraction_raw", 0.0))
        if year is None:
            return flat
        traj = self.__dict__.get("pspcl_grid_loss_by_period_raw") or {}
        if not traj:
            return flat
        return float(self._interp_trajectory(traj, int(year)))

    def ac_loss_fraction(self) -> float:
        """Multiplicative penalty on AC-bus deliveries.

        Applied to grid_import + V2G_discharge + battery_discharge as
        “effective delivery = source kWh * (1 - ac_loss_fraction)”.
        Equivalent to inflating the LP-side draw by 1 / (1 - ac_loss)
        to meet the same load. Read from
        ``electrical_losses.ac_loss_fraction`` in ``economics.yaml``
        (default 0.0).
        """
        return float(self.__dict__.get("ac_loss_fraction_raw", 0.0))

    def effective_rooftop_pv_capex_inr_per_kwp(self) -> float:
        """Active rooftop PV CAPEX per kWp after central PV subsidies.

 (A18 LP-side wiring): returns the share-weighted
        blended CAPEX from ``technologies.rooftop_pv.module_types`` when
        the table is populated; otherwise falls back to the legacy
        single ``capex_inr_per_kwp`` field. The mix-blend currently
        resolves to ~Rs 35,400/kWp (vs the legacy single Rs 35,000).

 (PM Surya Ghar Yojana): the result is also reduced
        by ``grid.rooftop_pv_capex_subsidy_fraction`` (default 0.30) to
        reflect the central-government residential rooftop subsidy
        (Pradhan Mantri Surya Ghar Muft Bijli Yojana, Feb 2024). Disable
        with `rooftop_pv_capex_subsidy_fraction: 0.0` in economics.yaml
        for policy-without-subsidy sensitivity runs.
        """
        rt = (self.technologies or {}).get("rooftop_pv") or {}
        if not rt:
            return 0.0
        types = rt.get("module_types") or {}
        if not types:
            base = float(rt.get("capex_inr_per_kwp", 35000))
        else:
            total_share = sum(float(v.get("share", 0.0)) for v in types.values())
            if total_share <= 0:
                base = float(rt.get("capex_inr_per_kwp", 35000))
            else:
                base = sum(
                    float(v.get("share", 0.0))
                    * float(v.get("capex_inr_per_kwp", 0.0))
                    for v in types.values()
                ) / total_share
        # PM Surya Ghar central subsidy
        sub = self.rooftop_pv_capex_subsidy_fraction()
        return base * (1.0 - max(0.0, min(1.0, sub)))

    def rooftop_pv_annualised_inr_per_kwp(self,
                                            actor: Optional[str] = None) -> float:
        """Annualised cost per kWp of rooftop PV.

 (ownership correction): when ``actor`` is None (the default,
        used by every dispatch call site), return the DEPLOYMENT-weighted blend
        across building owners (``rooftop_owner_weights`` -> ``rooftop_owner_actors``
        -> ``discount_rates``). Empty weights => legacy flat ``rwa_pooled`` rate, so
        the single-bus path stays byte-exact for fixtures without the ownership
        config. An explicit ``actor`` returns that one tier's rate (used by the
        blend itself + any tier-specific caller).

 (A18 LP-side wiring): the per-kWp CAPEX is the share-weighted
        blend across ``module_types`` (mono-PERC + poly-Si + thin-film CdTe) when
        that table is present; legacy single ``capex_inr_per_kwp`` is the fallback.
        """
        if actor is None:
            weights = self.rooftop_owner_weights or {}
            if weights:
                actors = self.rooftop_owner_actors or {}
                return sum(
                    float(wt) * self.rooftop_pv_annualised_inr_per_kwp(
                        actors.get(owner, "rwa_pooled"))
                    for owner, wt in weights.items()
                )
            actor = "rwa_pooled"
        tech = self.technologies["rooftop_pv"]
        capex = self.effective_rooftop_pv_capex_inr_per_kwp()
        lifetime = int(tech["lifetime_years"])
        rate = self.actor_discount_rate(actor)
        annual = annualised_capex(
            capex, rate, lifetime,
            eol_cost_fraction=self.end_of_life_cost_fraction(),
        )
        opex = capex * float(tech["opex_fraction_of_capex_per_year"])
        return annual + opex

    # (A18 module-mix LP decision variable, Claude 2):
    # per-module annualised cost so the Pyomo LP can choose mono / poly /
    # thin-film fractions instead of consuming a pre-blended single value.
    # Returns 0.0 when the module type is missing from the YAML table.
    def rooftop_pv_module_annualised_inr_per_kwp(
        self,
        module_type: str,
        actor: str = "rwa_pooled",
    ) -> float:
        """Annualised cost (INR / kWp / yr) for a single PV module type.

        Reads ``technologies.rooftop_pv.module_types[<module_type>]``.
        Each module type has its own ``capex_inr_per_kwp``. Lifetime and
        OPEX fraction are inherited from the top-level rooftop_pv block
        (no public 2030 source breaks these out per module type). EOL
        cost fraction is the same shared multiplier.
        """
        rt = (self.technologies or {}).get("rooftop_pv") or {}
        types = rt.get("module_types") or {}
        m_cfg = types.get(module_type) or {}
        capex = float(m_cfg.get("capex_inr_per_kwp", 0.0))
        if capex <= 0.0:
            return 0.0
        # (D2 fix,: apply the PM Surya Ghar
        # central rooftop CAPEX subsidy to the per-MODULE cost too. The
        # aggregate path (effective_rooftop_pv_capex_inr_per_kwp) already
        # applies it, but when the A18 module-mix LP is active the rooftop
        # cost runs through THIS method, so without the line below PMSGY
        # silently became a no-op in production. Same flat fractional
        # reduction; scales annuity + OPEX identically to the aggregate.
        sub = self.rooftop_pv_capex_subsidy_fraction()
        capex *= (1.0 - max(0.0, min(1.0, sub)))
        lifetime = int(rt.get("lifetime_years", 25))
        opex_frac = float(rt.get("opex_fraction_of_capex_per_year", 0.0))
        rate = self.actor_discount_rate(actor)
        annual = annualised_capex(
            capex, rate, lifetime,
            eol_cost_fraction=self.end_of_life_cost_fraction(),
        )
        opex = capex * opex_frac
        return annual + opex

    def rooftop_pv_module_share(self, module_type: str) -> float:
        """Share fraction (in [0,1]) for a single PV module type.

        Used as the LP variable's UPPER bound: each module type can take
        at most ``share * total_rooftop_ceiling``. This is a soft realism
        cap that lets the LP pick mostly mono / mostly thin-film if it
        wants but stops it loading 100 % of capacity on the cheapest
        single type (which would erase the calibrated A18 market mix).
        Returns 0.0 if the module is missing or the table is empty.
        """
        rt = (self.technologies or {}).get("rooftop_pv") or {}
        types = rt.get("module_types") or {}
        m_cfg = types.get(module_type) or {}
        return max(0.0, float(m_cfg.get("share", 0.0)))

    def rooftop_pv_module_types(self) -> List[str]:
        """List of module-type keys defined in the YAML (empty if absent)."""
        rt = (self.technologies or {}).get("rooftop_pv") or {}
        types = rt.get("module_types") or {}
        return [str(k) for k in types.keys()]

    def solar_farm_annualised_inr_per_kwp(self,
                                            actor: str = "utility") -> float:
        tech = self.technologies["solar_farm"]
        annual = self._annualised("solar_farm", "capex_inr_per_kwp", actor)
        opex = float(tech["capex_inr_per_kwp"]) * float(
            tech["opex_fraction_of_capex_per_year"]
        )
        return annual + opex

    def battery_annualised_inr_per_kwh(self,
                                         actor: str = "utility") -> float:
        # (OWNERSHIP CORRECTION,
        # every type"). Was `rwa_pooled` (8.5%) with NO rationale recorded
        # anywhere in the code or config. The built battery is ~494 MWh - a
        # district-scale asset on the distribution network, not a housing
        # society's rooftop pack. It is financed like the solar farm and the
        # CHP plants, i.e. at the CERC regulated WACC. Worth -Rs 5.91 Cr/yr
        # (-7.7%). See the ownership map in config/economics.yaml.
        tech = self.technologies["li_ion_battery"]
        annual = self._annualised("li_ion_battery", "capex_inr_per_kwh", actor)
        opex = float(tech["capex_inr_per_kwh"]) * float(
            tech["opex_fraction_of_capex_per_year"]
        )
        return annual + opex

    def v2g_annualised_inr_per_unit(self,
                                      actor: str = "private_high_income") -> float:
        tech = self.technologies["v2g_charger"]
        annual = self._annualised("v2g_charger", "capex_inr_per_unit", actor)
        opex = float(tech["opex_inr_per_unit_per_year"])
        return annual + opex

    # ----- Stage C: biomass CHP + tracked PV + carbon objective ---------

    def biomass_chp_annualised_inr_per_kw_e(self,
                                              actor: str = "utility") -> float:
        """Annualised cost per kW-electrical of biomass CHP capacity.

        Returns
        -------
        float
            INR / kW-e / yr (CAPEX annuity + EOL accrual + fixed OPEX,
            excluding fuel).
        """
        tech = self.technologies.get("biomass_chp", {})
        if not tech:
            return 0.0
        capex = float(tech["capex_inr_per_kw_e"])
        lifetime = int(tech["lifetime_years"])
        rate = self.actor_discount_rate(actor)
        annual = annualised_capex(
            capex, rate, lifetime,
            eol_cost_fraction=self.end_of_life_cost_fraction(),
        )
        opex = capex * float(tech.get("opex_fraction_of_capex_per_year", 0.04))
        return annual + opex

    def biomass_fuel_cost_inr_per_kwh(self) -> float:
        """Variable fuel cost per kWh of electricity generated.

        Computed as: fuel_cost_inr_per_tonne / (cal_value_kJ_per_tonne * eta_e)
        Tonne → kg = 1000; MJ → kWh = / 3.6; 1 MJ/kg = 1e6 J/tonne / 3.6e6 J/kWh ≈ 0.278 kWh/kg.
        Net: kWh_thermal_per_tonne = cal_MJ_kg * 1000 / 3.6
             kWh_electric_per_tonne = kWh_thermal × electrical_efficiency
             INR / kWh = fuel_inr_per_tonne / kWh_electric_per_tonne.
        """
        tech = self.technologies.get("biomass_chp", {})
        if not tech:
            return 0.0
        fuel = float(tech.get("fuel_cost_inr_per_tonne", 0))
        cal = float(tech.get("fuel_calorific_value_mj_per_kg", 14.5))
        eta = float(tech.get("electrical_efficiency", 0.27))
        if cal <= 0 or eta <= 0:
            return 0.0
        kwh_per_tonne_thermal = cal * 1000.0 / 3.6
        kwh_per_tonne_electric = kwh_per_tonne_thermal * eta
        return fuel / kwh_per_tonne_electric if kwh_per_tonne_electric > 0 else 0.0

    def biomass_operating_hours_per_year(self) -> float:
        tech = self.technologies.get("biomass_chp", {})
        return float(tech.get("operating_hours_per_year", 7000))

    def biomass_emission_factor_kgco2_per_kwh(self) -> float:
        tech = self.technologies.get("biomass_chp", {})
        return float(tech.get("operational_emission_kgco2_per_kwh", 0.05))

    # ----- FX-6 / N7+: straw fuel-supply realism --------
    def biomass_monthly_fuel_cost_multiplier(self, month: str) -> float:
        """Per-month straw-cost multiplier (storage economics).

        The base ``fuel_cost_inr_per_tonne`` is the harvest-window
        delivered price; stored straw accumulates covered-storage,
        handling and dry-matter-loss costs toward a pre-harvest (Sep)
        peak. Missing table or month -> 1.0 (back-compat).
        """
        tech = self.technologies.get("biomass_chp", {})
        tbl = tech.get("fuel_monthly_cost_multiplier", {}) or {}
        return float(tbl.get(month, 1.0))

    def biomass_monthly_availability_fraction(self, month: str) -> float:
        """Per-month ceiling on biomass generation as a fraction of
        nameplate energy in that month fix).

        Encodes the pre-harvest inventory trough + monsoon wet-straw
        handling derate (Jul-Sep). The LP keeps fresh-straw months at
        full availability. Missing table or month -> 1.0 (back-compat;
        the per-slice capacity constraint is then the only ceiling).
        """
        tech = self.technologies.get("biomass_chp", {})
        tbl = tech.get("fuel_monthly_availability_fraction", {}) or {}
        return float(tbl.get(month, 1.0))

    def biomass_fuel_price_period_multiplier(self, year: Optional[int] = None
                                             ) -> float:
        """TRJ-4: real straw-price COMPETITION path - CBG /
        industrial-boiler / biomass-power ex-situ demand tightens the
        catchment straw market across the horizon (CAQM Tier-1 anchors;
        derivation in economics.yaml ``biomass_chp.
        fuel_price_multiplier_by_period``). Stacks multiplicatively with
        the monthly storage multiplier. ``year=None`` or a missing table
        returns 1.0 (byte-exact single-period base)."""
        if year is None:
            return 1.0
        tech = self.technologies.get("biomass_chp", {})
        tbl = tech.get("fuel_price_multiplier_by_period") or {}
        return self._interp_year_table(tbl, year, default=1.0)

    def biomass_annual_straw_energy_cap_kwh(self) -> Optional[float]:
        """Annual electric-energy budget (kWh_e) from the district straw
        catchment (N7): ``annual_straw_available_tonnes`` x calorific value
        x electrical efficiency. Returns None when the tonnage key is
        absent (back-compat: no annual fuel budget constraint)."""
        tech = self.technologies.get("biomass_chp", {})
        tonnes = tech.get("annual_straw_available_tonnes")
        if tonnes is None:
            return None
        cal = float(tech.get("fuel_calorific_value_mj_per_kg", 14.5))
        eta = float(tech.get("electrical_efficiency", 0.27))
        if cal <= 0 or eta <= 0:
            return None
        return float(tonnes) * 1000.0 * cal / 3.6 * eta

    def tracked_pv_capex_multiplier(self) -> float:
        tech = self.technologies.get("tracked_pv", {})
        return float(tech.get("capex_multiplier_vs_fixed", 1.25))

    def tracked_pv_yield_multiplier(self) -> float:
        tech = self.technologies.get("tracked_pv", {})
        return float(tech.get("yield_multiplier_vs_fixed", 1.18))

    def tracked_pv_land_ratio_vs_fixed(self) -> float:
        """CRIT-2b /: land consumed per kWp of TRACKED
        farm capacity, in units of fixed-tilt kWp-equivalents (GCR-derived
        1.33; full citation block in economics.yaml tracked_pv). The Pyomo
        builders charge `fixed + ratio x tracked <= area-derived farm cap`.
        Absent key (legacy fixtures) -> 1.0, byte-exact old behaviour;
        clamped >= 1.0 (a tracker never uses LESS land than fixed)."""
        tech = self.technologies.get("tracked_pv", {})
        return max(1.0, float(tech.get("land_ratio_vs_fixed", 1.0)))

    def tracked_pv_annualised_inr_per_kwp(self,
                                            actor: str = "utility") -> float:
        """Annualised cost per kWp of single-axis-tracked ground-mount PV.

        Equals solar_farm_annualised × tracked_pv_capex_multiplier.
        """
        base = self.solar_farm_annualised_inr_per_kwp(actor)
        return base * self.tracked_pv_capex_multiplier()

    # ----- Stage C round 2: WTE + biogas + thermal cold storage ---------

    def _generic_dispatchable_annualised(self, key: str,
                                          actor: str) -> float:
        """Helper for biomass-pattern dispatchable techs (WTE, biogas).

 passes the global ``end_of_life_cost_fraction`` so
        WTE flue-gas-treatment demolition and biogas digester end-of-life
        decom flow into the levelised cost.
        """
        tech = self.technologies.get(key, {})
        if not tech:
            return 0.0
        capex = float(tech["capex_inr_per_kw_e"])
        lifetime = int(tech["lifetime_years"])
        rate = self.actor_discount_rate(actor)
        annual = annualised_capex(
            capex, rate, lifetime,
            eol_cost_fraction=self.end_of_life_cost_fraction(),
        )
        opex = capex * float(tech.get("opex_fraction_of_capex_per_year", 0.04))
        return annual + opex

    # WTE
    def wte_annualised_inr_per_kw_e(self, actor: str = "utility") -> float:
        return self._generic_dispatchable_annualised("wte_plant", actor)

    def wte_fuel_cost_inr_per_kwh(self) -> float:
        # WTE has zero or negative fuel cost (tipping fees); placeholder 0.
        tech = self.technologies.get("wte_plant", {})
        return float(tech.get("fuel_cost_inr_per_tonne", 0.0))   # treated as INR/kWh effectively 0 since fuel is municipal waste

    def wte_landfill_diversion_credit_inr_per_kwh(self) -> float:
        """Caveat-2 fix: WTE plants avoid landfill methane (~25x CO2) so
        receive a ~Rs 2-4/kWh diversion credit that reduces their effective
        marginal cost in dispatch. Default 0 when absent (legacy behaviour).
        """
        tech = self.technologies.get("wte_plant", {})
        return float(tech.get("landfill_diversion_credit_inr_per_kwh", 0.0))

    def wte_effective_fuel_cost_inr_per_kwh(self) -> float:
        """Net WTE marginal fuel cost after the landfill diversion credit.

        Used in the dispatch merit-order eligibility check (cheaper plants
        run first) and to reduce total cost. Can go negative when the
        diversion credit exceeds the placeholder fuel cost.
        """
        return (self.wte_fuel_cost_inr_per_kwh()
                - self.wte_landfill_diversion_credit_inr_per_kwh())

    def wte_operating_hours_per_year(self) -> float:
        return float(self.technologies.get("wte_plant", {})
                       .get("operating_hours_per_year", 7500))

    def wte_emission_factor_kgco2_per_kwh(self) -> float:
        return float(self.technologies.get("wte_plant", {})
                       .get("operational_emission_kgco2_per_kwh", 0.20))

    def wte_capacity_cap_kw_e(self, population: int = 100_000) -> float:
        """Upper bound on WTE capacity, sized to district MSW availability.

        MSW (t/yr) = pop × kg_per_cap_per_day × 365 / 1000
        kWh_th/yr = MSW_kg × cal_MJ_kg × 1000 / 3.6
        kWh_e/yr  = kWh_th × eta_e
        kW_cap    = kWh_e/yr / operating_hours
        """
        tech = self.technologies.get("wte_plant", {})
        if not tech:
            return 0.0
        msw_kg_cap_day = float(tech.get("msw_kg_per_cap_per_day", 0.5))
        cal_mj_kg = float(tech.get("fuel_calorific_value_mj_per_kg", 8.0))
        eta = float(tech.get("electrical_efficiency", 0.22))
        hours = self.wte_operating_hours_per_year()
        msw_kg_yr = population * msw_kg_cap_day * 365
        kwh_e_yr = msw_kg_yr * cal_mj_kg * 1000.0 / 3.6 * eta / 1000.0
        return kwh_e_yr / hours if hours > 0 else 0.0

    # Biogas
    def biogas_annualised_inr_per_kw_e(self,
                                         actor: str = "social_planner") -> float:
        # (OWNERSHIP CORRECTION). Was `utility` (6.5%). This is
        # the SEWAGE-WORKS digester, and sewage treatment is a municipal
        # function delivered by the urban local body under AMRUT - not an
        # IPP selling under a PPA. The ULB borrows at the social-planner
        # rate. Worth -Rs 0.14 Cr/yr (-6.1%). Contrast biomass_chp and
        # wte_plant, which correctly KEEP `utility`: PEDA Table-I shows ten
        # of eleven Punjab straw plants are private limited companies, and
        # Indian WTE is a private concession - for both, CERC's WACC IS the
        # regulated return allowed to that private developer.
        return self._generic_dispatchable_annualised("biogas_plant", actor)

    def biogas_fuel_cost_inr_per_kwh(self) -> float:
        return float(self.technologies.get("biogas_plant", {})
                       .get("fuel_cost_inr_per_kwh", 0.5))

    def biogas_operating_hours_per_year(self) -> float:
        return float(self.technologies.get("biogas_plant", {})
                       .get("operating_hours_per_year", 7800))

    def biogas_emission_factor_kgco2_per_kwh(self) -> float:
        return float(self.technologies.get("biogas_plant", {})
                       .get("operational_emission_kgco2_per_kwh", 0.02))

    # Thermal cold storage (cooling-specific battery analogue for Stage C)
    def thermal_storage_annualised_inr_per_kwh(self,
                                                  actor: str = "private_high_income") -> float:
        # (OWNERSHIP CORRECTION). Was `rwa_pooled` (8.5%), which
        # is the one tier that cannot be right: every entry in this tech's
        # own `eligible_categories` is COMMERCIAL or PUBLIC (shopping_centre,
        # office, hotel_guesthouse, healthcare, school,
        # warehouse_cold_storage, retail_highstreet, public_services) - not
        # one is a residents' welfare association. Commercial owners
        # dominate the eligible floor area, so the private rate applies.
        # This is also the CONSERVATIVE direction (LCOE Rs 1.372 -> 1.524),
        # which is the right way to be wrong about a technology supplying
        # 0.015% of district demand. The block's own comment names the
        # "fragmented-ownership problem (developer pays for tank, tenants
        # get the savings)", which argues for a HIGHER rate, not a pooled
        # residential one.
        tech = self.technologies.get("thermal_cold_storage", {})
        if not tech:
            return 0.0
        capex = float(tech["capex_inr_per_kwh_thermal"])
        lifetime = int(tech["lifetime_years"])
        rate = self.actor_discount_rate(actor)
        annual = annualised_capex(
            capex, rate, lifetime,
            eol_cost_fraction=self.end_of_life_cost_fraction(),
        )
        opex = capex * float(tech.get("opex_fraction_of_capex_per_year", 0.015))
        return annual + opex

    def thermal_storage_round_trip_efficiency(self) -> float:
        return float(self.technologies.get("thermal_cold_storage", {})
                       .get("round_trip_efficiency", 0.80))

    def thermal_storage_eligible_categories(self) -> List[str]:
        """Category names that can host central-cooling thermal storage.

 targeting refinement: TES requires chilled-water
        distribution which residential and small retail don't have.
        """
        tech = self.technologies.get("thermal_cold_storage", {})
        return list(tech.get("eligible_categories", []))

    def thermal_storage_kwh_per_m2(self) -> float:
        """kWh of thermal storage capacity per m^2 of eligible-cell floor area."""
        tech = self.technologies.get("thermal_cold_storage", {})
        return float(tech.get("kwh_per_m2_floor_area", 0.05))

    # ----- Carbon-cost weighted objective (Stage C) ---------------------

    def carbon_alphas(self) -> List[float]:
        """Return the alpha sweep values for the cost / carbon Pareto.

        Returns
        -------
        List[float]
            Five points in [0, 1] (default [0.0, 0.25, 0.5, 0.75, 1.0]).
        """
        cobj = self.__dict__.get("carbon_objective_raw")
        if cobj:
            return [float(a) for a in cobj.get("alphas", [0, 0.25, 0.5, 0.75, 1.0])]
        return [0.0, 0.25, 0.5, 0.75, 1.0]

    def carbon_price_inr_per_kgco2(self) -> float:
        """Carbon shadow price in INR / kgCO2 used to weight emissions."""
        cobj = self.__dict__.get("carbon_objective_raw")
        if cobj:
            return float(cobj.get("carbon_price_inr_per_kgco2", 2.5))
        return 2.5

    # ----- (A18): PV module-type blended properties --------
    def pv_module_mix_summary(self) -> Dict[str, float]:
        """Share-weighted blended PV module-type properties.

        Reads `technologies.rooftop_pv.module_types` and returns a dict
        with blended ``capex_inr_per_kwp``, ``efficiency``, and
        ``temp_coefficient_per_c``. Falls back to the legacy single
        ``rooftop_pv.capex_inr_per_kwp`` + an `efficiency` of 0.20 +
        a `temp_coefficient_per_c` of 0.004 when the new table is
        absent. Returned dict is empty if no rooftop_pv config exists.
        """
        rt = (self.technologies or {}).get("rooftop_pv") or {}
        if not rt:
            return {}
        types = rt.get("module_types") or {}
        if not types:
            return {
                "capex_inr_per_kwp": float(rt.get("capex_inr_per_kwp", 35000)),
                "efficiency": 0.20,
                "temp_coefficient_per_c": 0.004,
                "source": "legacy single rooftop_pv (no module_types table)",
            }
        total_share = sum(float(v.get("share", 0.0)) for v in types.values())
        if total_share <= 0:
            return {"capex_inr_per_kwp": float(rt.get("capex_inr_per_kwp", 35000))}
        capex = sum(
            float(v.get("share", 0.0))
            * float(v.get("capex_inr_per_kwp", 0.0))
            for v in types.values()
        ) / total_share
        eff = sum(
            float(v.get("share", 0.0)) * float(v.get("efficiency", 0.0))
            for v in types.values()
        ) / total_share
        tc = sum(
            float(v.get("share", 0.0))
            * float(v.get("temp_coefficient_per_c", 0.0))
            for v in types.values()
        ) / total_share
        return {
            "capex_inr_per_kwp": capex,
            "efficiency": eff,
            "temp_coefficient_per_c": tc,
            "source": "share-weighted across mono_perc / poly_si / thin_film_cdte",
        }

    # ----- A21: price + grid-EF trajectory scenarios -------------------

    def active_price_scenario(self) -> Optional[str]:
        """Return the name of the active price-trajectory scenario, or None.

        Reads `config/price_trajectories.yaml`'s `active_scenario` field via
        the cached `price_trajectories_raw` dict attached at load time.
        Returns None when the YAML is absent (default), when the active
        scenario is empty, or when the named scenario doesn't exist.
        """
        traj = self.__dict__.get("price_trajectories_raw") or {}
        if not traj:
            return None
        active = traj.get("active_scenario")
        if not active:
            return None
        scenarios = traj.get("scenarios") or {}
        if active in scenarios:
            return str(active)
        return None

    def _active_price_scenario_payload(self) -> Optional[Dict[str, object]]:
        active = self.active_price_scenario()
        if not active:
            return None
        traj = self.__dict__.get("price_trajectories_raw") or {}
        return (traj.get("scenarios") or {}).get(active)

    def tariff_escalation_real_annual_value(self) -> float:
        """Real annual tariff escalation. Honours active price scenario."""
        payload = self._active_price_scenario_payload()
        if payload and "tariff_escalation_real_annual" in payload:
            return float(payload["tariff_escalation_real_annual"])
        return float(self.tariff_escalation_real_annual)

    # ----- Stage C round 3: time-varying grid emission factor ----------

    def emission_factor_trajectory_average(self) -> float:
        """Project-lifetime-average grid emission factor (kgCO2/kWh).

        Resolution order:
          1. ACTIVE price-trajectory scenario's
             `emission_factor_trajectory_kgco2_per_kwh` table, if any
             (audit A21,).
          2. Legacy `grid.emission_factor_trajectory_kgco2_per_kwh` table
             when `use_grid_decarb_trajectory: true`.
          3. Static `grid.emission_factor_kgco2_per_kwh`.

        Always returns the project-lifetime mean across base_year.. base_year + lifetime.
        """
        # Pathway 1: active scenario trajectory.
        payload = self._active_price_scenario_payload()
        scenario_traj: Dict[str, float] = {}
        if payload:
            scenario_traj = (
                payload.get("emission_factor_trajectory_kgco2_per_kwh") or {}
            )
        if scenario_traj:
            return self._average_trajectory(scenario_traj)
        # Pathway 2 + 3: legacy.
        if not bool(self.grid.get("use_grid_decarb_trajectory", False)):
            return self.emission_factor()
        traj = self.grid.get("emission_factor_trajectory_kgco2_per_kwh", {})
        if not traj:
            return self.emission_factor()
        return self._average_trajectory(traj)

    def _average_trajectory(self, traj: Dict[str, float]) -> float:
        """Project-lifetime mean of a year-keyed EF trajectory (linear interp)."""
        lifetime = int(self.grid.get("project_lifetime_years", 25))
        start_year = int(self.base_year)
        try:
            pts = sorted((int(y), float(v)) for y, v in traj.items())
        except (ValueError, TypeError):
            return self.emission_factor()
        if not pts:
            return self.emission_factor()
        total = 0.0
        n = 0
        for offset in range(lifetime):
            year = start_year + offset
            if year <= pts[0][0]:
                v = pts[0][1]
            elif year >= pts[-1][0]:
                v = pts[-1][1]
            else:
                for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
                    if y0 <= year <= y1:
                        v = v0 + (v1 - v0) * (year - y0) / (y1 - y0)
                        break
            total += v
            n += 1
        if n <= 0:
            return self.emission_factor()   # premium applied inside
        # FX-5/B1: trajectory mean needs the premium applied here.
        return (total / n) * self.pspcl_ef_premium_factor()

    # ----- Stage C round 3: embodied carbon ----------------------------

    def embodied_carbon(self) -> Dict[str, float]:
        """Return the embodied-carbon table (kgCO2 per unit-of-capacity)."""
        return dict(self.__dict__.get("embodied_carbon_raw", {}))

    def include_embodied_carbon(self) -> bool:
        cobj = self.__dict__.get("carbon_objective_raw", {})
        return bool(cobj.get("include_embodied_carbon", False))

    def annualised_embodied_kgco2(self, tech_kgco2_per_unit: float,
                                    units: float, lifetime_years: int) -> float:
        """Annualise a one-time embodied-carbon outlay over its lifetime.

        Caveat-12 fix: bumps the manufactured embodied carbon by the
        end-of-life decommissioning + recycling fraction (default 10%)
        so PV-panel disposal, lithium recovery, and biomass-plant
        demolition are folded into the headline embodied number.
        """
        if lifetime_years <= 0:
            return 0.0
        eol_mult = 1.0 + self.end_of_life_carbon_fraction()
        return tech_kgco2_per_unit * units * eol_mult / lifetime_years

    def end_of_life_carbon_fraction(self) -> float:
        """End-of-life fraction (decommissioning + recycling)."""
        emb = self.__dict__.get("embodied_carbon_raw", {})
        return float(emb.get("end_of_life_carbon_fraction", 0.0))

    def embodied_kgco2_per_unit_at(self, key: str, build_year: int) -> float:
        """Embodied carbon per unit for capacity BUILT in ``build_year``.

. PV embodied carbon is not a constant across a 25-year
        horizon: module carbon intensity fell 0.61 -> 0.17 kgCO2/W over the
        recent survey period, so a panel installed in 2055 does not carry a
        2030 factory's footprint. This mirrors ``period_capex_factor`` - the
        model already prices each VINTAGE at its own capex, and embodied
        carbon is the same kind of quantity.

        Reads ``embodied_carbon.by_build_year[key]`` as a {year: value} table,
        linearly interpolated and clamped at the ends. Falls back to the flat
        ``embodied_carbon[key]`` when no table exists, so every technology
        without one is byte-unchanged.
        """
        emb = self.__dict__.get("embodied_carbon_raw", {}) or {}
        flat = float(emb.get(key, 0.0) or 0.0)
        tbl = (emb.get("by_build_year") or {}).get(key) or {}
        if not tbl:
            return flat
        try:
            pts = sorted((int(k), float(v)) for k, v in tbl.items())
        except (TypeError, ValueError):
            return flat
        if not pts:
            return flat
        y = int(build_year)
        if y <= pts[0][0]:
            return pts[0][1]
        if y >= pts[-1][0]:
            return pts[-1][1]
        for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
            if y0 <= y <= y1:
                if y1 == y0:
                    return v1
                return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
        return flat

    def project_lifetime_years(self) -> int:
        """Project planning horizon in years (default 25)."""
        return int(self.grid.get("project_lifetime_years", 25))

    # ----- (D1(b) — multi-period capacity expansion) ---------
    # Phase 0: opt-in config accessors. Phase 1: per-period parameters
    # (demand growth / grid EF / CAPEX learning / PV vintage degradation).
    # All return single-period-equivalent values when the block is
    # absent/disabled, so the legacy path is byte-for-byte unchanged.
    def multi_period_config(self) -> Dict[str, object]:
        return dict(self.__dict__.get("multi_period_raw", {}) or {})

    def multi_period_enabled(self) -> bool:
        return bool(self.multi_period_config().get("enabled", False))

    def multi_period_periods(self) -> List[Dict[str, int]]:
        """Ordered list of ``{year, represents_years}`` period dicts.

        Empty when the block is absent. ``represents_years`` should sum to
        ``project_lifetime_years`` (validated in Phase 2).
        """
        out: List[Dict[str, int]] = []
        for p in (self.multi_period_config().get("periods") or []):
            out.append({
                "year": int(p.get("year")),
                "represents_years": int(p.get("represents_years", 0)),
            })
        return out

    def multi_period_base_year(self) -> int:
        return int(self.multi_period_config().get("base_year", 2030))

    def multi_period_discount_rate(self) -> float:
        return float(self.multi_period_config().get("discount_rate_real", 0.0))

    @staticmethod
    def _interp_year_table(tbl: Dict, year: int, default: float = 1.0) -> float:
        """Clamped linear interpolation of a ``{year: value}`` table.

        Trajectory-batch helper: unlike ``_interp_trajectory``
        this degrades to ``default`` (not the emission factor) on an empty
        or malformed table, so multiplier tables fail safe to a no-op."""
        try:
            pts = sorted((int(k), float(v)) for k, v in (tbl or {}).items())
        except (TypeError, ValueError):
            return default
        if not pts:
            return default
        y = int(year)
        if y <= pts[0][0]:
            return pts[0][1]
        if y >= pts[-1][0]:
            return pts[-1][1]
        for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
            if y0 <= y <= y1:
                return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
        return pts[-1][1]

    def pv_density_ceiling_multiplier(self, year: int) -> float:
        """TRJ-1: area-limited PV cap multiplier for capacity
        CEILINGS evaluated in period ``year`` - later vintages pack more
        kWp on the same roof/land as module efficiency rises (ITRPV/NREL
        ATB; derivation + sources in economics.yaml ``multi_period.
        pv_density_ceiling_multiplier_by_period``). 1.0 at the 2030 base
        and whenever the table is absent (byte-stable back-compat)."""
        tbl = self.multi_period_config().get(
            "pv_density_ceiling_multiplier_by_period") or {}
        return self._interp_year_table(tbl, year, default=1.0)

    def pv_density_area_budget(self) -> bool:
        """: switch the multi-period PV surface caps from
        the legacy CEILING form to the AREA-BUDGET form.

        Legacy (False):  sum_v new_kwp[v]            <= base * dens[p] * land[p]
        Area   (True):   sum_v new_kwp[v] / dens[v]  <= base * land[p]

        The legacy form was written for phased land ("more land x better
        panels", dispatch.py ~2200) and was correct while the farm's land
        multiplier grew. released all 301 ha in 2030,
        flattening the land term - after which the density term silently
        re-rates ALREADY-INSTALLED vintages to later-period density on land
        that is already full (audit: 32,237 phantom farm kWp by 2055, plus
        575 carport / 811 floating). The area form conserves land: each
        vintage consumes surface at its OWN density, so a late build on
        EMPTY surface still packs denser (the 2042 canal fill survives),
        but standing capacity is never re-rated. Same pattern as the solar
        thermal `st_roof_share` constraint, which always budgeted area.

        Default False = byte-exact legacy until the re-pin flips it.
        2030 is IDENTICAL under both forms (dens[2030] = 1.0)."""
        return bool(self.multi_period_config().get(
            "pv_density_area_budget", False))

    def solar_farm_inter_row_derate(self) -> float:
        """: fixed-tilt inter-row self-shading, as an
        annual energy fraction. Derived from the model's own sun-path
        machinery (scripts/gcr_interrow_sweep.py - same `_sun_samples`
        energy weights as the building-shading table, geometry validated at
        the winter-solstice limit: first noon shading at GCR 0.648 at this
        latitude). 0.00021 at the ratified GCR 0.382, and that OVERSTATES
        the true loss (all irradiance treated as beam in a fog/diffuse
        winter). Default 0.0 = byte-exact legacy until the batch re-pin
        sets `technologies.solar_farm.inter_row_shading_derate`."""
        tech = (self.technologies or {}).get("solar_farm", {}) or {}
        return float(tech.get("inter_row_shading_derate", 0.0) or 0.0)

    # ----- Trajectory-batch A/B scenario hooks --------------
    # DEM-3 / DEM-8 / REV-3. Register 0e classed these as SCENARIOS: every
    # accessor returns its no-op value unless the hook's `enabled` is true,
    # so the production build is byte-identical with the block absent.

    def scenario_hook(self, name: str) -> Dict[str, object]:
        """Return one `scenario_hooks.<name>` block IF enabled, else {}."""
        block = (self.__dict__.get("scenario_hooks_raw") or {}).get(name) or {}
        if not bool(block.get("enabled", False)):
            return {}
        return dict(block)

    def duck_curve_import_multiplier(self, year: int, daypart: str) -> float:
        """DEM-3: retail-ToD drift multiplier for (period, daypart) -
        midday cheapens / evening firms as grid solar saturates (sources
        in economics.yaml scenario_hooks.duck_curve_drift). 1.0 when the
        hook is off or the (year, daypart) has no entry."""
        hook = self.scenario_hook("duck_curve_drift")
        if not hook:
            return 1.0
        tbl = (hook.get("import_multiplier_by_period_daypart") or {})
        row = tbl.get(year) or tbl.get(str(year)) or {}
        return float(row.get(daypart, 1.0) or 1.0)

    def duck_curve_export_multiplier(self, year: int) -> float:
        """DEM-3: feed-in value decline path. 1.0 when the hook is off."""
        hook = self.scenario_hook("duck_curve_drift")
        if not hook:
            return 1.0
        tbl = hook.get("export_multiplier_by_period") or {}
        return self._interp_year_table(tbl, year, default=1.0)

    def carbon_price_by_period_inr_per_kgco2(self, year: int) -> float:
        """DEM-8: real carbon price (CCTS/IEA WEO path) at ``year``.
        0.0 when the hook is off."""
        hook = self.scenario_hook("carbon_price")
        if not hook:
            return 0.0
        tbl = hook.get("price_inr_per_kgco2_by_period") or {}
        return self._interp_year_table(tbl, year, default=0.0)

    def reserve_margin_params(self) -> Dict[str, object]:
        """REV-3: {margin_fraction, capacity_credit{...}} when enabled,
        {} when off (no constraint built)."""
        return self.scenario_hook("reserve_margin")

    # (Stage D scaffold): per-cell / multi-bus dispatch gate.
    # Mirrors the multi_period gating pattern: when stage_d.enabled is
    # false, solve_dispatch_pyomo branches to the existing single-bus
    # path byte-for-byte. When true, branches to a new
    # _build_pyomo_model_stage_d (NOT YET BUILT).
    def stage_d_config(self) -> Dict[str, object]:
        return dict(self.__dict__.get("stage_d_raw", {}) or {})

    # (Phase 4): the REPORT-ONLY equity + P2P parameters. A
    # transfer, not a system cost, so these are read only by
    # `energy/equity_report.py` and never by the cost-minimisation LP.
    def equity_report_config(self) -> Dict[str, object]:
        return dict(self.__dict__.get("equity_report_raw", {}) or {})

    def stage_d_enabled(self) -> bool:
        return bool(self.stage_d_config().get("enabled", False))

    def stage_d_feature_enabled(self, feature_name: str) -> bool:
        """Per-feature flag inside the stage_d block. Defaults False."""
        return bool(self.stage_d_config().get(feature_name, False))

    def stage_d_cable_thermal_kw_default(self) -> float:
        return float(self.stage_d_config().get(
            "cable_thermal_kw_default", 6000.0
        ))

    def stage_d_cable_resistance_ohm_per_km(self) -> float:
        return float(self.stage_d_config().get(
            "cable_resistance_ohm_per_km", 0.275
        ))

    def stage_d_cable_voltage_kv(self) -> float:
        return float(self.stage_d_config().get("cable_voltage_kv", 11.0))

    def stage_d_p2p_tariff_inr_per_kwh(self) -> float:
        return float(self.stage_d_config().get(
            "p2p_trading_tariff_inr_per_kwh", 4.5
        ))

    def stage_d_reconciliation_tolerance_fraction(self) -> float:
        return float(self.stage_d_config().get(
            "reconciliation_tolerance_fraction", 0.01
        ))

    # ----- ELECTRICAL ASSET MODEL (Stage D Phases B-E,) ----------
    # All accessors read the `electrical_network:` YAML block. `enabled: false`
    # by default -> the dispatch never adds these terms -> production byte-exact.
    def electrical_network_config(self) -> Dict[str, object]:
        return dict(self.__dict__.get("electrical_network_raw", {}) or {})

    def electrical_network_enabled(self) -> bool:
        return bool(self.electrical_network_config().get("enabled", False))

    # --- Phase B: cable capex ---
    def en_cable_capex_inr_per_km(self, voltage_class: str) -> float:
        """Cable CAPEX (INR/route-km) for a voltage-class key, e.g.
        'backbone_33kv_oh', 'dist_11kv_ug'. 0.0 if absent."""
        return float(self.electrical_network_config()
                     .get("cable_capex_inr_per_km", {}).get(voltage_class, 0.0))

    def en_underground_fraction(self, tier: str) -> float:
        """UG fraction for a tier ('backbone_33kv' | 'dist_11kv')."""
        return float(self.electrical_network_config()
                     .get("underground_fraction", {}).get(tier, 0.0))

    def en_cable_lifetime_years(self) -> int:
        return int(self.electrical_network_config().get("cable_lifetime_years", 40))

    def en_cost_in_production_enabled(self) -> bool:
        """Charge the district's internal electrical network (cables +
        substation + distribution transformers) as an annualised PARITY
        constant in the production dispatch paths.

        Distinct from ``electrical_network_enabled``: that flag is read
        only by the Stage-D builders and additionally switches on
        distributed plant injection, explicit transformer losses and the
        I2R layer. This one adds CAPEX and nothing else, so it can be true
        while Stage-D stays off. False reproduces the pre- pins
        byte-for-byte.
        """
        return bool(self.electrical_network_config()
                    .get("cost_in_production", False))

    def internal_network_embodied(self) -> Dict[str, float]:
        """Embodied-carbon factors for the district's OWN cables, substation
        and distribution transformers.

        Distinct from the national-grid infrastructure exclusion documented
        alongside it: that is the transmission network outside the boundary,
        this is the kit inside it, which the same batch started charging in
        production. Empty dict => the term is absent, not zero-by-accident.
        """
        return dict((self.__dict__.get("embodied_carbon_raw", {}) or {})
                    .get("internal_network", {}) or {})

    def internal_network_embodied_enabled(self) -> bool:
        """True when the factors are present AND embodied carbon is counted
        at all (`include_embodied_carbon`). Both gates, so switching the
        global flag off does not leave this term stranded on."""
        return bool(self.internal_network_embodied()
                    and self.include_embodied_carbon())

    # --- Phase C: substation + voltage tiers ---
    def en_substation(self) -> Dict[str, float]:
        return dict(self.electrical_network_config().get("substation", {}) or {})

    def en_substation_capex_inr_per_mva(self) -> float:
        return float(self.en_substation().get("capex_inr_per_mva", 0.0))

    def en_substation_mva_installed(self) -> float:
        return float(self.en_substation().get("mva_installed", 0.0))

    def en_substation_lifetime_years(self) -> int:
        return int(self.en_substation().get("lifetime_years", 35))

    def en_substation_power_factor(self) -> float:
        return float(self.en_substation().get("power_factor", 0.95))

    def en_substation_throughput_cap_kw(self) -> float:
        """Substation MW throughput cap = MVA x power factor x 1000 (kW)."""
        return (self.en_substation_mva_installed()
                * self.en_substation_power_factor() * 1000.0)

    def en_voltage_tier_thermal_kw(self, voltage_class: str) -> float:
        """Per-edge thermal cap (kW) by voltage class:
        'backbone_33kv' or 'dist_11kv'. Falls back to the 11 kV value."""
        vt = self.electrical_network_config().get("voltage_tiers", {}) or {}
        key = f"{voltage_class}_thermal_kw"
        return float(vt.get(key, vt.get("dist_11kv_thermal_kw", 6000.0)))

    def en_backbone_assignment(self) -> str:
        return str(self.electrical_network_config()
                   .get("backbone_assignment", "none"))

    def en_backbone_n_feeders(self) -> int:
        return int(self.electrical_network_config().get("backbone_n_feeders", 4))

    # --- Phase D: distribution transformers ---
    def en_transformer(self) -> Dict[str, float]:
        return dict(self.electrical_network_config().get("transformer", {}) or {})

    def en_transformer_capex_inr_per_kva(self) -> float:
        return float(self.en_transformer().get("capex_inr_per_kva", 0.0))

    def en_transformer_no_load_loss_fraction(self) -> float:
        return float(self.en_transformer().get("no_load_loss_fraction", 0.0))

    def en_transformer_load_loss_fraction_at_rated(self) -> float:
        return float(self.en_transformer().get("load_loss_fraction_at_rated", 0.0))

    def en_transformer_lifetime_years(self) -> int:
        return int(self.en_transformer().get("lifetime_years", 25))

    def en_transformer_sizing_headroom(self) -> float:
        return float(self.en_transformer().get("sizing_headroom", 1.25))

    def en_transformer_share_of_ac_loss(self) -> float:
        return float(self.en_transformer().get("share_of_ac_loss_fraction", 0.0))

    # --- Phase E: per-cable resistance ---
    def en_conductor_resistance_ohm_per_km(self, voltage_class: str) -> float:
        return float(self.electrical_network_config()
                     .get("conductor_resistance_ohm_per_km", {})
                     .get(voltage_class, 0.275))

    def en_loss_piecewise_segments(self) -> int:
        return int(self.electrical_network_config().get("loss_piecewise_segments", 3))

    # --- Reinforce-over-time-closure): period-dependent per-edge caps ---
    def en_reinforcement_config(self) -> Dict[str, object]:
        return dict(self.electrical_network_config().get("reinforcement", {}) or {})

    def en_reinforcement_enabled(self) -> bool:
        return bool(self.en_reinforcement_config().get("enabled", False))

    def en_reinforcement_base_thermal_kw(self, voltage_class: str) -> float:
        """2030 base per-edge thermal cap by voltage class (before period scaling).
        Falls back to the flat voltage_tier cap if not set."""
        cfg = self.en_reinforcement_config()
        if voltage_class == "backbone_33kv":
            return float(cfg.get("base_backbone_33kv_thermal_kw",
                                 self.en_voltage_tier_thermal_kw("backbone_33kv")))
        return float(cfg.get("base_dist_11kv_thermal_kw",
                             self.en_voltage_tier_thermal_kw("dist_11kv")))

    def en_reinforcement_period_multiplier(self, year: int) -> float:
        """Per-period cap-scaling factor (reinforce-over-time). Uses the explicit
        period_cap_multiplier if present (int OR str year key — guard against the
        YAML int-key trap), else the district demand-growth multiplier so the
        network tracks load. Returns 1.0 on any failure (safe = flat caps)."""
        cfg = self.en_reinforcement_config()
        pm = cfg.get("period_cap_multiplier", {}) or {}
        if year in pm:
            return float(pm[year])
        if str(year) in pm:
            return float(pm[str(year)])
        # the bare `except Exception: return 1.0` here turned any
        # real fault in period_demand_multiplier into "no demand growth", which
        # is a plausible-looking wrong answer. That method already has its own
        # documented no-op paths (absent / disabled block -> 1.0), so it has no
        # legitimate reason to raise; if it does, that is a bug and should
        # surface rather than be papered over.
        return float(self.period_demand_multiplier(year))

    # (PPA scaffold): Power Purchase Agreement counter-
    # parties (data centre / corporate industrial / group captive)
    # + optional on-site data centre heat exchange. YAML schema lands
    # now; LP integration is Stage E. Default `enabled: false` keeps
    # the production headline unchanged.
    def ppa_config(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("ppa_raw", {}) or {})

    def ppa_enabled(self) -> bool:
        """Master PPA switch. A per-instance override (`set_ppa_enabled`) wins
        over the YAML default, so the dispatch can A/B the data-centre PPA on
        the same network (mirrors `dynamic_tariff_enabled`)."""
        override = self.__dict__.get("_force_ppa_enabled")
        if override is not None:
            return bool(override)
        return bool(self.ppa_config().get("enabled", False))

    def set_ppa_enabled(self, flag: Optional[bool]) -> None:
        """Force the PPA master switch on/off (True/False) or revert to the
        YAML default (None) — used by scenarios / tests for an A/B."""
        self.__dict__["_force_ppa_enabled"] = flag

    def ppa_counterparty_net_tariff_inr_per_kwh(self, name: str) -> float:
        """NET PPA revenue to the district per kWh delivered (INR/kWh, real):
        tariff x (1 - wheeling_loss_fraction) - wheeling_charge - cross_subsidy.

        Standard HT open-access (`data_centre_offsite`): 5.0 - 1.27 - 1.20 =
        ~2.53 (below the 3.5 grid feed-in -> only worth it for energy curtailed
        above the 60 MW export cap). RE intra-state concession
        (`data_centre_offsite_re_concession`): 5.0 x (1 - 0.022) - 0.10 - 0.0 =
        ~4.79 (beats the feed-in -> worth it for ALL surplus). Cited in YAML."""
        cps = self.ppa_counterparties()
        if name not in cps:
            return 0.0
        spec = cps[name]
        tariff = float(spec.get("tariff_inr_per_kwh", 0.0))
        loss = float(spec.get("wheeling_loss_fraction", 0.0))
        wheel = float(spec.get("wheeling_charge_inr_per_kwh", 0.0))
        css = float(spec.get("cross_subsidy_surcharge_inr_per_kwh", 0.0))
        # SHAPE DISCOUNT.
        # DEFAULT 1.0 = NO CHANGE, so the base case is untouched.
        # WHY THE BASE CASE IS ALREADY DEFENSIBLE AT 1.0: this tariff is the
        # buyer's AVOIDED RETAIL COST via open access, not a generation
        # tariff. In every hour the town delivers, the buyer genuinely does
        # not buy that kWh from the grid, so the per-kWh value is the same
        # whether the supply is firm or solar-shaped. The shape is already
        # priced - through VOLUME, not rate: the town supplies 06:00-17:00
        # only and covers ~38% of a flat 25 MW block, so it earns on 38% of
        # the hours and nothing on the rest.
        # WHAT A DISCOUNT WOULD REPRESENT, if applied: the balancing and
        # deviation-settlement cost of a variable supply, plus whatever
        # commercial haircut a buyer demands for non-firm energy. Both are
        # real; neither has been sourced to an Indian figure yet, so
        # applying one now would swap a defensible number for a guess.
        # RUN IT AS A SENSITIVITY (0.90 / 0.85 / 0.80) and report the range.
        shape = float(spec.get("shape_discount_factor", 1.0))
        return (tariff * (1.0 - loss) - wheel - css) * shape

    def ppa_counterparties(self) -> Dict[str, Dict[str, Any]]:
        cps = self.ppa_config().get("counterparties", {}) or {}
        return {name: dict(spec) for name, spec in cps.items()}

    def ppa_active_counterparties(self) -> Dict[str, Dict[str, Any]]:
        """Return only the PPA counterparties with enabled: true."""
        return {
            name: spec for name, spec in self.ppa_counterparties().items()
            if spec.get("enabled")
        }

    def ppa_max_share_of_district_demand(self) -> float:
        return float(self.ppa_config().get(
            "max_ppa_share_of_district_demand", 0.60
        ))

    def ppa_total_offtake_kw_constant(self) -> float:
        """Sum of constant kW off-take across ALL active PPAs (sanity-
        bounded by `max_ppa_share_of_district_demand` × district peak
        when wired into the LP)."""
        return sum(
            float(spec.get("offtake_kw_constant", 0.0))
            for spec in self.ppa_active_counterparties().values()
        )

    def ppa_counterparty_annualised_capex_inr(self, name: str,
                                                actor: str = "utility") -> float:
        """Annualised CAPEX (CRF) for ONE active PPA counterparty.

        CRF uses the actor-tier discount rate (utility = ~6.5 % real)
        over `ppa_capex_lifetime_yrs` (default 25). Sums interconnection
        + legal-filing one-time CAPEX. Used by the Stage E LP cost term.
        """
        cps = self.ppa_counterparties()
        if name not in cps:
            return 0.0
        spec = cps[name]
        capex = (float(spec.get("interconnection_capex_inr", 0.0))
                 + float(spec.get("legal_filing_capex_inr", 0.0)))
        if capex <= 0:
            return 0.0
        years = int(spec.get("ppa_capex_lifetime_yrs", 25))
        # Reuse existing CRF helper (same discount-rate-actor table).
        rate = self.actor_discount_rate(actor)
        return capex * crf(rate, years)

    def ppa_counterparty_annual_admin_inr(self, name: str) -> float:
        """Fixed annual admin / renewal / metering AMC cost."""
        cps = self.ppa_counterparties()
        if name not in cps:
            return 0.0
        return float(cps[name].get("annual_admin_inr", 0.0))

    # ------------------------------------------------------------------
    # B21 REGIONAL INTEGRATION - buy-side green
    # open access + boundary opex + interconnection + TRJ-7 land rent.
    # Values + full citations live in economics.yaml; spec + research pack
    # ------------------------------------------------------------------
    def green_purchase_config(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("green_purchase_raw", {}) or {})

    def green_purchase_enabled(self) -> bool:
        """Master buy-side switch; per-instance override wins (the
        set_ppa_enabled pattern) so tests can A/B on one network."""
        override = self.__dict__.get("_force_green_purchase_enabled")
        if override is not None:
            return bool(override)
        return bool(self.green_purchase_config().get("enabled", False))

    def set_green_purchase_enabled(self, flag: Optional[bool]) -> None:
        self.__dict__["_force_green_purchase_enabled"] = flag

    def green_purchase_delivered_price_inr_per_kwh(self) -> float:
        """Delivered cost per kWh RECEIVED at the district bus (real):
        gen x (1 + in-kind T&W + OA losses borne in kind) + CSS + AS.
        FY25-26 intra-state NRSE route at 66/33 kV drawal:
        2.97 x (1 + 0.02 + 0.0400) + 0.85 + 0 = 3.9982 (~Rs 4.00).

        CONVENTION: the two in-kind
        components stack ADDITIVELY (1 + 0.02 + 0.04 = 1.06). The exact
        compounding form is 1.02 / (1 - 0.04) = 1.0625, i.e. this price is
        ~0.19% LOW on the energy component (4.00 vs 4.006 delivered) -
        immaterial against the ~Rs 2/kWh arbitrage margin; the exact
        form is queued as a rider on the-anneal re-pin. Contracted MW
        (gp_mw) is DELIVERED capacity by the same convention - the wire
        carries the in-kind extras upstream of the metering point."""
        cfg = self.green_purchase_config()
        gen = float(cfg.get("gen_price_inr_per_kwh", 0.0))
        inkind = float(cfg.get("inkind_tw_charge_fraction", 0.0))
        loss = float(cfg.get("oa_loss_fraction", 0.0))
        css = float(cfg.get("css_inr_per_kwh", 0.0))
        surcharge = float(cfg.get("additional_surcharge_inr_per_kwh", 0.0))
        # additive stack - to RECEIVE 1 kWh with `loss` borne in kind the
        # generator injects 1/(1-loss), and the 2% in-kind charge applies
        # to energy injected: x(1+inkind)/(1-loss) = 1.02/0.96 = 1.0625
        # (additive 1.06 was ~0.19% low; convention note above retained
        # for the derivation history). 2.97 x 1.0625 + 0.85 = 4.0056.
        return gen * (1.0 + inkind) / (1.0 - loss) + css + surcharge

    def green_purchase_annual_admin_inr(self) -> float:
        return float(self.green_purchase_config().get("annual_admin_inr", 0.0))

    def green_purchase_contracted_mw_max(self) -> float:
        return float(self.green_purchase_config().get("contracted_mw_max", 0.0))

    def green_purchase_emission_factor(self) -> float:
        """0.0 = the GEOA green attribute (operational convention)."""
        return float(self.green_purchase_config().get(
            "emission_factor_kgco2_per_kwh", 0.0))

    def boundary_opex_config(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("boundary_opex_raw", {}) or {})

    def boundary_opex_enabled(self) -> bool:
        return bool(self.boundary_opex_config().get("enabled", False))

    def boundary_opex_annual_inr(self, year: int) -> float:
        """Waste gate fee on exported residues (per-period tonnage) + canal
        water allocation charge (static volume). PARITY: applied to every
        scenario incl. BAU by the builders."""
        cfg = self.boundary_opex_config()
        if not self.boundary_opex_enabled():
            return 0.0
        residues = cfg.get("waste_residues_tonnes_by_period", {}) or {}
        res_t = float(residues.get(str(year), residues.get("2030", 0.0)))
        gate = float(cfg.get("waste_gate_fee_inr_per_tonne", 0.0))
        water_kl = float(cfg.get("canal_water_kl_per_year", 0.0))
        water_rate = float(cfg.get("canal_water_charge_inr_per_kl", 0.0))
        return res_t * gate + water_kl * water_rate

    def interconnection_config(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("interconnection_raw", {}) or {})

    def interconnection_enabled(self) -> bool:
        return bool(self.interconnection_config().get("enabled", False))

    def interconnection_annualised_inr(self) -> float:
        """District-substation interconnection capex, CRF-annualised at the
        named actor's rate (FX-12/AUD-8 made real). PARITY: BAU pays too."""
        cfg = self.interconnection_config()
        if not self.interconnection_enabled():
            return 0.0
        capex = float(cfg.get("capex_inr", 0.0))
        if capex <= 0.0:
            return 0.0
        years = int(cfg.get("lifetime_years", 35))
        rate = self.actor_discount_rate(str(cfg.get("actor", "utility")))
        return capex * crf(rate, years)

    def interconnection_sizing_enabled(self) -> bool:
        """True when the grid connection is SIZED to each scenario's own peak
        import and charged per MW, instead of a flat annual figure.

. Default FALSE so an older config reproduces the flat
        charge byte-for-byte; production sets it true. Requires the parent
        `interconnection` block to be enabled - a sized charge on a disabled
        connection would be a charge for an asset the scenario does not have.
        See the long note in economics.yaml:interconnection.sizing.
        """
        if not self.interconnection_enabled():
            return False
        blk = self.interconnection_config().get("sizing") or {}
        if not isinstance(blk, dict):
            return False
        return bool(blk.get("enabled", False))

    def interconnection_design_basis_mw(self) -> float:
        """MW the flat interconnection capex was costed for (default 600)."""
        blk = self.interconnection_config().get("sizing") or {}
        if not isinstance(blk, dict):
            return 600.0
        return float(blk.get("design_basis_mw", 600.0) or 600.0)

    def interconnection_annualised_inr_per_mw(self) -> float:
        """Annualised connection cost per MW of sized capacity.

        DERIVED from this block's own numbers rather than declared, so it
        cannot drift from the flat figure:
            interconnection_annualised_inr / design_basis_mw
        At the full 600 MW basis this reproduces the flat charge EXACTLY,
        which is the equivalence test for the sizing switch.
        """
        basis = self.interconnection_design_basis_mw()
        if basis <= 0:
            return 0.0
        return self.interconnection_annualised_inr() / basis

    def farm_land_rent_config(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("farm_land_rent_raw", {}) or {})

    def farm_land_rent_enabled(self) -> bool:
        return bool(self.farm_land_rent_config().get("enabled", False))

    def farm_land_rent_annual_inr(self, year: int) -> float:
        """TRJ-7: rent on the GRANTED farm hectares at ``year`` (granted,
        not built - a grant reserves the land either way). Grant schedule =
        multi_period.farm_land_cells_by_period (1 cell = 1 ha at 100 m).
        mode agricultural: ha x theka rate; mode market: ha x value x
        opportunity rate. Scenario gating (farm scenarios only) is the
        builders' job."""
        cfg = self.farm_land_rent_config()
        if not self.farm_land_rent_enabled():
            return 0.0
        mp = dict(self.__dict__.get("multi_period_raw", {}) or {})
        cells = mp.get("farm_land_cells_by_period", {}) or {}
        ha = float(cells.get(str(year), cells.get("2030", 0.0)))
        if str(cfg.get("mode", "agricultural")) == "market":
            return (ha * float(cfg.get("market_value_inr_per_ha", 0.0))
                    * float(cfg.get("market_opportunity_rate_real", 0.0)))
        return ha * float(cfg.get("agricultural_inr_per_ha_yr", 0.0))

    def period_demand_multiplier(self, year: int) -> float:
        """District-demand scaling at ``year`` vs the 2030 base, stacking
        the ``lifetime_demand_trajectory`` drivers (D1(b)).

        ``population_growth`` uses its compound CAGRs. Every other driver
        either (a) carries an explicit ``multiplier_by_period`` table
        (DEM-1/DEM-5,) - linearly interpolated at ``year``,
        replacing the legacy ramp for that driver (no double count) - or
        (b) ramps linearly from 1.0 (2030) to an endpoint ``E = 2*avg - 1``
        (2055), so the 25-yr mean reproduces the documented
        ``lifetime_avg_multiplier``. Returns 1.0 at 2030, and 1.0 when
        the trajectory block is absent or ``enabled: false`` (back-compat).
        """
        # one cached read, and a malformed file now raises
        # instead of silently disabling every driver. See
        # `_lifetime_demand_trajectory`.
        block = self._lifetime_demand_trajectory()
        if not block:
            return 1.0
        base, end = 2030, 2055
        span = float(end - base)
        frac = max(0.0, min(1.0, (year - base) / span)) if span > 0 else 0.0
        mult = 1.0
        pop = block.get("population_growth") or {}
        if pop:
            c1 = float(pop.get("cagr_2030_2040", 0.0))
            c2 = float(pop.get("cagr_2040_2055", 0.0))
            if year <= 2040:
                mult *= (1.0 + c1) ** max(0, year - base)
            else:
                mult *= (1.0 + c1) ** 10 * (1.0 + c2) ** (year - 2040)

        def _interp_period_table(tbl: Dict, y: int) -> float:
            """Linear interp of a {year: mult} table, clamped to the ends.
            Local (NOT _interp_trajectory) so a malformed table degrades to
            a 1.0 no-op instead of the emission-factor fallback."""
            try:
                pts = sorted((int(k), float(v)) for k, v in tbl.items())
            except (TypeError, ValueError):
                return 1.0
            if not pts:
                return 1.0
            if y <= pts[0][0]:
                return pts[0][1]
            if y >= pts[-1][0]:
                return pts[-1][1]
            for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
                if y0 <= y <= y1:
                    return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
            return pts[-1][1]

        #: `climate_drift_cooling` is NO LONGER in this
        # list. It was a flat multiplier on all demand, so +2 C of warming
        # raised January 2055 demand by 3%. It now enters through
        # `cooling_warming_multiplier` on the COOLING term only. Its
        # delta-T block is still read - by that method and by TRJ-5's
        # `pv_warming_period_derate` - so the two sides of warming still
        # share one source of truth.
        for key in ("ev_adoption_ramp",
                    "cooking_electrification", "income_mobility",
                    # AI/datacentre uplift trajectory.
                    "ai_demand_uplift",
                    # DEM-5 + V-7: groundwater-lift growth net
                    # of the rainwater/greywater harvesting credit.
                    "water_energy"):
            sub = block.get(key) or {}
            if sub.get("enabled") is False:
                continue
            # DEM-1: explicit per-period table supersedes the
            # lifetime-average linear ramp for this driver.
            per_period = sub.get("multiplier_by_period") or {}
            if per_period:
                mult *= _interp_period_table(per_period, int(year))
                continue
            avg = float(sub.get("lifetime_avg_multiplier", 1.0) or 1.0)
            endpoint = 2.0 * avg - 1.0
            mult *= 1.0 + (endpoint - 1.0) * frac
        return mult

    def _interp_trajectory(self, traj: Dict[str, float], year: int) -> float:
        """Linear interpolation of a year-keyed trajectory at one year."""
        try:
            pts = sorted((int(y), float(v)) for y, v in traj.items())
        except (ValueError, TypeError):
            return self.emission_factor()
        if not pts:
            return self.emission_factor()
        if year <= pts[0][0]:
            return pts[0][1]
        if year >= pts[-1][0]:
            return pts[-1][1]
        for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
            if y0 <= year <= y1:
                return v0 + (v1 - v0) * (year - y0) / (y1 - y0)
        return pts[-1][1]

    def period_emission_factor(self, year: int) -> float:
        """Grid emission factor (kgCO2/kWh) at a single ``year`` from the
        active EF trajectory (linear interp), mirroring the resolution
        order of ``emission_factor_trajectory_average``. Falls back to the
        static EF when no trajectory is available."""
        payload = self._active_price_scenario_payload()
        traj: Dict[str, float] = {}
        if payload:
            traj = payload.get("emission_factor_trajectory_kgco2_per_kwh") or {}
        if not traj and bool(self.grid.get("use_grid_decarb_trajectory", False)):
            traj = self.grid.get("emission_factor_trajectory_kgco2_per_kwh", {})
        if not traj:
            return self.emission_factor()   # premium applied inside
        # FX-5/B1: trajectory path needs the premium applied here.
        return self._interp_trajectory(traj, year) * self.pspcl_ef_premium_factor()

    #: Technologies whose CAPEX is DERIVED from another technology's CAPEX by
    #: a constant multiplier (see the ``*_annualised_inr_per_kwp`` accessors).
    #: They must inherit that parent's learning rate - this is forced by the
    #: algebra, not a judgement call: if capex_child = capex_parent x k then
    #: capex_child(y) = capex_parent(2030) x factor_parent(y) x k, so
    #: factor_child == factor_parent identically.
    _DERIVED_CAPEX_PARENT = {
        "bipv_facade": "rooftop_pv",     # = rooftop x bipv_capex_multiplier
        "solar_carport": "solar_farm",   # = farm    x carport_capex_multiplier
        "floating_pv": "solar_farm",     # = farm    x floating_capex_multiplier
        "tracked_pv": "solar_farm",      # = farm    x capex_multiplier_vs_fixed
    }

    def period_capex_factor(self, tech: str, build_year: int) -> float:
        """CAPEX multiplier for capacity BUILT in ``build_year``, per the
        Phase 1B real decline: ``(1 - decline)^(build_year - base_year)``.
        Returns 1.0 when the tech has no declared decline rate.

        *** BUG: DERIVED PV TECHNOLOGIES WERE GETTING NO
        LEARNING AT ALL. *** `bipv_facade`, `solar_carport` and `floating_pv`
        have no entry in `technologies:`, because their cost is DERIVED - each
        is its parent's annualised cost times a constant multiplier. But the
        learning factor was looked up under the CHILD's own name, found
        nothing, and returned 1.0. So their capex BASE inherited from the
        parent while their capex DECLINE did not.
        Effect: by 2055 rooftop PV cost 0.7395x and the solar farm 0.6853x,
        while BIPV, carport PV and floating PV stayed at 1.0000x - a 26-31%
        phantom cost penalty on three technologies built from the SAME
        MODULES, applied precisely in the periods where the LP chooses how
        much of each to build. It biased the model against distributed PV in
        2042 and 2055 for no physical reason.
        The fix inherits the parent's rate. It needs no new number and no new
        citation: it is the same modules, and the multiplier is a constant.
        """
        d = self.tech_capex_real_decline_per_year(tech)
        if d <= 0:
            parent = self._DERIVED_CAPEX_PARENT.get(tech)
            if parent:
                d = self.tech_capex_real_decline_per_year(parent)
        if d <= 0:
            return 1.0
        age = max(0, int(build_year) - int(self.multi_period_base_year()))
        return (1.0 - d) ** age

    def pm25_period_soiling_relief(self, period_year: int) -> float:
        """B5/FX-5: PV-yield relief in ``period_year`` from the
        projected ambient-PM2.5 decline (config/climate.yaml
        ``pm25_ambient_scale_by_period``: NCAP + Punjab stubble-burning
        enforcement -> ~0.80x ambient by 2055; see that block's citations).

        relief = mean_m[soil_mult(pm25_m x scale)] / mean_m[soil_mult(pm25_m)]
        with months weighted by PV energy share (pv_monthly_modifier x
        days), so high-yield months count proportionally. The dust-storm
        and rain-recovery terms are NOT scaled (dust is wind-blown soil,
        not combustion PM2.5). Missing table, scale 1.0, or no climate
        PM2.5 data -> 1.0 (byte-stable back-compat).
        """
        tbl = self.__dict__.get("pm25_ambient_scale_by_period_raw") or {}
        if not tbl or not self.climate:
            return 1.0
        try:
            scale = self._interp_trajectory(
                {str(k): float(v) for k, v in tbl.items()}, int(period_year)
            )
        except (ValueError, TypeError):
            return 1.0
        if abs(scale - 1.0) < 1e-12:
            return 1.0
        num = 0.0
        den = 0.0
        for month in MONTHS:
            cm = self.climate.get(month, {}) or {}
            pm25 = cm.get("pm25_ugm3")
            if pm25 is None:
                return 1.0
            rain_days = float(cm.get("rain_days", 0.0) or 0.0)
            dust_days = float(cm.get("dust_storm_days", 0.0) or 0.0)
            w = (float(self.pv_monthly_modifier.get(month, 1.0))
                 * DAYS_IN_MONTH.get(month, 30))
            base = self.pv_soiling_multiplier_for_month(month)
            loss = max(0.0, PV_SOILING_PER_PM25_UGM3 * float(pm25) * scale
                       + PV_SOILING_PER_DUST_STORM_DAY * dust_days
                       - PV_SOILING_RAIN_RECOVERY_PER_DAY * rain_days)
            scaled = max(PV_SOILING_FLOOR, 1.0 - loss)
            num += w * scaled
            den += w * base
        if den <= 0:
            return 1.0
        return num / den

    def climate_drift_delta_t_c(self, year: int) -> float:
        """TRJ-5: ambient-warming delta-T (deg C) at ``year``
        from the SAME climate-drift block that drives cooling demand
        (config/district_composition.yaml lifetime_demand_trajectory.
        climate_drift_cooling: delta_t_2030_c 0.0 -> delta_t_2055_c 2.0,
        IPCC AR6 SSP2-4.5 central; linear in between, clamped outside).
        Single source of truth = symmetry between the demand-side and
        PV-supply-side warming effects. 0.0 when unconfigured. The block
        is cached on first read (one YAML read per Economics instance)."""
        block = self.__dict__.get("_climate_drift_block_cache")
        if block is None:
            # third copy of the same file read, now routed through
            # the shared cached loader. A malformed file raises rather than
            # silently zeroing delta-T (which would silently remove warming
            # from BOTH the demand and the PV-derate side).
            traj = self._lifetime_demand_trajectory()
            block = (traj.get("climate_drift_cooling") or {}) if traj else {}
            self.__dict__["_climate_drift_block_cache"] = block
        if not block:
            return 0.0
        t0 = float(block.get("delta_t_2030_c", 0.0) or 0.0)
        t1 = float(block.get("delta_t_2055_c", 0.0) or 0.0)
        base, end = 2030, 2055
        frac = max(0.0, min(1.0, (int(year) - base) / float(end - base)))
        return t0 + (t1 - t0) * frac

    def cooling_warming_multiplier(self, year: int) -> float:
        """: the climate-warming uplift on the COOLING term
        at ``year``. The demand-side twin of ``pv_warming_period_derate``, and
        it reads the same delta-T so the two cannot disagree.

            1 + cooling_elasticity_per_c x delta_t_c(year)

        WHY THIS EXISTS. The warming driver used to be a flat multiplier on
        all demand via ``period_demand_multiplier``, which meant +2 C of
        global warming raised JANUARY 2055 demand by 3%. Warming raises
        cooling and lowers heating; it does not raise winter demand. Applied
        to cooling only, January moves by essentially nothing and the summer
        peak rises where it should.

        It also brings back the two fields the config had cited and then not
        used: ``cooling_elasticity_per_c`` (0.10/C) and, by construction, the
        model's real cooling share instead of the stale 0.25 written beside
        it. Running the config's own stated method gives +6.4% district
        demand at 2055 against the +3.0% that was coded - a factor of 2.14
        between a model's documentation and its behaviour.

        *** CITATION. This docstring used to attribute
        0.10/C to an "AEEE/CEEW 8-12%/C band". THAT BAND DOES NOT EXIST - the
        report was downloaded and parsed in full (98 pp) on and
        contains ZERO occurrences of "elasticity", "degree-day", "per degree"
        or "%/C". The config was corrected then; this copy in the code was
        missed and survived until the sweep. A retracted citation
        living on in a docstring is exactly how a dead number gets requoted,
        so it is named here rather than silently deleted.
        THE VALUE 0.10 NEVER CHANGED, only its provenance. It now rests on
        two independent lines: Petri & Caldeira (2015, Scientific Reports)
        reporting the US CCSP synthesis - "a 5-20% increase for cooling per
        1 C of temperature increase", so 10 is mid-band - and an India CDD
        derivation from IEA "The Future of Cooling" (2018) giving ~11%/C.

        UNITS TRAP, do not quote it wrong: 0.10 applies to the COOLING TERM
        only, not to total demand. At this model's ~32% cooling share that is
        ~3.2%/C on district demand, and it is a LONG-RUN elasticity (stock
        grows as well as usage), so it SHOULD sit above short-run
        fixed-stock figures like IEA's ~2%/C. See ``_cooling_stock_note``.

        Returns 1.0 at 2030 and whenever the block is unconfigured."""
        dt = self.climate_drift_delta_t_c(int(year))
        if dt <= 0:
            return 1.0
        block = self.__dict__.get("_climate_drift_block_cache") or {}
        elas = float(block.get("cooling_elasticity_per_c", 0.0) or 0.0)
        if elas <= 0:
            return 1.0
        return 1.0 + elas * dt

    def _cooling_stock_note(self) -> str:
        """WHY COOLING-APPLIANCE OWNERSHIP IS FROZEN AT 2030, settled
. Carried as code, not a comment, so it cannot drift away
        from the accessor it explains.

        CLAUDE.md listed "cooling ownership is frozen at 2030 across all
        periods" as an open item to settle before the re-pin. Settled: it is
        left frozen, deliberately, and here is the reasoning and the residual
        exposure.

        1. THERE IS ALMOST NO HEADROOM TO RAMP. The 2030 baseline already
           assumes near-saturation for the two tiers that can afford cooling:
             high income  100% inverter AC
             mid income    80% AC (32% window + 48% inverter), 20% cooler
           Only LOW income has none (25% fan / 75% desert cooler). So an
           "ownership ramp" would really be one change - giving the poorest
           tier air conditioning.

        2. THE ENERGY OF THAT CHANGE IS ALREADY COUNTED, AND COUNTING IT
           TWICE WAS THE REAL RISK. `income_mobility` moves the low-income
           share 0.40 -> 0.28 by 2055 and raises district demand by 14.26%,
           calibrated on the model's OWN measured per-tier consumption -
           which contains those tiers' cooling. Layering an ownership ramp on
           top would charge the same households' new ACs twice.

        3. COOLING ALREADY GROWS SUBSTANTIALLY. `period_demand_multiplier`
           scales the cooling term along with everything else, and the
           warming multiplier stacks on top:
             2042  1.1551 x 1.0576 = 1.2217  (+22.2%)
             2055  1.3290 x 1.1200 = 1.4885  (+48.9%)
           against non-cooling growth of +15.5% / +32.9%. Cooling is already
           the fastest-growing end use in the model.

        4. WHAT IS GENUINELY NOT CAPTURED - state this as a limitation.
           The cooling tech mix is attached to the LAND-USE category, which
           the frozen layout fixes, so a household getting richer raises its
           ENERGY but never changes its cooling TECHNOLOGY. A desert cooler
           replaced by an AC changes the summer PEAK and the daily SHAPE, not
           just the annual total. So the model captures the kWh and misses
           the shape, and the bias is toward UNDERSTATING the 2055 summer
           peak in low-income areas.

        5. AND IT IS WHY THE ELASTICITY STAYS AT 0.10. 0.10/C is a LONG-RUN
           coefficient - it already embeds households buying more cooling as
           the climate warms. With ownership frozen, that coefficient is
           doing exactly the job it was measured for. If an explicit
           ownership ramp were ever added, 0.10 would have to fall to a
           short-run fixed-stock value or the adaptation would be counted
           twice. The two changes must land together or not at all.

        6. *** THE DECIDING ARGUMENT, AND IT IS the author'S:
           OWNERSHIP RISES, BUT EFFICIENCY RISES TOO, AND THE TWO LARGELY
           CANCEL. *** The model freezes BOTH. That is not two omissions - it
           is one internally consistent choice, and freezing both is closer
           to the truth than freezing either one alone.
             OWNERSHIP, upward pressure. The only tier with headroom is low
             income: 40% of households at 2030, 28% by 2055. Moving from
             25% fan / 75% desert cooler (6.25 W/m2) to a mid-income mix
             (15.04 W/m2) is ~2.4x. If HALF of that tier gained AC by 2055,
             district cooling rises very roughly +20%.
             EFFICIENCY, downward pressure. BEE ratchets the ISEER star
             bands and has done so repeatedly - the January 2026 revision
             raised every band by 10-14%, so what was a 5-star AC became a
             4-star, and industry expects the next tightening around
             2028-29. Sustained at even ~1%/yr real efficiency improvement,
             a 2055 AC delivers the same cooling for 0.99^25 = 0.78 of the
             2030 energy, i.e. **-22%**.
             NET: +20% ownership against -22% efficiency. They offset to
             within a few points, which is well inside the uncertainty of
             either estimate.
           SO THE HONEST STATEMENT IS NOT "ownership is frozen, which
           understates demand". It is "ownership and efficiency are both
           held at 2030, and their omitted effects run in opposite
           directions at similar magnitude". Modelling one without the other
           would introduce a bias the current treatment does not have.
           WHAT WOULD BE NEEDED TO DO IT PROPERLY: an India appliance-stock
           turnover model (ownership by tier by year x efficiency by vintage)
           with the star-band ratchet as an input. No such dataset was found
           in the sweep, and building one from assumptions would
           replace a self-cancelling pair with two invented curves.
           RESIDUAL, still true and still worth stating: the SHAPE point in
           (4) does not cancel. A desert cooler replaced by an AC changes the
           summer peak even if annual kWh is unchanged by the efficiency
           gain. The peak exposure stands; the energy exposure roughly nets
           out.
        """
        return "cooling stock frozen at 2030 by design - see docstring"

    def pv_warming_period_derate(self, period_year: int) -> float:
        """TRJ-5: PV-yield derate in ``period_year`` from
        climate-drift ambient warming - the supply-side symmetry partner
        of the climate_drift_cooling demand driver. Hotter cells produce
        less: the per-month temperature derate (pv_inverter.
        temperature_derating_per_celsius x (ambient + NOCT - 25), exactly
        the ``pv_temperature_derating`` formula) is recomputed with the
        period's delta-T added to every month's ambient, and the ratio of
        PV-energy-weighted means is returned (months weighted by
        pv_monthly_modifier x days, mirroring pm25_period_soiling_relief).
        1.0 at the 2030 base year (delta-T = 0) and whenever the derating
        coefficient / ambient table / drift block is unconfigured
        (byte-stable back-compat). Cached per period_year."""
        cache = self.__dict__.setdefault("_pv_warming_derate_cache", {})
        key = int(period_year)
        if key in cache:
            return cache[key]
        result = 1.0
        dt = self.climate_drift_delta_t_c(key)
        inv = self.pv_inverter or {}
        coef = float(inv.get("temperature_derating_per_celsius", 0.0))
        ambient_table = inv.get("ambient_temperature_c_by_month", {}) or {}
        if dt > 1e-9 and coef > 0 and ambient_table:
            noct = float(inv.get("noct_temperature_uplift_c", 25.0))

            def _derate(ambient_c: float) -> float:
                delta = ambient_c + noct - 25.0
                if delta <= 0:
                    return 1.0
                return max(0.0, 1.0 - coef * delta)

            num = 0.0
            den = 0.0
            for month in MONTHS:
                w = (float(self.pv_monthly_modifier.get(month, 1.0))
                     * DAYS_IN_MONTH.get(month, 30))
                ambient_c = float(ambient_table.get(month, 25.0))
                num += w * _derate(ambient_c + dt)
                den += w * _derate(ambient_c)
            if den > 0:
                result = num / den
        cache[key] = result
        return result

    def pv_vintage_yield_factor(self, tech: str, vintage_year: int,
                                period_year: int) -> float:
        """Output retention for capacity of ``vintage_year`` evaluated in
        ``period_year``: degradation ``(1 - g)^age`` x the period's
        PM2.5-decline soiling relief (B5/FX-5, ``pm25_period_soiling_relief``)
        x the period's climate-drift warming derate (TRJ-5,
        ``pv_warming_period_derate``); all three are 1.0 at the 2030 base
        year and whenever unconfigured. Returns the period factors alone
        for a new/future vintage or a tech with no declared degradation."""
        relief = (self.pm25_period_soiling_relief(period_year)
                  * self.pv_warming_period_derate(period_year))
        g = self.tech_degradation_per_year(tech)
        age = max(0, int(period_year) - int(vintage_year))
        if g <= 0 or age == 0:
            return relief
        return relief * (1.0 - g) ** age

    def battery_vintage_capacity_factor(self, vintage_year: int,
                                        period_year: int) -> float:
        """Usable-capacity retention for Li-ion built in ``vintage_year``,
        evaluated in ``period_year``: ``(1 - calendar_fade)^age``.
        consumes ``li_ion_battery.calendar_fade_per_year`` (was reference-only)
        so a battery's usable kWh shrinks with age in the multi-period LP.
        Returns 1.0 for a new vintage or when no fade is declared.

 FIX: THE AGE CLOCK RESETS ON EACH
        IMPLICIT REPLACEMENT. The multi-period build note at dispatch.py:1742
        states that "battery / V2G replacement is treated implicitly via the
        annualised CRF (each vintage keeps paying its annuity in every period
        after its build year)". So the district BUYS a replacement battery
        every `lifetime_years`. It was then handed the capacity of a unit that
        had never been replaced: a 2030 vintage evaluated in 2055 was 25 years
        old at a factor of 0.6035, having been paid for two and a half times.
        Pay for new, receive old.

        One parameter was doing duty as two things - within-life degradation
        AND across-replacement decline. Ageing modulo the lifetime keeps the
        first and removes the second:

            vintage 2030 @ 2042   0.7847 -> 0.9604   (age 12 -> 2)
            vintage 2030 @ 2055   0.6035 -> 0.9039   (age 25 -> 5)
            vintage 2042 @ 2055   0.7690 -> 0.9412   (age 13 -> 3)

        The audit measured this as LATENT: the pin at the time built battery
        in 2055 only, so the sole vintage was evaluated in its own build year
        at exactly 1.0000 and the defect cost nothing. It was flagged because
 (+64 GWh of PV) raises the value of storage and could pull the
        battery to an earlier vintage - and economics.yaml:773 records that
        under FX-1 economics the LP DID build at 2042. Fixed here rather than
        left, because a latent defect that a fix in the same batch can
        activate is not latent.

        Direction: understates battery capacity, so it biases AGAINST the
        designed town - the same direction as not offsetting it."""
        tech = self.technologies.get("li_ion_battery") or {}
        fade = float(tech.get("calendar_fade_per_year", 0.0))
        age = max(0, int(period_year) - int(vintage_year))
        life = int(tech.get("lifetime_years", 0) or 0)
        if life > 0:
            # implicit CRF-funded replacement resets the clock; a unit at
            # exactly `life` years is brand new again, hence the modulo.
            age = age % life
        if fade <= 0 or age == 0:
            return 1.0
        return (1.0 - fade) ** age

    # ----- Stage C round 3: reliability multiplier ---------------------

    def reliability_params(self) -> Dict[str, float]:
        """Return the reliability section as a flat dict."""
        return dict(self.__dict__.get("reliability_raw", {}))

    def diesel_displacement_value_inr_per_kwh(self) -> float:
        """Avoided cost when battery / V2G covers an outage hour.

        Equals the diesel-genset cost (₹15-20/kWh in India) that would
        otherwise be incurred. Used to add hidden value to battery + V2G.
        """
        rel = self.reliability_params()
        return float(rel.get("diesel_genset_cost_inr_per_kwh", 17.0))

    def diesel_displacement_emission_kgco2_per_kwh(self) -> float:
        rel = self.reliability_params()
        return float(rel.get("diesel_genset_emission_kgco2_per_kwh", 0.27))

    def outage_hours_per_year(self) -> float:
        rel = self.reliability_params()
        return float(rel.get("outage_hours_per_year", 60))

    def reliability_coverage_fraction(self) -> float:
        rel = self.reliability_params()
        return float(rel.get("reliability_coverage_fraction", 0.30))

    def symmetric_diesel_backup_enabled(self) -> bool:
        """True when diesel is charged to EVERY scenario as an uncovered-
        outage cost, instead of credited to storage-owning scenarios only.

. Default FALSE so an older config, or one with the block
        removed, reproduces the pre- numbers byte-for-byte; the
        production config sets it true. See the long note in
        ``economics.yaml:reliability.symmetric_diesel_backup``.
        """
        rel = self.reliability_params()
        blk = rel.get("symmetric_diesel_backup") or {}
        if not isinstance(blk, dict):
            return False
        return bool(blk.get("enabled", False))

    def chp_outage_availability(self) -> float:
        """Fraction of outage hours the dispatchable CHP fleet (biomass + WTE
        + biogas) can actually run. 1.0 by default - see the long note in
        ``economics.yaml:reliability.symmetric_diesel_backup``: measured
        that a 72-hour event burns ~0.6% of the annual straw budget, so fuel
        does not bind over the ~60 outage hours a year this term models."""
        rel = self.reliability_params()
        blk = rel.get("symmetric_diesel_backup") or {}
        if not isinstance(blk, dict):
            return 1.0
        return float(blk.get("chp_outage_availability", 1.0))

    def critical_outage_energy_kwh(self, annual_demand_kwh: float) -> float:
        """Energy the district's CRITICAL load needs during outages in a year.

        ``annual_demand_kwh x (outage_hours_per_year / 8760) x
        reliability_coverage_fraction`` - i.e. the demand falling inside
        outage hours, times the share of it that is critical enough to be
        backed up. This is the CEILING on how much diesel any scenario can
        displace, and it is what makes the reliability term bounded.
        """
        if annual_demand_kwh <= 0:
            return 0.0
        return (float(annual_demand_kwh)
                * (self.outage_hours_per_year() / 8760.0)
                * self.reliability_coverage_fraction())

    # ----- Stage C round 3 (Claude 2): per-cell panel orientation -------

    def pv_orientations(self) -> Dict[str, Dict[str, Any]]:
        """Return the per-orientation yield curve table from YAML."""
        return dict(self.__dict__.get("pv_orientations_raw", {}))

    def pv_orientation_default_for_category(self, category_name: Optional[str]) -> str:
        """Heuristic default orientation for a built-cell category.

        Falls back to ``DEFAULT_PV_ORIENTATION`` (defined in
        ``core/land_use.py``) if the YAML mapping is missing the category
        or the cell is not built (``category_name is None``). Sharing the
        constant with ``core/export_3d.py`` removes the literal-string
        drift risk Claude 2's critical review surfaced.
        """
        from core.land_use import DEFAULT_PV_ORIENTATION
        if category_name is None:
            return DEFAULT_PV_ORIENTATION
        defaults = self.__dict__.get("pv_orientation_defaults_raw", {})
        return str(defaults.get(category_name, DEFAULT_PV_ORIENTATION))

    def pv_orientation_yield_multiplier(self, slice_id: str,
                                         orientation: str) -> float:
        """Return the per-slice yield multiplier vs. south_fixed for a
        given orientation. south_fixed always returns 1.0.

        Computed as ``yield_multiplier_vs_south * daypart_shape[daypart]``.
        """
        orientations = self.pv_orientations()
        cfg = orientations.get(orientation)
        if not cfg:
            return 1.0
        slice_obj = self.slice_by_id(slice_id)
        whole_day = float(cfg.get("yield_multiplier_vs_south", 1.0))
        shape = float(cfg.get("daypart_shape", {}).get(slice_obj.daypart, 1.0))
        return whole_day * shape

    def pv_capacity_factor_by_orientation(self, slice_id: str,
                                            orientation: str = "south_fixed"
                                            ) -> float:
        """Absolute PV capacity factor for a given orientation in a slice.

        Equals ``pv_capacity_factor(slice_id)`` times the orientation
        multiplier. south_fixed reduces to the legacy function.
        """
        base = self.pv_capacity_factor(slice_id)
        return base * self.pv_orientation_yield_multiplier(slice_id, orientation)

    # ----- Stage C round 3 (Claude 2): DSR --------------------------------

    def dsr_params(self) -> Dict[str, Any]:
        """Return the demand_side_response block (categories + aggregates)."""
        return dict(self.__dict__.get("dsr_raw", {}))

    def dsr_enabled(self) -> bool:
        return bool(self.dsr_params().get("enabled", False))

    def dsr_comfort_cost_inr_per_kwh(self) -> float:
        """Effective DSR comfort cost in INR/kWh shifted.

 (Realism audit A3): if a per-category split is present
        under ``comfort_cost_by_category_inr_per_kwh``, return a pool-
        contribution-weighted average across {ac_precool, geyser_thermal,
        ev_charging_window}. The pool weights come from typical Punjab
        district load shares: cooling ~30 % of demand x 30 % shiftable
        (ac_precool pool ~ 9 % of total); heating ~3 % x 50 % shiftable
        (geyser pool ~ 1.5 %); EV ~5 % x 100 % shiftable (EV pool ~ 5 %).
        Resulting weighted cost ~ 1.0 INR/kWh (was 1.5 flat). Falls back
        to the legacy single ``comfort_cost_inr_per_kwh`` value if the
        category split is missing.
        """
        p = self.dsr_params()
        split = p.get("comfort_cost_by_category_inr_per_kwh") or {}
        if not split:
            return float(p.get("comfort_cost_inr_per_kwh", 1.5))
        # Pool contribution weights -- aligned with the category yaml structure.
        weights = {
            "ac_precool": 9.0,        # cooling 30% x 30% shiftable
            "geyser_thermal": 1.5,    # heating 3% x 50% shiftable
            "ev_charging_window": 5.0,  # EV 5% x 100% shiftable
        }
        total_w = 0.0
        total_cost = 0.0
        for key, w in weights.items():
            cost = split.get(key)
            if cost is None:
                continue
            total_w += w
            total_cost += w * float(cost)
        if total_w <= 0:
            return float(p.get("comfort_cost_inr_per_kwh", 1.5))
        return total_cost / total_w

    def dsr_aggregate_shiftable_fraction(self) -> float:
        """Fraction of peak / super_peak demand the foundation shifts."""
        return float(self.dsr_params().get(
            "aggregate_shiftable_fraction_in_peak", 0.0
        ))

    def dsr_shift_window_hours(self) -> int:
        return int(self.dsr_params().get("shift_window_hours", 4))

    def dsr_category_params(self, family: str) -> Dict[str, Any]:
        """Return one DSR family (ac_precool / geyser_thermal / ev_charging_window)."""
        cats = self.dsr_params().get("categories", {})
        return dict(cats.get(family, {}))

    # ----- Stage C round 3 (Claude 2): Allume SolShare --------------------

    def solshare_params(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("solshare_raw", {}))

    def solshare_capex_premium_fraction(self) -> float:
        return float(self.solshare_params().get("capex_premium_fraction", 0.10))

    def solshare_apartment_uptake_fraction(self) -> float:
        return float(self.solshare_params().get(
            "default_apartment_uptake_fraction", 0.60
        ))

    def solshare_apartment_roof_share(self) -> float:
        return float(self.solshare_params().get(
            "apartment_roof_share_of_total", 0.50
        ))

    def rooftop_pv_capex_multiplier_with_solshare(self,
                                                    scenario: Scenario
                                                    ) -> float:
        """Effective multiplier on rooftop-PV CAPEX given a scenario.

        Equals 1.0 when ``scenario.allow_solshare`` is False, otherwise
        ``1 + apartment_roof_share x uptake x premium`` (defaults give
        1 + 0.5 x 0.6 x 0.10 = 1.030, i.e. +3% district-aggregate rooftop
        CAPEX from SolShare hardware on adopting apartment cells).
        """
        if not getattr(scenario, "allow_solshare", False):
            return 1.0
        apt = self.solshare_apartment_roof_share()
        uptake = self.solshare_apartment_uptake_fraction()
        premium = self.solshare_capex_premium_fraction()
        return 1.0 + apt * uptake * premium

    # ----- Stage C round 3 (Claude 2): biosolar roof ----------------------

    def biosolar_params(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("biosolar_raw", {}))

    def biosolar_pv_yield_multiplier_per_cell(self) -> float:
        return float(self.biosolar_params().get("pv_yield_multiplier", 1.06))

    def biosolar_cooling_multiplier_per_cell(self) -> float:
        return float(self.biosolar_params().get(
            "cooling_demand_multiplier", 0.93
        ))

    def biosolar_capex_multiplier_per_cell(self) -> float:
        return float(self.biosolar_params().get("roof_capex_multiplier", 1.35))

    def biosolar_uptake_fraction(self) -> float:
        return float(self.biosolar_params().get(
            "default_built_uptake_fraction", 0.30
        ))

    def biosolar_cooling_share_of_total_demand(self) -> float:
        return float(self.biosolar_params().get(
            "cooling_share_of_total_demand", 0.30
        ))

    def rooftop_pv_capex_multiplier_with_biosolar(self,
                                                    scenario: Scenario
                                                    ) -> float:
        if not getattr(scenario, "allow_biosolar", False):
            return 1.0
        uptake = self.biosolar_uptake_fraction()
        premium = self.biosolar_capex_multiplier_per_cell() - 1.0
        return 1.0 + uptake * premium

    def rooftop_pv_yield_multiplier_with_biosolar(self,
                                                    scenario: Scenario
                                                    ) -> float:
        if not getattr(scenario, "allow_biosolar", False):
            return 1.0
        uptake = self.biosolar_uptake_fraction()
        bonus = self.biosolar_pv_yield_multiplier_per_cell() - 1.0
        return 1.0 + uptake * bonus

    def total_demand_multiplier_with_biosolar(self,
                                                scenario: Scenario
                                                ) -> float:
        """Aggregate demand multiplier when biosolar is active.

        The per-cell cooling-demand reduction (0.93) applies to top-floor
        cooling only; at the district level the impact scales with
        uptake x cooling_share_of_total_demand x (1 - cooling_mult).
        Defaults give 1 - 0.30 x 0.30 x 0.07 = 0.9937, ie ~0.6% lower
        district demand on biosolar cells.
        """
        if not getattr(scenario, "allow_biosolar", False):
            return 1.0
        uptake = self.biosolar_uptake_fraction()
        cooling_share = self.biosolar_cooling_share_of_total_demand()
        cooling_drop = 1.0 - self.biosolar_cooling_multiplier_per_cell()
        return 1.0 - uptake * cooling_share * cooling_drop

    # ----- Stage C round 3 (Claude 2): BIPV facade ------------------------

    def bipv_params(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("bipv_raw", {}))

    def bipv_applies_above_height_m(self) -> float:
        return float(self.bipv_params().get("applies_above_height_m", 18.0))

    def bipv_yield_multiplier_vs_rooftop(self) -> float:
        return float(self.bipv_params().get(
            "yield_multiplier_vs_rooftop", 0.60
        ))

    def bipv_capex_multiplier_vs_rooftop(self) -> float:
        return float(self.bipv_params().get(
            "capex_multiplier_vs_rooftop", 2.0
        ))

    def bipv_kwp_per_meter_of_height(self) -> float:
        return float(self.bipv_params().get(
            "kwp_per_meter_of_height", 10.0
        ))

    def bipv_uptake_fraction(self) -> float:
        return float(self.bipv_params().get("default_uptake_fraction", 0.50))

    def bipv_annualised_inr_per_kwp(self, actor: Optional[str] = None) -> float:
        """Per-kWp annualised cost of BIPV — rooftop annualised x capex_mult.

        actor=None => the owner-blended rooftop rate (BIPV sits on the same
        buildings as rooftop PV, so it shares the financing blend;).
        """
        rooftop = self.rooftop_pv_annualised_inr_per_kwp(actor)
        return rooftop * self.bipv_capex_multiplier_vs_rooftop()

    # ----- Stage C round 3 (Claude 2): solar carport ----------------------

    def carport_params(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("carport_raw", {}))

    def carport_eligible_land_uses(self) -> List[str]:
        return list(self.carport_params().get(
            "eligible_land_uses", ["road", "office", "shopping_centre"],
        ))

    def carport_kwp_per_cell_default(self) -> float:
        return float(self.carport_params().get("kwp_per_cell_default", 800.0))

    def carport_capex_multiplier_vs_ground_mount(self) -> float:
        return float(self.carport_params().get(
            "capex_multiplier_vs_ground_mount", 1.20
        ))

    def carport_uptake_fraction(self) -> float:
        return float(self.carport_params().get("default_uptake_fraction", 0.40))

    def carport_annualised_inr_per_kwp(self, actor: str = "utility") -> float:
        """Per-kWp annualised cost of solar carport.

        Equals ``solar_farm_annualised x carport_capex_mult``. Same actor
        tier as the ground-mount farm (utility default).
        """
        base = self.solar_farm_annualised_inr_per_kwp(actor)
        return base * self.carport_capex_multiplier_vs_ground_mount()

    # ----- Stage C round 5: floating PV on BLUE_SPACE ------

    def floating_pv_params(self) -> Dict[str, Any]:
        return dict(self.__dict__.get("floating_pv_raw", {}))

    def floating_pv_eligible_land_uses(self) -> List[str]:
        return list(self.floating_pv_params().get(
            "eligible_land_uses", ["blue_space"],
        ))

    def floating_pv_kwp_per_cell_default(self) -> float:
        return float(self.floating_pv_params().get("kwp_per_cell_default", 1500.0))

    def floating_pv_capex_multiplier_vs_ground_mount(self) -> float:
        return float(self.floating_pv_params().get(
            "capex_multiplier_vs_ground_mount", 1.18
        ))

    def floating_pv_yield_multiplier_vs_ground_mount(self) -> float:
        return float(self.floating_pv_params().get(
            "yield_multiplier_vs_ground_mount", 1.04
        ))

    def floating_pv_uptake_fraction(self) -> float:
        return float(self.floating_pv_params().get("default_uptake_fraction", 0.30))

    def canal_pv_kwp_per_cell(self) -> float:
        """STAGE- (Q23): canal-top PV nameplate per 100 m canal cell.

        Default 210 kWp/cell = 2.1 MW per canal-km (PEDA Sidhwan/Ghaggar
        canal-top deployments, Tier 1-2; see economics.yaml
        ``floating_pv.canal``). Applied INSTEAD of the pond per-cell x
        uptake product on BLUE_SPACE cells tagged ``amenity_subtype ==
        "canal"`` - a linear canal-top structure's density is already net
        of walkway and support-frame spacing, so no uptake fraction stacks.
        The LP's existing floating-PV decision variable sizes the build
        within the resulting ceiling (register Q23: capacity is a decision
        variable capped by canal length x density).
        """
        canal = self.floating_pv_params().get("canal") or {}
        return float(canal.get("kwp_per_cell", 210.0))

    def floating_pv_min_cluster_size(self) -> int:
        """Minimum 4-connected BLUE_SPACE cluster size for floating-PV deployment.

        Default 2 — drops isolated BLUE_SPACE singletons from the LP cap
        (aesthetic + BOS-cost rationale). Setting to 1 in
        ``floating_pv.site_selection.min_cluster_size`` restores the
        legacy "every water cell hosts" behaviour without code changes.
        """
        block = self.floating_pv_params().get("site_selection") or {}
        try:
            return max(1, int(block.get("min_cluster_size", 2)))
        except (TypeError, ValueError):
            return 2

    def floating_pv_annualised_inr_per_kwp(self, actor: str = "utility") -> float:
        """Per-kWp annualised cost of floating PV (BLUE_SPACE-hosted).

        Equals ``solar_farm_annualised x floating_pv_capex_mult``. Same actor
        tier as ground-mount (utility default).
        """
        base = self.solar_farm_annualised_inr_per_kwp(actor)
        return base * self.floating_pv_capex_multiplier_vs_ground_mount()

    def weighted_cost_objective(self, annual_cost_inr: float,
                                  annual_emissions_kgco2: float,
                                  alpha: float) -> float:
        """Weighted Stage C objective combining cost and carbon.

        (1 - alpha) * cost + alpha * carbon_price * emissions

        Returns
        -------
        float
            Composite INR-denominated objective value (for ranking only;
            not a real INR figure when alpha > 0).
        """
        return ((1.0 - alpha) * annual_cost_inr
                + alpha * self.carbon_price_inr_per_kgco2() * annual_emissions_kgco2)

    # ----- battery / V2G specs (unchanged signature) ------------------
    def battery_round_trip_efficiency(self) -> float:
        return float(self.technologies["li_ion_battery"].get(
            "round_trip_efficiency", 0.90
        ))

    def battery_round_trip_efficiency_for(self, coupling_mode: str = "ac_traditional"
                                            ) -> float:
        """Stage C round 3 (Claude 2): battery RTE varies by coupling mode.

        ``ac_traditional`` returns the legacy value
        (``battery_round_trip_efficiency``); ``dc_native`` (SigEnergy
        SigenStor-style integrated PV+battery) raises RTE by skipping the
        DC->AC->DC conversion. YAML overrides under ``battery_coupling``
        win when present.
        """
        bc = self.__dict__.get("battery_coupling_raw", {}) or {}
        if coupling_mode == "dc_native":
            return float(bc.get(
                "dc_native_round_trip_efficiency", 0.94,
            ))
        return float(bc.get(
            "ac_traditional_round_trip_efficiency",
            self.battery_round_trip_efficiency(),
        ))

    def battery_auxiliary_energy_consumption_fraction(self) -> float:
        """Battery plant auxiliary (house) load, as a fraction of charging
        energy. Thermal management, BMS standby, fire protection, controls.

        Defaults to 0.0 so any config without the key stays byte-exact.

 the two RTE figures are on a CONVERSION boundary (their
        derivation attributes the whole 0.90 -> 0.94 delta to removing a
        DC->AC->DC stage), so this is additive, not a double-count. See the
        ``battery_coupling`` block in config/economics.yaml for the CERC
        citation and the declared limitations.
        """
        bc = self.__dict__.get("battery_coupling_raw", {}) or {}
        return float(bc.get("auxiliary_energy_consumption_fraction", 0.0))

    def battery_rte_net_of_aux_for(self,
                                     coupling_mode: str = "ac_traditional"
                                     ) -> float:
        """Round-trip efficiency NET of the plant's own auxiliary load.

        ``battery_round_trip_efficiency_for x (1 - aux)``, mirroring
        CERC's own ``RTE x (1 - AEC)`` formulation, which reports the two
        as separate rows (Form-3: "Round-Trip Efficiency %" and "Auxiliary
        Energy Consumption of ESS %").

        This is DELIBERATELY a separate getter from
        ``battery_round_trip_efficiency_for``: that one is asserted to
        return exactly 0.90 / 0.94 by ``tests/test_energy_milp.py`` and
        must keep testing the coupling model on its own. Dispatch and the
        resilience script consume THIS one.
        """
        return (self.battery_round_trip_efficiency_for(coupling_mode)
                * (1.0 - self.battery_auxiliary_energy_consumption_fraction()))

    def battery_max_dod(self) -> float:
        return float(self.technologies["li_ion_battery"].get(
            "max_depth_of_discharge", 0.90
        ))

    # FX-1/: real storage power limits (C-rates), replacing the
    # old per-slice hours/24 throughput proxy (~C/27, unphysically slow).
    def battery_c_rate_per_hour(self) -> float:
        return float(self.technologies["li_ion_battery"].get(
            "c_rate_per_hour", 0.5
        ))

    def thermal_storage_c_rate_per_hour(self) -> float:
        return float(self.technologies["thermal_cold_storage"].get(
            "c_rate_per_hour", 0.2
        ))

    # ------------------------------------------------------------------
    # SOLAR WATER HEATING. Flag-gated; every accessor returns
    # a falsy/neutral value when `technologies.solar_thermal.enabled` is
    # false, so the production path is untouched until the flag flips.
    # ------------------------------------------------------------------
    def _solar_thermal(self) -> Dict[str, object]:
        return (self.technologies or {}).get("solar_thermal", {}) or {}

    def solar_thermal_enabled(self) -> bool:
        return bool(self._solar_thermal().get("enabled", False))

    def solar_thermal_kw_per_m2(self, slice_id: str) -> float:
        """Useful collector heat, kW per m2 of aperture, in this slice.

        Same convention as `pv_capacity_factor`: the value is the AVERAGE
        power over the slice, so multiplying by the slice's hours gives kWh.

        The table is derived, not assumed - see
        scripts/solar_thermal_yield_derivation.py, which transposes the GSA
        hourly DNI to the 46 deg collector plane, applies the IS 12933
        efficiency curve with an incidence angle modifier, a seasonal
        collector inlet and PM2.5/dust soiling, and clamps each hour at the
        cutoff irradiance below which a real system stops circulating.

        NOTE THE COLLECTOR'S DAY IS SHORTER THAN PV'S, and that is physics
        rather than a table error: in January this returns zero for 06-08 and
        16-18 while PV still generates, because those hours never cross
        G* = a1 (Ti - Ta) / eta0 = 194 W/m2.
        """
        if not self.solar_thermal_enabled():
            return 0.0
        s = self.slice_by_id(slice_id)
        tab = self._solar_thermal().get("kw_per_m2_by_month_daypart") or {}
        by_month = tab.get(s.month) or {}
        return float(by_month.get(s.daypart, 0.0))

    def solar_thermal_tank_kwh_per_m2(self) -> float:
        """Usable tank energy per m2 of collector, kWh.

        MNRE sizes 100 LPD onto ~2 m2, i.e. 50 litres per m2, and the useful
        store is that mass over the rise from inlet to setpoint. Uses the
        DHW block's own setpoint so the two cannot drift apart.
        """
        st = self._solar_thermal()
        litres = float(st.get("tank_litres_per_m2_collector", 0.0))
        dhw = (self.heating_loads or {}).get("dhw", {}) or {}
        setpoint = float(dhw.get("setpoint_c", 60.0))
        inlet = float(dhw.get("reference_inlet_c", 12.0))
        return litres * 4.186 * max(0.0, setpoint - inlet) / 3600.0

    def solar_thermal_tank_retention(self, hours: float) -> float:
        """Fraction of stored heat surviving `hours` of standing loss."""
        loss = float(self._solar_thermal().get(
            "tank_standing_loss_frac_per_hour", 0.0))
        if loss <= 0.0 or hours <= 0.0:
            return 1.0
        return max(0.0, (1.0 - loss) ** hours)

    def solar_thermal_capex_inr_per_m2(self) -> float:
        """Installed capex per m2, NET of the geyser it replaces.

        MNRE's standard specification item 09 is "Electrical back up - XX KW
        booster heater", i.e. a solar water heater is ONE appliance with an
        integral element, not a solar tank plus a separate geyser. So the
        geyser capex genuinely is avoided: "The saving in terms of capital
        cost for two geysers may be up to Rs. 10000 to 12000".
        WHAT IS *NOT* AVOIDED is the electricity - the booster still runs on
        cloudy days and winter mornings, and that stays in the LP as ordinary
        water-heating demand the collector failed to cover.
        """
        st = self._solar_thermal()
        gross = float(st.get("capex_inr_per_m2", 0.0))
        credit = float(st.get("avoided_geyser_capex_inr_per_system", 0.0))
        per_sys = float(st.get("m2_per_100_lpd", 0.0))
        if per_sys > 0:
            gross -= credit / per_sys
        return max(0.0, gross)

    def solar_thermal_annualised_inr_per_m2(self, actor: str = "rwa_pooled"
                                            ) -> float:
        """Levelised annual cost per m2 at `actor`'s cost of capital.

        CRF handles the 15-year collector inside a 25-year town WITHOUT an
        explicit replacement event: a shorter life means a larger annual
        charge, which is exactly the sinking fund the replacement needs.
        OPEX is charged on the GROSS capex, because maintenance scales with
        the hardware installed, not with the price net of a credit.
        """
        st = self._solar_thermal()
        life = int(st.get("lifetime_years", 15))
        opex_f = float(st.get("opex_fraction_of_capex_per_year", 0.0))
        gross = float(st.get("capex_inr_per_m2", 0.0))
        rate = self.actor_discount_rate(actor)
        return (annualised_capex(self.solar_thermal_capex_inr_per_m2(),
                                 rate, life)
                + gross * opex_f)

    def solar_thermal_blended_annualised_inr_per_m2(self) -> float:
        """Levelised annual cost per m2 at the BLENDED cost of capital.

        Same construction as rooftop PV's four-way owner blend: one
        technology, four owners, weighted by where the water heating
        actually is. The two blends land within 0.1 pp of each other
        (8.92% vs ~8.82%), which is the check that the ownership map was
        not invented - it is the same roofs and the same people.

        Falls back to the single rwa_pooled rate when no weights are
        configured, so a fixture without the table still prices.
        """
        w = self._solar_thermal().get("owner_weights") or {}
        if not w:
            return self.solar_thermal_annualised_inr_per_m2("rwa_pooled")
        tot = sum(float(v) for v in w.values())
        if tot <= 0:
            return self.solar_thermal_annualised_inr_per_m2("rwa_pooled")
        return sum(float(v) / tot
                   * self.solar_thermal_annualised_inr_per_m2(str(a))
                   for a, v in w.items())

    def solar_thermal_owner_actor(self, category: str) -> str:
        """Actor tier financing the collector on this category's roof.

        Physically the same asset class as rooftop PV - roof-mounted, owned
        by whoever owns the roof - so it reuses the SAME actor tiers rather
        than inventing a parallel set.
        """
        m = self._solar_thermal().get("owner_actors") or {}
        return str(m.get(category, "rwa_pooled"))

    def solar_thermal_eligible(self, category: str) -> bool:
        el = self._solar_thermal().get("eligible_categories") or []
        return category in el

    def solar_thermal_roof_pair_form(self) -> bool:
        """: switch the roof-competition constraint from
        the legacy single inequality to the correct PAIR.

        Legacy (False):  PV_area(ALL categories) + ST  <=  ELIGIBLE roof
        Pair   (True):   ST <= ELIGIBLE roof   and   PV_area + ST <= TOTAL roof

        The legacy form charges every m2 of district rooftop PV - including
        PV on offices, retail, warehouses and industry, which draw no hot
        water - against the hot-water-eligible roof alone. Measured on the
 pins: PV 428,628.5 m2 + ST 63,226.0 m2 = 491,854.5 m2 =
        the eligible roof EXACTLY (binding), while 177,000 m2 of
        non-eligible roof sits outside the constraint. PV is fungible
        across roofs at aggregate level, collectors are not, so the correct
        pair caps collectors by the eligible roof and conserves the TOTAL
        surface for both. Same shared-surface-accounting defect family as
. Default False = byte-exact legacy until the batch re-pin."""
        return bool(self._solar_thermal().get("roof_pair_constraint", False))

    def solar_thermal_embodied_kgco2_per_m2(self) -> float:
        v = self._solar_thermal().get("embodied_kgco2_per_m2")
        return float(v) if v else 0.0

    def dhw_only_split_factor(self, category: str, slice_id: str) -> float:
        """The WATER-HEATING leg of `heating_split_factor`, on its own.

        HEAT-1 already split the heating load into two products:

            f * dhw_month(m) * dhw_daypart(cat, dp)
          + (1-f) * space_month(m) * space_daypart(cat, dp)

        so the water leg is the FIRST product alone. Solar thermal can only
        displace that one - it cannot heat a room.

        *** THIS IS DELIBERATELY A SEPARATE FUNCTION AND NOT A REFACTOR OF
        `heating_split_factor`. *** That function's arithmetic feeds the
        production demand accumulator, whose float ADDITION ORDER is
        pin-sensitive under the byte-exact suite. Recomposing the two legs
        here and asserting they sum back to it is the drift guard; touching
        the original would move pinned totals for no gain.

        Falls back to zero (not to the legacy product) when the split is not
        configured, because a model with no DHW split has no water-heating
        leg for a collector to serve.
        """
        hl = self.heating_loads or {}
        shares = hl.get("dhw_share_of_peak_by_category", {}) or {}
        if not shares or "dhw" not in hl or not self.climate:
            return 0.0
        s = self.slice_by_id(slice_id)
        f = float(shares.get(category, 0.0))
        if f <= 0.0:
            return 0.0
        return (f * self.dhw_month_factor(s.month)
                * self._heat_daypart("dhw", category, s.daypart))

    def v2g_cycle_degradation_inr_per_kwh(self) -> float:
        return float(self.technologies["v2g_charger"].get(
            "cycle_degradation_inr_per_kwh", 0.0
        ))

    def v2g_kwh_per_unit_per_day(self) -> float:
        return float(self.technologies["v2g_charger"].get(
            "available_kwh_per_unit_per_day", 0.0
        ))

    def v2g_kwh_per_unit_per_day_at(self, year: Optional[int] = None) -> float:
        """TRJ-3: per-period V2G energy budget per unit -
        fleet-average EV pack sizes grow across the horizon (~6 kWh/day
        2030 -> ~9.5 kWh/day 2055 at the same 20% daily export depth;
        sources in economics.yaml ``v2g_charger.
        available_kwh_per_unit_per_day_by_period``). ``year=None`` or a
        missing table returns the static 2030 value (byte-exact base)."""
        static = self.v2g_kwh_per_unit_per_day()
        if year is None:
            return static
        tbl = self.technologies["v2g_charger"].get(
            "available_kwh_per_unit_per_day_by_period") or {}
        return self._interp_year_table(tbl, year, default=static)

    def v2g_power_kw_per_unit(self) -> float:
        return float(self.technologies["v2g_charger"].get(
            "nominal_power_kw_per_unit", 0.0
        ))

    # ----- EV adoption ------------------------------------------------
    def ev_scenario(self, name: Optional[str] = None) -> Dict[str, float]:
        """Return EV adoption params for a scenario name (default 'default')."""
        scen = name or self.ev_adoption.get("default_scenario", "2030_default")
        return self.ev_adoption.get("scenarios", {}).get(scen, {})

    # ----- REV-2: EV smart charging ------------------------
    def ev_smart_charging_config(self) -> Dict[str, object]:
        return dict(self.ev_adoption.get("smart_charging", {}) or {})

    def ev_smart_charging_enabled(self) -> bool:
        """True when the managed-charging block exists and is enabled.
        The Pyomo builders additionally gate on the scenario's
        ``allow_ev_smart_charging`` flag (BAU keeps dumb charging)."""
        return bool(self.ev_smart_charging_config().get("enabled", False))

    def ev_shiftable_fraction(self, charging_class: str) -> float:
        """Movable share of a class's EV-charging energy within its
        plug-in window (charging_class in {'residential', 'workplace'};
        sources + derivation in economics.yaml ``ev_adoption.
        smart_charging``). 0.0 for unknown classes / missing keys."""
        cfg = self.ev_smart_charging_config()
        key = f"shiftable_fraction_{charging_class}"
        # raise when the block is ENABLED but the key is missing.
        # The bare `.get(key, 0.0)` silently switched smart charging off for
        # that class, so renaming the key in YAML would have removed the
        # flexibility with no error - the family again. Absent block still
        # returns 0.0, so legacy fixtures without smart charging stay exact.
        if (charging_class in ("residential", "workplace")
                and cfg and cfg.get("enabled") and key not in cfg):
            raise ValueError(
                f"ev_adoption.smart_charging is enabled but '{key}' is "
                f"missing - refusing the silent 0.0 that would disable "
                f"{charging_class} EV load shifting"
            )
        return float(cfg.get(key, 0.0) or 0.0)

    def ev_smart_charging_cost_inr_per_kwh(self) -> float:
        """Aggregator/platform fee per SHIFTED kWh (managed-charging OpEx)."""
        return float(self.ev_smart_charging_config()
                     .get("program_cost_inr_per_kwh", 0.0) or 0.0)

    # ----- EV ownership BY INCOME ------------------------
    _INCOME_BY_CATEGORY = {
        "low_income_residential": "low",
        "mid_income_residential": "mid",
        "high_income_residential": "high",
    }

    def income_for_category(self, category: str) -> Optional[str]:
        """Map a residential category name to an income tier, else None."""
        return self._INCOME_BY_CATEGORY.get(category)

    @staticmethod
    def _period_table_lookup(table: dict, year: int, income: str) -> Optional[float]:
        """Resolve ``table[year][income]`` from a period-keyed ramp table whose
        outer keys may be ints or strings. Exact match when ``year`` is a
        tabulated period (the multi-period model solves at exactly these years);
        otherwise linear-interpolates across the sorted periods and clamps at
        the ends. Returns None when the table is empty / income absent."""
        if not table:
            return None
        pts = []
        for k, row in table.items():
            try:
                yk = int(k)
            except (ValueError, TypeError):
                continue
            if income in (row or {}):
                pts.append((yk, float(row[income])))
        if not pts:
            return None
        pts.sort()
        for yk, v in pts:
            if yk == year:
                return v
        if year <= pts[0][0]:
            return pts[0][1]
        if year >= pts[-1][0]:
            return pts[-1][1]
        for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
            if y0 <= year <= y1:
                return v0 + (v1 - v0) * (year - y0) / (y1 - y0)
        return pts[-1][1]

    def ev_car_share(self, income: str, year: Optional[int] = None) -> float:
        """Fraction of households of this income tier owning an EV-CAR.

        When ``year`` is given and the per-period ramp table
        ``ev_vehicle_ownership.ev_car_share_by_period`` contains it, return the
        ramped value (2030/2042/2055); otherwise fall back to the 2030
        ``by_income`` baseline. Used by the multi-period dispatch so V2G
        capacity + EV charge load grow as the EV-car fleet matures."""
        own = self.ev_vehicle_ownership or {}
        if year is not None:
            ramped = self._period_table_lookup(
                own.get("ev_car_share_by_period", {}), year, income)
            if ramped is not None:
                return float(ramped)
        return float(own.get("by_income", {})
                     .get(income, {}).get("ev_car_share", 0.0))

    def e2w_share(self, income: str) -> float:
        """Fraction of households of this income tier owning an electric
        2-wheeler (held flat across periods; no e-2W period ramp table)."""
        return float(self.ev_vehicle_ownership.get("by_income", {})
                     .get(income, {}).get("e2w_share", 0.0))

    def cars_per_owning_household(self, income: str) -> float:
        """Average EV-cars per CAR-OWNING household of this income tier (multi-car:
        affluent households often own 2+). Defaults to 1.0 (single-car) when the
        table is absent — preserves the pre- behaviour byte-exactly."""
        return float((self.ev_vehicle_ownership or {})
                     .get("cars_per_owning_household", {}).get(income, 1.0))

    def ev_cars_per_household(self, income: str, year: Optional[int] = None) -> float:
        """Effective EV-cars PER HOUSEHOLD = ev_car_share(year) x cars_per_owning
        _household. Drives the V2G fleet (each car is a V2G unit) and the EV-car
        charging load (more cars per HH -> more charging)."""
        return self.ev_car_share(income, year) * self.cars_per_owning_household(income)

    def v2g_willingness(self, income: str) -> float:
        """Fraction of EV-CAR owners of this income tier willing to do V2G."""
        return float(self.ev_vehicle_ownership.get("v2g_willingness_by_income", {})
                     .get(income, 0.0))

    def street_lighting_daypart_shape(self) -> Dict[str, float]:
        """Night-heavy daypart shape (fractions summing to ~1.0) for the
        grid-powered street-lighting load. Empty when not configured."""
        return dict(self.street_lighting.get("daypart_shape", {}) or {})

    def street_lighting_monthly_modifier(self, month: str) -> float:
        """ (Part 4): per-month burn-hour multiplier (dusk→dawn window
        scales with daylength: winter ~1.17, summer ~0.84). Mean across months
        ~1.0 so the ANNUAL streetlight energy is unchanged; only the seasonal
        shape shifts. OPT-IN: returns 1.0 (flat, byte-exact production) unless
        `monthly_modifier_enabled` is true — the seasonal shape moves the headline
        by only -0.00024%, so it is a realism scenario, not the default baseline."""
        if not bool(self.street_lighting.get("monthly_modifier_enabled", False)):
            return 1.0
        return float(
            self.street_lighting.get("monthly_modifier", {}).get(month, 1.0)
        )

    def daypart_hours_per_day(self) -> Dict[str, float]:
        """Hours of a DAY covered by each daypart, derived from the slice table
        rather than assumed (12 x 2 h in the 864-slice model).

        ``hours_per_year`` already carries each slice's day-count weight, so
        summing it per daypart and dividing by 365 recovers that daypart's
        length in hours regardless of how many day-types the calendar splits
        into. Cached on the instance."""
        cache = self.__dict__.get("_daypart_hours_per_day_cache")
        if cache is None:
            acc: Dict[str, float] = {}
            for s in self.slices:
                acc[s.daypart] = acc.get(s.daypart, 0.0) + s.hours_per_year
            cache = {dp: h / 365.0 for dp, h in acc.items()}
            self.__dict__["_daypart_hours_per_day_cache"] = cache
        return cache

    def ev_kwh_per_household_per_day(self, income: str,
                                      year: Optional[int] = None) -> float:
        """: daily EV-charging energy for ONE household of
        this income tier, built bottom-up from the vehicle stock the config
        already declares and cites:

            cars/HH  (ev_car_share[year] x cars_per_owning_household)
                     x ev_car_kwh_per_day
          + e-2W/HH  (e2w_share, held flat across periods)
                     x e2w_kwh_per_day

        This REPLACES ``charge_mult``, which multiplied a per-HOUSEHOLD
        ownership concept by a per-CELL peak. Because cells carry roughly the
        same base peak whatever their household count, that route handed a
        high-income household 15.7x a low-income one and implied 24.3
        kWh/car/day - 121 km/day in a 5 x 5 km town. See audit."""
        own = self.ev_vehicle_ownership or {}
        car_kwh = float(own.get("ev_car_kwh_per_day", 0.0))
        e2w_kwh = float(own.get("e2w_kwh_per_day", 0.0))
        return (self.ev_cars_per_household(income, year) * car_kwh
                + self.e2w_share(income) * e2w_kwh)

    def ev_kw_per_household(self, category: str, slice_id: str,
                             year: Optional[int] = None) -> float:
        """: residential EV-charging POWER for one household in this slice.

        The daypart shape is normalised by its own sum before use, so the day's
        energy is exactly ``ev_kwh_per_household_per_day`` whatever the shape
        table happens to hold; dividing by the daypart's length in hours turns
        that energy share into kW.

        Returns 0.0 for non-residential categories. Office EV stays on
        ``ev_demand_multiplier``, where a fraction-of-peak IS dimensionally
        right: a workplace charger bank scales with the building, not with a
        household count."""
        income = self.income_for_category(category)
        if income is None:
            return 0.0
        shape = self.ev_adoption.get(
            "ev_charging_daypart_shape_residential", {}) or {}
        total = sum(float(v) for v in shape.values())
        if total <= 0.0:
            return 0.0
        s = self.slice_by_id(slice_id)
        frac = float(shape.get(s.daypart, 0.0)) / total
        if frac <= 0.0:
            return 0.0
        hours = self.daypart_hours_per_day().get(s.daypart, 0.0)
        if hours <= 0.0:
            return 0.0
        return self.ev_kwh_per_household_per_day(income, year) * frac / hours

    def ev_charge_ramp_factor(self, income: str, year: Optional[int] = None) -> float:
        """Per-income EV-charging load ramp at ``year`` relative to the 2030
        anchor (=1.0 at year None / 2030).

: this used to hold its own copy of the
        car-plus-e-2W arithmetic in order to decompose ``charge_mult``. The
        load is now built bottom-up, so the ramp is simply the ratio of the
        same daily-energy function at two years and cannot drift from it.
        Div-by-zero safe because every income tier owns some e-2W, so the 2030
        denominator is strictly positive even where car_share = 0 (low
        income)."""
        if year is None:
            return 1.0
        base = self.ev_kwh_per_household_per_day(income, None)
        if base <= 0.0:
            return 1.0
        return self.ev_kwh_per_household_per_day(income, year) / base

    def ev_demand_multiplier(self, category: str, slice_id: str,
                              ev_scenario_name: Optional[str] = None,
                              year: Optional[int] = None) -> float:
        """Per-slice EV-charging demand multiplier (fraction of peak demand).

        OFFICE ONLY since. Residential EV charging moved to
        ``ev_kw_per_household`` x the cell's household count, because a
        fraction-of-peak was the wrong dimension for a per-household fleet;
        this method returns 0.0 for residential categories so the old route
        cannot be reached by accident. Callers should go through
        ``EnergyNetwork.ev_node_kw``, which picks the right route per node.
        """
        s = self.slice_by_id(slice_id)
        ev = self.ev_scenario(ev_scenario_name)
        if self.income_for_category(category) is not None:
            return 0.0
        if category == "office":
            adopt = float(ev.get("fleet_share", 0.0))
            shape = float(self.ev_adoption.get(
                "ev_charging_daypart_shape_office", {}
            ).get(s.daypart, 0.0))
            # (Realism audit A4): replace magic 0.30 scalar with
            # a charger-type-mix weighted multiplier. Fall back to 0.30 if
            # the mix table is absent (legacy compatibility).
            mix = self.ev_adoption.get("ev_charger_type_mix_office", {})
            if mix:
                office_mult = sum(
                    float(v.get("share", 0.0)) * float(v.get("duty_cycle", 0.0))
                    for v in mix.values()
                )
            else:
                office_mult = 0.30
            return adopt * shape * office_mult
        return 0.0


# ---------------------------------------------------------------------------
# Cached singleton (matches the pattern of core.config.load_config)
# ---------------------------------------------------------------------------
_cached: Optional[Economics] = None


def load_economics(path: Optional[Path] = None,
                   force_reload: bool = False) -> Economics:
    """Get the cached Economics singleton, loading the YAML on first call."""
    global _cached
    if _cached is None or force_reload:
        _cached = Economics.from_yaml(path)
    return _cached


if __name__ == "__main__":
    econ = load_economics(force_reload=True)
    print(f"loaded economics: {econ.currency} {econ.base_year}, "
          f"{len(econ.slices)} slices, {len(econ.design_days)} design days")
    print("\nDiscount rates per actor tier:")
    for actor in ACTOR_TIERS:
        print(f"  {actor:<24} {econ.actor_discount_rate(actor):.3%}")
    print("\nAnnualised CAPEX (assuming RWA-pooled actor where applicable):")
    print(f"  rooftop PV: INR {econ.rooftop_pv_annualised_inr_per_kwp():,.0f} / kWp / yr")
    print(f"  solar farm: INR {econ.solar_farm_annualised_inr_per_kwp():,.0f} / kWp / yr")
    print(f"  battery:    INR {econ.battery_annualised_inr_per_kwh():,.0f} / kWh / yr")
    print(f"  V2G:        INR {econ.v2g_annualised_inr_per_unit():,.0f} / unit / yr")
    print(f"\nEmission factor: {econ.emission_factor():.2f} kgCO2/kWh")
    print(f"Scenarios: {sorted(econ.scenarios.keys())}")
    # Sanity-check a few slice values
    print(f"\nExample slices:")
    for sid in ("jan_18_20", "jun_14_16", "dec_06_08", "nov_18_20"):
        s = econ.slice_by_id(sid)
        cf = econ.pv_capacity_factor(sid)
        tariff = econ.import_tariff(sid)
        mid_dem = econ.daypart_multiplier("mid_income_residential", sid)
        print(f"  {sid:<12} band={s.tariff_band:<14} cf={cf:.2f} tariff={tariff:.2f} mid_demand={mid_dem:.2f}")
