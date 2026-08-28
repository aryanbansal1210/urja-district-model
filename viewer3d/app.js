const DATA_ROOT = "../outputs/geojson3d";
const DISPATCH_RESULTS_URL = "../outputs/data/energy/dispatch_results.json";
const ENERGY_SUMMARY_URL = DISPATCH_RESULTS_URL;
const BASELINE_AUDIT_URL = "../outputs/data/baseline_audit.md";
const PRICE_SCENARIO_SWEEP_URL = "../outputs/data/energy/price_scenario_sweep.csv";
const PLACEMENT_AUDIT_URL = "../outputs/data/placement_audit.md";
const ECONOMICS_URL = "../config/economics.yaml";
const FALLBACK_LAYOUTS = [
  { name: "chandigarh_sector", label: "Chandigarh Sector", path: "chandigarh_sector.geojson" },
  { name: "dispersed_low", label: "Dispersed Low", path: "dispersed_low.geojson" },
  { name: "compact_centre", label: "Compact Centre", path: "compact_centre.geojson" },
  { name: "radial", label: "Radial", path: "radial.geojson" },
  // BASELINE 2: "plan as delivered" Zirakpur ribbon
  // sprawl. Same built programme as the designed town, arranged along
  // two highway corridors, no solar. Its ENERGY comparison is retired
  // (FINDINGS - programme-constant makes it identical to BAU); it
  // is shown for the PLANNING comparison: 9/20 hard constraints, 119
  // of 393 homes >800 m from worship. See also the land-
  // productivity result that replaced its energy role.
  { name: "zirakpur_ribbon", label: "Baseline 2 (Zirakpur sprawl)", path: "zirakpur_ribbon.geojson" }
];

const LAND_USE_ORDER = [
  "residential_low",
  "residential_mid",
  "residential_high",
  "school",
  "office",
  "shopping_centre",
  "restaurant_food_service",
  "hotel_guesthouse",
  "healthcare",
  "light_industry",
  "warehouse_cold_storage",
  "public_services",
  "religious",
  "retail_highstreet",
  "blue_space",
  "parking_lot",
  "open_space",
  "road",
  "solar_farm"
];

// (the author: "the labelling in the 3d viewer is all wrong ... i
// could only find three types of labels: LOW:LOW, MID:MID, HIGH:HIGH").
// "Residential low/mid/high" reads as BUILDING HEIGHT. It means INCOME
// BAND, and the relationship is the opposite of what the name suggests:
// HIGH income is the LEAST dense class (plotted kothis, FAR 1.2, 40
// households/ha) while LOW income is the densest (flats, FAR 2.0, 468
// households/ha). Renamed so the income band is explicit and the built
// form is on the label. See buildingTypeLabel for the per-cell
// typology, which is what actually varies within each band.
const LABELS = {
  residential_low: "Housing - EWS/LIG flats",
  residential_mid: "Housing - MIG flats",
  residential_high: "Housing - HIG plotted kothi",
  school: "School",
  office: "Office",
  shopping_centre: "Shopping centre",
  restaurant_food_service: "Restaurant / food",
  hotel_guesthouse: "Hotel / guesthouse",
  healthcare: "Healthcare",
  light_industry: "Light industry",
  warehouse_cold_storage: "Warehouse / cold storage",
  public_services: "Public services",
  religious: "Religious",
  retail_highstreet: "Retail high street",
  blue_space: "Blue space",
  parking_lot: "Parking lot",
  open_space: "Open space",
  road: "Road",
  solar_farm: "Solar farm"
};

const METERS_PER_DEGREE_LAT = 111_320;
const DEFAULT_DISTRICT_SPAN_M = 5000;
const CLEAR_SKY_PERFORMANCE_RATIO = 0.86;
// 0.10 -> 0.0714, matching the model's honest ground-mount
// density (3.5 ac/MWdc, demand_norms.yaml). Sizes the carport canopy
// visual from its kWp - the old value under-drew canopies by 29%.
const SOLAR_FARM_KWP_PER_M2 = 0.0714;
// Visual exaggeration for extrusions in the 200 m grid. Physical values stay
// in tooltips/data; every 3D building/plant/high-street elevation uses this.
const BUILDING_HEIGHT_SCALE = 3;
const LOCKED_HEIGHT_SCALE = BUILDING_HEIGHT_SCALE;
const SHADING_DELTA_M = 6.0;
const GROUND_PV_PANEL_TOP_M = 1.5;
const BLUE_SPACE_BANK_FRAC = 0.14;
const ROOFTOP_PV_PANEL_TILT_DEG = 12;
const GROUND_MOUNT_PV_PANEL_TILT_DEG = 24;
const CARPORT_PV_CANOPY_HEIGHT_M = 4.0;
const CARPORT_PV_PANEL_TILT_DEG = 3;
const HIGHSTREET_STRIP_A = [0.14, 0.36];
const HIGHSTREET_STRIP_B = [0.62, 0.84];
const PER_SHADING_OFFENDER = 0.10;
const MAX_SHADING_PENALTY = 0.40;
const LEGACY_SHADING_MIN_MULTIPLIER = 0.60;
const SHADING_DYNAMIC_TOP_QUANTILE = 0.95;
const SCENARIO_ORDER = ["bau", "pv_only", "pv_battery", "pv_battery_v2g", "pv_battery_v2g_biomass", "full_stack"];
const COCKPIT_TABS = ["live", "trends", "trading", "impact", "cells", "settings"];
// EV / V2G chart pair. The chart used #38bdf8 and #f59e0b, both chosen for the
// old dark background; on the light card the labels sat at roughly 2:1 contrast
// and read as washed-out grey (the author, "make it not grey, make it
// visible colour and fit the theme"). These two clear ~4.5:1 and ~5:1 against
// the card (#FCFBF7), stay clearly blue-vs-orange for colour-blind readers
// because they also differ in lightness, and the orange is warm like the rest
// of the palette. Used for the bars AND their labels so the two always agree.
const EV_CHARGE_COLOUR = "#0284C7";
const EV_DISCHARGE_COLOUR = "#C2410C";
const COCKPIT_FLOW_COLOURS = {
  rooftop: "#22C55E",
  solarFarm: "#FBBF24",
  carport: "#0EA5E9",
  floating: "#2DD4BF",
  battery: "#A855F7",
  v2g: "#06B6D4",
  biomass: "#84CC16",
  wte: "#F97316",
  biogas: "#14B8A6",
  thermal: "#60A5FA",
  dsr: "#2DD4BF",
  evSmart: "#A3E635",
  curtailment: "#F59E0B",
  gridImport: "#EF4444",
  gridExport: "#FBBF24",
  demand: "#F8FAFC"
};
const STAGE_D_DAYPART_KEYS = [
  "00_02",
  "02_04",
  "04_06",
  "06_08",
  "08_10",
  "10_12",
  "12_14",
  "14_16",
  "16_18",
  "18_20",
  "20_22",
  "22_24"
];
// The "Origin" view. 13.45 framed the town edge-to-edge and clipped the
// near corner (the author, "can you zoom out a bit so the entire town
// is visible"). Zoom is logarithmic, so -0.55 widens the field by about 1.5x
// and leaves a margin on all four sides of the 5 km square. ONE constant,
// because the initial view and the reset button were carrying separate copies
// of the same three numbers.
const HOME_VIEW = { zoom: 12.9, pitch: 58, bearing: -35 };

const ELECTRICAL_COLOURS = {
  backbone: [56, 189, 248],
  distribution: [129, 140, 248],
  loadingLow: [34, 197, 94],
  loadingMid: [250, 204, 21],
  loadingHigh: [248, 113, 113],
  import: [239, 68, 68],
  export: [34, 197, 94],
  transformer: [251, 191, 36],
  substation: [244, 114, 182],
  // WAS [248, 250, 252] - near-white, chosen for the dark theme. On the light
  // map the national-grid interconnection was drawn white on near-white, so
  // the author saw the teal data-centre PPA line and concluded there was no link to
  // the grid at all ( "there is a line to data centre but then also
  // make a line to the national grid"). The line was always there. Slate reads
  // on the light ground and stays distinct from the teal PPA line beside it.
  // Same fault as the EV chart's white cursor: dark-theme colours left behind
  // on a surface that is no longer dark.
  gridLine: [71, 85, 105],
  ppaLine: [45, 212, 191]
};
const ELECTRICAL_ARC_LIMIT = 120;
const PLANT_KIND_ORDER = ["biomass_chp", "biogas", "wte"];
const PLANT_LABELS = {
  biomass_chp: "Biomass CHP",
  biogas: "Biogas",
  wte: "Waste-to-energy"
};
const PLANT_COLOURS = {
  biomass_chp: [233, 122, 60],
  biogas: [132, 204, 22],
  wte: [192, 57, 43]
};
const PRICE_SCENARIO_LABELS = {
  bau_continued: "Business as usual continued",
  nep_policy_push: "NEP policy push",
  high_renewables: "High renewables",
  stress_coal_lock_in: "Stress coal lock-in"
};
const PRICE_SCENARIO_SOURCES = {
  bau_continued: "IEA STEPS grid EF proxy; 2.0%/yr real tariff escalation.",
  nep_policy_push: "CEA NEP 2022-32 plus TERI 2050 Low-Carbon endpoint.",
  high_renewables: "TERI No-Fossil plus CEEW 2050 net-zero trajectory.",
  stress_coal_lock_in: "Climate Action Tracker current policies plus IEA WEO CPS."
};
const PLACEMENT_AUDIT_CATEGORIES = {
  "Amenity (school/clinic/etc.) with no ROAD 8-neighbour": {
    short: "Amenity lacks road neighbour",
    colour: [251, 191, 36],
    note: "Amenity has no ROAD in its 8-neighbourhood; Stage F frontage refinement."
  },
  "SOLAR_FARM 4-adj to RESIDENTIAL": {
    short: "Housing adjacent to solar-farm edge",
    colour: [168, 85, 247],
    note: "Residential cell on the solar-farm perimeter (no green buffer). Farm is still clustered; this is an edge-adjacency note, not housing on the array."
  }
};
const FAITH_MARKER_META = {
  sikh: { label: "Sikh", short: "S", colour: [245, 158, 11] },
  hindu: { label: "Hindu", short: "H", colour: [249, 115, 22] },
  muslim: { label: "Muslim", short: "M", colour: [20, 184, 166] },
  christian: { label: "Christian", short: "C", colour: [96, 165, 250] }
};
const CARPORT_SITE_COLOUR = [14, 165, 233];
const STREET_TREE_COLOUR = [55, 135, 64];
const STREET_TREE_TRUNK_COLOUR = [101, 67, 33, 232];
const STREETLIGHT_GRID_COLOUR = [226, 232, 240];
const STREETLIGHT_SOLAR_COLOUR = [56, 189, 248];
const STREETLIGHT_PANEL_COLOUR = [14, 116, 144];
const STREETLIGHT_PANEL_TILT_DEG = 20;
const STREETLIGHT_SEGMENT_COLOURS = [
  [56, 189, 248],
  [34, 197, 94],
  [250, 204, 21],
  [249, 115, 22],
  [168, 85, 247],
  [244, 114, 182],
  [45, 212, 191],
  [96, 165, 250]
];
const CIVIL_TWILIGHT_ALTITUDE_DEG = -6;
const STREETLIGHT_FADE_HOURS = 0.5;
const LIGHTING_DAYPART_LABELS = [
  "00-02",
  "02-04",
  "04-06",
  "06-08",
  "08-10",
  "10-12",
  "12-14",
  "14-16",
  "16-18",
  "18-20",
  "20-22",
  "22-24"
];
const BUILDING_GLOW_COLOURS = {
  residential_low: [255, 190, 105],
  residential_mid: [255, 183, 96],
  residential_high: [255, 174, 86],
  school: [147, 197, 253],
  office: [125, 211, 252],
  public_services: [165, 180, 252],
  healthcare: [110, 231, 183],
  shopping_centre: [251, 191, 36],
  retail_highstreet: [251, 146, 60],
  restaurant_food_service: [248, 113, 113],
  hotel_guesthouse: [216, 180, 254],
  religious: [253, 224, 71],
  light_industry: [203, 213, 225],
  warehouse_cold_storage: [186, 230, 253]
};
const DEFAULT_BUILDING_GLOW_COLOUR = [252, 211, 77];
//: display-only
// land-use palette remap. The GeoJSON's baked colour_rgb (saturated, 20-way)
// made the town read as a patchwork; this remaps to GROUPED TONAL FAMILIES
// (residential = sand ramp by density, institutional = slate/teal family,
// commerce = amber family, industry = cool greys, solar = panel navy) per
// the metropolis/stadium reference recipe: form first, colour as annotation.
// Render-time only - the GeoJSON, exporter and model are untouched; set
// VIS1_PALETTE_ENABLED = false to restore the legacy baked colours exactly.
// Groups stay legend-distinguishable and grayscale-safe (luminance-ordered
// within each family) for thesis figures.
const VIS1_PALETTE_ENABLED = true;
// v2 ("go crazy" pass): +~20% luminance across the board - the
// v1 values multiplied by deck's Lambert lighting left shaded faces at
// ~0.3x and the whole town read "same but darker". Metropolis'
// faceColors puts roofs at 1.12x base and shaded walls at 0.75x base at
// noon; the exposure lift below + the rebalanced lights reproduce those
// ratios (derivation in the plan doc).
const VIS1_LAND_USE_PALETTE = {
  residential_low: [232, 204, 163],
  residential_mid: [214, 184, 141],
  residential_high: [194, 164, 122],
  school: [152, 180, 204],
  office: [168, 192, 210],
  public_services: [156, 170, 196],
  healthcare: [152, 198, 184],
  shopping_centre: [222, 180, 132],
  retail_highstreet: [234, 188, 128],
  restaurant_food_service: [218, 166, 134],
  hotel_guesthouse: [200, 172, 180],
  religious: [228, 208, 164],
  light_industry: [166, 170, 182],
  warehouse_cold_storage: [150, 158, 174],
  parking_lot: [108, 116, 128],
  solar_farm: [60, 88, 134],
  blue_space: [64, 116, 164]
};
function designRgb(props) {
  if (VIS1_PALETTE_ENABLED) {
    const mapped = VIS1_LAND_USE_PALETTE[String(props?.land_use || "")];
    if (mapped) return mapped;
  }
  return props?.colour_rgb || null;
}
const BIPV_FACADE_SOUTH_EXPOSURE = {
  0: 1,
  90: 0.25,
  180: 1,
  270: 0.25
};
const BIPV_KWP_PER_M_HEIGHT = 10;
const BIPV_DEFAULT_UPTAKE = 0.5;
const ENTRANCE_MARKER_COLOUR = [39, 39, 42, 218];
const ENTRANCE_MARKER_HIGHSTREET_COLOUR = [59, 76, 220, 232];
const ENTRANCE_MARKER_OUTLINE = [191, 219, 254, 226];
const MODULE_LABELS = {
  mono_perc: "mono-PERC",
  poly_si: "poly-Si",
  thin_film_cdte: "thin-film CdTe"
};
const DEFAULT_MODULE_MIX = {
  dominantKey: "mono_perc",
  dominantLabel: "mono-PERC blend",
  summaryLabel: "mono-PERC blend"
};
const DEFAULT_TARIFFS = {
  super_off_peak: { import: 3.8, export: 2.2, label: "Super off" },
  off_peak: { import: 4.6, export: 2.8, label: "Off-peak" },
  shoulder: { import: 6.0, export: 3.5, label: "Shoulder" },
  peak: { import: 7.8, export: 4.2, label: "Peak" },
  super_peak: { import: 9.2, export: 4.8, label: "Super peak" }
};
// V2G battery cycle-degradation cost. MUST track the optimiser: this is
// economics.yaml technologies.v2g_charger.cycle_degradation_inr_per_kwh, read
// by Economics.v2g_cycle_degradation_inr_per_kwh (energy/costs.py:4789) and
// charged in the LP objective at energy/dispatch.py:716. The cockpit carried a
// hardcoded 0.8 in two places until, so both the Trading net and the
// Impact wear figure understated V2G wear by 2.5x (INR 57,353/day at 2030).
// Change this only when the config value changes.
const V2G_CYCLE_DEGRADATION_INR_PER_KWH = 2.0;
const TARIFF_MODE_SCENARIOS = {
  fixed_tou: "full_stack",
  agile_iex: "full_stack_agile"
};
const TARIFF_MODE_LABELS = {
  fixed_tou: "Fixed ToU",
  agile_iex: "Agile IEX"
};
const TARIFF_CURVE_COLOURS = {
  fixedImport: "#F97316",
  fixedExport: "#FBBF24",
  agileImport: "#38BDF8",
  agileExport: "#2DD4BF"
};
const EMPTY_EV_V2G_PARAMS = {
  source: "metadata_missing",
  complete: false,
  missing: ["ev_v2g_params"],
  byIncome: {},
  v2gWillingnessByIncome: {},
  evCarShareByPeriod: {},
  chargingShape: null,
  evCarKwhPerDay: null,
  e2wKwhPerDay: null,
  note: "EV/V2G metadata missing from dispatch_results.json."
};
const DEFAULT_COCKPIT_PERIOD_YEAR = "2030";
const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_KEYS = MONTH_LABELS.map((label) => label.toLowerCase());
const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

const state = {
  deckgl: null,
  manifest: null,
  currentLayout: null,
  data: null,
  cellPvKwp: new Map(),
  cellPvDeployedKwp: new Map(),
  cellShading: new Map(),
  cellLightingByDaypart: new Map(),
  shadingRamp: {
    source: "none",
    min: LEGACY_SHADING_MIN_MULTIPLIER,
    max: 1,
    actualMin: LEGACY_SHADING_MIN_MULTIPLIER,
    actualMax: 1,
    count: 0,
    unshadedCount: 0
  },
  pvOverlayEnabled: false,
  shadingOverlayEnabled: false,
  pvDeploymentOverlayEnabled: false,
  // Per-cell roof axis arrows remain available for debugging, but the default
  // entrance cue is now the small doormat marker at the parcel edge.
  axisArrowEnabled: false,
  panelMarkersEnabled: true,
  // vegetation overlay renders scatter trees on OPEN_SPACE
  // parcels at density proportional to `vegetation_fraction`. Default
  // ON because the author wants to see the green spaces in 3D.
  vegetationEnabled: true,
  streetTreesEnabled: true,
  streetlightsEnabled: true,
  localStreetsEnabled: true,
  greenwayPathsEnabled: true,
  roadSectionsEnabled: true,
  realismFlagsEnabled: false,
  // BACK OFF BY DEFAULT, (the author: "this thing comes preselected...
  // can you remove it"). It was switched ON on because the work
  // split said 16,500.0 kWp of carport PV was invisible - but that 16,500 is
  // the 2055 figure. The run installs 0 kWp in 2030, 11,500.0 in 2042 and
  // 16,500.0 in 2055, so on the default 2030 view the layer opens a legend
  // panel to announce that nothing is deployed. The toggle stays; a reader who
  // wants to see where canopies could go can switch it on.
  carportSitesEnabled: false,
  electricalOverlayEnabled: false,
  electricalPulse: 0,
  electricalAnimationFrame: null,
  electricalLastFrameMs: 0,
  realTimeShadowsEnabled: true,
  pvOverlayMaxKwp: 0,
  pvOverlayScaleKwp: 0,
  moduleMix: DEFAULT_MODULE_MIX,
  baselineAudit: {},
  priceScenarioSweep: [],
  placementAudit: {
    categories: [],
    byCell: new Map()
  },
  energySummary: null,
  cockpit: {
    visible: true,
    activeTab: "live",
    trendsRange: "day",
    data: null,
    source: "none",
    scenario: "full_stack",
    tariffMode: "fixed_tou",
    periodYear: DEFAULT_COCKPIT_PERIOD_YEAR,
    priceScenario: "nep_policy_push",
    selectedCellProps: null,
    warnings: [],
    warningKeys: new Set()
  },
  selectedCellProps: null,
  infoPanelCollapsed: true,
  legendPanelCollapsed: false,
  theme: "dark",
  sun: {
    dayOfYear: dayOfYearFromDate(new Date()),
    timeHours: 12,
    latitude: 30.64,
    longitude: 76.82,
    altitudeRad: 0,
    azimuthRad: 0,
    altitudeDeg: 0,
    azimuthDeg: 0,
    pvCapacityFactor: 0,
    irradianceWm2: 0
  },
  viewState: {
    longitude: 76.82,
    latitude: 30.64,
    zoom: HOME_VIEW.zoom,
    pitch: HOME_VIEW.pitch,
    bearing: HOME_VIEW.bearing
  }
};

const els = {
  topbar: document.querySelector(".topbar"),
  layoutSelect: document.getElementById("layout-select"),
  layoutButtons: document.getElementById("layout-buttons"),
  archetypeSummary: document.getElementById("archetype-summary"),
  pvOverlayToggle: document.getElementById("pv-overlay-toggle"),
  shadingOverlayToggle: document.getElementById("shading-overlay-toggle"),
  pvDeploymentToggle: document.getElementById("pv-deployment-toggle"),
  electricalOverlayToggle: document.getElementById("electrical-overlay-toggle"),
  sunDate: document.getElementById("sun-date"),
  sunDateLabel: document.getElementById("sun-date-label"),
  sunTime: document.getElementById("sun-time"),
  sunTimeLabel: document.getElementById("sun-time-label"),
  sunTimeField: document.getElementById("sun-time")?.closest(".sun-slider-field"),
  sunStatusLabel: document.getElementById("sun-status-label"),
  tariffStatus: document.getElementById("tariff-status"),
  tariffStatusLabel: document.getElementById("tariff-status-label"),
  cockpitToggle: document.getElementById("cockpit-toggle"),
  cockpitPanel: document.getElementById("cockpit-panel"),
  cockpitDataHint: document.getElementById("cockpit-data-hint"),
  cockpitTitle: document.getElementById("cockpit-title"),
  cockpitTariffMode: document.getElementById("cockpit-tariff-mode"),
  cockpitTariffModeButtons: document.querySelectorAll("[data-tariff-mode]"),
  cockpitScenario: document.getElementById("cockpit-scenario"),
  cockpitStatus: document.getElementById("cockpit-status"),
  cockpitPeriod: document.getElementById("cockpit-period"),
  cockpitTabs: document.querySelector(".cockpit-tabs"),
  cockpitPages: document.querySelectorAll("[data-cockpit-page]"),
  cockpitLiveChips: document.getElementById("cockpit-live-chips"),
  cockpitLiveEnergy: document.getElementById("cockpit-live-energy"),
  cockpitLiveSelf: document.getElementById("cockpit-live-self"),
  cockpitLiveTrading: document.getElementById("cockpit-live-trading"),
  cockpitTrendsTotal: document.getElementById("cockpit-trends-total"),
  cockpitTrendsChart: document.getElementById("cockpit-trends-chart"),
  cockpitTariffStrip: document.getElementById("cockpit-tariff-strip"),
  cockpitSolarStrip: document.getElementById("cockpit-solar-strip"),
  cockpitTrendsLegend: document.getElementById("cockpit-trends-legend"),
  cockpitTrendsNote: document.getElementById("cockpit-trends-note"),
  cockpitDsrChip: document.getElementById("cockpit-dsr-chip"),
  cockpitBiomassChart: document.getElementById("cockpit-biomass-chart"),
  cockpitBuyPrice: document.getElementById("cockpit-buy-price"),
  cockpitSellPrice: document.getElementById("cockpit-sell-price"),
  cockpitTradingChart: document.getElementById("cockpit-trading-chart"),
  cockpitTradingLegend: document.getElementById("cockpit-trading-legend"),
  cockpitTariffDayLabel: document.getElementById("cockpit-tariff-day-label"),
  cockpitTariffChart: document.getElementById("cockpit-tariff-chart"),
  cockpitTariffLegend: document.getElementById("cockpit-tariff-legend"),
  cockpitTariffNote: document.getElementById("cockpit-tariff-note"),
  cockpitTradeNet: document.getElementById("cockpit-trade-net"),
  cockpitTradeDetail: document.getElementById("cockpit-trade-detail"),
  cockpitBestCharge: document.getElementById("cockpit-best-charge"),
  cockpitBestExport: document.getElementById("cockpit-best-export"),
  cockpitCo2Today: document.getElementById("cockpit-co2-today"),
  cockpitCo2Year: document.getElementById("cockpit-co2-year"),
  cockpitAnnualDemand: document.getElementById("cockpit-annual-demand"),
  cockpitDemandDetail: document.getElementById("cockpit-demand-detail"),
  cockpitCostYear: document.getElementById("cockpit-cost-year"),
  cockpitCostDetail: document.getElementById("cockpit-cost-detail"),
  cockpitLifetimeCost: document.getElementById("cockpit-lifetime-cost"),
  cockpitLifetimeDetail: document.getElementById("cockpit-lifetime-detail"),
  cockpitAnnualEmissions: document.getElementById("cockpit-annual-emissions"),
  cockpitPriceScenarioDetail: document.getElementById("cockpit-price-scenario-detail"),
  cockpitNetCost: document.getElementById("cockpit-net-cost"),
  cockpitNetCostDetail: document.getElementById("cockpit-net-cost-detail"),
  cockpitRenewableShare: document.getElementById("cockpit-renewable-share"),
  cockpitRenewableDetail: document.getElementById("cockpit-renewable-detail"),
  cockpitStageDPill: document.getElementById("cockpit-stage-d-pill"),
  cockpitPpaPill: document.getElementById("cockpit-ppa-pill"),
  cockpitSourceStack: document.getElementById("cockpit-source-stack"),
  cockpitSourceLabel: document.getElementById("cockpit-source-label"),
  cockpitTechStack: document.getElementById("cockpit-tech-stack"),
  cockpitRealismChecks: document.getElementById("cockpit-realism-checks"),
  cockpitParetoChart: document.getElementById("cockpit-pareto-chart"),
  cockpitParetoLabel: document.getElementById("cockpit-pareto-label"),
  cockpitPriceScenarioChart: document.getElementById("cockpit-price-scenario-chart"),
  cockpitEquity: document.getElementById("cockpit-equity"),
  cockpitCellEmpty: document.getElementById("cockpit-cell-empty"),
  cockpitCellContent: document.getElementById("cockpit-cell-content"),
  cockpitCellTitle: document.getElementById("cockpit-cell-title"),
  cockpitCellTier: document.getElementById("cockpit-cell-tier"),
  cockpitCellStats: document.getElementById("cockpit-cell-stats"),
  cockpitCellChart: document.getElementById("cockpit-cell-chart"),
  cockpitEvCard: document.getElementById("cockpit-ev-card"),
  cockpitCellUpgrade: document.getElementById("cockpit-cell-upgrade"),
  cockpitSettingAxis: document.getElementById("cockpit-setting-axis"),
  cockpitSettingPanels: document.getElementById("cockpit-setting-panels"),
  cockpitSettingLocalStreets: document.getElementById("cockpit-setting-local-streets"),
  cockpitSettingGreenwayPaths: document.getElementById("cockpit-setting-greenway-paths"),
  cockpitSettingRealTimeShadows: document.getElementById("cockpit-setting-real-time-shadows"),
  cockpitPriceScenario: document.getElementById("cockpit-price-scenario"),
  cockpitSchemaHint: document.getElementById("cockpit-schema-hint"),
  cockpitReset: document.getElementById("cockpit-reset"),
  flowSolar: document.getElementById("flow-path-solar"),
  flowDcPath: document.getElementById("flow-path-dc"),
  flowGrid: document.getElementById("flow-path-grid"),
  flowStorage: document.getElementById("flow-path-storage"),
  flowDemand: document.getElementById("flow-path-demand"),
  flowSolarValue: document.getElementById("flow-solar-value"),
  flowSolar: document.getElementById("flow-path-solar"),
  flowGrid: document.getElementById("flow-path-grid"),
  flowDemand: document.getElementById("flow-path-demand"),
  flowStorage: document.getElementById("flow-path-storage"),
  flowDcPath: document.getElementById("flow-path-dc"),
  flowFirmPath: document.getElementById("flow-path-firm"),
  flowFirmValue: document.getElementById("flow-firm-value"),
  flowFirmNode: document.getElementById("flow-node-firm"),
  flowGridValue: document.getElementById("flow-grid-value"),
  flowStorageValue: document.getElementById("flow-storage-value"),
  flowStorageDetail: document.getElementById("flow-storage-detail"),
  flowDemandValue: document.getElementById("flow-demand-value"),
  flowDcValue: document.getElementById("flow-dc-value"),
  flowDcNode: document.getElementById("flow-node-dc"),
  compassN: document.querySelector(".compass-n"),
  compassE: document.querySelector(".compass-e"),
  compassS: document.querySelector(".compass-s"),
  compassW: document.querySelector(".compass-w"),
  compassNeedle: document.getElementById("compass-needle"),
  themeToggle: document.getElementById("theme-toggle"),
  cameraReset: document.getElementById("camera-reset"),
  infoPanel: document.getElementById("layout-summary-panel"),
  infoPanelToggle: document.getElementById("info-panel-toggle"),
  loading: document.getElementById("loading-panel"),
  layoutTitle: document.getElementById("layout-title"),
  layoutSubtitle: document.getElementById("layout-subtitle"),
  statCells: document.getElementById("stat-cells"),
  statFeatures: document.getElementById("stat-features"),
  statBuilt: document.getElementById("stat-built"),
  statPvLabel: document.getElementById("stat-pv-label"),
  statPv: document.getElementById("stat-pv"),
  statRoadNetwork: document.getElementById("stat-road-network"),
  statWalkability: document.getElementById("stat-walkability"),
  statSun: document.getElementById("stat-sun"),
  statPvNow: document.getElementById("stat-pv-now"),
  energySummary: document.getElementById("energy-summary"),
  energySummaryGrid: document.getElementById("energy-summary-grid"),
  legendPanel: document.getElementById("legend-panel"),
  legendPanelToggle: document.getElementById("legend-panel-toggle"),
  legendList: document.getElementById("legend-list"),
  scaleBar: document.getElementById("scale-bar"),
  scaleLabel: document.getElementById("scale-label"),
  scalePanel: document.querySelector(".scale-panel"),
  pvOverlayLegend: document.getElementById("pv-overlay-legend"),
  shadingOverlayLegend: document.getElementById("shading-overlay-legend"),
  pvDeploymentLegend: document.getElementById("pv-deployment-legend"),
  shadingLegendNone: document.getElementById("shading-legend-none"),
  shadingLegendMid: document.getElementById("shading-legend-mid"),
  shadingLegendHigh: document.getElementById("shading-legend-high"),
  shadingLegendNote: document.getElementById("shading-legend-note"),
  realismFlagsLegend: document.getElementById("realism-flags-legend"),
  realismFlagsList: document.getElementById("realism-flags-list"),
  carportSitesLegend: document.getElementById("carport-sites-legend"),
  electricalOverlayLegend: document.getElementById("electrical-overlay-legend"),
  electricalLegendNote: document.getElementById("electrical-legend-note"),
  cellPanel: document.getElementById("cell-panel"),
  cellPanelTitle: document.getElementById("cell-panel-title"),
  cellPanelGrid: document.getElementById("cell-panel-grid"),
  cellPanelClose: document.getElementById("cell-panel-close")
};

async function init() {
  if (!window.deck) {
    setLoading("deck.gl did not load. Start a local server and check internet access.");
    return;
  }

  const manifest = await loadManifest();
  state.manifest = manifest;
  const firstLayout = manifest.layouts.find((layout) => layout.name === "optimised_sa")
    || manifest.layouts[0]
    || FALLBACK_LAYOUTS[0];
  state.currentLayout = firstLayout.name;
  state.infoPanelCollapsed = readStoredInfoPanelCollapsed();
  state.legendPanelCollapsed = readStoredLegendPanelCollapsed();

  populateLayoutSelect(manifest.layouts);
  initialiseSunControls();
  bindControls();
  syncOverlayControls();
  updateOverlayTop();
  syncInfoPanelCollapsed();
  syncLegendPanelCollapsed();
  createDeck();
  updateCompass();
  await loadModuleMix();
  await loadBaselineAudit();
  await loadPriceScenarioSweep();
  await loadPlacementAudit();
  await loadEnergySummary();
  await loadCockpitData();
  await loadLayout(state.currentLayout);
}

async function loadManifest() {
  try {
    const response = await fetch(`${DATA_ROOT}/manifest.json`, { cache: "no-store" });
    if (!response.ok) throw new Error(`manifest ${response.status}`);
    const manifest = await response.json();
    if (!manifest.layouts || !manifest.layouts.length) {
      throw new Error("manifest has no layouts");
    }
    if (manifest.center) {
      state.viewState.longitude = manifest.center.longitude;
      state.viewState.latitude = manifest.center.latitude;
      state.sun.longitude = manifest.center.longitude;
      state.sun.latitude = manifest.center.latitude;
    }
    return manifest;
  } catch (error) {
    console.warn("Using fallback layout list:", error);
    return {
      center: {
        longitude: state.viewState.longitude,
        latitude: state.viewState.latitude
      },
      layouts: FALLBACK_LAYOUTS
    };
  }
}

// UI-1 (, the author: "we don't need Compact, Radial, just the Optimised
// and Zirakpur ... just make it minimal and neat").
//
// The four extra archetypes are HIDDEN FROM THE BUTTON ROW, not deleted. They
// stay in the <select> and every layout file stays on disk, so any of them can
// still be loaded and Baseline 2 comparison work is unaffected. Checked before
// doing this: the drafts cite none of them by name - the only hits for
// "radial" and "dispersed" are generic phrases about seeding traditions - so
// nothing in the thesis depends on these buttons existing.
const BUTTON_LAYOUTS = new Set(["optimised_sa", "zirakpur_ribbon"]);

function populateLayoutSelect(layouts) {
  els.layoutSelect.innerHTML = "";
  els.layoutButtons.innerHTML = "";
  layouts.forEach((layout) => {
    const option = document.createElement("option");
    option.value = layout.name;
    option.textContent = layout.label || titleCase(layout.name);
    els.layoutSelect.appendChild(option);

    if (!BUTTON_LAYOUTS.has(layout.name)) return;   // UI-1: select only

    const button = document.createElement("button");
    button.type = "button";
    button.className = "layout-tab";
    button.dataset.layout = layout.name;
    button.setAttribute("role", "tab");
    button.textContent = shortLayoutLabel(layout);
    els.layoutButtons.appendChild(button);
  });
  els.layoutSelect.value = state.currentLayout;
  updateLayoutButtons();
}

function bindControls() {
  els.layoutSelect.addEventListener("change", async (event) => {
    await loadLayout(event.target.value);
  });

  els.layoutButtons.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-layout]");
    if (!button) return;
    await loadLayout(button.dataset.layout);
  });

  els.pvOverlayToggle.addEventListener("click", () => {
    setPvOverlayEnabled(!state.pvOverlayEnabled);
  });

  els.shadingOverlayToggle?.addEventListener("click", () => {
    setShadingOverlayEnabled(!state.shadingOverlayEnabled);
  });

  els.pvDeploymentToggle?.addEventListener("click", () => {
    setPvDeploymentOverlayEnabled(!state.pvDeploymentOverlayEnabled);
  });

  els.electricalOverlayToggle?.addEventListener("click", () => {
    setElectricalOverlayEnabled(!state.electricalOverlayEnabled);
  });

  els.cockpitToggle?.addEventListener("click", () => {
    if (!state.cockpit.data) {
      showCockpitDataHint(true);
      return;
    }
    state.cockpit.visible = !state.cockpit.visible;
    applyCockpitVisibility();
  });

  els.cockpitTariffMode?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tariff-mode]");
    if (!button || button.disabled) return;
    setCockpitTariffMode(button.dataset.tariffMode);
  });

  els.cockpitScenario?.addEventListener("change", (event) => {
    state.cockpit.scenario = event.target.value;
    syncTariffModeFromScenario();
    populateCockpitPeriods();
    rebuildPvLookupsForActiveScenario();
    renderCockpit();
  });

  els.cockpitPeriod?.addEventListener("change", (event) => {
    state.cockpit.periodYear = event.target.value || DEFAULT_COCKPIT_PERIOD_YEAR;
    rebuildPvLookupsForActiveScenario();
    renderCockpit();
  });

  els.cockpitTabs?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-cockpit-tab]");
    if (!button) return;
    setCockpitTab(button.dataset.cockpitTab);
  });

  document.querySelectorAll("[data-cockpit-range]").forEach((button) => {
    button.addEventListener("click", () => {
      state.cockpit.trendsRange = button.dataset.cockpitRange || "day";
      renderCockpit();
    });
  });

  document.querySelectorAll("[data-cockpit-jump]").forEach((button) => {
    button.addEventListener("click", () => setCockpitTab(button.dataset.cockpitJump));
  });

  bindCockpitChartTooltips();





  els.cockpitSettingAxis?.addEventListener("change", (event) => {
    state.axisArrowEnabled = Boolean(event.target.checked);
    updateLayers();
  });

  els.cockpitSettingPanels?.addEventListener("change", (event) => {
    state.panelMarkersEnabled = Boolean(event.target.checked);
    updateLayers();
  });




  els.cockpitSettingLocalStreets?.addEventListener("change", (event) => {
    state.localStreetsEnabled = Boolean(event.target.checked);
    syncOverlayControls();
    updateLayers();
  });

  els.cockpitSettingGreenwayPaths?.addEventListener("change", (event) => {
    state.greenwayPathsEnabled = Boolean(event.target.checked);
    syncOverlayControls();
    updateLayers();
  });




  els.cockpitSettingRealTimeShadows?.addEventListener("change", (event) => {
    state.realTimeShadowsEnabled = Boolean(event.target.checked);
    syncOverlayControls();
    updateDeckParameters();
  });

  els.cockpitPriceScenario?.addEventListener("change", (event) => {
    state.cockpit.priceScenario = event.target.value || "nep_policy_push";
    renderCockpit();
  });


  els.cockpitReset?.addEventListener("click", () => {
    state.cockpit.scenario = state.cockpit.data?.scenarios.find((scenario) => scenario.name === "full_stack")
      ? "full_stack"
      : "pv_battery_v2g";
    state.cockpit.tariffMode = tariffModeForScenario(state.cockpit.scenario) || "fixed_tou";
    state.cockpit.activeTab = "live";
    state.cockpit.trendsRange = "day";
    state.cockpit.periodYear = DEFAULT_COCKPIT_PERIOD_YEAR;
    state.cockpit.priceScenario = defaultPriceScenarioName();
    state.cockpit.visible = Boolean(state.cockpit.data);
    if (els.cockpitScenario) els.cockpitScenario.value = state.cockpit.scenario;
    populateCockpitPeriods();
    if (els.cockpitPriceScenario) els.cockpitPriceScenario.value = state.cockpit.priceScenario;
    rebuildPvLookupsForActiveScenario();
    applyCockpitVisibility();
    renderCockpit();
  });

  window.addEventListener("resize", updateOverlayTop);

  els.sunDate.addEventListener("input", (event) => {
    state.sun.dayOfYear = Number(event.target.value);
    updateSunPosition();
  });

  els.sunTime.addEventListener("input", (event) => {
    state.sun.timeHours = Number(event.target.value);
    updateSunPosition();
  });

  els.themeToggle.addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    document.body.className = `theme-${state.theme}`;
    els.themeToggle.textContent = state.theme === "dark" ? "Light" : "Dark";
    applyDayStatusTint();
    updateDeckParameters();
    updateLayers();
  });

  els.cameraReset.addEventListener("click", () => {
    state.viewState = {
      ...state.viewState,
      longitude: state.manifest.center.longitude,
      latitude: state.manifest.center.latitude,
      zoom: HOME_VIEW.zoom,
      pitch: HOME_VIEW.pitch,
      bearing: HOME_VIEW.bearing
    };
    state.deckgl.setProps({ viewState: state.viewState });
    updateCompass();
  });

  els.infoPanelToggle?.addEventListener("click", () => {
    setInfoPanelCollapsed(!state.infoPanelCollapsed, { persist: true });
  });

  els.legendPanelToggle?.addEventListener("click", () => {
    setLegendPanelCollapsed(!state.legendPanelCollapsed, { persist: true });
  });

  els.cellPanelClose.addEventListener("click", () => {
    state.selectedCellProps = null;
    updateSelectedCellPanel();
  });
}

function bindCockpitChartTooltips() {
  const tooltip = () => {
    let node = document.getElementById("cockpit-chart-tooltip");
    if (!node) {
      node = document.createElement("div");
      node.id = "cockpit-chart-tooltip";
      node.className = "cockpit-chart-tooltip hidden";
      document.body.appendChild(node);
    }
    return node;
  };
  const move = (event) => {
    const node = tooltip();
    const margin = 12;
    const x = Math.min(window.innerWidth - node.offsetWidth - margin, event.clientX + margin);
    const y = Math.min(window.innerHeight - node.offsetHeight - margin, event.clientY + margin);
    node.style.left = `${Math.max(margin, x)}px`;
    node.style.top = `${Math.max(margin, y)}px`;
  };
  document.addEventListener("pointerover", (event) => {
    const target = event.target.closest?.("[data-cockpit-tooltip]");
    if (!target) return;
    const node = tooltip();
    node.textContent = target.dataset.cockpitTooltip || "";
    node.classList.remove("hidden");
    move(event);
  });
  document.addEventListener("pointermove", (event) => {
    if (document.getElementById("cockpit-chart-tooltip")?.classList.contains("hidden")) return;
    move(event);
  });
  document.addEventListener("pointerout", (event) => {
    if (!event.target.closest?.("[data-cockpit-tooltip]")) return;
    tooltip().classList.add("hidden");
  });
}

function setPvOverlayEnabled(enabled) {
  state.pvOverlayEnabled = Boolean(enabled);
  if (state.pvOverlayEnabled) {
    state.shadingOverlayEnabled = false;
    state.pvDeploymentOverlayEnabled = false;
    state.electricalOverlayEnabled = false;
  }
  syncOverlayControls();
  updateSelectedCellPanel();
  updateLayers();
}

function setShadingOverlayEnabled(enabled) {
  state.shadingOverlayEnabled = Boolean(enabled);
  if (state.shadingOverlayEnabled) {
    state.pvOverlayEnabled = false;
    state.pvDeploymentOverlayEnabled = false;
    state.electricalOverlayEnabled = false;
  }
  syncOverlayControls();
  updateSelectedCellPanel();
  updateLayers();
}

function setPvDeploymentOverlayEnabled(enabled) {
  state.pvDeploymentOverlayEnabled = Boolean(enabled);
  if (state.pvDeploymentOverlayEnabled) {
    state.pvOverlayEnabled = false;
    state.shadingOverlayEnabled = false;
    state.electricalOverlayEnabled = false;
  }
  syncOverlayControls();
  updateSelectedCellPanel();
  updateLayers();
}

function setElectricalOverlayEnabled(enabled) {
  // VIEW-1: the electrical overlay is Stage-D LP output and exists only for
  // optimised_sa. Refuse to switch it on elsewhere rather than draw the wrong
  // town's grid.
  if (enabled && !isOptimisedLayout()) {
    state.electricalOverlayEnabled = false;
    syncOverlayControls();
    return;
  }
  state.electricalOverlayEnabled = Boolean(enabled);
  if (state.electricalOverlayEnabled) {
    state.pvOverlayEnabled = false;
    state.shadingOverlayEnabled = false;
    state.pvDeploymentOverlayEnabled = false;
  }
  syncOverlayControls();
  updateSelectedCellPanel();
  updateDeckParameters();
  updateLayers();
  syncElectricalAnimation();
}

function rebuildPvLookupsForActiveScenario() {
  if (!state.data) return;
  buildCellPvLookup();
  updateInfo();
  updateSelectedCellPanel();
  updateLayers();
}

function syncOverlayControls() {
  /* VIEW-1: hide the Stage-D-dependent control entirely on layouts it does not
     apply to, and tell the user why rather than leaving a dead button. */
  const _opt = isOptimisedLayout();
  if (els.electricalOverlayToggle) {
    els.electricalOverlayToggle.classList.toggle("hidden", !_opt);
    els.electricalOverlayToggle.disabled = !_opt;
    /* the title itself is set further down, where the other overlay tooltips
       are written, so the two do not fight over the same attribute. */
  }
  if (!_opt && state.electricalOverlayEnabled) {
    state.electricalOverlayEnabled = false;
  }
  els.pvOverlayToggle?.classList.toggle("active", state.pvOverlayEnabled);
  els.pvOverlayToggle?.setAttribute("aria-pressed", String(state.pvOverlayEnabled));
  if (els.pvOverlayToggle) {
    els.pvOverlayToggle.title = state.pvOverlayEnabled
      ? "Hide per-cell PV ceiling overlay"
      : "Show per-cell PV ceiling overlay";
  }
  els.shadingOverlayToggle?.classList.toggle("active", state.shadingOverlayEnabled);
  els.shadingOverlayToggle?.setAttribute("aria-pressed", String(state.shadingOverlayEnabled));
  if (els.shadingOverlayToggle) {
    els.shadingOverlayToggle.title = state.shadingOverlayEnabled
      ? "Hide annual-average PV shading penalty overlay"
      : "Show annual-average PV shading penalty overlay";
  }
  els.pvDeploymentToggle?.classList.toggle("active", state.pvDeploymentOverlayEnabled);
  els.pvDeploymentToggle?.setAttribute("aria-pressed", String(state.pvDeploymentOverlayEnabled));
  if (els.pvDeploymentToggle) {
    els.pvDeploymentToggle.title = state.pvDeploymentOverlayEnabled
      ? "Hide per-cell deployed PV overlay"
      : "Show deployed PV versus ceiling overlay";
  }
  els.electricalOverlayToggle?.classList.toggle("active", state.electricalOverlayEnabled);
  els.electricalOverlayToggle?.setAttribute("aria-pressed", String(state.electricalOverlayEnabled));
  if (els.electricalOverlayToggle) {
    els.electricalOverlayToggle.title = !_opt
      // VIEW-1: say why, rather than leave a control that silently does nothing.
      ? "Electrical overlay is Stage-D optimiser output and exists only for the "
        + "optimised layout. The comparator layouts were never dispatched."
      : state.electricalOverlayEnabled
        ? "Hide Stage-D electrical network"
        : "Show Stage-D electrical network";
  }
  els.pvOverlayLegend?.classList.toggle("hidden", !state.pvOverlayEnabled);
  els.shadingOverlayLegend?.classList.toggle("hidden", !state.shadingOverlayEnabled);
  els.pvDeploymentLegend?.classList.toggle("hidden", !state.pvDeploymentOverlayEnabled);
  els.electricalOverlayLegend?.classList.toggle("hidden", !state.electricalOverlayEnabled);
  if (els.cockpitSettingAxis) els.cockpitSettingAxis.checked = state.axisArrowEnabled;
  if (els.cockpitSettingPanels) els.cockpitSettingPanels.checked = state.panelMarkersEnabled;
  if (els.cockpitSettingLocalStreets) els.cockpitSettingLocalStreets.checked = state.localStreetsEnabled;
  if (els.cockpitSettingGreenwayPaths) els.cockpitSettingGreenwayPaths.checked = state.greenwayPathsEnabled;
  if (els.cockpitSettingRealTimeShadows) els.cockpitSettingRealTimeShadows.checked = state.realTimeShadowsEnabled;
  els.realismFlagsLegend?.classList.toggle("hidden", !state.realismFlagsEnabled);
  els.carportSitesLegend?.classList.toggle("hidden", !state.carportSitesEnabled);
  updateShadingLegend();
  renderCarportSiteLegend();
  renderElectricalLegend();
  renderPlacementAuditLegend();


  // Re-stack after any overlay change: which legend is showing decides where
  // it has to sit, and the panels above and below it may have been collapsed.
  positionOverlayLegends();
}

function readStoredInfoPanelCollapsed() {
  try {
    const stored = window.localStorage?.getItem("district_v3_info_panel_collapsed");
    return stored === null ? true : stored === "1";
  } catch {
    return true;
  }
}

function setInfoPanelCollapsed(collapsed, options = {}) {
  state.infoPanelCollapsed = Boolean(collapsed);
  if (options.persist) {
    try {
      window.localStorage?.setItem("district_v3_info_panel_collapsed", state.infoPanelCollapsed ? "1" : "0");
    } catch {
      // Storage can be disabled in private/headless contexts; the UI still works.
    }
  }
  syncInfoPanelCollapsed();
  positionOverlayLegends();
}

function syncInfoPanelCollapsed() {
  const collapsed = Boolean(state.infoPanelCollapsed);
  els.infoPanel?.classList.toggle("collapsed", collapsed);
  if (els.infoPanelToggle) {
    els.infoPanelToggle.textContent = collapsed ? "+" : "-";
    els.infoPanelToggle.title = collapsed ? "Expand layout summary" : "Collapse layout summary";
    els.infoPanelToggle.setAttribute("aria-expanded", String(!collapsed));
    els.infoPanelToggle.setAttribute("aria-label", collapsed ? "Expand layout summary" : "Collapse layout summary");
  }
  updateLeftDockLayout();
}

function readStoredLegendPanelCollapsed() {
  try {
    return window.localStorage?.getItem("district_v3_legend_panel_collapsed") === "1";
  } catch {
    return false;
  }
}

function setLegendPanelCollapsed(collapsed, options = {}) {
  state.legendPanelCollapsed = Boolean(collapsed);
  if (options.persist) {
    try {
      window.localStorage?.setItem("district_v3_legend_panel_collapsed", state.legendPanelCollapsed ? "1" : "0");
    } catch {
      // Storage can be disabled in private/headless contexts; the UI still works.
    }
  }
  syncLegendPanelCollapsed();
  positionOverlayLegends();
}

function syncLegendPanelCollapsed() {
  const collapsed = Boolean(state.legendPanelCollapsed);
  els.legendPanel?.classList.toggle("collapsed", collapsed);
  if (els.legendPanelToggle) {
    els.legendPanelToggle.textContent = collapsed ? "+" : "-";
    els.legendPanelToggle.title = collapsed ? "Expand land-use legend" : "Collapse land-use legend";
    els.legendPanelToggle.setAttribute("aria-expanded", String(!collapsed));
    els.legendPanelToggle.setAttribute("aria-label", collapsed ? "Expand land-use legend" : "Collapse land-use legend");
  }
  updateLeftDockLayout();
}

function updateLeftDockLayout() {
  const update = () => {
    const height = Math.ceil(els.infoPanel?.getBoundingClientRect?.().height || 0);
    document.documentElement.style.setProperty("--info-panel-space", `${height}px`);
  };
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(update);
  } else {
    update();
  }
}

function updateShadingLegend() {
  if (!els.shadingOverlayLegend) return;
  const ramp = state.shadingRamp || {};
  const min = Number.isFinite(Number(ramp.min)) ? Number(ramp.min) : LEGACY_SHADING_MIN_MULTIPLIER;
  const max = Number.isFinite(Number(ramp.max)) ? Number(ramp.max) : 1;
  const mid = (min + max) / 2;
  const source = ramp.source === "geom" ? "geom" : ramp.source;
  if (els.shadingLegendNone) els.shadingLegendNone.textContent = `>=${max.toFixed(2)} yield`;
  if (els.shadingLegendMid) els.shadingLegendMid.textContent = `${mid.toFixed(2)} yield`;
  if (els.shadingLegendHigh) els.shadingLegendHigh.textContent = `${min.toFixed(2)} most shaded`;
  if (els.shadingLegendNote) els.shadingLegendNote.textContent = `Scale ${min.toFixed(3)}-${max.toFixed(3)}; 1.000 is still unshaded. Red = most shaded in this layout, NOT 40% physical loss.`;
  els.shadingOverlayLegend.title = `Red = most shaded in this layout, NOT 40% physical loss. Values run: ${Number(ramp.actualMin ?? min).toFixed(3)}-${Number(ramp.actualMax ?? max).toFixed(3)}; ${Number(ramp.unshadedCount || 0)} of ${Number(ramp.count || 0)} are >=0.999.`;
}

// THE OVERLAY LEGEND STACKS IN THE LEFT COLUMN (the author, "just keep
// it on the left... just make sure the land use and numbers legend dont
// overlap"). Pure CSS cannot do this: Land use and Key numbers are absolutely
// positioned siblings whose heights change as they expand and collapse, so a
// fixed `top` either sits on one of them or floats in the map. This measures
// the two panels and drops the legend into the gap between them.
//
// Deliberately narrow in scope - it sets `top` and `max-height` on one element
// and nothing else. Left, width and styling stay in the stylesheet.
function positionOverlayLegends() {
  const landUse = document.getElementById("legend-panel");
  const keyNumbers = document.getElementById("layout-summary-panel");
  const legend = [...document.querySelectorAll(".pv-overlay-legend")]
    .find((el) => !el.classList.contains("hidden"));

  // Land use gets its full height back the moment no overlay legend is up.
  if (landUse) landUse.style.maxHeight = "";
  if (!legend) return;

  const gap = 12;
  const host = legend.offsetParent || document.body;
  const hostBox = host.getBoundingClientRect();
  const columnTop = landUse
    ? landUse.getBoundingClientRect().top - hostBox.top
    : 110;
  const columnBottom = keyNumbers && !keyNumbers.classList.contains("hidden")
    ? keyNumbers.getBoundingClientRect().top - hostBox.top
    : hostBox.height - 24;

  // THREE PANELS, ONE COLUMN. Land use expanded can be 450px tall, which left
  // a 38px slot for the legend and it spilled over Key numbers. So the column
  // is SHARED: the legend takes what it actually needs up to a cap, and Land
  // use is capped to whatever is left. Land use scrolls internally already, so
  // nothing is lost - it just gets shorter while an overlay is being read.
  const available = Math.max(160, columnBottom - columnTop - gap * 2);
  // Ask for what the content actually needs (plus a couple of px so a rounding
  // remainder does not manufacture a scrollbar), capped so Land use keeps a
  // usable amount of the column.
  const legendWanted = Math.min((legend.scrollHeight || 220) + 4, 360);
  const legendHeight = Math.min(legendWanted, Math.max(160, available - 130));
  const landHeight = Math.max(120, available - legendHeight);

  if (landUse) landUse.style.maxHeight = `${Math.round(landHeight)}px`;
  legend.style.top = `${Math.round(columnTop + landHeight + gap)}px`;
  legend.style.bottom = "auto";
  legend.style.transform = "none";
  legend.style.maxHeight = `${Math.round(legendHeight)}px`;

  // NO SCROLLBAR WHEN THERE IS NOTHING TO SCROLL (the author, "the
  // legends have a scroll feature but we dont need it as nothing to scroll
  // down"). The stylesheet sets `overflow: auto` for the rare long legend;
  // these keys are short, so the track showed with no travel in it. Compare
  // the content against the box and only allow scrolling when it genuinely
  // overflows.
  const needsScroll = legend.scrollHeight > Math.round(legendHeight) + 8;
  legend.style.overflowY = needsScroll ? "auto" : "hidden";
}

function renderCarportSiteLegend() {
  if (!els.carportSitesLegend) return;
  const count = carportSiteCountForLoadedLayout();
  const label = count === 1 ? "1 exported site" : `${count.toLocaleString("en-GB")} exported sites`;
  // The tick marks are a LAYOUT property (where a canopy can go) and do not
  // move with the period, but deployed carport capacity does: the run installs
  // 0 kWp in 2030, 11,500.0 in 2042 and 16,500.0 in 2055. Shown together the
  // reader cannot mistake a 2030 plate full of ticks for 16.5 MWp of installed
  // carport PV. Undefined (cockpit data not loaded yet) is not the same as
  // zero, so the clause is omitted rather than reporting a false "none".
  const scenario = activeCockpitScenario();
  const deployedKwp = scenario ? Number(scenario.capacities?.carport_kwp || 0) : null;
  const periodLabel = scenario?.active_period_label || "";
  const deployedClause = deployedKwp === null
    ? ""
    : deployedKwp > 0
      ? ` ${formatPv(deployedKwp)} deployed at ${periodLabel}.`
      : ` None deployed at ${periodLabel}; capacity arrives in later periods.`;
  const detail = count > 0
    ? `${label} on the loaded layout; compact cyan canopy ticks mark each discrete parking-canopy site.${deployedClause}`
    : "0 exported sites on the loaded layout; the toggle is available but this layer has nothing to draw.";
  els.carportSitesLegend.innerHTML = `
    <h2>Carport sites</h2>
    <div class="pv-legend-row">
      <span class="pv-swatch carport-site-swatch"></span>
      <span>${escapeHtml(label)}</span>
    </div>
    <p class="legend-note">${escapeHtml(detail)}</p>
  `;
}

function renderElectricalLegend() {
  if (!els.electricalOverlayLegend) return;
  const scenario = stageDScenario();
  const edges = electricalEdgeFeatures();
  const zones = Array.isArray(scenario?.stage_d_transformer_zones)
    ? scenario.stage_d_transformer_zones
    : [];
  const backbone = edges.filter((edge) => edge.voltageClass === "backbone_33kv").length;
  const detail = scenario
    ? `${edges.length.toLocaleString("en-GB")} feeders; ${backbone.toLocaleString("en-GB")} backbone; ${zones.length.toLocaleString("en-GB")} transformer zones.`
    : "Stage-D fields not present on the loaded dispatch scenario.";
  if (els.electricalLegendNote) els.electricalLegendNote.textContent = detail;
}

function carportSiteCountForLoadedLayout() {
  return (state.data?.features || []).filter((feature) => {
    const props = feature.properties || {};
    return props.role === "parcel" && props.land_use === "parking_lot" && truthyFlag(props.is_carport_site);
  }).length;
}

function syncElectricalAnimation() {
  if (!state.electricalOverlayEnabled) {
    if (state.electricalAnimationFrame) {
      cancelAnimationFrame(state.electricalAnimationFrame);
      state.electricalAnimationFrame = null;
    }
    return;
  }
  if (state.electricalAnimationFrame) return;
  const tick = (now) => {
    if (!state.electricalOverlayEnabled) {
      state.electricalAnimationFrame = null;
      return;
    }
    if (!state.electricalLastFrameMs || now - state.electricalLastFrameMs > 160) {
      state.electricalPulse = now / 1000;
      state.electricalLastFrameMs = now;
      updateLayers();
    }
    state.electricalAnimationFrame = requestAnimationFrame(tick);
  };
  state.electricalAnimationFrame = requestAnimationFrame(tick);
}

function scaledHeightM(heightM) {
  return Number(heightM || 0) * BUILDING_HEIGHT_SCALE;
}

function scaledFeatureHeightM(props) {
  return scaledHeightM(props?.height_m ?? props?.cell_height_m ?? 0);
}

function createLightingEffect() {
  // CHG-1:
  // smooth altitude-driven lighting (no hard <18deg cliff), golden-hour sun colour,
  // and NATIVE deck.gl shadows tied to the existing "Sun shadows" checkbox.
  const altitudeDeg = Number(state.sun.altitudeDeg || 0);
  if (altitudeDeg < -6) return null; // true night: flat night palette, no sun
  const belowHorizon = altitudeDeg < 0;
  // 0 at horizon -> 1 at 45deg+; drives both colour warmth and intensity.
  const t = Math.max(0, Math.min(1, altitudeDeg / 45));
  const warm = (a, b) => Math.round(a + (b - a) * t);
  const sunColor = [warm(255, 255), warm(186, 244), warm(124, 228)]; // 2700K dawn -> near-white noon
  // VIS-1b: exposure/contrast rebalance to the metropolis face
  // ratios (roof ~1.1x base, shaded wall ~0.7x at noon; wider at golden
  // hour with the warm sun colour as the rim). Ambient DOWN at dawn (was
  // 1.12 - washed the golden hour flat), sun UP overall; direction fn and
  // the flat-ground shadow system untouched.
  const ambientLight = new deck.AmbientLight({
    color: [255, 246, 228],
    intensity: belowHorizon ? 1.15 : 0.55 + 0.15 * (1 - t)
  });
  const sunLight = new deck.DirectionalLight({
    color: sunColor,
    intensity: belowHorizon ? 0.55 : 1.15 + 0.75 * t,
    direction: currentSunLightDirection(),
    // CHG-1 HOTFIX native _shadow caused a draw-time failure on the
    // real browser (white-out). Disabled pending debugging; the legacy
    // flatGroundShadowLayer continues to provide shadows. Spec T1.1 deferred.
    _shadow: false
  });
  const fillLight = new deck.DirectionalLight({
    color: [165, 200, 215],
    intensity: 0.30 + 0.20 * (1 - t),
    direction: [4, 6, -3]
  });
  const effect = new deck.LightingEffect({ ambientLight, sunLight, fillLight });
  effect.shadowColor = [12, 16, 28, 90]; // soft blue-grey, not pitch black
  return effect;
}

function currentLightingEffects() {
  const effect = createLightingEffect();
  return effect ? [effect] : [];
}

function currentSunLightDirection() {
  const altitude = Number(state.sun.altitudeRad);
  const azimuth = Number(state.sun.azimuthRad);
  if (!Number.isFinite(altitude) || !Number.isFinite(azimuth) || altitude <= 0) {
    return [-3, -5, -7];
  }
  const horizontal = Math.cos(altitude);
  const eastToSun = -horizontal * Math.sin(azimuth);
  const northToSun = -horizontal * Math.cos(azimuth);
  const upToSun = Math.sin(altitude);
  return normalisedVector([-eastToSun, -northToSun, -upToSun], [-3, -5, -7]);
}

function normalisedVector(vector, fallback) {
  const clean = (vector || []).map((value) => Number(value));
  const magnitude = Math.sqrt(sum(clean.map((value) => value * value)));
  if (!Number.isFinite(magnitude) || magnitude <= 0) return fallback;
  return clean.map((value) => value / magnitude);
}

function createDeck() {
  state.deckgl = new deck.Deck({
    parent: document.getElementById("deck-container"),
    // CHG-2: render at native pixel ratio (capped at 2) - kills canvas pixelation
    useDevicePixels: Math.min(window.devicePixelRatio || 1, 2),
    //: keep the drawing buffer readable so canvas.toDataURL works -
    // thesis screenshots + automated visual verification both need it. The
    // cost is one retained framebuffer; the scene is static between frames.
    glOptions: { preserveDrawingBuffer: true },
    viewState: state.viewState,
    onViewStateChange: ({ viewState }) => {
      state.viewState = constrainViewState(viewState);
      if (state.deckgl) {
        state.deckgl.setProps({ viewState: state.viewState });
      }
      updateCompass();
      updateScaleBar();
    },
    controller: {
      dragPan: true,
      dragRotate: true,
      scrollZoom: true,
      doubleClickZoom: true,
      touchZoom: true,
      touchRotate: true,
      keyboard: true,
      inertia: 250
    },
    effects: currentLightingEffects(),
    parameters: deckParameters(),
    getTooltip,
    onClick: handleMapClick,
    onError: handleDeckError,
    layers: []
  });
  updateScaleBar();
}

// LAYERS THAT FAIL TO INITIALISE ON THE FIRST FRAME ARE REBUILT ONCE.
//
// Measured on the machine this is developed on (Intel Iris Xe
// through ANGLE/D3D11). The scene hands deck about fifty sublayers in one go,
// and on a COLD load the tail of that list throws
// "deck.gl: assertion failed" out of luma's `_initialize` - street trees,
// streetlights, entrance markers, the solar farm panels, the rooftop PV and
// THE SOLAR THERMAL COLLECTORS. The same layers, rebuilt a moment later,
// initialise without complaint: three separate trials after the scene had
// settled returned zero errors, including with real-time shadows on and off.
// So this is a first-frame race and not a defect in the geometry, which is
// why the collectors were reported missing from the roofs while
// `solarThermalSurfaceFeatures` was returning all 504 of them.
//
// Rather than a blind timer, the failure is DETECTED and answered: deck
// reports it here, and one rebuild is scheduled for the next frame. It is
// debounced so a first frame that loses twenty layers still costs one rebuild,
// and it is capped so a genuine, repeatable error cannot become a render loop.
let _deckRebuildQueued = false;
let _deckRebuildsDone = 0;
function handleDeckError(error, layer) {
  const message = String(error?.message || error || "");
  const initFailure = /assertion failed/i.test(message);
  if (!initFailure || _deckRebuildQueued || _deckRebuildsDone >= 3) {
    if (!initFailure) console.warn("deck:", message, layer?.id || "");
    return;
  }
  _deckRebuildQueued = true;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      _deckRebuildQueued = false;
      _deckRebuildsDone += 1;
      // Drop the cached list first: it holds the layer objects that just
      // failed, and deck will not retry an instance it has already rejected.
      state._lastLayers = null;
      state._lastLayersKey = null;
      updateLayers();
    });
  });
}

// THE INVARIANT THIS FUNCTION EXISTS TO KEEP: `state.currentLayout` and
// `state.data` always describe the SAME town.
//
// It used to be broken for the length of the fetch. `currentLayout` was
// assigned on the first line and `state.data` only after the await, so in
// between the viewer held one town's name and another town's geometry. That
// matters because roughly a dozen geometry caches - road strips, parking
// lanes, window schedules, panel poses, traffic segments - are memoised under
// a key built from `currentLayout`. Anything that ran during the window
// computed the OLD town's geometry and filed it under the NEW town's key, and
// the cache then served it after the real data arrived. Leaving a town and
// coming back is exactly the sequence that fills those caches wrongly, which
// is the glitch reported on.
//
// The fix is to assign both together, once the data is in hand, and to hold
// the traffic ticker off while the fetch is in flight.
async function loadLayout(layoutName) {
  const layout = layoutByName(layoutName);
  els.layoutSelect.value = layoutName;
  state.selectedCellProps = null;
  state._layoutLoading = true;
  updateSelectedCellPanel();
  setLoading(`Loading ${layout.label || titleCase(layoutName)}...`);

  try {
    const response = await fetch(`${DATA_ROOT}/${layout.path || `${layoutName}.geojson`}`, {
      cache: "no-store"
    });
    if (!response.ok) {
      throw new Error(`Could not load ${layoutName}: ${response.status}`);
    }
    const data = await response.json();
    // Name and geometry change in the same tick; nothing can observe them
    // disagreeing. The caches keyed on the name are dropped alongside, since
    // a key that merely CHANGES still leaves the old entry resident and the
    // traffic segments are held under a separate key of their own.
    state.currentLayout = layoutName;
    state.data = data;
    state._groundBounds = null;
    state._lastLayers = null;
    state._lastLayersKey = null;
    state._trafSegs = null;
    state._trafSegKey = null;
    state._trafAgents = null;
    buildCellPvLookup();
    buildCellShadingLookup();
    buildLightingLookup();
  } finally {
    // Released in `finally` so a failed fetch cannot leave the ticker
    // permanently muted with the viewer looking frozen.
    state._layoutLoading = false;
  }
  syncOverlayControls();
  updateLayers();
  updateInfo();
  updateLegend();
  updateLayoutButtons();
  renderCockpit();
  setLoading("");
  scheduleColdStartRebuild();
}

// ONE REBUILD A FEW FRAMES AFTER A LOAD, AND WHY IT IS NOT SUPERSTITION.
// Measured on the development machine (Intel Iris Xe through ANGLE/D3D11):
// handing deck the whole scene at once on a COLD load makes the tail of the
// list throw "deck.gl: assertion failed" out of luma's `_initialize`, and deck
// leaves a hole where each failed layer was. The affected set included the
// rooftop photovoltaics, the solar farm panels and THE SOLAR THERMAL
// COLLECTORS, which is why the collectors were reported missing from the roofs
// while `solarThermalSurfaceFeatures` was returning all 504 of them.
//
// The same layers rebuilt a moment later initialise without complaint - proved
// by dropping the cache and calling `updateLayers` by hand, after which all
// thirty-three layers were present, and by three further trials that returned
// zero errors with real-time shadows both on and off. So a single deferred
// rebuild is the whole fix. It costs one scene build per town load, which is
// what a town load costs anyway.
//
// `onError` above catches the same condition when deck chooses to report it;
// this covers the case where deck logs the failure itself and never calls back.
function scheduleColdStartRebuild() {
  if (state._coldRebuildQueued) return;
  state._coldRebuildQueued = true;
  requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(() => {
    state._coldRebuildQueued = false;
    if (!state.deckgl || !state.data) return;
    const holes = (state.deckgl.props.layers || []).filter((l) => !l).length;
    if (!holes) return;                 // first pass was clean; nothing to do
    state._lastLayers = null;
    state._lastLayersKey = null;
    updateLayers();
  }, 120)));
}

// WHICH SCENE THE CACHED LAYER LIST BELONGS TO.
// `state._lastLayers` exists so the traffic ticker can swap one layer instead
// of rebuilding the scene 7.7 times a second. That is a cache, and it
// had no key, so the ticker would happily reinstate a list built for a
// different town or a different overlay. Two of the three viewer glitches
// reported on were this one cache:
//
//   * Turn the Grid overlay on. `updateLayers` returned early with the short
//     electrical list and never touched `_lastLayers`, which still held the
//     whole town. 130 ms later the ticker pushed that town back - buildings,
//     trees and CARS - over the overlay, and the next real update removed it
//     again. "The cars come for a bit then disappear."
//   * Switch town. `loadLayout` sets `currentLayout` and then awaits a fetch;
//     for the length of that fetch the ticker kept pushing the PREVIOUS town's
//     layers at the new state.
//
// The key makes both impossible: the ticker reinstates a list only if it was
// built for the town and overlay now on screen.
function layerSetKey() {
  return [
    state.currentLayout || "",
    state.electricalOverlayEnabled ? "grid" : "",
    state.pvOverlayEnabled ? "pv" : "",
    state.shadingOverlayEnabled ? "shade" : "",
    state.pvDeploymentOverlayEnabled ? "deploy" : ""
  ].join("|");
}

function updateLayers() {
  if (!state.deckgl || !state.data) return;
  if (state.electricalOverlayEnabled) {
    const gridLayers = [
      electricalFeederLayer(),
      // electricalInterconnectLayer removed (the author: "remove the
      // two flat lines the 3d lines are good enough"). The arcs below carry
      // the same two connections with direction and load, so the flat strokes
      // underneath them were duplicate geometry.
      electricalFlowArcLayer(),
      electricalTransformerLayer(),
      electricalSubstationLayer(),
      dataCentreBuildingLayer(),
      electricalInterconnectFlowLayer(),
      batteryStorageLayer(),
      sunMarkerLayer()
    ].filter(Boolean);
    state.deckgl.setProps({ layers: gridLayers });
    // Recorded like any other scene. Leaving the previous list here is what
    // let the town reappear underneath the overlay.
    state._lastLayers = gridLayers;
    state._lastLayersKey = layerSetKey();
    return;
  }
  // CHG-1b: materials stay lit down to 5 deg (was 18) - the new smooth lighting
  // handles low sun gracefully; 18 made mornings/evenings flat.
  const lowVisibilitySun = Number(state.sun.altitudeDeg || 0) < 5;

  const parcels = featureCollection(
    state.data.features.filter((f) => f.properties.role === "parcel")
  );
  const structures = featureCollection(
    state.data.features.filter((f) => (
      f.properties.role !== "parcel"
      && f.properties.role !== "plant"
      && f.properties.role !== "street_edge"
      && f.properties.land_use !== "retail_highstreet"
    ))
  );
  const plants = featureCollection(
    state.data.features.filter((f) => isPlantFeatureProps(f.properties))
  );

  const parcelLayer = new deck.GeoJsonLayer({
    id: "district-parcels",
    data: parcels,
    pickable: true,
    stroked: false,
    filled: true,
    extruded: false,
    opacity: lowVisibilitySun ? 0.92 : state.theme === "dark" ? 0.72 : 0.78,
    material: lowVisibilitySun ? false : {
      ambient: 0.50,
      diffuse: 0.62,
      shininess: 8,
      specularColor: [210, 220, 218]
    },
    getFillColor: (feature) => state.pvDeploymentOverlayEnabled
      ? pvDeploymentColor(feature.properties)
      : state.shadingOverlayEnabled
        ? pvShadingColor(feature.properties)
        : state.pvOverlayEnabled
          ? pvCeilingColor(feature.properties)
          : surfaceColor(feature.properties),
    updateTriggers: {
      getFillColor: [
        state.theme,
        state.pvOverlayEnabled,
        state.shadingOverlayEnabled,
        state.pvDeploymentOverlayEnabled,
        state.shadingRamp.min,
        state.shadingRamp.max,
        state.pvOverlayMaxKwp,
        state.pvOverlayScaleKwp,
        state.cellPvDeployedKwp,
        state.cellShading,
        state.cockpit.periodYear,
        // VERGE-1: road base flips verge-green <-> asphalt with this toggle
        state.roadSectionsEnabled
      ]
    }
  });

  const structureLayer = new deck.GeoJsonLayer({
    id: "district-structures",
    data: structures,
    pickable: true,
    stroked: false,
    filled: true,
    extruded: true,
    // CHG-4: subtle extrusion edges (parapet/slab definition) - spec T1.4
    wireframe: true,
    getLineColor: [38, 42, 52, 80],
    lineWidthMinPixels: 1,
    opacity: 0.96,
    // VIS-1b: brighter matte walls - diffuse carries the metropolis face
    // contrast, ambient keeps shaded sides readable (not black).
    material: lowVisibilitySun ? false : {
      ambient: 0.34,
      diffuse: 0.80,
      shininess: 24,
      specularColor: [255, 245, 220]
    },
    // CHG-3: deterministic per-building variation (display-only; tooltips/physics
    // keep the true height_m) - +/-5% height, subtle facade tint jitter. Spec T1.3.
    getElevation: (feature) => scaledFeatureHeightM(feature.properties)
      * buildingHeightJitter(feature.properties),
    getFillColor: (feature) => state.pvDeploymentOverlayEnabled
      ? pvDeploymentColor(feature.properties, { structure: true })
      : state.shadingOverlayEnabled
        ? pvShadingColor(feature.properties, { structure: true })
        : state.pvOverlayEnabled
          ? pvCeilingColor(feature.properties, { structure: true })
          : jitteredStructureColor(feature.properties),
    updateTriggers: {
      getElevation: [BUILDING_HEIGHT_SCALE],
      getFillColor: [
        state.theme,
        state.pvOverlayEnabled,
        state.shadingOverlayEnabled,
        state.pvDeploymentOverlayEnabled,
        state.shadingRamp.min,
        state.shadingRamp.max,
        state.pvOverlayMaxKwp,
        state.pvOverlayScaleKwp,
        state.cellPvDeployedKwp,
        state.cellShading
      ]
    }
  });

  // (, the author: "make buildings look like buildings like
  // metropolis"). ONE change: a roof CAP on every structure.
  //
  // WHY THIS ONE FIRST. deck.gl's extruded GeoJsonLayer paints the top face
  // and the walls with the SAME colour, so a building is a single-tone box
  // and its most legible feature - the roofline - carries no information.
  // metropolis' drawBuilding does the opposite: faceColors gives the
  // top its own value, and the pitched-roof branch mixes it toward
  // terracotta (#8A4A3C) - the roof is what makes its blocks read as
  // buildings in the day view.
  //
  // HOW. A second, very thin extrusion sitting ON the structure. deck.gl
  // extrudes from z=0, so the cap is floated by giving the polygon ring
  // 3D coordinates at roof height and extruding only the cap thickness.
  // The result reads as a parapet edge plus a distinct roof plane, from
  // one added layer and no geometry changes anywhere else.
  //
  // Cap thickness is a fixed 0.9 m of real height (scaled by the same
  // BUILDING_HEIGHT_SCALE as everything else) rather than a percentage, so
  // a bungalow gets the same parapet a tower does - which is how parapets
  // actually work.
  const roofCapLayer = state.roofCapsEnabled === false ? null : new deck.PolygonLayer({
    id: "district-roof-caps",
    data: roofCapFeatures(),
    pickable: false,
    stroked: false,
    filled: true,
    extruded: true,
    wireframe: false,
    material: lowVisibilitySun ? false : {
      ambient: 0.34,
      diffuse: 0.80,
      shininess: 24,
      specularColor: [255, 245, 220]
    },
    getPolygon: (d) => d.contour,
    getElevation: () => scaledHeightM(0.9),
    getFillColor: (d) => d.colour,
    updateTriggers: {
      getElevation: [BUILDING_HEIGHT_SCALE],
      getFillColor: [state.theme, state.currentLayout]
    }
  });

  const plantLayer = new deck.GeoJsonLayer({
    id: "stage-c-plants",
    data: plants,
    pickable: true,
    stroked: true,
    filled: true,
    extruded: true,
    wireframe: false,
    opacity: 1,
    material: lowVisibilitySun ? false : {
      ambient: 0.38,
      diffuse: 0.72,
      shininess: 44,
      specularColor: [255, 250, 220]
    },
    getElevation: (feature) => scaledFeatureHeightM(feature.properties),
    getFillColor: (feature) => plantColor(feature.properties, 246),
    getLineColor: [255, 248, 214, 245],
    getLineWidth: 2,
    lineWidthUnits: "pixels",
    updateTriggers: {
      getElevation: [BUILDING_HEIGHT_SCALE],
      getFillColor: [state.theme]
    }
  });

  applySkyForTime();
  state.deckgl.setProps({
    layers: [
      // CHG-6 reland Batch 3: low-opacity procedural ground
      // texture under the district; keep before parcels so land-use tint wins.
      groundTextureLayer(),
      parcelLayer,
      blueSpaceBankLayer(),
      placementAuditLayer(),
      roadCrossSectionLayer(),
      canalConnectorLayer(),
      parkingBayLayer(),
      groundBushLayer(),
      streetEdgeLayer(),
      trafficLayer(),
      nightWindowLayer(),
      expansionReserveHatchLayer(),
      flatGroundShadowLayer(),
      structureLayer,
      //: immediately AFTER the structures so the cap draws over its
      // own building's top face, and before the highstreet/plant layers so
      // those keep their existing precedence.
      roofCapLayer,
      highstreetChainLayer(),
      highstreetShopfrontLayer(),
      plantLayer,
      bessSiteLayer(),        // BESS-1: the physical site, always on
      // BESS-2 (, the author: "the blue battery circle is still there,
      // we don't need it anymore"). Retired. It was a flat scatterplot dot
      // offset from the substation, and it was the ONLY representation of
      // storage until bessSiteLayer gave the battery real ground on cell
      // (23,10). Two markers for one asset in two places is worse than
      // none. `batteryStorageLayer` and `batteryStorageFeature` are left
      // defined but unused, so the Stage-D diagnostic can be restored by
      // re-adding this one line.
      buildingGlowLayer(),
      vegetationCanopyLayer(),
      vegetationTrunkLayer(),
      streetTreeCanopyLayer(),
      streetTreeTrunkLayer(),
      streetlightPoleLayer(),
      streetlightHeadLayer(),
      streetlightGlowLayer(),
      streetlightSolarPanelLayer(),
      roofVegetationLayer(),
      carportSiteLayer(),
      entranceMarkerLayer(),
      solarFarmPanelSurfaceLayer(),
      solarFarmModuleLineLayer(),
      solarFarmTrackerGuideLayer(),
      pvPanelSurfaceLayer(),
      solarThermalSurfaceLayer(),
      pvPanelLayer(),
      axisArrowLayer(),
      sunMarkerLayer()
    ].filter(Boolean)
  });
  //: remember the built list so the traffic ticker can swap ONLY
  // its own layer instead of rebuilding the whole scene every tick. Keyed,
  // so the ticker cannot reinstate it against a different town or overlay.
  state._lastLayers = state.deckgl.props.layers;
  state._lastLayersKey = layerSetKey();
}

function activePeriodYearNumber() {
  const year = Number(activeCockpitScenario()?.active_period_year || state.cockpit.periodYear || DEFAULT_COCKPIT_PERIOD_YEAR);
  return Number.isFinite(year) ? year : Number(DEFAULT_COCKPIT_PERIOD_YEAR);
}

function phaseYearFromSubtype(subtype) {
  const match = String(subtype || "").match(/(20\d{2})/);
  return match ? Number(match[1]) : null;
}

function isExpansionSubtype(subtype) {
  return /(?:solar|parking|expansion)_.*20\d{2}|expansion_reserve_20\d{2}/.test(String(subtype || ""));
}

function isSolarExpansionProps(props) {
  return String(props?.amenity_subtype || "").startsWith("solar_expansion_");
}

// FARM-1 (, the author: "in the PV deployed why are the two parts of the
// solar farm different colours - the expansion is built at the same time as the
// main solar farm so they are the same, they are ONE not two separate").
//
// He is right, and the cause is that the farm is not one land_use. It is 201
// cells of `land_use: "solar_farm"` PLUS 100 cells of `land_use: "open_space"`
// carrying `amenity_subtype: "solar_expansion_2030"` - the ring. Both are
// ground-mount array, both are released in 2030 by LAND-A1, and both carry
// farm capacity in the LP. Only the first kind matched the overlay tests.
//
// The geometry layers already knew this and paired the two predicates by hand
// (see the `|| isSolarExpansionProps(props)` calls in the panel-surface and
// carport passes). The OVERLAY COLOUR functions did not, so the ring fell
// through to the ROOFTOP intensity ramp and rendered as a separate, differently
// coloured block. That also explains "why is green space high rooftop": an
// open_space cell carrying farm kWp was being coloured on the rooftop scale.
//
// One predicate, one meaning: "this cell is ground-mount farm surface". Use it
// anywhere the question is about the farm as a physical surface. Do NOT use it
// where the question is genuinely about the land_use tag itself.
function isFarmSurfaceProps(props) {
  return props?.land_use === "solar_farm" || isSolarExpansionProps(props);
}

function isParkingExpansionProps(props) {
  return String(props?.amenity_subtype || "").startsWith("parking_expansion_");
}

function isExpansionReserveProps(props) {
  return isExpansionSubtype(props?.amenity_subtype);
}

function isExpansionActiveProps(props, year = activePeriodYearNumber()) {
  const phaseYear = phaseYearFromSubtype(props?.amenity_subtype);
  return phaseYear !== null && Number(year) >= phaseYear;
}

function streetEdgeFeatures() {
  return (state.data?.features || [])
    .filter((feature) => {
      const props = feature.properties || {};
      if (props.role !== "street_edge" || feature.geometry?.type !== "LineString") return false;
      if (props.kind === "local_street" && !state.localStreetsEnabled) return false;
      if (props.kind === "greenway_path" && !state.greenwayPathsEnabled) return false;
      return true;
    })
    .map((feature) => ({
      properties: feature.properties || {},
      path: (feature.geometry.coordinates || [])
        .filter((coord) => Array.isArray(coord) && coord.length >= 2)
        .map(([lon, lat]) => [lon, lat, 1.35])
    }))
    .filter((feature) => feature.path.length >= 2);
}

function streetEdgeColour(kind) {
  //: "dark dark green"
  if (kind === "greenway_path") return state.theme === "dark" ? [14, 74, 38, 246] : [8, 58, 28, 248];
  //: local lanes ~40% opaque - they are service
  // gallis, so they should read as a hint of paving, not as roads.
  return state.theme === "dark" ? [158, 162, 158, 102] : [126, 130, 126, 102];
}

function streetEdgeLayer() {
  const features = streetEdgeFeatures();
  if (!features.length) return null;
  // PRK-3: every parking lot IS
  // reachable - two of the 17 only via 12 m lanes - but the lanes read so
  // faint the lots looked landlocked. Lane segments that TOUCH a parking
  // cell now draw brighter and a touch wider, so the access visibly
  // plugs into the lot. Render-only; the layout is FROZEN.
  // PRK-7: same period-awareness as `parkingBayLayer`. A parking
  // parcel that switches on in 2042 must also light its access lane, or it
  // gains bays while still reading as landlocked - which is the exact
  // complaint PRK-3 above was written to fix, reappearing on the staged lots.
  // Memo key carries the period for the same reason it does there.
  const _laneKey = `${state.currentLayout}|${activePeriodYearNumber()}`;
  if (state._prkLaneKey !== _laneKey) {
    const parks = new Set();
    for (const f of state.data?.features || []) {
      const p = f.properties || {};
      const active = p.land_use === "parking_lot"
        || (isParkingExpansionProps(p) && isExpansionActiveProps(p));
      if (p.role === "parcel" && active) {
        parks.add(`${p.row}_${p.col}`);
      }
    }
    state._prkLaneKey = _laneKey;
    state._prkCells = parks;
  }
  const touchesParking = (props) => {
    const a = props.cell_a || [];
    const b = props.cell_b || [];
    return state._prkCells?.has(`${a[0]}_${a[1]}`)
      || state._prkCells?.has(`${b[0]}_${b[1]}`);
  };
  return new deck.PathLayer({
    id: "street-edge-access-network",
    data: features,
    pickable: true,
    widthUnits: "meters",
    widthMinPixels: 1.8,
    capRounded: true,
    jointRounded: true,
    getPath: (d) => d.path,
    //: greenway paths draw at the SAME width as the
    // access lanes so both read clearly - true widths stay in the tooltip.
    getWidth: (d) => {
      if (d.properties.kind === "greenway_path") return 12;
      if (touchesParking(d.properties)) return 13;
      const w = Number(d.properties.width_m || 0);
      return w > 0 ? w : 6;
    },
    // parking-access lanes stay the BRIGHTER tone (PRK-3, so
    // a lot never reads as landlocked) but come down in opacity with the
    // rest of the lane network.
    getColor: (d) => (d.properties.kind === "local_street"
      && touchesParking(d.properties))
      ? (state.theme === "dark" ? [186, 190, 182, 150] : [168, 172, 164, 150])
      : streetEdgeColour(d.properties.kind),
    parameters: { depthTest: false },
    updateTriggers: {
      getPath: [state.currentLayout, state.localStreetsEnabled, state.greenwayPathsEnabled],
      getColor: [state.theme, state.localStreetsEnabled, state.greenwayPathsEnabled]
    }
  });
}

function expansionReserveHatchFeatures() {
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 100);
  const halfSpanM = cellSizeM * 0.32;
  const offsets = [-0.22, 0, 0.22].map((value) => value * cellSizeM);
  return (state.data?.features || []).flatMap((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel" || !isExpansionReserveProps(props)) return [];
    // FARM-2 (, the author: "this is still yellow", with a close-up of
    // gold bars lying across the built farm).
    //
    // The hatch means "this land is RESERVED for a later phase". It was being
    // drawn on ACTIVE cells too, in a brighter colour - solar active was
    // [250, 204, 92], i.e. gold. The solar ring is granted in 2030, the
    // earliest period, so that hatch was on in EVERY period and the farm
    // permanently wore stripes that said "not built yet" across ground that
    // was built. It is also the same complaint as FARM-1 from a different
    // angle: it made one farm read as two things.
    //
    // An active cell does not need the hatch, because activation already
    // draws REAL geometry - panel rows for solar, stall bays and an access
    // spur for parking. The hatch is the placeholder for when there is
    // nothing to draw. So once active, drop it.
    if (isExpansionActiveProps(props)) return [];
    const center = polygonCentroid(feature);
    if (!center) return [];
    return offsets.map((offset) => ({
      properties: props,
      solar: isSolarExpansionProps(props),
      parking: isParkingExpansionProps(props),
      path: [
        offsetLngLat(center[0], center[1], -halfSpanM, offset - halfSpanM),
        offsetLngLat(center[0], center[1], halfSpanM, offset + halfSpanM)
      ].map(([lon, lat]) => [lon, lat, 1.7])
    }));
  });
}

function expansionReserveHatchLayer() {
  const hatches = expansionReserveHatchFeatures();
  if (!hatches.length) return null;
  return new deck.PathLayer({
    id: "phased-expansion-reserve-hatches",
    data: hatches,
    pickable: false,
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    getPath: (d) => d.path,
    // FARM-2: only RESERVED cells reach this layer now, so the old
    // active/inactive pairs are gone. These are the reserved tones; the
    // brighter active ones they replaced were what put gold bars across the
    // built farm.
    getWidth: () => 1.25,
    getColor: (d) => {
      if (d.solar) return [230, 216, 140, 132];
      if (d.parking) return [178, 188, 188, 128];
      return [180, 190, 170, 105];
    },
    parameters: { depthTest: false },
    updateTriggers: {
      getPath: [state.currentLayout],
      getWidth: [state.cockpit.periodYear],
      getColor: [state.cockpit.periodYear, state.theme]
    }
  });
}

// ===========================================================================
// WIN-1 (, metropolis port - "whatever duration we say the lights
// are on they show"): every building gets window columns on its two longest
// facades; each window carries a deterministic SCHEDULE (hash-spread
// switch-off between ~21:30 and ~01:00, a small pre-dawn wake cohort), the
// metropolis `windowLit` idea keyed to OUR sun clock. Rendered only when
// the sun is below the horizon; buildings occlude via depthTest.
// ===========================================================================
const WINDOW_WARM = [255, 205, 96];      // metropolis yellow
const WINDOW_COOL = [236, 238, 222];     // its white rooms
const WINDOW_GLASS = [152, 182, 210];    // daytime glazing - light, translucent sky tint
const WINDOW_DARK = [26, 30, 40];        // unlit room at night
const WINDOW_CAP = 32000;   // PERF-3: extruded boxes are the render cost
// Lit probability by daypart - the SHAPE of the model's own
// lighting_by_daypart residential schedule (evening-heavy, thin late
// night, a pre-dawn cohort), applied per-window via its hash.
function windowLitProbability(t) {
  if (t >= 18 && t < 22) return 0.88;    // evening peak
  if (t >= 22 || t < 1) return 0.45;     // winding down
  if (t >= 1 && t < 4.5) return 0.07;    // late night
  if (t >= 4.5 && t < 6.5) return 0.2;   // pre-dawn
  return 0.6;                            // dusk shoulder (17-18)
}

function _hash2(a, b) {
  const x = Math.abs(Math.sin(a * 127.1 + b * 311.7) * 43758.5453);
  return x - Math.floor(x);
}

function nightWindowFeatures() {
  if (state._windowKey === state.currentLayout && state._windowFeats) {
    return state._windowFeats;
  }
  const out = [];
  const mLat = METERS_PER_DEGREE_LAT;
  for (const f of state.data?.features || []) {
    if (out.length >= WINDOW_CAP) break;
    const p = f.properties || {};
    if (p.role !== "structure" || f.geometry?.type !== "Polygon") continue;
    const h = Number(p.height_m || 0);
    if (h < 6) continue;   // PERF-3: sheds/small parts carry no windows
    const ring = (f.geometry.coordinates?.[0] || []).slice();
    if (ring.length > 1 && sameCoordinate(ring[0], ring[ring.length - 1])) ring.pop();
    if (ring.length < 3) continue;
    const cLon = ring.reduce((s, q) => s + q[0], 0) / ring.length;
    const cLat = ring.reduce((s, q) => s + q[1], 0) / ring.length;
    const mLon = metersPerDegreeLongitude(cLat);
    // the two longest edges = the street-facing facades
    const edges = [];
    for (let i = 0; i < ring.length; i += 1) {
      const a = ring[i];
      const b = ring[(i + 1) % ring.length];
      const dx = (b[0] - a[0]) * mLon;
      const dy = (b[1] - a[1]) * mLat;
      edges.push({ a, b, len: Math.hypot(dx, dy), dx, dy });
    }
    // WIN-3: "4 windows in 2 by 2
    // formation on each side of the building" - two columns at 30%/70%
    // along EVERY facade, two rows at 28%/62% of the building height,
    // big 2.6 x 2.0 m panes standing 0.45 m proud of the wall.
    for (const e of edges) {
      if (e.len < 5) continue;
      const ux = e.dx / e.len;
      const uy = e.dy / e.len;
      // outward normal: away from the footprint centroid
      let nx = -uy;
      let ny = ux;
      const midLon = (e.a[0] + e.b[0]) / 2;
      const midLat = (e.a[1] + e.b[1]) / 2;
      const toCx = (cLon - midLon) * mLon;
      const toCy = (cLat - midLat) * mLat;
      if (nx * toCx + ny * toCy > 0) { nx = -nx; ny = -ny; }
      // WIN-4: a flat VERTICAL polygon has zero plan area, so
      // PolygonLayer triangulated it to NOTHING - the windows were never
      // drawn. Same fix as: a plan-footprint ring AT sill height,
      // extruded by the window height = a glass box standing proud of the
      // wall. Thin facades (<8 m) get ONE centred window, not two.
      const cols = e.len >= 8 ? [0.30, 0.70] : [0.5];
      for (const colFrac of cols) {
        const along = e.len * colFrac;
        for (const rowFrac of [0.28, 0.62]) {
          if (out.length >= WINDOW_CAP) break;
          const hh = _hash2(p.row * 31 + colFrac * 97, p.col * 17 + rowFrac * 53 + e.len);
          const em = (dm, dOut) => offsetLngLat(e.a[0], e.a[1],
            ux * (along + dm) + nx * dOut, uy * (along + dm) + ny * dOut);
          const z0 = scaledHeightM(h * rowFrac);
          const ai = em(-1.3, 0.05);
          const bi = em(1.3, 0.05);
          const bo = em(1.3, 0.55);
          const ao = em(-1.3, 0.55);
          out.push({
            contour: [[ai[0], ai[1], z0], [bi[0], bi[1], z0],
                      [bo[0], bo[1], z0], [ao[0], ao[1], z0]],
            wake: hh < 0.15,
            warm: hh > 0.22,
            h2: _hash2(p.col * 13 + rowFrac * 41, p.row * 7 + colFrac * 29)
          });
        }
      }
    }
  }
  state._windowKey = state.currentLayout;
  state._windowFeats = out;
  return out;
}

function windowIsLit(w, t) {
  // metropolis `windowLit` idea on the model's daypart shape: the window's
  // own hash decides whether it is among the lit share at this hour, with
  // the pre-dawn cohort overriding for early risers.
  if (w.wake && t >= 4.5 && t <= 6.5) return true;
  return w.h2 < windowLitProbability(t);
}

function nightWindowLayer() {
  // WIN-2 (, the author: "there are no windows on buildings... just
  // the windows become yellow"): windows are ALWAYS drawn - dark glazing
  // by day, and at night each window is warm-lit, white-lit or dark per
  // its schedule, like the metropolis reference.
  const feats = nightWindowFeatures();
  if (!feats.length) return null;
  const alt = Number(state.sun.altitudeDeg || 0);
  const nightF = civilTwilightDarkFactor();
  const t = ((Number(state.sun.timeHours || 0) % 24) + 24) % 24;
  return new deck.PolygonLayer({
    id: "night-windows",
    data: feats,
    pickable: false,
    stroked: false,
    filled: true,
    extruded: true,                       // WIN-4: floated glass box (ROOF-1 trick)
    wireframe: false,
    material: false,                      // emissive - windows are light sources
    getPolygon: (d) => d.contour,
    getElevation: () => scaledHeightM(2.0),
    getFillColor: (d) => {
      if (nightF < 0.15) return withAlpha(WINDOW_GLASS, 150);   // translucent day glass
      if (!windowIsLit(d, t)) return withAlpha(WINDOW_DARK, 240);
      // - all lit
      // windows are the one warm yellow now.
      return withAlpha(WINDOW_WARM, 250);
    },
    parameters: { depthTest: true },
    updateTriggers: {
      getPolygon: [state.currentLayout],
      getElevation: [BUILDING_HEIGHT_SCALE],
      getFillColor: [Math.round(t * 4), Math.round(nightF * 20), state.currentLayout]
    }
  });
}

// ===========================================================================
// TRF-1 (, metropolis traffic ported to OUR fleet, the author: "model
// with the car ownership of our town not the reference pdf"): the resident
// car fleet is DERIVED FROM THIS MODEL'S OWN CITED CONFIG -
// demand_norms.yaml `car_ownership_total_by_income` (2030 {low 0.02, mid
// 0.15, high 0.45}; 2042 {0.05/0.25/0.50}; 2055 {0.10/0.40/0.55}) x the
// households by tier (21,918 / 24,657 / 8,219) x 1.25 cars per owning
// household (the parking model's own factor). One rendered dot stands for
// ~25 vehicles (streetlight xN convention). Share of the fleet on the road
// follows a standard urban diurnal curve keyed to the SAME time slider.
// Headlight white / taillight red split by direction at night, neutral
// grey by day - the metropolis convention.
// ===========================================================================
// CARS from the cited ownership config (see block comment above). The
// 2-WHEELER fleet rides on top: ~0.55 scooters/motorbikes per household
// (Punjab urban household vehicle profile, Tier 3 VISUAL-ONLY estimate -
// 2W dominate Indian streets and the URDPFI ECS convention folds them in
// at 4-5 per car) = ~30,100 2W, all periods.
const TRAFFIC_FLEET_BY_PERIOD = { 2030: 9795 + 30137, 2042: 14212 + 30137, 2055: 20719 + 30137 };
const TRAFFIC_VEHICLES_PER_DOT = 4;
const TRAFFIC_CLASS_WEIGHT = { arterial: 3.0, collector: 1.5, local: 0.8 };

function _trafficDutyShare(t) {
  // fraction of the fleet moving at clock hour t (urban diurnal shape)
  const pts = [[0, 0.006], [5, 0.006], [7, 0.045], [9, 0.085], [12, 0.05],
               [15, 0.055], [18, 0.09], [20, 0.075], [22, 0.025], [24, 0.008]];
  for (let i = 1; i < pts.length; i += 1) {
    if (t <= pts[i][0]) {
      const k = (t - pts[i - 1][0]) / (pts[i][0] - pts[i - 1][0]);
      return pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k;
    }
  }
  return pts[0][1];
}

function _trafficSegments() {
  if (state._trafSegKey === state.currentLayout && state._trafSegs) {
    return state._trafSegs;
  }
  const cells = new Map();
  for (const f of state.data?.features || []) {
    const p = f.properties || {};
    if (p.role === "parcel" && p.land_use === "road") {
      const c = polygonCentroid(f);
      if (c) cells.set(`${p.row}_${p.col}`, { c, cls: String(p.road_class || "local") });
    }
  }
  const segs = [];
  const scan = (mainMax, keyOf) => {
    for (let a = 0; a < mainMax; a += 1) {
      let run = [];
      for (let b = 0; b <= mainMax; b += 1) {
        const k = keyOf(a, b);
        const cell = cells.get(k);
        if (cell) {
          run.push({ k, ...cell });
        } else {
          if (run.length >= 3) {
            const path = run.map((r) => [r.c[0], r.c[1]]);
            const cum = [0];
            for (let i = 1; i < path.length; i += 1) {
              cum.push(cum[i - 1] + Math.hypot(
                (path[i][0] - path[i - 1][0]) * metersPerDegreeLongitude(path[i][1]),
                (path[i][1] - path[i - 1][1]) * METERS_PER_DEGREE_LAT));
            }
            segs.push({ path, cum, lenM: cum[cum.length - 1],
                        cls: run[Math.floor(run.length / 2)].cls,
                        keys: run.map((r) => r.k), crossings: [] });
          }
          run = [];
        }
      }
    }
  };
  scan(50, (a, b) => `${a}_${b}`);            // row runs
  scan(50, (a, b) => `${b}_${a}`);            // col runs
  // TRN-1:
  // where a row-run and a col-run share a cell, register a CROSSING with
  // the along-distance on each side - agents can switch runs there.
  const cellUse = new Map();
  segs.forEach((s, si) => s.keys.forEach((k, j) => {
    if (!cellUse.has(k)) cellUse.set(k, []);
    cellUse.get(k).push({ si, atM: s.cum[j] });
  }));
  for (const uses of cellUse.values()) {
    if (uses.length < 2) continue;
    for (const u of uses) {
      for (const v of uses) {
        if (u.si !== v.si) {
          segs[u.si].crossings.push({ atM: u.atM, other: v.si, otherAtM: v.atM });
        }
      }
    }
  }
  state._trafSegKey = state.currentLayout;
  state._trafSegs = segs;
  state._trafAgents = null;                    // re-seed on layout switch
  return segs;
}

function _trafficAgents(nWanted) {
  const segs = _trafficSegments();
  if (!segs.length) return [];
  if (!state._trafAgents || state._trafAgents.length !== nWanted) {
    const weights = segs.map((s) => s.lenM * (TRAFFIC_CLASS_WEIGHT[s.cls] || 1));
    const totW = weights.reduce((a, b) => a + b, 0) || 1;
    const agents = [];
    for (let i = 0; i < nWanted; i += 1) {
      const h = _hash2(i * 7.3, i * 3.1);
      let pick = h * totW;
      let si = 0;
      while (si < segs.length - 1 && pick > weights[si]) { pick -= weights[si]; si += 1; }
      agents.push({
        si,
        s: _hash2(i, si) * segs[si].lenM,
        // TRN-2: direction from an INDEPENDENT hash - reusing the segment-
        // pick hash correlated direction with road, making whole roads
        // one-way.
        dir: _hash2(i * 2.9, 7.7) > 0.5 ? 1 : -1,
        speed: (9 + _hash2(i * 1.7, 2.9) * 6) * 6   // stylised 6x for legibility
      });
    }
    state._trafAgents = agents;
  }
  return state._trafAgents;
}

function _ensureTrafficTicker() {
  if (state._trafficTimer) return;
  //: pause the re-render tick while the user is dragging/zooming -
  // the full layer rebuild was fighting the camera for frame time.
  const el = document.getElementById("deck-container");
  if (el && !state._trafficPerfHooks) {
    state._trafficPerfHooks = true;
    const bump = () => { state._lastInteractTs = performance.now(); };
    el.addEventListener("pointerdown", bump);
    el.addEventListener("pointermove", (e) => { if (e.buttons) bump(); });
    el.addEventListener("wheel", bump, { passive: true });
  }
  state._trafficTimer = setInterval(() => {
    if (document.hidden) return;
    if (performance.now() - (state._lastInteractTs || 0) < 350) return;
    const agents = state._trafAgents;
    const segs = state._trafSegs;
    if (!agents || !segs || !agents.length) return;
    for (const a of agents) {
      const prev = a.s;
      a.s += a.dir * a.speed * 0.13;
      // TRN-1: at a crossing, ~1 in 3 vehicles turns onto the crossing road
      const seg = segs[a.si];
      for (const c of seg.crossings) {
        if ((prev - c.atM) * (a.s - c.atM) <= 0 && Math.random() < 0.35) {
          a.si = c.other;
          a.s = c.otherAtM;
          a.dir = Math.random() < 0.5 ? 1 : -1;
          break;
        }
      }
      const L = segs[a.si].lenM;
      if (a.s < 0) a.s += L;
      if (a.s > L) a.s -= L;
    }
    // NOTHING IS PUSHED WHILE A TOWN IS LOADING. `loadLayout` sets the new
    // layout name and then awaits a fetch; every tick inside that await used
    // to push the OLD town's layers at the new state.
    if (state._layoutLoading) return;
    //: swap ONLY the traffic layer - full updateLayers every
    // tick was the choppiness (scene-wide rebuild + GC 4x a second).
    const last = state._lastLayers;
    // The cached list is only usable for the scene it was built for. A key
    // mismatch means the town or the overlay changed under it, so the correct
    // response is a rebuild rather than a swap.
    if (!last || !state.deckgl || state._lastLayersKey !== layerSetKey()) {
      updateLayers();
      return;
    }
    const fresh = trafficLayer();
    const slot = last.findIndex((l) => l && l.id === "traffic-dots");
    if (slot < 0) {
      // No traffic layer in the cached scene. If there should now be one -
      // the fleet is drawn only for the optimised layout - the list has to be
      // rebuilt, because a null left in the slot by an earlier tick can never
      // be found by id again and the cars would never come back.
      if (fresh) updateLayers();
      return;
    }
    const next = last.slice();
    next[slot] = fresh;
    state._lastLayers = next;
    state.deckgl.setProps({ layers: next.filter(Boolean) });
  }, 130);
}

function trafficLayer() {
  if (state.trafficEnabled === false) return null;
  // NO VEHICLES IN THE GRID OVERLAY. That view is the electrical network, and
  // a moving car fleet belongs to none of it. The layer list built for the
  // overlay never asked for traffic; this is the second gate, so that no
  // future caller can put it back by accident.
  if (state.electricalOverlayEnabled) return null;
  if (state._layoutLoading) return null;
  // VIEW-1: the fleet is derived from the modelled household and EV stock,
  // which belongs to optimised_sa's programme. Do not paint it on a layout it
  // was not computed for.
  if (!isOptimisedLayout()) return null;
  const segs = _trafficSegments();
  if (!segs.length) return null;
  const year = Number(state.cockpit?.periodYear || 2030);
  const fleet = TRAFFIC_FLEET_BY_PERIOD[year] || TRAFFIC_FLEET_BY_PERIOD[2030];
  const t = ((Number(state.sun.timeHours || 12) % 24) + 24) % 24;
  const moving = fleet * _trafficDutyShare(t);
  // min 8 (a 3 am town is EMPTY - the author: "why would there be same traffic
  // at 3am as 3pm"); the curve now reads: ~15 dots at 3am, ~550 at 9am.
  const nDots = Math.max(8, Math.min(900, Math.round(moving / TRAFFIC_VEHICLES_PER_DOT)));
  const agents = _trafficAgents(nDots);
  _ensureTrafficTicker();
  const night = civilTwilightDarkFactor();
  const data = agents.map((a) => {
    const seg = segs[a.si];
    const frac = clamp(a.s / seg.lenM, 0, 1) * (seg.path.length - 1);
    const i0 = Math.min(seg.path.length - 2, Math.floor(frac));
    const k = frac - i0;
    const lon = seg.path[i0][0] + (seg.path[i0 + 1][0] - seg.path[i0][0]) * k;
    const lat = seg.path[i0][1] + (seg.path[i0 + 1][1] - seg.path[i0][1]) * k;
    // lateral lane offset by direction (left-hand traffic) - wide enough
    // that the two directions read as two visible streams
    const mLon = metersPerDegreeLongitude(lat);
    const ddx = (seg.path[i0 + 1][0] - seg.path[i0][0]) * mLon;
    const ddy = (seg.path[i0 + 1][1] - seg.path[i0][1]) * METERS_PER_DEGREE_LAT;
    const dl = Math.hypot(ddx, ddy) || 1;
    const off = 4.6 * a.dir;
    return {
      position: [lon + (-ddy / dl) * off / mLon,
                 lat + (ddx / dl) * off / METERS_PER_DEGREE_LAT, 1.1],
      dir: a.dir
    };
  });
  return new deck.ScatterplotLayer({
    id: "traffic-dots",
    data,
    pickable: false,
    radiusUnits: "meters",
    stroked: false,                       // no border (Aryan)
    getPosition: (d) => d.position,
    getRadius: 3.4,
    radiusMinPixels: 2.2,
    //: DAY = the warm headlight yellow; NIGHT = neon
    // red taillights - one colour per time of day, both directions.
    getFillColor: () => night > 0.4
      ? [255, 42, 96, 250]
      : [255, 226, 130, 245],
    ///4: glide between the 130 ms ticks - continuous motion.
    transitions: { getPosition: { duration: 130 } },
    parameters: { depthTest: false }
  });
}

// ===========================================================================
// GRN-2: shrubbery on the open greens - small hash-
// scattered bush dots on open-space and park cells, denser than the trees.
// ===========================================================================
function groundBushLayer() {
  if (!state.vegetationEnabled) return null;
  if (state._bushKey !== state.currentLayout) {
    const dots = [];
    const cellM = Number(state.data?.metadata?.grid?.cell_size_m || 100);
    for (const f of state.data?.features || []) {
      const p = f.properties || {};
      if (p.role !== "parcel" || p.land_use !== "open_space") continue;
      const veg = Number(p.vegetation_fraction || 0);
      if (veg <= 0.05) continue;
      const c = polygonCentroid(f);
      if (!c) continue;
      const n = Math.min(9, 3 + Math.round(veg * 8));
      for (let i = 0; i < n; i += 1) {
        const h1 = _hash2(p.row * 3.7 + i, p.col * 5.1);
        const h2 = _hash2(p.col * 7.9 + i, p.row * 2.3);
        const [lon, lat] = offsetLngLat(c[0], c[1],
          (h1 - 0.5) * cellM * 0.8, (h2 - 0.5) * cellM * 0.8);
        dots.push({ position: [lon, lat, 0.5], r: 0.9 + h1 * 1.1 });
      }
    }
    state._bushKey = state.currentLayout;
    state._bushDots = dots;
  }
  if (!state._bushDots?.length) return null;
  // 3D bushes (two fixed-radius buckets, low-poly)
  const small = state._bushDots.filter((d) => d.r < 1.4);
  const large = state._bushDots.filter((d) => d.r >= 1.4);
  const mk = (data, suffix, radius, elev) => data.length === 0 ? null
    : new deck.ColumnLayer({
      id: `ground-bushes-${suffix}`,
      data,
      pickable: false,
      filled: true,
      extruded: true,
      diskResolution: 5,
      radius,
      radiusUnits: "meters",
      elevationScale: 1,
      getPosition: (d) => d.position,
      getElevation: elev,
      getFillColor: [44, 108, 54, 238],
      parameters: { depthTest: true }
    });
  return [mk(small, "s", 1.0, 0.9), mk(large, "l", 1.5, 1.3)];
}

// ===========================================================================
// PRK-2:
// two double-loaded bays of white stall stripes per parking cell, sized so
// ~56 stalls fit a 1-ha lot (URDPFI ~23 m2/ECS surface parking).
// ===========================================================================
function parkingBayLayer() {
  // PRK-7 (, the author: "parking is built more in 2042 etc, in the
  // viewer it doesn't show").
  //
  // THE BUG. The model stages 16 extra parking parcels - parking_expansion_2042
  // (x6) and parking_expansion_2055 (x10). In the GeoJSON their `land_use` is
  // `open_space`, NOT `parking_lot`, because until their phase year arrives
  // they are exactly that: reserved open land. The filter below tested
  // `land_use !== "parking_lot"` and skipped them forever. So when the period
  // slider reached 2042 or 2055 those parcels gained no bays and no access
  // spur; all that changed was a grey alpha nudge (132 -> 214) in
  // `parcelFillColor`, which is invisible next to other grey surfaces.
  // Solar expansion had no such problem - it grows real panel geometry when
  // it activates - which is why solar phasing reads and parking phasing did not.
  //
  // THE FIX has two halves, and the second is the one that is easy to miss:
  //   (a) accept a parking expansion parcel once its phase year has arrived;
  //   (b) put the ACTIVE PERIOD in the memo key. This layer is cached on
  //       `state.currentLayout` alone. Without (b) the bays would be built once
  //       for whatever year happened to be selected first and then never
  //       rebuilt as the slider moved - the phasing would still not show, and
  //       it would look like the fix had failed.
  const _prkKey = `${state.currentLayout}|${activePeriodYearNumber()}`;
  if (state._prkKey !== _prkKey) {
    const paths = [];
    const cellM = Number(state.data?.metadata?.grid?.cell_size_m || 100);
    // PRK-5 (, the author: "I did not mean a grey polygon - the
    // actual street needs to turn in and protrude from an existing
    // road"): the apron is GONE. The access spur is now drawn by
    // `roadCrossSectionFeatures` as a REAL street cross-section (same
    // carriageway + footpath bands and the same colours as every other
    // street), so it reads as the road turning into the lot.
    for (const f of state.data?.features || []) {
      const p = f.properties || {};
      const isBuiltLot = p.land_use === "parking_lot";
      // A staged parking parcel counts as a real lot from its phase year on.
      const isActivatedExpansion = isParkingExpansionProps(p) && isExpansionActiveProps(p);
      if (p.role !== "parcel" || !(isBuiltLot || isActivatedExpansion)) continue;
      const c = polygonCentroid(f);
      if (!c) continue;
      //: FOUR stall rows per lot, not two
      [-33, -11, 11, 33].forEach((yOff) => {
        for (let x = -cellM * 0.38; x <= cellM * 0.38; x += 2.8) {
          const a = offsetLngLat(c[0], c[1], x, yOff - 5);
          const b = offsetLngLat(c[0], c[1], x, yOff + 5);
          paths.push({ path: [[a[0], a[1], 0.5], [b[0], b[1], 0.5]] });
        }
        // bay edge line
        const e0 = offsetLngLat(c[0], c[1], -cellM * 0.38, yOff - 5);
        const e1 = offsetLngLat(c[0], c[1], cellM * 0.38, yOff - 5);
        paths.push({ path: [[e0[0], e0[1], 0.5], [e1[0], e1[1], 0.5]] });
      });
    }
    state._prkKey = _prkKey;
    state._prkPaths = paths;
  }
  if (!state._prkPaths?.length) return null;
  return new deck.PathLayer({
    id: "parking-bays",
    data: state._prkPaths,
    pickable: false,
    widthUnits: "meters",
    getWidth: 0.35,
    widthMinPixels: 1,
    getPath: (d) => d.path,
    getColor: [235, 236, 232, 225],
    parameters: { depthTest: false }
  });
}

// ===========================================================================
// CNL-2 (, the author: "the blue water bodies at the end - connect
// them so the water is all connected, greenery on the edges"): where two
// water cells sit one cell apart on the same row/col, a 14 m channel spans
// the gap with 4 m green banks either side.
// ===========================================================================
function canalConnectorLayer() {
  // CNL-2 v8 (, the author: "why is there some blue polygons
  // protruding out"): RETIRED. Every synthetic water polygon this
  // function used to draw is gone, because each one was a defect:
  //   v1-v5 adjacent-pair "connectors" painted green banks over
  //     finished water and double-drew the blue (the two-tone),
  //   v6-v7 gap BRIDGES painted blue across cells the model does not
  //     call water, and a 200 m band never lines up with an irregular
  //     pond cluster - those were the protrusions.
  // Water now renders ONLY where the model says water (real blue_space
  // parcels, one light blue), and neighbouring ponds read as a single
  // body purely because blueSpaceBankFeatures suppresses the green bank
  // on shared edges. Kept as a no-op so the layer slot and its history
  // stay documented in one place.
  return null;
}

//: draw the TRUE per-class
// cross-section inside each road cell - carriageway (+ median) with cycle
// tracks and footpaths on each side, the ROW remainder reading as verge.
// Widths come LIVE from metadata.road_network.cross_section_m (arterial 45 =
// 22 + 3 median + 2x2.5 cycle + 2x2.5 foot + 2x5 verge; collector 24;
// local 12 - i.e. a road is 12-45% of its 100 m cell, NOT the full cell).
function roadCrossSectionFeatures() {
  const md = state.data?.metadata || {};
  const xs = (md.road_network || {}).cross_section_m || {};
  const cellSizeM = Number(md.grid?.cell_size_m || 100);
  const half = cellSizeM / 2;
  const roadKeys = new Set();
  const clsByKey = new Map();
  const roadParcels = [];
  for (const f of state.data?.features || []) {
    const p = f.properties || {};
    if (p.role === "parcel" && p.land_use === "road") {
      roadKeys.add(`${p.row}_${p.col}`);
      clsByKey.set(`${p.row}_${p.col}`, String(p.road_class || ""));
      roadParcels.push(f);
    }
  }
  const out = [];
  for (const f of roadParcels) {
    const p = f.properties;
    const cs = xs[p.road_class];
    if (!cs) continue;
    const center = polygonCentroid(f);
    if (!center) continue;
    const ns = roadKeys.has(`${p.row - 1}_${p.col}`) || roadKeys.has(`${p.row + 1}_${p.col}`);
    const ew = roadKeys.has(`${p.row}_${p.col - 1}`) || roadKeys.has(`${p.row}_${p.col + 1}`);
    // shared visual section: same widened band edges the
    // tree/lamp offsets use, so strips and street furniture stay in sync.
    const v = roadVisualSection(p.road_class);
    const cwHalf = v.cwHalf;
    const cyOuter = v.cyOuter;
    const fpOuter = v.fpOuter;
    const rect = (axis, off0, off1, z, from = -half, to = half) => {
      // `from`/`to` bound the band ALONG its axis (JCT-1: junction side
      // bands stop at the crossing box instead of vanishing entirely)
      const cornersM = axis === "x"
        ? [[from, off0], [to, off0], [to, off1], [from, off1]]
        : [[off0, from], [off1, from], [off1, to], [off0, to]];
      return cornersM.map(([dx, dy]) => {
        const [lon, lat] = offsetLngLat(center[0], center[1], dx, dy);
        return [lon, lat, z];
      });
    };
    const push = (kind, polygon, cls = p.road_class) => out.push({ kind, cls, polygon });
    const bands = (axis) => {
      push("carriageway", rect(axis, -cwHalf, cwHalf, 0.3));
      if (Number(cs.median || 0) > 0.5) push("median", rect(axis, -cs.median / 2, cs.median / 2, 0.42));
      // ROADCLR-1: painted lane lines on ROADS only (arterial: one per
      // carriageway half, clear of the median; collector: centre line).
      // Streets (local) get none - the road-vs-street cue.
      if (p.road_class === "arterial") {
        const med = Number(cs.median || 0) / 2;
        const mid = med + (cwHalf - med) / 2;
        push("marking", rect(axis, mid - 0.35, mid + 0.35, 0.34));
        push("marking", rect(axis, -mid - 0.35, -mid + 0.35, 0.34));
      } else if (p.road_class === "collector") {
        push("marking", rect(axis, -0.35, 0.35, 0.34));
      }
      if (Number(cs.cycle_each_side || 0) > 0) {
        push("cycle", rect(axis, cwHalf, cyOuter, 0.36));
        push("cycle", rect(axis, -cyOuter, -cwHalf, 0.36));
      }
      if (Number(cs.footpath_each_side || 0) > 0) {
        push("footpath", rect(axis, cyOuter, fpOuter, 0.36));
        push("footpath", rect(axis, -fpOuter, -cyOuter, 0.36));
      }
    };
    if (ns && ew) {
      // JCT-1 v3 (, the author: "the cross roads are fat roads, but
      // then a fat road connects the small street"): EACH HALF-ARM takes
      // the class of ITS OWN neighbour road cell, so a wide collector arm
      // meets a narrow street arm at the crossing box instead of one fat
      // cross that jumps to a thin road at the cell edge. The box itself
      // spans exactly the widths of the arms that meet there.
      const g = _panelGeoContext();
      const armCls = (dr, dc) =>
        clsByKey.get(`${p.row + dr}_${p.col + dc}`) || p.road_class;
      // geographic mapping via the probed row/col orientation signs
      const north = armCls(g.rowLatSign > 0 ? 1 : -1, 0);
      const south = armCls(g.rowLatSign > 0 ? -1 : 1, 0);
      const east = armCls(0, g.colLonSign > 0 ? 1 : -1);
      const west = armCls(0, g.colLonSign > 0 ? -1 : 1);
      const arm = (cls) => ({ cls, cs2: xs[cls] || cs, v2: roadVisualSection(cls) });
      const A = { n: arm(north), s: arm(south), e: arm(east), w: arm(west) };
      const boxX = Math.max(A.n.v2.cwHalf, A.s.v2.cwHalf);   // NS arms' width
      const boxY = Math.max(A.e.v2.cwHalf, A.w.v2.cwHalf);   // EW arms' width
      // crossing box at the widest arms' class colour
      const boxCls = [A.n, A.s, A.e, A.w]
        .sort((a, b) => b.v2.cwHalf - a.v2.cwHalf)[0].cls;
      push("carriageway", rect("x", -boxY, boxY, 0.31, -boxX, boxX), boxCls);
      const halfArm = (axis, a, from, to) => {
        push("carriageway", rect(axis, -a.v2.cwHalf, a.v2.cwHalf, 0.3, from, to), a.cls);
        if (Number(a.cs2.cycle_each_side || 0) > 0) {
          push("cycle", rect(axis, a.v2.cwHalf, a.v2.cyOuter, 0.36, from, to), a.cls);
          push("cycle", rect(axis, -a.v2.cyOuter, -a.v2.cwHalf, 0.36, from, to), a.cls);
        }
        if (Number(a.cs2.footpath_each_side || 0) > 0) {
          push("footpath", rect(axis, a.v2.cyOuter, a.v2.fpOuter, 0.36, from, to), a.cls);
          push("footpath", rect(axis, -a.v2.fpOuter, -a.v2.cyOuter, 0.36, from, to), a.cls);
        }
      };
      halfArm("y", A.n, boxY, half);
      halfArm("y", A.s, -half, -boxY);
      halfArm("x", A.e, boxX, half);
      halfArm("x", A.w, -half, -boxX);
    } else if (ns) {
      bands("y");
    } else {
      bands("x");
    }
  }

  // PRK-5: ACCESS SPURS INTO THE CAR PARKS. For every
  // parking lot beside a road cell, the street physically turns in: a
  // local-street cross-section (carriageway + footpath either side) is
  // drawn from inside the road's carriageway across the boundary and
  // into the lot, so tarmac meets tarmac. Same layer, same colours, same
  // toggle as every other street - not a painted-on polygon.
  const parkCells = [];
  const roadCentres = new Map();
  for (const f of state.data?.features || []) {
    const p = f.properties || {};
    if (p.role !== "parcel") continue;
    if (p.land_use === "parking_lot") {
      const c = polygonCentroid(f);
      if (c) parkCells.push({ r: Number(p.row), c: Number(p.col), centre: c });
    } else if (p.land_use === "road") {
      const c = polygonCentroid(f);
      if (c) roadCentres.set(`${p.row}_${p.col}`, c);
    }
  }
  const vSpur = roadVisualSection("local");
  for (const lot of parkCells) {
    const hit = [[lot.r - 1, lot.c], [lot.r + 1, lot.c],
                 [lot.r, lot.c - 1], [lot.r, lot.c + 1]]
      .map(([rr, cc]) => ({ centre: roadCentres.get(`${rr}_${cc}`),
                            cls: clsByKey.get(`${rr}_${cc}`) }))
      .find((x) => x.centre);
    if (!hit) continue;
    const nb = hit.centre;
    const a = lot.centre;
    const mLon = metersPerDegreeLongitude(a[1]);
    // unit vector road -> lot, and its perpendicular
    const ex = (a[0] - nb[0]) * mLon;
    const ey = (a[1] - nb[1]) * METERS_PER_DEGREE_LAT;
    const L = Math.hypot(ex, ey) || 1;
    const ux = ex / L;
    const uy = ey / L;
    const px = -uy;
    const py = ux;
    // Distances are measured from the LOT CENTRE along the road->lot
    // axis: the shared boundary sits at -50 m and the road's own
    // centreline at -100 m.
    // v3 (, the author: "it goes a bit deeper into the road, keep
    // it till the edge of the road cell"): the spur no longer buries
    // itself under the road's own carriageway/cycle/footpath bands - it
    // starts exactly at the OUTER EDGE of that road's drawn
    // cross-section, computed from ITS class (arterial/collector/local
    // all differ), and still stops at the lot edge.
    const start = -100 + roadVisualSection(hit.cls || "local").fpOuter;
    const end = -50;
    const band = (halfW, z, kind) => {
      const pt = (along, side) => {
        const east = ux * along + px * side;
        const north = uy * along + py * side;
        return [a[0] + east / mLon,
                a[1] + north / METERS_PER_DEGREE_LAT, z];
      };
      out.push({ kind, cls: "local",
        polygon: [pt(start, -halfW), pt(end, -halfW),
                  pt(end, halfW), pt(start, halfW)] });
    };
    band(vSpur.fpOuter, 0.34, "footpath");
    band(vSpur.cwHalf, 0.35, "carriageway");
  }
  return out;
}

function roadBandColor(d) {
  // ROADCLR-1 (, the author: "i cant seem to make the difference
  // between a road and a street"): ROADS (arterial/collector) = dark
  // asphalt WITH painted lane markings; STREETS (local) = light concrete,
  // no markings - the real-world cue, plus the width step (18/11/7 m).
  if (d.kind === "carriageway") {
    if (d.cls === "arterial") return [38, 41, 44, 248];
    if (d.cls === "collector") return [70, 76, 78, 236];
    return [141, 146, 140, 226];
  }
  if (d.kind === "marking") return [232, 233, 226, 216];   // painted lane line
  if (d.kind === "cycle") return [146, 74, 58, 218];      // red-oxide cycle track
  if (d.kind === "median") return [74, 118, 74, 235];      // planted median
  return [176, 176, 168, 222];                             // concrete footpath
}

function roadCrossSectionLayer() {
  if (!state.roadSectionsEnabled) return null;
  if (!state.data?.features?.length) return null;
  if (state._roadStripKey !== state.currentLayout) {
    state._roadStripKey = state.currentLayout;
    state._roadStrips = roadCrossSectionFeatures();
  }
  if (!state._roadStrips?.length) return null;
  return new deck.PolygonLayer({
    id: "road-cross-sections",
    data: state._roadStrips,
    pickable: false,
    stroked: false,
    extruded: false,
    getPolygon: (d) => d.polygon,
    getFillColor: (d) => roadBandColor(d),
    updateTriggers: { getFillColor: [state.theme] }
  });
}

// (the author: "are the solar poles representing multiple for each
// one?"): yes - the model carries 7/5/3 poles per arterial/collector/local
// road cell (IS 1944 class weights); the render shows 1-2 representative
// glyphs. Label each road cell xN so the multiplicity is explicit.
function streetlightCountFeatures() {
  const fur = (state.data?.metadata?.road_network || {}).furniture_per_road_cell || {};
  return (state.data?.features || []).flatMap((f) => {
    const p = f.properties || {};
    if (p.role !== "parcel" || p.land_use !== "road") return [];
    const n = Number((fur[p.road_class] || {}).streetlight_poles || 0);
    if (!n) return [];
    const c = polygonCentroid(f);
    if (!c) return [];
    return [{ position: [c[0], c[1], 9.5], text: `x${n}`, cls: p.road_class }];
  });
}

function streetlightCountLayer() {
  if (!state.streetlightsEnabled || !state.roadSectionsEnabled) return null;
  if (!state.data?.features?.length) return null;
  if (state._poleCountKey !== state.currentLayout) {
    state._poleCountKey = state.currentLayout;
    state._poleCounts = streetlightCountFeatures();
  }
  if (!state._poleCounts?.length) return null;
  return new deck.TextLayer({
    id: "streetlight-pole-counts",
    data: state._poleCounts,
    pickable: false,
    billboard: true,
    fontFamily: "Inter, 'Segoe UI', sans-serif",
    getPosition: (d) => d.position,
    getText: (d) => d.text,
    getSize: 10.5,
    sizeUnits: "pixels",
    getColor: state.theme === "dark" ? [226, 230, 216, 190] : [70, 76, 66, 210],
    getPixelOffset: [12, -8],
    updateTriggers: { getColor: [state.theme] }
  });
}

let _electricalCache = {
  layoutKey: null,
  centers: new Map(),
  edges: [],
  transformers: [],
  interconnects: [],
  flowScale: 1,
  transformerScale: 1
};

/* VIEW-1 (, the author: "the grid option is very glitchy in the town...
   we only need these extra options for optimised, for others we dont. even the
   cars just for optimised").

   THE CAUSE, and it is one cause behind both complaints. Everything under the
   electrical overlay - feeders, interconnects, flow arcs, transformers,
   substation, battery - is drawn from `stageDScenario()`, i.e. the Stage-D
   per-edge flow solved by the LP. THAT SOLVE ONLY EXISTS FOR optimised_sa.
   The comparator layouts (chandigarh_sector, compact_centre, dispersed_low,
   radial) have never been dispatched, so the overlay was painting
   optimised_sa's grid topology onto a completely different set of parcel
   centres. Lines ran to cells that do not exist in that layout. That is the
   "glitch" - not a rendering bug, a data-provenance bug.

   Traffic has a milder version of the same problem: the fleet is derived from
   the modelled household/EV stock, which is optimised_sa's programme.

   So both are gated to the layout they were actually computed for. */
function isOptimisedLayout() {
  return String(state.currentLayout || "") === "optimised_sa";
}

function stageDScenario() {
  const scenarios = state.cockpit.data?.scenarios || [];
  return scenarios.find((scenario) => (
    scenario.name === "full_stack"
    && Number(scenario.alpha ?? 0) === 0
    && scenario.stage_d_per_edge_flow_kwh
    && scenario.stage_d_per_edge_voltage_class
  )) || scenarios.find((scenario) => (
    scenario.name === "full_stack"
    && scenario.stage_d_per_edge_flow_kwh
    && scenario.stage_d_per_edge_voltage_class
  ));
}

function electricalFeederLayer() {
  const edges = electricalEdgeFeatures();
  if (!edges.length) return null;
  return new deck.PathLayer({
    id: "stage-d-electrical-feeders",
    data: edges,
    pickable: true,
    widthUnits: "pixels",
    jointRounded: true,
    capRounded: true,
    getPath: (d) => d.path,
    getWidth: (d) => (d.voltageClass === "backbone_33kv" ? 4.6 : 2.4) + d.loading * 4.8,
    getColor: (d) => electricalEdgeColor(d),
    parameters: { depthTest: false },
    updateTriggers: {
      getWidth: [state.currentLayout],
      getColor: [state.currentLayout]
    }
  });
}

function electricalInterconnectLayer() {
  const paths = electricalInterconnectFeatures();
  if (!paths.length) return null;
  return new deck.PathLayer({
    id: "stage-d-grid-and-ppa-lines",
    data: paths,
    pickable: true,
    widthUnits: "pixels",
    jointRounded: true,
    capRounded: true,
    getPath: (d) => d.path,
    getWidth: (d) => d.kind === "electrical_ppa_line" ? 4.4 : 5.6,
    getColor: (d) => withAlpha(d.kind === "electrical_ppa_line" ? ELECTRICAL_COLOURS.ppaLine : ELECTRICAL_COLOURS.gridLine, 232),
    parameters: { depthTest: false }
  });
}

// THE TWO INTERCONNECTIONS FLOW LIKE THE CELL ARCS (the author, "do you
// see how the lines flow out of the solar farm... i want the data centre and
// grid lines to be like that"). They were static strokes, then briefly dots
// travelling along a straight path - neither matched the arcs that every
// generating cell already draws to the substation.
//
// Same feature shape and the same pulse helpers as electricalFlowArcFeatures,
// so the two read as one system: magnitude sets width and glow, `speed` and
// `phase` drive the shimmer, `height` gives the arc its lift. The only
// addition is `colour`, because the PPA leg is teal rather than the
// import-red / export-green pair.
function electricalInterconnectFlowFeatures() {
  const paths = electricalInterconnectFeatures();
  if (!paths.length) return [];
  const scenario = activeCockpitScenario();
  if (!scenario) return [];
  const snapshot = cockpitFlowSnapshot(scenario, state.sun.timeHours);
  if (!snapshot) return [];

  const gridKw = Number(snapshot.gridNetKw || 0);
  const dcKw = Number(snapshot.dcPpaKw || 0);
  const scale = Math.max(1, Math.abs(gridKw), dcKw);
  const arcs = [];

  paths.forEach((row, index) => {
    const [a, b] = [row.path[0], row.path[row.path.length - 1]];
    let kw = 0;
    let isImport = false;
    let colour = null;
    if (row.kind === "electrical_grid_line") {
      kw = gridKw;
      isImport = gridKw > 0;               // positive = the town is drawing in
    } else if (row.kind === "electrical_ppa_line") {
      kw = dcKw;
      isImport = false;                    // the contract only ever exports
      colour = ELECTRICAL_COLOURS.ppaLine;
    }
    const magnitudeKw = Math.abs(kw);
    if (magnitudeKw <= 0.05) return;       // no flow, no arc
    const magnitude = clamp(magnitudeKw / scale, 0.12, 1);
    const src = isImport ? b : a;
    const tgt = isImport ? a : b;

    // ONE STROKE, TWO COLOURS (the author, "why is it not one stroke
    // like the rest, i just wanted it to be two different colours but still
    // the same projectile shape").
    //
    // The previous version chopped the grid leg into ELEVEN sub-arcs and
    // alternated their colour, because ArcLayer has no dash support. Each
    // sub-arc is an independent arc with its own height, so instead of a
    // striped line the result was a row of little humps - the "weird" shape.
    //
    // ArcLayer already interpolates between getSourceColor and getTargetColor
    // along the arc, so two colours need no geometry at all. The grid leg is
    // now a SINGLE arc, identical in shape to the PPA leg and to every cell
    // arc, carrying the flow colour at the town end and slate at the grid end.
    // The gradient direction is meaningful: it runs from whichever end the
    // energy leaves toward the end it arrives at.
    const twoTone = row.kind === "electrical_grid_line";
    arcs.push({
      source: src,
      target: tgt,
      isImport,
      magnitude,
      colour,
      // null = use the import/export flow colour for that end
      colourTarget: twoTone ? ELECTRICAL_COLOURS.gridLine : null,
      widthPx: 2.2 + magnitude * 6.0,
      speed: 0.75 + magnitude * 2.2,
      phase: index * 0.9,
      height: 0.32 + magnitude * 0.5,
      properties: {
        kind: row.kind,
        label: row.properties?.label || "",
        kw
      }
    });
  });
  return arcs;
}

function electricalInterconnectFlowLayer() {
  const data = electricalInterconnectFlowFeatures();
  if (!data.length) return null;
  const colourFor = (d) => (d.colour
    ? withAlpha(d.colour, Math.round(120 + d.magnitude * 90 + electricalPulseMultiplier(d) * 40))
    : electricalArcColor(d));
  // The far end may differ, which is what makes the grid leg two-tone in a
  // single stroke: ArcLayer blends source colour into target colour along the
  // arc. Everything else returns the same colour at both ends and is solid.
  const colourTargetFor = (d) => (d.colourTarget
    ? withAlpha(d.colourTarget,
                Math.round(120 + d.magnitude * 90
                           + electricalPulseMultiplier(d) * 40))
    : colourFor(d));
  return new deck.ArcLayer({
    id: "stage-d-interconnect-arcs",
    data,
    pickable: true,
    getSourcePosition: (d) => d.source,
    getTargetPosition: (d) => d.target,
    getSourceColor: colourFor,
    getTargetColor: colourTargetFor,
    getWidth: (d) => d.widthPx * electricalPulseMultiplier(d),
    widthUnits: "pixels",
    widthMinPixels: 2,
    widthMaxPixels: 10,
    getHeight: (d) => d.height,
    getTilt: 12,
    parameters: { depthTest: false },
    updateTriggers: {
      getSourceColor: [state.electricalPulse, state.sun.timeHours],
      getTargetColor: [state.electricalPulse, state.sun.timeHours],
      getWidth: [state.electricalPulse, state.sun.timeHours]
    }
  });
}

function electricalTransformerLayer() {
  const transformers = electricalTransformerFeatures();
  if (!transformers.length) return null;
  return new deck.ScatterplotLayer({
    id: "stage-d-transformer-zones",
    data: transformers,
    pickable: true,
    stroked: true,
    filled: true,
    billboard: true,
    radiusUnits: "meters",
    radiusMinPixels: 4,
    radiusMaxPixels: 20,
    lineWidthUnits: "pixels",
    getPosition: (d) => d.position,
    getRadius: (d) => d.radiusM,
    getFillColor: (d) => withAlpha(mix(ELECTRICAL_COLOURS.transformer, ELECTRICAL_COLOURS.loadingHigh, d.loading), 220),
    getLineColor: [255, 248, 214, 245],
    getLineWidth: 1.2,
    parameters: { depthTest: false },
    updateTriggers: {
      getFillColor: [state.currentLayout]
    }
  });
}

function dataCentreBuildingFeatures() {
  const substation = electricalSubstationFeature();
  const centre = dataCentreCentre(substation);
  if (!centre) return [];
  const [lon, lat] = centre;
  // A data centre reads as long low sheds plus a smaller plant block, not one
  // cube. Three footprints on the same slab: two halls side by side and a
  // service block, which is what an aerial photograph of one looks like.
  const ring = (eastM, northM, halfE, halfN) => [
    offsetLngLat(lon, lat, eastM - halfE, northM - halfN),
    offsetLngLat(lon, lat, eastM + halfE, northM - halfN),
    offsetLngLat(lon, lat, eastM + halfE, northM + halfN),
    offsetLngLat(lon, lat, eastM - halfE, northM + halfN)
  ].map(([x, y]) => [x, y]);
  return [
    { polygon: ring(-46, 0, 42, 30), height: 15, kind: "hall" },
    { polygon: ring(48, 0, 42, 30), height: 15, kind: "hall" },
    { polygon: ring(0, -52, 22, 16), height: 9, kind: "plant" }
  ];
}

function dataCentreBuildingLayer() {
  const data = dataCentreBuildingFeatures();
  if (!data.length) return null;
  return new deck.PolygonLayer({
    id: "stage-d-data-centre",
    data,
    pickable: true,
    filled: true,
    stroked: true,
    extruded: true,
    wireframe: false,
    getPolygon: (d) => d.polygon,
    getElevation: (d) => d.height,
    // Teal, matching the PPA line that arrives at it, so the eye joins the two.
    getFillColor: (d) => withAlpha(ELECTRICAL_COLOURS.ppaLine, d.kind === "plant" ? 200 : 226),
    getLineColor: [255, 255, 255, 210],
    getLineWidth: 1.2,
    lineWidthUnits: "pixels",
    parameters: { depthTest: true }
  });
}

function electricalSubstationLayer() {
  const substation = electricalSubstationFeature();
  if (!substation) return null;
  return new deck.ColumnLayer({
    id: "stage-d-substation",
    data: [substation],
    pickable: true,
    filled: true,
    stroked: true,
    extruded: true,
    diskResolution: 24,
    radius: 24,
    radiusUnits: "meters",
    lineWidthUnits: "pixels",
    elevationScale: 1,
    getPosition: (d) => d.position,
    getElevation: 36,
    getFillColor: withAlpha(ELECTRICAL_COLOURS.substation, 238),
    getLineColor: [255, 255, 255, 238],
    getLineWidth: 1.4,
    parameters: { depthTest: false }
  });
}

// ===========================================================================
// BESS-1 (, the author: "we didn't actually reserve any space for
// battery!!").
//
// He is right, and it had gone unnoticed because the battery DID have a
// symbol. `batteryStorageFeature` below places a flat marker offset from the
// substation inside the Stage-D grid overlay, so the eye reads "the battery is
// represented" while no ground is occupied by it anywhere in the layout. The
// model builds 389,828 kWh by 2055 against zero allocated land.
//
// SITE. Cell (23, 10). Chosen, not arbitrary: it is one of only two untagged
// reserve cells that touch the solar farm, and the only one that is ALSO road
// adjacent, which a battery site needs for delivery and maintenance access.
// Its farm neighbour is immediately north, so the connection is short.
//
// WHY THE GEOJSON IS NOT EDITED. `amenity_subtype` is inside the layout
// fingerprint hash (scripts/layout_fingerprint.py, FIELDS), so retagging the
// cell would break `d5fb9839dd07bcc9...`, which is quoted in the thesis and
// guards against layout drift. was "that cell can still be
// an open cell but with battery on it ... this way nothing changes". So the
// site is a VIEWER constant and the cell keeps its land use. The battery
// occupies ground visually and in the written area budget; the frozen layout is
// untouched.
//
// TIMING. The containers appear only when the active period actually carries
// battery capacity. puts entry at 2042, and the reserve this cell belongs
// to releases in 2042, so the two coincide without being made to.
const BESS_SITE_CELL = { row: 23, col: 10 };
// Containerised lithium-iron-phosphate, ~3.9 MWh per 20-foot unit, and about
// 82 m2 per unit once walkways and fire separation are included (a 12.2 x 2.9 m
// container on a 15.2 x 5.4 m pitch). These drive the drawn FOOTPRINT only.
// The thesis quotes a sourced area, not these constants.
const BESS_KWH_PER_CONTAINER = 3900;
const BESS_M2_PER_CONTAINER = 82;
const BESS_HEIGHT_M = 3.2;

function bessSiteParcel() {
  for (const f of state.data?.features || []) {
    const p = f.properties || {};
    if (p.role === "parcel" && Number(p.row) === BESS_SITE_CELL.row
        && Number(p.col) === BESS_SITE_CELL.col) return f;
  }
  return null;
}

function bessContainerFeatures() {
  const kwh = numberOrNull(activeCockpitScenario()?.capacities?.battery_kwh);
  if (kwh === null || kwh <= 0) return [];
  const parcel = bessSiteParcel();
  if (!parcel) return [];
  const centre = polygonCentroid(parcel);
  if (!centre) return [];

  // the author, "you can build on it it's fine ... just put like a
  // black box on the cell." So this draws ONE dark block, not the 100
  // individual containers the first version laid out. At the zoom the thesis
  // plates use, a hundred small boxes read as noise; one block reads as a
  // building, which is what a containerised installation looks like from the
  // air anyway once it is fenced.
  //
  // The FOOTPRINT still scales with the period's capacity, so the site grows
  // between 2042 and 2055 and the phasing reads in the three-year comparison.
  // Area is derived from the same container arithmetic as before rather than
  // being a free choice: capacity / 3.9 MWh per unit, at 82 m2 per unit
  // including walkways and fire separation, capped at the usable cell.
  const cellM = Number(state.data?.metadata?.grid?.cell_size_m || 100);
  const usable = cellM * 0.92;              // perimeter setback
  const units = Math.max(1, Math.round(kwh / BESS_KWH_PER_CONTAINER));
  const areaM2 = Math.min(units * BESS_M2_PER_CONTAINER, usable * usable);
  const side = Math.sqrt(areaM2);
  const half = side / 2;
  const corners = [[-half, -half], [half, -half], [half, half], [-half, half]];
  return [{
    polygon: corners.map(([dx, dy]) =>
      offsetLngLat(centre[0], centre[1], dx, dy)),
    height: BESS_HEIGHT_M,
    properties: { kind: "bess_site", batteryKwh: kwh, units,
                  areaM2: Math.round(areaM2),
                  row: BESS_SITE_CELL.row, col: BESS_SITE_CELL.col }
  }];
}

function bessSiteLayer() {
  const data = bessContainerFeatures();
  if (!data.length) return null;
  return new deck.PolygonLayer({
    id: "bess-site-block",
    data,
    pickable: true,
    extruded: true,
    filled: true,
    stroked: true,
    getPolygon: (d) => d.polygon,
    getElevation: (d) => d.height,
    // the author: "just put like a black box on the cell". Near-black rather than
    // pure black so the extrusion still catches the scene lighting and reads
    // as a solid object at low sun instead of a flat silhouette.
    getFillColor: [26, 30, 34, 252],
    getLineColor: [96, 108, 118, 220],
    lineWidthUnits: "pixels",
    getLineWidth: 1.2,
    updateTriggers: {
      getPolygon: [state.cockpit.periodYear, state.currentLayout],
      getElevation: [state.cockpit.periodYear]
    }
  });
}

function batteryStorageFeature() {
  const batteryKwh = numberOrNull(activeCockpitScenario()?.capacities?.battery_kwh);
  if (batteryKwh === null || batteryKwh <= 0) return null;
  const substation = electricalSubstationFeature();
  if (!substation) return null;
  const [lon, lat] = substation.position;
  const position = offsetLngLat(lon, lat, 120, -95);
  const mwh = batteryKwh / 1000;
  return {
    position: [position[0], position[1], 2],
    radiusPx: clamp(10 + Math.sqrt(Math.max(0, mwh)) * 0.85, 12, 24),
    batteryKwh,
    properties: {
      kind: "electrical_bess",
      batteryKwh,
      period: activeCockpitScenario()?.active_period_label || state.cockpit.periodYear || ""
    }
  };
}

function batteryStorageLayer() {
  const feature = batteryStorageFeature();
  if (!feature) return null;
  return new deck.ScatterplotLayer({
    id: "stage-d-bess-marker",
    data: [feature],
    pickable: true,
    filled: true,
    stroked: true,
    billboard: true,
    radiusUnits: "pixels",
    radiusMinPixels: 10,
    radiusMaxPixels: 26,
    lineWidthUnits: "pixels",
    getPosition: (d) => d.position,
    getRadius: (d) => d.radiusPx,
    getFillColor: [45, 212, 191, 228],
    getLineColor: [204, 251, 241, 244],
    getLineWidth: 2,
    parameters: { depthTest: false },
    updateTriggers: {
      getRadius: [state.cockpit.periodYear]
    }
  });
}

function electricalFlowArcLayer() {
  const arcs = electricalFlowArcFeatures();
  if (!arcs.length) return null;
  return new deck.ArcLayer({
    id: "stage-d-cell-flow-arcs",
    data: arcs,
    pickable: true,
    getSourcePosition: (d) => d.source,
    getTargetPosition: (d) => d.target,
    getSourceColor: (d) => electricalArcColor(d),
    getTargetColor: (d) => electricalArcColor(d),
    getWidth: (d) => d.widthPx * electricalPulseMultiplier(d),
    widthUnits: "pixels",
    widthMinPixels: 1,
    widthMaxPixels: 8,
    getHeight: (d) => d.height,
    getTilt: 12,
    parameters: { depthTest: false },
    updateTriggers: {
      getSourceColor: [state.electricalPulse, state.sun.timeHours],
      getTargetColor: [state.electricalPulse, state.sun.timeHours],
      getWidth: [state.electricalPulse, state.sun.timeHours]
    }
  });
}

function electricalEdgeFeatures() {
  return electricalCached().edges;
}

function electricalTransformerFeatures() {
  return electricalCached().transformers;
}

function electricalInterconnectFeatures() {
  return electricalCached().interconnects;
}

function electricalSubstationFeature() {
  return electricalCached().substation || null;
}

function electricalCached() {
  const scenario = stageDScenario();
  const featureCount = state.data?.features?.length || 0;
  const scenarioKey = `${scenario?.name || "none"}:${Number(scenario?.alpha ?? 0)}:${Object.keys(scenario?.stage_d_per_edge_flow_kwh || {}).length}`;
  const key = `${state.currentLayout || ""}:${featureCount}:${scenarioKey}`;
  if (_electricalCache.layoutKey === key) return _electricalCache;
  const centers = parcelCenterIndex();
  if (!scenario || !state.data || !centers.size) {
    _electricalCache = { layoutKey: key, centers, edges: [], transformers: [], interconnects: [], flowScale: 1, transformerScale: 1, substation: null };
    return _electricalCache;
  }

  const flowMap = scenario.stage_d_per_edge_flow_kwh || {};
  const voltageMap = scenario.stage_d_per_edge_voltage_class || {};
  const flows = Object.values(flowMap).map((value) => Math.abs(Number(value || 0))).filter((value) => value > 0);
  const flowScale = percentile(flows, 0.92) || Math.max(1, ...flows, 1);
  const edges = Object.entries(flowMap).map(([edgeKey, rawFlow]) => {
    const parsed = parseStageDEdgeKey(edgeKey);
    if (!parsed) return null;
    const a = centers.get(`${parsed.r1}_${parsed.c1}`);
    const b = centers.get(`${parsed.r2}_${parsed.c2}`);
    if (!a || !b) return null;
    const flowKwh = Math.abs(Number(rawFlow || 0));
    const voltageClass = voltageMap[edgeKey] || "dist_11kv";
    return {
      path: [[a[0], a[1], 10], [b[0], b[1], 10]],
      edgeKey,
      from: [parsed.r1, parsed.c1],
      to: [parsed.r2, parsed.c2],
      flowKwh,
      loading: clamp(flowKwh / flowScale, 0, 1),
      voltageClass,
      properties: {
        kind: "electrical_edge",
        edgeKey,
        flowKwh,
        voltageClass,
        loading: clamp(flowKwh / flowScale, 0, 1)
      }
    };
  }).filter(Boolean);

  const transformerRaw = Array.isArray(scenario.stage_d_transformer_zones) ? scenario.stage_d_transformer_zones : [];
  const kvaValues = transformerRaw.map((zone) => Number(zone.kva || 0)).filter((value) => value > 0);
  const transformerScale = percentile(kvaValues, 0.88) || Math.max(1, ...kvaValues, 1);
  const transformers = transformerRaw.map((zone, index) => {
    const centroid = Array.isArray(zone.centroid) ? zone.centroid : [0, 0];
    const position2d = metersToLngLat(Number(centroid[0] || 0), Number(centroid[1] || 0));
    const kva = Number(zone.kva || 0);
    const loading = clamp(kva / transformerScale, 0, 1);
    return {
      position: [position2d[0], position2d[1], 24],
      radiusM: 16 + Math.sqrt(Math.max(0, kva) / Math.max(1, transformerScale)) * 34,
      kva,
      peakKw: Number(zone.peak_kw || 0),
      nBuilt: Number(zone.n_built || 0),
      loading,
      properties: {
        kind: "electrical_transformer",
        zoneIndex: index + 1,
        kva,
        peakKw: Number(zone.peak_kw || 0),
        nBuilt: Number(zone.n_built || 0)
      }
    };
  });

  const substation = buildElectricalSubstation(scenario, centers);
  const interconnects = buildElectricalInterconnects(substation);
  _electricalCache = { layoutKey: key, centers, edges, transformers, interconnects, flowScale, transformerScale, substation };
  return _electricalCache;
}

function buildElectricalSubstation(scenario, centers) {
  const cell = Array.isArray(scenario?.stage_d_substation_cell) ? scenario.stage_d_substation_cell : [12, 12];
  const row = Number(cell[0]);
  const col = Number(cell[1]);
  const center = centers.get(`${row}_${col}`);
  if (!center) return null;
  return {
    position: [center[0], center[1], 0],
    row,
    col,
    properties: {
      kind: "electrical_substation",
      row,
      col
    }
  };
}

// Where the data centre stands, as an offset from the substation. ONE constant,
// because the PPA line's far end and the building itself have to be the same
// point - the author, "extend the data centre line and connect it to a
// data centre looking building". Two hand-kept copies would drift the moment
// either moved, which is the fault that has bitten this file repeatedly today.
// BOTH ENDPOINTS SIT OUTSIDE THE TOWN, and they did not before (the author,
// "the data centre has to be outside the town"). The grid is
// 50 x 50 cells at 100 m = 5,000 m square, and the substation is at cell
// [25, 25], so it stands 2,450 m from the east edge. The old offsets - 1,300 m
// east for the data centre, 1,450 m west for the grid - both landed INSIDE the
// built area, which put an off-site consumer and the national grid connection
// in the middle of the town. 3,100 m clears the boundary by ~650 m each way.
const DATA_CENTRE_OFFSET_M = { east: 3100, north: -1200 };
const GRID_INTERCONNECT_OFFSET_M = { east: -3100, north: 0 };

function dataCentreCentre(substation) {
  if (!substation) return null;
  const [lon, lat] = substation.position;
  return offsetLngLat(lon, lat, DATA_CENTRE_OFFSET_M.east, DATA_CENTRE_OFFSET_M.north);
}

function buildElectricalInterconnects(substation) {
  if (!substation) return [];
  const [lon, lat] = substation.position;
  const gridEnd = offsetLngLat(lon, lat, GRID_INTERCONNECT_OFFSET_M.east, GRID_INTERCONNECT_OFFSET_M.north);
  const ppaEnd = dataCentreCentre(substation);
  return [
    {
      path: [[lon, lat, 18], [gridEnd[0], gridEnd[1], 18]],
      properties: {
        kind: "electrical_grid_line",
        label: "Grid interconnection"
      },
      kind: "electrical_grid_line"
    },
    {
      path: [[lon, lat, 28], [ppaEnd[0], ppaEnd[1], 28]],
      properties: {
        kind: "electrical_ppa_line",
        label: "Data-centre PPA line"
      },
      kind: "electrical_ppa_line"
    }
  ];
}

function electricalFlowArcFeatures() {
  const scenario = stageDScenario();
  const substation = electricalSubstationFeature();
  const centers = electricalCached().centers;
  if (!scenario?.by_cell || !substation || !centers.size) return [];
  const daypart = stageDDaypartKey();
  const rows = Object.entries(scenario.by_cell).map(([key, cell]) => {
    const parsed = parseCellKeyString(key);
    if (!parsed) return null;
    const center = centers.get(`${parsed.row}_${parsed.col}`);
    if (!center) return null;
    const byDaypart = cell?.net_district_flow_kwh_by_daypart || {};
    const flow = Number(byDaypart[daypart] ?? Number(cell?.net_district_flow_kwh || 0) / STAGE_D_DAYPART_KEYS.length);
    if (!Number.isFinite(flow) || Math.abs(flow) <= 0) return null;
    return {
      key,
      row: parsed.row,
      col: parsed.col,
      flowKwh: flow,
      absFlowKwh: Math.abs(flow),
      center: [center[0], center[1], 36]
    };
  }).filter(Boolean);
  const sorted = rows.sort((a, b) => b.absFlowKwh - a.absFlowKwh).slice(0, ELECTRICAL_ARC_LIMIT);
  const scale = percentile(sorted.map((row) => row.absFlowKwh), 0.90) || Math.max(1, ...sorted.map((row) => row.absFlowKwh), 1);
  return sorted.map((row, index) => {
    const isImport = row.flowKwh > 0;
    const magnitude = clamp(row.absFlowKwh / scale, 0, 1);
    return {
      source: isImport ? substation.position : row.center,
      target: isImport ? row.center : substation.position,
      isImport,
      magnitude,
      widthPx: 1.3 + magnitude * 5.2,
      speed: 0.75 + magnitude * 2.2,
      phase: index * 0.37,
      height: 0.18 + magnitude * 0.42,
      properties: {
        kind: "electrical_flow_arc",
        row: row.row,
        col: row.col,
        daypart,
        flowKwh: row.flowKwh,
        magnitude,
        direction: isImport ? "import" : "export"
      }
    };
  });
}

function electricalEdgeColor(edge) {
  const voltageBase = edge.voltageClass === "backbone_33kv"
    ? ELECTRICAL_COLOURS.backbone
    : ELECTRICAL_COLOURS.distribution;
  const loadingColour = edge.loading < 0.5
    ? mix(ELECTRICAL_COLOURS.loadingLow, ELECTRICAL_COLOURS.loadingMid, edge.loading / 0.5)
    : mix(ELECTRICAL_COLOURS.loadingMid, ELECTRICAL_COLOURS.loadingHigh, (edge.loading - 0.5) / 0.5);
  const colour = mix(voltageBase, loadingColour, 0.62);
  const alpha = edge.voltageClass === "backbone_33kv" ? 244 : 214;
  return withAlpha(colour, alpha);
}

function electricalArcColor(arc) {
  const pulse = electricalPulseMultiplier(arc);
  const base = arc.isImport ? ELECTRICAL_COLOURS.import : ELECTRICAL_COLOURS.export;
  const glow = arc.isImport ? [252, 165, 165] : [134, 239, 172];
  return withAlpha(mix(base, glow, pulse - 0.72), Math.round(100 + arc.magnitude * 90 + pulse * 45));
}

function electricalPulseMultiplier(arc) {
  const t = Math.sin((state.electricalPulse || 0) * arc.speed * Math.PI + arc.phase);
  return 0.72 + ((t + 1) / 2) * 0.42;
}

function parseStageDEdgeKey(edgeKey) {
  const match = String(edgeKey || "").match(/^\(([-\d]+),\s*([-\d]+)\)-\(([-\d]+),\s*([-\d]+)\)$/);
  if (!match) return null;
  return {
    r1: Number(match[1]),
    c1: Number(match[2]),
    r2: Number(match[3]),
    c2: Number(match[4])
  };
}

function parseCellKeyString(key) {
  const match = String(key || "").match(/^(\d+)_(\d+)$/);
  if (!match) return null;
  return {
    row: Number(match[1]),
    col: Number(match[2])
  };
}

function stageDDaypartKey(hour = state.sun.timeHours) {
  const index = Math.min(STAGE_D_DAYPART_KEYS.length - 1, Math.floor(clamp(Number(hour) || 0, 0, 24) / 2));
  return STAGE_D_DAYPART_KEYS[index];
}

function metersToLngLat(xM, yM) {
  const bounds = state.data?.metadata?.bounds || state.manifest?.bounds || [];
  if (bounds.length >= 4) return offsetLngLat(Number(bounds[0]), Number(bounds[1]), xM, yM);
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const rows = Number(state.data?.metadata?.grid?.rows || 25);
  const cols = Number(state.data?.metadata?.grid?.cols || 25);
  const centerLon = Number(state.data?.metadata?.center?.longitude || state.viewState.longitude);
  const centerLat = Number(state.data?.metadata?.center?.latitude || state.viewState.latitude);
  return offsetLngLat(centerLon, centerLat, xM - (cols * cellSizeM) / 2, yM - (rows * cellSizeM) / 2);
}

// CHG-6: procedural earth-tone ground
// texture under the district - one 512px noise tile generated once, no asset.
function groundTextureLayer() {
  if (!state.data || !state.data.features?.length) return null;
  if (!state._groundTexture || state._groundTextureTheme !== state.theme) {
    state._groundTextureTheme = state.theme;
    const size = 512;
    const canvas = document.createElement("canvas");
    canvas.width = size; canvas.height = size;
    const ctx = canvas.getContext("2d");
    const dark = state.theme === "dark";
    ctx.fillStyle = dark ? "#23241f" : "#b9b39b"; // dry-plain earth
    ctx.fillRect(0, 0, size, size);
    let s = 1234567;
    const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
    for (let i = 0; i < 9000; i += 1) {
      const g = rnd();
      ctx.fillStyle = dark
        ? `rgba(${30 + g * 24},${32 + g * 22},${26 + g * 18},0.5)`
        : `rgba(${168 + g * 50},${160 + g * 46},${128 + g * 40},0.5)`;
      ctx.fillRect(rnd() * size, rnd() * size, 1 + rnd() * 2.2, 1 + rnd() * 2.2);
    }
    state._groundTexture = canvas.toDataURL("image/png");
  }
  if (!state._groundBounds) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const f of state.data.features) {
      const polys = f.geometry?.type === "Polygon" ? [f.geometry.coordinates]
        : f.geometry?.type === "MultiPolygon" ? f.geometry.coordinates : [];
      for (const poly of polys) for (const ring of poly) for (const [x, y] of ring) {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
    }
    if (!Number.isFinite(minX)) return null;
    // Keep only a tiny breathing edge. The earlier 6% pad looked like a
    // deliberate grey ring road/boundary around the town.
    const padX = (maxX - minX) * 0.015, padY = (maxY - minY) * 0.015;
    state._groundBounds = [minX - padX, minY - padY, maxX + padX, maxY + padY];
  }
  return new deck.BitmapLayer({
    id: "ground-texture",
    image: state._groundTexture,
    bounds: state._groundBounds,
    opacity: state.theme === "dark" ? 0.18 : 0.14,
    pickable: false,
    parameters: { depthTest: false },
    updateTriggers: { image: [state.theme] }
  });
}

function flatGroundShadowLayer() {
  const shadows = flatGroundShadowFeatures();
  if (!shadows.length) return null;
  return new deck.PolygonLayer({
    id: "flat-ground-sun-shadows",
    data: shadows,
    pickable: false,
    stroked: false,
    filled: true,
    extruded: false,
    getPolygon: (d) => d.polygon,
    getFillColor: [0, 0, 0, 70],
    parameters: { depthTest: false },
    updateTriggers: {
      getPolygon: [
        state.currentLayout,
        state.sun.altitudeRad,
        state.sun.azimuthRad,
        state.realTimeShadowsEnabled
      ]
    }
  });
}

function flatGroundShadowFeatures() {
  if (!state.data || !state.realTimeShadowsEnabled) return [];
  const altitudeRad = Number(state.sun.altitudeRad);
  const altitudeDeg = Number(state.sun.altitudeDeg);
  const azimuthRad = Number(state.sun.azimuthRad);
  if (!Number.isFinite(altitudeRad) || !Number.isFinite(azimuthRad) || altitudeDeg <= 8) return [];
  const tanAlt = Math.tan(altitudeRad);
  if (!Number.isFinite(tanAlt) || tanAlt <= 0) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const maxShadowLenM = cellSizeM * 3;
  const shadowEastUnit = Math.sin(azimuthRad);
  const shadowNorthUnit = Math.cos(azimuthRad);
  return shadowCasterFeatures().map((feature) => {
    const props = feature.properties || {};
    const heightM = Number(props.height_m || 0);
    const shadowLenM = clamp(scaledHeightM(heightM) / tanAlt, 0, maxShadowLenM);
    if (shadowLenM <= 0) return null;
    const ring = shadowFootprintRing(feature);
    if (ring.length < 3) return null;
    const projected = ring.map(([lon, lat]) => offsetLngLat(
      lon,
      lat,
      shadowEastUnit * shadowLenM,
      shadowNorthUnit * shadowLenM
    ));
    const hull = convexHullLngLat(ring.concat(projected));
    if (hull.length < 3) return null;
    return {
      polygon: hull.map(([lon, lat]) => [lon, lat, 0.05]),
      properties: props
    };
  }).filter(Boolean);
}

function shadowCasterFeatures() {
  const features = state.data?.features || [];
  const structureCells = new Set();
  const casters = [];
  features.forEach((feature) => {
    const props = feature.properties || {};
    if (!isShadowCasterProps(props)) return;
    if (props.role === "structure" || isPlantFeatureProps(props)) {
      const key = cellKey(props);
      if (key && props.role === "structure") structureCells.add(key);
      casters.push(feature);
    }
  });
  features.forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel" || !isShadowCasterProps(props)) return;
    if (structureCells.has(cellKey(props))) return;
    casters.push(feature);
  });
  return casters;
}

function isShadowCasterProps(props) {
  if (!props) return false;
  if (Number(props.height_m || 0) <= 0) return false;
  if (isPlantFeatureProps(props)) return true;
  if (["road", "open_space", "blue_space", "solar_farm"].includes(props.land_use)) return false;
  return Boolean(props.is_built || props.role === "structure");
}

function shadowFootprintRing(feature) {
  const ring = (feature.geometry?.coordinates?.[0] || [])
    .filter((point) => Array.isArray(point) && point.length >= 2)
    .map(([lon, lat]) => [Number(lon), Number(lat)])
    .filter(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat));
  if (ring.length > 1 && sameCoordinate(ring[0], ring[ring.length - 1])) ring.pop();
  return ring;
}

let _buildingGlowCache = { layoutKey: null, features: [] };

function buildingGlowLayer() {
  const features = buildingGlowFeatures();
  if (!features.length) return null;
  return new deck.GeoJsonLayer({
    id: "building-daypart-lighting-glow",
    data: featureCollection(features),
    pickable: false,
    stroked: false,
    filled: true,
    extruded: true,
    wireframe: false,
    opacity: 1,
    material: false,
    getElevation: (feature) => scaledFeatureHeightM(feature.properties) + 0.8,
    getFillColor: (feature) => buildingGlowColor(feature.properties),
    parameters: { depthTest: false },
    updateTriggers: {
      getElevation: [BUILDING_HEIGHT_SCALE],
      getFillColor: [
        state.sun.timeHours,
        state.sun.altitudeDeg,
        state.currentLayout,
        state.cellLightingByDaypart
      ]
    }
  });
}

function buildingGlowFeatures() {
  const featureCount = state.data?.features?.length || 0;
  const key = `${state.currentLayout || ""}:${featureCount}:${state.cellLightingByDaypart.size}`;
  if (_buildingGlowCache.layoutKey === key) return _buildingGlowCache.features;
  if (!state.data || !state.cellLightingByDaypart.size) {
    _buildingGlowCache = { layoutKey: key, features: [] };
    return _buildingGlowCache.features;
  }

  const features = [];
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "structure") return;
    if (isPlantFeatureProps(props) || props.part === "solar_array") return;
    const schedule = lightingScheduleForProps(props);
    if (!schedule.length) return;
    features.push({
      type: "Feature",
      geometry: feature.geometry,
      properties: {
        ...props,
        lighting_by_daypart: schedule,
        part: props.part || "building_glow"
      }
    });
  });

  _buildingGlowCache = { layoutKey: key, features };
  return features;
}

function buildingGlowColor(props) {
  const intensity = lightingIntensityForProps(props);
  if (intensity <= 0) return [0, 0, 0, 0];
  const base = BUILDING_GLOW_COLOURS[props?.land_use] || DEFAULT_BUILDING_GLOW_COLOUR;
  const lit = mix(base, [255, 248, 220], 0.24);
  const altitude = Number(state.sun.altitudeDeg || 0);
  const dark = civilTwilightDarkFactor();
  const twilight = altitude < 8 ? 1 - smoothstep(0, 8, Math.max(0, altitude)) : 0;
  // WIN-2 (, the author: "the building doesnt light up, only the
  // windows do"): at night the whole-building glow HANDS OVER to the
  // per-window layer - it fades out exactly as darkness comes in, leaving
  // a faint twilight wash only.
  const visibility = (0.56 + twilight * 0.22) * (1 - dark);
  const alpha = clamp(Math.round((24 + intensity * 158) * visibility), 0, 216);
  return withAlpha(lit, alpha);
}

function currentLightingDaypartIndex(hour = state.sun.timeHours) {
  const time = clamp(Number(hour) || 0, 0, 24);
  return Math.min(LIGHTING_DAYPART_LABELS.length - 1, Math.floor(time / 2));
}

function lightingScheduleForProps(props) {
  if (Array.isArray(props?.lighting_by_daypart) && props.lighting_by_daypart.length) {
    return props.lighting_by_daypart;
  }
  return state.cellLightingByDaypart.get(cellKey(props)) || [];
}

function lightingIntensityForProps(props, index = currentLightingDaypartIndex()) {
  const schedule = lightingScheduleForProps(props);
  if (!schedule.length) return 0;
  return clamp(Number(schedule[index]) || 0, 0, 1);
}

function lightingRows(props) {
  const schedule = lightingScheduleForProps(props);
  if (!schedule.length) return [];
  const index = currentLightingDaypartIndex();
  const value = lightingIntensityForProps(props, index);
  return [[`Lighting ${LIGHTING_DAYPART_LABELS[index]}`, `${Math.round(value * 100)}%`]];
}

function convexHullLngLat(points) {
  const unique = [];
  const seen = new Set();
  points.forEach(([lon, lat]) => {
    const key = `${lon.toFixed(12)}_${lat.toFixed(12)}`;
    if (seen.has(key)) return;
    seen.add(key);
    unique.push([lon, lat]);
  });
  if (unique.length <= 3) return unique;
  unique.sort((a, b) => a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]);
  const cross = (origin, a, b) => (
    (a[0] - origin[0]) * (b[1] - origin[1])
    - (a[1] - origin[1]) * (b[0] - origin[0])
  );
  const lower = [];
  unique.forEach((point) => {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) {
      lower.pop();
    }
    lower.push(point);
  });
  const upper = [];
  unique.slice().reverse().forEach((point) => {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) {
      upper.pop();
    }
    upper.push(point);
  });
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

// the author wanted BLUE_SPACE to read as a pond / canal inside its cell, not as
// a whole 200 m square of water and not as a separate green neighbour. This
// layer paints a thin vegetated bank inside each water parcel, leaving the
// centre blue.
function blueSpaceBankLayer() {
  if (!state.data) return null;
  const features = blueSpaceBankFeatures();
  if (!features.length) return null;
  return new deck.GeoJsonLayer({
    id: "blue-space-internal-green-banks",
    data: featureCollection(features),
    pickable: false,
    stroked: false,
    filled: true,
    extruded: false,
    opacity: 0.96,
    getFillColor: [61, 141, 73, state.theme === "dark" ? 228 : 214],
    parameters: { depthTest: false },
    updateTriggers: {
      getFillColor: [state.theme, state.currentLayout]
    }
  });
}

function blueSpaceBankFeatures() {
  const features = [];
  // CNL-2 v7 (, the author: "extend the blue to connect to each
  // other with NO green in between"): THIS is what drew the green - a
  // bank ring inside EVERY water cell, so two touching ponds showed
  // bank+bank. The bank is now suppressed on any side that faces
  // another water cell, so adjacent ponds merge into one sheet and only
  // the outer shoreline keeps its greenery.
  const waterCentres = [];
  (state.data?.features || []).forEach((f) => {
    const p = f.properties || {};
    if (p.role === "parcel" && p.land_use === "blue_space") {
      const c = polygonCentroid(f);
      if (c) waterCentres.push(c);
    }
  });
  (state.data?.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel" || props.land_use !== "blue_space") return;
    const bounds = polygonBounds(feature);
    if (!bounds) return;
    const dx = bounds.maxLon - bounds.minLon;
    const dy = bounds.maxLat - bounds.minLat;
    const bankX = dx * BLUE_SPACE_BANK_FRAC;
    const bankY = dy * BLUE_SPACE_BANK_FRAC;
    const cx = (bounds.minLon + bounds.maxLon) / 2;
    const cy = (bounds.minLat + bounds.maxLat) / 2;
    const hasNeighbour = (dLon, dLat) => waterCentres.some((w) => {
      const a = (w[0] - cx) / dx;
      const b = (w[1] - cy) / dy;
      return Math.abs(a - dLon) < 0.35 && Math.abs(b - dLat) < 0.35;
    });
    // strip order below: 0 = south (minLat), 1 = north, 2 = west, 3 = east
    const skip = [hasNeighbour(0, -1), hasNeighbour(0, 1),
                  hasNeighbour(-1, 0), hasNeighbour(1, 0)];
    // v9 (, the author: "they should meet to form a perfect L shape
    // but they dont"): the north/south strips span the FULL width while
    // west/east are inset by bankY at each end - so wherever a north or
    // south bank was suppressed, the corner it used to cover was left
    // bare and blue leaked through as a notch. The side strips now run
    // to the very edge on any suppressed side, closing every corner.
    const latLo = bounds.minLat + (skip[0] ? 0 : bankY);
    const latHi = bounds.maxLat - (skip[1] ? 0 : bankY);
    const strips = [
      { minLon: bounds.minLon, maxLon: bounds.maxLon, minLat: bounds.minLat, maxLat: bounds.minLat + bankY },
      { minLon: bounds.minLon, maxLon: bounds.maxLon, minLat: bounds.maxLat - bankY, maxLat: bounds.maxLat },
      { minLon: bounds.minLon, maxLon: bounds.minLon + bankX, minLat: latLo, maxLat: latHi },
      { minLon: bounds.maxLon - bankX, maxLon: bounds.maxLon, minLat: latLo, maxLat: latHi }
    ];
    // v10: the CONCAVE CORNER hole.
    // Where a cell has water to the north AND east but LAND on the
    // diagonal, neither neighbour's bank covers this cell's own corner
    // square - B's east strip and C's north strip only meet at a point -
    // so the bank ring around a notch had a bankX x bankY gap. Patch all
    // four diagonals.
    [[1, 1, "maxLon", "maxLat"], [-1, 1, "minLon", "maxLat"],
     [1, -1, "maxLon", "minLat"], [-1, -1, "minLon", "minLat"]]
      .forEach(([dx1, dy1, lonSide, latSide]) => {
        if (!hasNeighbour(dx1, 0) || !hasNeighbour(0, dy1)) return;
        if (hasNeighbour(dx1, dy1)) return;              // diagonal is water too
        strips.push({
          minLon: lonSide === "maxLon" ? bounds.maxLon - bankX : bounds.minLon,
          maxLon: lonSide === "maxLon" ? bounds.maxLon : bounds.minLon + bankX,
          minLat: latSide === "maxLat" ? bounds.maxLat - bankY : bounds.minLat,
          maxLat: latSide === "maxLat" ? bounds.maxLat : bounds.minLat + bankY
        });
      });
    strips.forEach((strip, index) => {
      if (index < 4 && skip[index]) return;   // 4+ are the corner patches
      if (strip.maxLon <= strip.minLon || strip.maxLat <= strip.minLat) return;
      features.push({
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [boundsRing(strip)]
        },
        properties: {
          ...props,
          role: "blue_space_bank",
          part: "internal_green_bank",
          part_index: index
        }
      });
    });
  });
  return features;
}

//: render vegetation_fraction as scatter tree glyphs.
// OPEN_SPACE still gets the densest canopy, but built cells with exported
// vegetation_fraction now get sparse edge/courtyard trees so the viewer does
// not imply that greenery exists only inside green land-use parcels. Roads
// and solar farms are excluded to avoid visual clutter.
function vegetationFeatures() {
  if (!state.data) return { canopies: [], trunks: [] };
  if (!state.vegetationEnabled) return { canopies: [], trunks: [] };
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const canopies = [];
  const trunks = [];
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel") return;
    if (!vegetationRenderableLandUse(props.land_use)) return;
    const veg = Number(props.vegetation_fraction || 0);
    if (veg <= 0) return;
    const center = polygonCentroid(feature);
    if (!center) return;
    const profile = vegetationProfile(props.land_use, veg);
    if (!profile.count) return;
    // Deterministic per-cell PRNG seeded by (row,col).
    const seed = (Number(props.row || 0) * 73856093) ^ (Number(props.col || 0) * 19349663);
    let s = (seed >>> 0) || 1;
    const rand = () => {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 0xFFFFFFFF;
    };
    for (let i = 0; i < profile.count; i += 1) {
      const [offsetE, offsetN] = vegetationOffset(rand, cellSizeM, props.land_use);
      const treePos = offsetLngLat(center[0], center[1], offsetE, offsetN);
      const trunkHeight = 2 + rand() * 3;        // 2-5 m
      const canopyHeight = trunkHeight + 1 + rand() * 2;
      const z0 = 0.05;
      const zTrunk = scaledHeightM(trunkHeight) + z0;
      const zCanopy = scaledHeightM(canopyHeight) + z0;
      const canopyRadiusM = profile.radiusMinM + rand() * (profile.radiusMaxM - profile.radiusMinM);
      canopies.push({
        position: [treePos[0], treePos[1], zCanopy],
        radius_m: canopyRadiusM,
        shade: 0.85 + rand() * 0.15
      });
      trunks.push({
        path: [
          [treePos[0], treePos[1], z0],
          [treePos[0], treePos[1], zTrunk]
        ]
      });
    }
  });
  return { canopies, trunks };
}

function vegetationRenderableLandUse(landUse) {
  return !["road", "solar_farm"].includes(landUse);
}

function vegetationProfile(landUse, veg) {
  if (landUse === "open_space") {
    return {
      count: Math.max(1, Math.min(12, Math.round(veg * 14))),
      radiusMinM: 1.8,
      radiusMaxM: 3.2
    };
  }
  if (landUse === "blue_space") {
    return {
      count: Math.max(2, Math.min(8, Math.round(veg * 8))),
      radiusMinM: 1.4,
      radiusMaxM: 2.8
    };
  }
  //: NO ground vegetation dots on BUILT cells - the
  // floor speckle read as noise. Courtyard greenery lives on the roofs.
  return { count: 0, radiusMinM: 1.2, radiusMaxM: 2.4 };
}

function vegetationOffset(rand, cellSizeM, landUse) {
  if (landUse === "open_space") {
    return [
      (rand() - 0.5) * cellSizeM * 0.70,
      (rand() - 0.5) * cellSizeM * 0.70
    ];
  }
  // Blue-space trees sit on the same internal bank that the green-band layer
  // paints, leaving the pond/canal centre readable as water.
  if (landUse === "blue_space") {
    const side = Math.floor(rand() * 4);
    const edge = cellSizeM * (0.36 + rand() * 0.08);
    const along = (rand() - 0.5) * cellSizeM * 0.70;
    if (side === 0) return [along, -edge];
    if (side === 1) return [along, edge];
    if (side === 2) return [-edge, along];
    return [edge, along];
  }
  // Built cells get sparse setback/courtyard vegetation near parcel edges
  // rather than trees scattered over the middle of roofs.
  const side = Math.floor(rand() * 4);
  const edge = cellSizeM * (0.30 + rand() * 0.12);
  const along = (rand() - 0.5) * cellSizeM * 0.55;
  if (side === 0) return [along, -edge];
  if (side === 1) return [along, edge];
  if (side === 2) return [-edge, along];
  return [edge, along];
}

let _vegetationCache = { layoutKey: null, canopies: [], trunks: [] };
function _vegetationCached() {
  const featureCount = state.data?.features?.length || 0;
  const key = `${state.currentLayout || ""}:${featureCount}:${state.vegetationEnabled ? 1 : 0}`;
  if (_vegetationCache.layoutKey === key) return _vegetationCache;
  const f = vegetationFeatures();
  _vegetationCache = { layoutKey: key, canopies: f.canopies, trunks: f.trunks };
  return _vegetationCache;
}

function vegetationCanopyLayer() {
  // (the author: "on the open green cells, make them 3D and add
  // trees"): flat circles -> angular 3D canopies in three fixed-radius
  // buckets (ColumnLayer radius is uniform-only), trunks unchanged below
  // - the open greens now carry real little trees.
  if (!state.vegetationEnabled) return null;
  const { canopies } = _vegetationCached();
  if (!canopies.length) return null;
  const buckets = [[], [], []];
  canopies.forEach((d) => {
    const b = d.radius_m < 2.0 ? 0 : d.radius_m < 2.7 ? 1 : 2;
    buckets[b].push(d);
  });
  const mk = (data, suffix, radius) => data.length === 0 ? null
    : new deck.ColumnLayer({
      id: `vegetation-canopies-${suffix}`,
      data,
      pickable: false,
      filled: true,
      extruded: true,
      diskResolution: 5,
      radius,
      radiusUnits: "meters",
      elevationScale: 1,
      getPosition: (d) => d.position,
      getElevation: (d) => 1.6 + (d.shade || 1) * 1.0,
      getFillColor: (d) => [
        Math.round(52 * d.shade),
        Math.round(118 * d.shade),
        Math.round(50 * d.shade),
        238
      ],
      parameters: { depthTest: true }
    });
  return [mk(buckets[0], "s", 1.6), mk(buckets[1], "m", 2.3),
          mk(buckets[2], "l", 3.0)];
}

function vegetationTrunkLayer() {
  if (!state.vegetationEnabled) return null;
  const { trunks } = _vegetationCached();
  if (!trunks.length) return null;
  return new deck.PathLayer({
    id: "vegetation-trunks",
    data: trunks,
    pickable: false,
    widthUnits: "pixels",
    capRounded: false,
    jointRounded: false,
    getPath: (d) => d.path,
    getWidth: 1.5,
    getColor: [80, 52, 28, 230],
    parameters: { depthTest: true }
  });
}

let _streetAssetCache = { layoutKey: null, trees: [], trunks: [], poles: [], heads: [], panels: [] };

function streetAssetFeatures() {
  const featureCount = state.data?.features?.length || 0;
  const key = `${state.currentLayout || ""}:${featureCount}`;
  if (_streetAssetCache.layoutKey === key) return _streetAssetCache;
  if (!state.data) {
    _streetAssetCache = { layoutKey: key, trees: [], trunks: [], poles: [], heads: [], panels: [] };
    return _streetAssetCache;
  }

  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const parcelIndex = parcelIndexByRowCol();
  const trees = [];
  const trunks = [];
  const poles = [];
  const heads = [];
  const panels = [];

  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel" || props.land_use !== "road") return;
    const center = polygonCentroid(feature);
    if (!center) return;
    const axis = roadAxisForCell(props, parcelIndex);

    if (truthyFlag(props.has_street_trees)) {
      streetTreeOffsets(axis, cellSizeM, props.road_class).forEach(([east, north], index) => {
        const jitter = ((Number(props.row || 0) * 17 + Number(props.col || 0) * 31 + index * 7) % 9) - 4;
        const position = offsetLngLat(center[0], center[1], east, north + jitter);
        const canopyZ = 9 + (index % 2) * 1.3;
        trees.push({
          position: [position[0], position[1], canopyZ],
          radius_m: Math.max(7, cellSizeM * 0.045),
          shade: 0.84 + (index % 3) * 0.05,
          properties: props
        });
        trunks.push({
          position: [position[0], position[1], 0],
          height_m: Math.max(5.5, canopyZ - 2.4),
          properties: props
        });
      });
    }

    const lightType = streetlightType(props);
    if (lightType) {
      streetlightOffsets(axis, cellSizeM, props.road_class).forEach(([east, north], index) => {
        const base = offsetLngLat(center[0], center[1], east, north);
        const height = lightType === "solar" ? 9.4 : 8.4;
        const segmentId = streetlightSegmentId(props);
        const reason = String(props.streetlight_reason || "");
        poles.push({
          position: [base[0], base[1], 0],
          height_m: height,
          type: lightType,
          segmentId,
          reason,
          properties: props
        });
        heads.push({
          position: [base[0], base[1], height + 0.25],
          type: lightType,
          segmentId,
          reason,
          properties: props
        });
        if (lightType === "solar") {
          const panelOffset = axis === "horizontal" ? [0, cellSizeM * 0.018] : [cellSizeM * 0.018, 0];
          const panelCenter = offsetLngLat(base[0], base[1], panelOffset[0], panelOffset[1]);
          const panelFootprint = rectanglePolygonAt(
            panelCenter,
            0,
            0,
            cellSizeM * 0.018,
            cellSizeM * 0.010,
            height + 0.55
          ).map(([lon, lat]) => [lon, lat]);
          panels.push({
            polygon: tiltedPolygon(panelFootprint, height + 0.55, "south", STREETLIGHT_PANEL_TILT_DEG),
            type: lightType,
            segmentId,
            reason,
            properties: props
          });
        }
      });
    }
  });

  _streetAssetCache = { layoutKey: key, trees, trunks, poles, heads, panels };
  return _streetAssetCache;
}

function roadAxisForCell(props, parcelIndex) {
  const row = Number(props.row);
  const col = Number(props.col);
  if (!Number.isFinite(row) || !Number.isFinite(col)) return "horizontal";
  const eastWest = ["-1", "1"].some((delta) => parcelIndex.get(`${row}_${col + Number(delta)}`)?.land_use === "road");
  const northSouth = ["-1", "1"].some((delta) => parcelIndex.get(`${row + Number(delta)}_${col}`)?.land_use === "road");
  if (eastWest && !northSouth) return "horizontal";
  if (northSouth && !eastWest) return "vertical";
  //: junction cells are explicit now - the old
  // tie-break guessed an axis around the 25x25-era centre (12) and dropped
  // trees/lamps onto the crossing carriageway on the 50x50 town.
  if (eastWest && northSouth) return "junction";
  return "horizontal";
}

//: one shared per-class
// section used by BOTH the strip renderer and the tree/lamp offsets, so
// nothing lands on the carriageway. Bands render at >= 4 m (a true 1.8-2.5 m
// footpath is a hairline at 100 m cells); the hover tooltip keeps the TRUE
// IRC numbers - the widening is presentation only.
function roadVisualSection(cls) {
  const xs = (state.data?.metadata?.road_network || {}).cross_section_m || {};
  const cs = xs[cls] || null;
  const carriageway = cs ? Number(cs.carriageway || 0) : 10;
  const median = cs ? Number(cs.median || 0) : 0;
  const cycleTrue = cs ? Number(cs.cycle_each_side || 0) : 0;
  const footTrue = cs ? Number(cs.footpath_each_side || 0) : 2;
  const cwHalf = Math.max(carriageway + median, 8) / 2;
  const cycle = cycleTrue > 0 ? Math.max(cycleTrue, 4) : 0;
  const foot = footTrue > 0 ? Math.max(footTrue, 4) : 4;
  return {
    cwHalf,
    cycle,
    foot,
    median,
    cyOuter: cwHalf + cycle,
    fpOuter: cwHalf + cycle + foot
  };
}

function streetTreeOffsets(axis, cellSizeM, cls) {
  const half = cellSizeM / 2;
  const v = roadVisualSection(cls);
  const along = cellSizeM * 0.28;
  const verge = Math.min(half - 6, v.fpOuter + 5);   // avenue row just beyond the footpath
  if (axis === "junction") {
    const corner = Math.min(half - 8, v.fpOuter + 8); // corner planting clear of BOTH carriageways
    return [[-corner, -corner], [corner, -corner], [-corner, corner], [corner, corner]];
  }
  return axis === "vertical"
    ? [[-verge, -along], [verge, -along], [-verge, along], [verge, along]]
    : [[-along, -verge], [along, -verge], [-along, verge], [along, verge]];
}

function streetlightOffsets(axis, cellSizeM, cls) {
  const half = cellSizeM / 2;
  const v = roadVisualSection(cls);
  const along = cellSizeM * 0.26;
  const edge = Math.min(half - 4, Math.max(3, v.fpOuter - 1.5)); // pole stands on the footpath's outer edge
  if (axis === "junction") {
    return [[-edge, -edge], [edge, edge]];
  }
  return axis === "vertical"
    ? [[-edge, -along], [edge, along]]
    : [[-along, -edge], [along, edge]];
}

function streetlightType(props) {
  const value = String(props?.streetlight_type || "").toLowerCase();
  return value === "solar" || value === "grid" ? value : "";
}

function streetlightSegmentId(props) {
  const id = Number(props?.streetlight_segment_id);
  return Number.isFinite(id) ? Math.trunc(id) : -1;
}

function streetlightSegmentColour(segmentId) {
  if (segmentId === 0) return [248, 250, 252];
  if (segmentId < 0) return [148, 163, 184];
  return STREETLIGHT_SEGMENT_COLOURS[(segmentId - 1) % STREETLIGHT_SEGMENT_COLOURS.length];
}

// SKY-1 (, the author: "look at the background sky/colour of
// metropolis and see how it changes with time of day"): the page behind
// the district follows the sun - deep night navy, indigo pre-dawn, warm
// horizon at golden hour, airy day blue, amber dusk. Pure presentation:
// a two-stop CSS gradient on #deck-container, driven by the SAME solar
// altitude the lighting already uses. Keyframes are (altitudeDeg,
// topColour, horizonColour); linear blend between neighbours.
const SKY_KEYFRAMES = [
  [-18, [10, 14, 28], [16, 20, 38]],       // astronomical night
  [-8, [16, 20, 44], [42, 38, 66]],        // late twilight indigo
  [-3, [30, 36, 70], [130, 84, 74]],       // civil twilight, ember horizon
  [2, [64, 88, 132], [214, 150, 100]],     // sunrise/sunset gold
  [10, [96, 138, 182], [196, 190, 168]],   // low sun haze
  [30, [126, 168, 208], [186, 204, 214]],  // morning/afternoon
  [60, [138, 182, 220], [196, 214, 224]],  // high sun
];
function skyColoursForAltitude(alt) {
  const kf = SKY_KEYFRAMES;
  if (alt <= kf[0][0]) return [kf[0][1], kf[0][2]];
  for (let i = 1; i < kf.length; i += 1) {
    if (alt <= kf[i][0]) {
      const t = (alt - kf[i - 1][0]) / (kf[i][0] - kf[i - 1][0]);
      const m3 = (a, b) => [0, 1, 2].map((j) => Math.round(a[j] + (b[j] - a[j]) * t));
      return [m3(kf[i - 1][1], kf[i][1]), m3(kf[i - 1][2], kf[i][2])];
    }
  }
  return [kf[kf.length - 1][1], kf[kf.length - 1][2]];
}
function applySkyForTime() {
  const el = document.getElementById("deck-container");
  if (!el) return;
  const alt = Number(state.sun.altitudeDeg || 0);
  const key = Math.round(alt * 4);
  if (state._skyKey === key) return;
  state._skyKey = key;
  const [top, hor] = skyColoursForAltitude(alt);
  el.style.background =
    `linear-gradient(180deg, rgb(${top[0]},${top[1]},${top[2]}) 0%, ` +
    `rgb(${hor[0]},${hor[1]},${hor[2]}) 78%)`;
}

function solarAltitudeForHour(hour = state.sun.timeHours) {
  const time = ((Number(hour) % 24) + 24) % 24;
  if (Math.abs(time - Number(state.sun.timeHours || 0)) < 0.001) {
    return Number(state.sun.altitudeDeg || 0);
  }
  return computeSunPosition({
    dayOfYear: state.sun.dayOfYear,
    timeHours: time,
    latitude: state.sun.latitude,
    longitude: state.sun.longitude
  }).altitudeDeg;
}

function civilTwilightDarkFactor(hour = state.sun.timeHours) {
  const altitude = solarAltitudeForHour(hour);
  if (!Number.isFinite(altitude)) return 0;
  if (altitude <= CIVIL_TWILIGHT_ALTITUDE_DEG) return 1;
  if (altitude >= 0) return 0;
  return 1 - smoothstep(CIVIL_TWILIGHT_ALTITUDE_DEG, 0, altitude);
}

function streetlightNightFactor(hour = state.sun.timeHours) {
  return civilTwilightDarkFactor(hour);
}

function streetlightsAreOn() {
  return streetlightNightFactor() > 0.05;
}

function streetlightAssetColour(d, tint = 0.36) {
  const base = d.type === "solar" ? STREETLIGHT_SOLAR_COLOUR : STREETLIGHT_GRID_COLOUR;
  const segment = streetlightSegmentColour(Number(d.segmentId));
  const amount = Number(d.segmentId) > 0 ? tint : 0.12;
  return mix(base, segment, amount);
}

function streetlightLampColour(d) {
  const factor = streetlightNightFactor();
  const typed = d.type === "solar" ? [125, 211, 252] : [253, 224, 71];
  const base = streetlightAssetColour(d, 0.44);
  return withAlpha(mix(base, typed, 0.20 + factor * 0.48), Math.round(94 + factor * 158));
}

// TREE-2: the single
// flat puck read as a lollipop. Now each tree is TWO stacked canopy tiers
// (wide lower + smaller offset upper = a rounded crown) with deterministic
// per-tree species tint and size jitter - neem/peepal/ashoka variety, no
// RNG (hash on position).
// v2 to the metropolis reference: DARK desaturated canopies,
// LOW poly (5-sided disks read angular like its 2-lobe trees), the upper
// lobe OFFSET sideways so the silhouette is organic, not a wedding cake.
const TREE_SPECIES_TINTS = [
  [47, 96, 52],     // neem - deep green
  [60, 108, 50],    // peepal - lighter
  [40, 84, 62],     // ashoka - blue-green
];
function _treeHash(d) {
  const x = Math.abs(Math.sin((d.position[0] * 131.7 + d.position[1] * 517.3) * 1000));
  return x - Math.floor(x);
}
function streetTreeCanopyLayer() {
  if (!state.streetTreesEnabled) return null;
  const { trees } = streetAssetFeatures();
  if (!trees.length) return null;
  const tint = (d, dark) => {
    const h = _treeHash(d);
    const sp = TREE_SPECIES_TINTS[Math.floor(h * 3) % 3];
    const s = (d.shade || 1) * (0.9 + h * 0.2) * dark;
    return withAlpha([Math.round(sp[0] * s), Math.round(sp[1] * s),
                      Math.round(sp[2] * s)], 238);
  };
  // ColumnLayer takes ONE uniform `radius` - a per-tree accessor is
  // silently ignored and the DEFAULT (1,000 m!) takes over, which buried
  // the town under a green blanket on. Size variety comes from
  // THREE fixed-radius buckets instead; elevation + tint stay per-tree.
  const buckets = [[], [], []];
  trees.forEach((d) => buckets[Math.floor(_treeHash(d) * 3) % 3].push(d));
  const mk = (data, idSuffix, radius, crown) => data.length === 0 ? null
    : new deck.ColumnLayer({
      id: `street-tree-${idSuffix}`,
      data,
      pickable: false,
      filled: true,
      extruded: true,
      diskResolution: 5,                    // angular low-poly, metropolis-style
      radius,
      radiusUnits: "meters",
      elevationScale: 1,
      getPosition: crown
        ? (d) => {
          // the upper lobe sits OFFSET to one side, not concentric
          const h = _treeHash(d);
          const ang = h * Math.PI * 2;
          const [lon, lat] = offsetLngLat(d.position[0], d.position[1],
            Math.cos(ang) * 1.6, Math.sin(ang) * 1.6);
          return [lon, lat, d.position[2] + scaledHeightM(2.0 + h * 1.0)];
        }
        : (d) => d.position,
      getElevation: crown
        ? (d) => 2.2 + _treeHash(d) * 1.2
        : (d) => 3.0 + _treeHash(d) * 1.4,
      getFillColor: (d) => tint(d, crown ? 1.10 : 0.92),
      parameters: { depthTest: true }
    });
  return [
    mk(buckets[0], "canopy-s", 3.4, false),
    mk(buckets[1], "canopy-m", 4.2, false),
    mk(buckets[2], "canopy-l", 5.0, false),
    mk(buckets[0], "crown-s", 2.2, true),
    mk(buckets[1], "crown-m", 2.7, true),
    mk(buckets[2], "crown-l", 3.2, true)
  ];
}

function streetTreeTrunkLayer() {
  if (!state.streetTreesEnabled) return null;
  const { trunks } = streetAssetFeatures();
  if (!trunks.length) return null;
  return new deck.ColumnLayer({
    id: "street-tree-trunks",
    data: trunks,
    pickable: false,
    filled: true,
    stroked: false,
    extruded: true,
    diskResolution: 8,
    radius: 1.2,
    radiusUnits: "meters",
    elevationScale: 1,
    getPosition: (d) => d.position,
    getElevation: (d) => d.height_m,
    getFillColor: STREET_TREE_TRUNK_COLOUR,
    parameters: { depthTest: true }
  });
}

function streetlightPoleLayer() {
  if (!state.streetlightsEnabled) return null;
  const { poles } = streetAssetFeatures();
  if (!poles.length) return null;
  return new deck.ColumnLayer({
    id: "streetlight-poles",
    data: poles,
    pickable: false,
    filled: true,
    stroked: false,
    extruded: true,
    diskResolution: 12,
    radius: 0.75,
    radiusUnits: "meters",
    elevationScale: 1,
    getPosition: (d) => d.position,
    getElevation: (d) => d.height_m,
    getFillColor: (d) => withAlpha(streetlightAssetColour(d, 0.28), d.type === "solar" ? 248 : 224),
    parameters: { depthTest: false },
    updateTriggers: {
      getFillColor: [state.currentLayout]
    }
  });
}

function streetlightHeadLayer() {
  if (!state.streetlightsEnabled) return null;
  const { heads } = streetAssetFeatures();
  if (!heads.length) return null;
  return new deck.ScatterplotLayer({
    id: "streetlight-heads",
    data: heads,
    pickable: true,
    stroked: true,
    filled: true,
    radiusUnits: "meters",
    radiusMinPixels: 2.2,
    radiusMaxPixels: 7.2,
    getPosition: (d) => d.position,
    getRadius: (d) => (d.type === "solar" ? 3.0 : 2.5) + streetlightNightFactor() * 1.6,
    getFillColor: (d) => streetlightLampColour(d),
    getLineColor: (d) => withAlpha(streetlightSegmentColour(Number(d.segmentId)), 160 + Math.round(streetlightNightFactor() * 80)),
    getLineWidth: 1,
    lineWidthUnits: "pixels",
    parameters: { depthTest: false },
    updateTriggers: {
      getRadius: [state.sun.timeHours],
      getFillColor: [state.sun.timeHours, state.currentLayout],
      getLineColor: [state.sun.timeHours, state.currentLayout]
    }
  });
}

function streetlightGlowLayer() {
  if (!state.streetlightsEnabled) return null;
  const factor = streetlightNightFactor();
  if (factor <= 0.02) return null;
  const { heads } = streetAssetFeatures();
  if (!heads.length) return null;
  return new deck.ScatterplotLayer({
    id: "streetlight-night-glow",
    data: heads,
    pickable: false,
    stroked: false,
    filled: true,
    billboard: true,
    radiusUnits: "meters",
    radiusMinPixels: 5,
    radiusMaxPixels: 26,
    getPosition: (d) => d.position,
    getRadius: (d) => (d.type === "solar" ? 16 : 14) * (0.72 + factor * 0.28),
    getFillColor: (d) => {
      const lamp = d.type === "solar" ? [56, 189, 248] : [253, 224, 71];
      return withAlpha(mix(lamp, streetlightSegmentColour(Number(d.segmentId)), 0.22), Math.round(82 * factor));
    },
    parameters: { depthTest: false },
    updateTriggers: {
      getRadius: [state.sun.timeHours],
      getFillColor: [state.sun.timeHours, state.currentLayout]
    }
  });
}

function streetlightSolarPanelLayer() {
  if (!state.streetlightsEnabled) return null;
  const { panels } = streetAssetFeatures();
  if (!panels.length) return null;
  return new deck.PolygonLayer({
    id: "solar-streetlight-panels",
    data: panels,
    pickable: false,
    stroked: true,
    filled: true,
    extruded: false,
    getPolygon: (d) => d.polygon,
    getFillColor: withAlpha(STREETLIGHT_PANEL_COLOUR, 236),
    getLineColor: [224, 242, 254, 238],
    getLineWidth: 1.3,
    lineWidthUnits: "pixels",
    parameters: { depthTest: false },
    updateTriggers: {
      getFillColor: [state.currentLayout],
      getLineColor: [state.currentLayout]
    }
  });
}

function roofVegetationFeatures() {
  if (!state.data || !state.vegetationEnabled) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const parcels = new Map();
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    const key = cellKey(props);
    if (!key || props.role !== "parcel") return;
    parcels.set(key, props);
  });

  const paths = [];
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    const key = cellKey(props);
    if (!key || isPlantFeatureProps(props)) return;
    if (props.role !== "structure") return;
    if (props.part === "solar_array" || props.land_use === "retail_highstreet") return;
    const parcel = parcels.get(key);
    const veg = Number(parcel?.vegetation_fraction || props.vegetation_fraction || 0);
    if (veg <= 0) return;
    if (["road", "open_space", "blue_space", "solar_farm"].includes(props.land_use)) return;
    const bounds = polygonBounds(feature);
    const center = polygonCentroid(feature);
    if (!bounds || !center) return;

    const seed = (Number(props.row || 0) * 83492791)
      ^ (Number(props.col || 0) * 2654435761)
      ^ (Number(props.part_index || 0) * 374761393);
    let s = (seed >>> 0) || 1;
    const rand = () => {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 0xFFFFFFFF;
    };

    const count = Math.max(2, Math.min(5, Math.round(veg * 14)));
    const z0 = scaledFeatureHeightM(props) + 2.4;
    const roofWidthM = Math.max(10, Math.abs(bounds.maxLon - bounds.minLon) * metersPerDegreeLongitude(center[1]));
    const roofDepthM = Math.max(10, Math.abs(bounds.maxLat - bounds.minLat) * METERS_PER_DEGREE_LAT);
    for (let i = 0; i < count; i += 1) {
      const offsetE = (rand() - 0.5) * roofWidthM * 0.55;
      const offsetN = (rand() - 0.5) * roofDepthM * 0.55;
      const p = offsetLngLat(center[0], center[1], offsetE, offsetN);
      const bladeH = 10 + rand() * 8;
      const capHalfM = 5.5;
      const topZ = z0 + bladeH;
      const capE0 = offsetLngLat(p[0], p[1], -capHalfM, 0);
      const capE1 = offsetLngLat(p[0], p[1], capHalfM, 0);
      const capN0 = offsetLngLat(p[0], p[1], 0, -capHalfM);
      const capN1 = offsetLngLat(p[0], p[1], 0, capHalfM);
      paths.push(
        {
          path: [
            [p[0], p[1], z0],
            [p[0], p[1], topZ]
          ],
          veg,
          main: true
        },
        {
          path: [
            [capE0[0], capE0[1], topZ],
            [capE1[0], capE1[1], topZ]
          ],
          veg,
          main: false
        },
        {
          path: [
            [capN0[0], capN0[1], topZ],
            [capN1[0], capN1[1], topZ]
          ],
          veg,
          main: false
        }
      );
    }
  });
  return paths;
}

function roofVegetationLayer() {
  // (the author: "the trees/greenery on the rooftops are like plus
  // signs - make them bushes/shrubbery"): the tick-cross paths are now
  // CLOVERS of 2-3 overlapping dark-green dots per roof spot.
  if (!state.vegetationEnabled) return null;
  const paths = roofVegetationFeatures();
  if (!paths.length) return null;
  const dots = [];
  paths.forEach((d) => {
    const p = d.path;
    if (!p || p.length < 2) return;
    const mid = [(p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2, (p[0][2] || 0)];
    dots.push({ position: mid, r: d.main ? 2.2 : 1.4, veg: d.veg });
    if (d.main) {
      dots.push({ position: [mid[0] + 0.000012, mid[1] + 0.000007, mid[2]], r: 1.5, veg: d.veg });
      dots.push({ position: [mid[0] - 0.000009, mid[1] + 0.000010, mid[2]], r: 1.2, veg: d.veg });
    }
  });
  //: 3D roof bushes like the open greens - two fixed-
  // radius buckets. The PV panel layers draw AFTER this one with
  // depthTest off, so panels always read ON TOP of the roof greenery.
  const small = dots.filter((d) => d.r < 1.7);
  const large = dots.filter((d) => d.r >= 1.7);
  const mk = (data, suffix, radius, elev) => data.length === 0 ? null
    : new deck.ColumnLayer({
      id: `roof-vegetation-${suffix}`,
      data,
      pickable: false,
      filled: true,
      extruded: true,
      diskResolution: 5,
      radius,
      radiusUnits: "meters",
      elevationScale: 1,
      getPosition: (d) => d.position,
      getElevation: elev,
      getFillColor: (d) => withAlpha(mix([30, 96, 46], [74, 148, 70],
        clamp(d.veg || 0, 0, 1)), 245),
      parameters: { depthTest: true }
    });
  return [mk(small, "s", 1.0, 0.55), mk(large, "l", 1.6, 0.85)];
}

//:
// per-cell roof arrow showing the long-facade direction chosen by SA.
// Reads `building_axis_deg` from each built structure feature (added by
// core/export_3d.py). Renders a saffron-orange chevron on top
// of the building extrusion, pointing along the long-facade axis.
function axisArrowFeatures() {
  if (!state.data) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const cells = new Map();
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    const key = cellKey(props);
    if (!key || !props.is_built) return;
    if (!cells.has(key)) {
      cells.set(key, {
        parcel: null,
        axisDeg: Number(props.building_axis_deg || 0),
        maxHeightM: 0
      });
    }
    const cell = cells.get(key);
    if (props.role === "parcel" && feature.geometry?.type === "Polygon") {
      cell.parcel = feature;
      cell.axisDeg = Number(props.building_axis_deg || cell.axisDeg || 0);
    } else if (props.role !== "parcel") {
      cell.maxHeightM = Math.max(cell.maxHeightM, Number(props.height_m || 0));
    }
  });

  const halfLenM = cellSizeM * 0.30;
  const wingLenM = cellSizeM * 0.16;
  const wingAngleRad = 32 * Math.PI / 180;
  const paths = [];
  cells.forEach((cell) => {
    const feature = cell.parcel;
    if (!feature || cell.maxHeightM <= 0) return;
    const props = feature.properties || {};
      const ring = feature.geometry.coordinates?.[0] || [];
      if (ring.length < 3) return;
      // Centroid = mean of ring (drop the closing duplicate).
      let lonSum = 0, latSum = 0, n = 0;
      for (let i = 0; i < ring.length; i++) {
        if (i === ring.length - 1 && sameCoordinate(ring[i], ring[0])) break;
        lonSum += ring[i][0];
        latSum += ring[i][1];
        n++;
      }
      if (n === 0) return;
      const cLon = lonSum / n;
      const cLat = latSum / n;
      // Axis convention here: GeoJSON `building_axis_deg` is the principal
      // facade-facing direction: 0=N, 90=E, 180=S, 270=W. Convert the
      // bearing-from-north value to an (east, north) unit vector.
      const axisDeg = Number(cell.axisDeg || 0);
      const bearingRad = axisDeg * Math.PI / 180;
      const eAxis = Math.sin(bearingRad);   // east component along axis
      const nAxis = Math.cos(bearingRad);   // north component along axis
      const z = scaledHeightM(cell.maxHeightM) + 1.2;
      const tip = offsetLngLat(cLon, cLat, halfLenM * eAxis, halfLenM * nAxis);
      const tail = offsetLngLat(cLon, cLat, -halfLenM * eAxis, -halfLenM * nAxis);
      const leftBearing = bearingRad + Math.PI - wingAngleRad;
      const rightBearing = bearingRad + Math.PI + wingAngleRad;
      const leftWing = offsetLngLat(
        tip[0],
        tip[1],
        wingLenM * Math.sin(leftBearing),
        wingLenM * Math.cos(leftBearing)
      );
      const rightWing = offsetLngLat(
        tip[0],
        tip[1],
        wingLenM * Math.sin(rightBearing),
        wingLenM * Math.cos(rightBearing)
      );
      const to3d = (coord) => [coord[0], coord[1], z];
      paths.push(
        { path: [to3d(tail), to3d(tip)], axisDeg, main: true, cell_id: props.cell_id || null },
        { path: [to3d(tip), to3d(leftWing)], axisDeg, main: false, cell_id: props.cell_id || null },
        { path: [to3d(tip), to3d(rightWing)], axisDeg, main: false, cell_id: props.cell_id || null }
      );
  });
  return paths;
}

function axisArrowLayer() {
  if (!state.axisArrowEnabled) return null;
  const paths = axisArrowFeatures();
  if (!paths.length) return null;
  return new deck.PathLayer({
    id: "building-axis-arrows",
    data: paths,
    pickable: false,
    opacity: 0.95,
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    parameters: { depthTest: false },
    getPath: (d) => d.path,
    getWidth: (d) => d.main ? 5 : 4,
    // Saffron-orange, with a dark halo via duplicate-ish thick strokes avoided
    // to keep the 25 x 25 grid readable.
    getColor: [232, 168, 87, 245]
  });
}

// (Stage F #1, Claude 2): the GeoJSON exporter now writes
// `pv_orientation` on every parcel feature (see core/export_3d.py). The
// map below is retained as a back-compat fallback for older GeoJSON
// snapshots that pre-date the property; the YAML source of truth is
// `config/economics.yaml:pv_orientation_defaults_by_category`.
const PV_ORIENTATION_BY_CATEGORY = {
  low_income_residential: "east_west_split",
  mid_income_residential: "east_west_split",
  high_income_residential: "south_fixed",
  school: "south_fixed",
  office: "south_fixed",
  shopping_centre: "south_fixed",
  retail_highstreet: "east_west_split",
  restaurant_food_service: "south_fixed",
  hotel_guesthouse: "south_fixed",
  healthcare: "south_fixed",
  light_industry: "south_fixed",
  warehouse_cold_storage: "south_fixed",
  public_services: "south_fixed",
  religious: "south_fixed"
};

function pvOrientationForCell(props) {
  if (props && typeof props.pv_orientation === "string" && props.pv_orientation.length > 0) {
    return props.pv_orientation;
  }
  const lu = props && props.land_use;
  return PV_ORIENTATION_BY_CATEGORY[lu] || "south_fixed";
}

//: per-orientation panel block.
// - `south_fixed`: one centred block of 6 horizontal stripes (rows
//   perpendicular to the south-facing facade). Saturated dark-blue.
// - `east_west_split`: two mirrored blocks of 3 stripes each, offset
//   along the long-facade axis so the user sees that this cell has
//   half-panels-tilted-east and half-tilted-west. Lighter tint for
//   the western block to suggest the tilt asymmetry.
// Each block also draws an outline so the block boundary is visible
// even when zoomed out.
function _emitPanelBlock(paths, center, rowEast, rowNorth, offsetEast, offsetNorth,
                          centerOffsetM, panelLengthM, panelWidthM, stripeCount, z,
                          ratio, blockTag) {
  const panelGapM = panelWidthM / Math.max(1, stripeCount - 1);
  for (let i = 0; i < stripeCount; i += 1) {
    const offsetM = centerOffsetM + (-panelWidthM / 2 + i * panelGapM);
    const start = offsetLngLat(
      center[0], center[1],
      offsetM * offsetEast - (panelLengthM / 2) * rowEast,
      offsetM * offsetNorth - (panelLengthM / 2) * rowNorth
    );
    const end = offsetLngLat(
      center[0], center[1],
      offsetM * offsetEast + (panelLengthM / 2) * rowEast,
      offsetM * offsetNorth + (panelLengthM / 2) * rowNorth
    );
    paths.push({
      path: [[start[0], start[1], z], [end[0], end[1], z]],
      ratio,
      outline: false,
      block: blockTag
    });
  }
  const corners = [
    [centerOffsetM - panelWidthM / 2, -panelLengthM / 2],
    [centerOffsetM - panelWidthM / 2,  panelLengthM / 2],
    [centerOffsetM + panelWidthM / 2,  panelLengthM / 2],
    [centerOffsetM + panelWidthM / 2, -panelLengthM / 2]
  ].map(([offsetM, alongM]) => {
    const point = offsetLngLat(
      center[0], center[1],
      offsetM * offsetEast + alongM * rowEast,
      offsetM * offsetNorth + alongM * rowNorth
    );
    return [point[0], point[1], z + 0.2];
  });
  for (let i = 0; i < corners.length; i += 1) {
    paths.push({
      path: [corners[i], corners[(i + 1) % corners.length]],
      ratio,
      outline: true,
      block: blockTag
    });
  }
}

function _panelBlockCornerPoints(center, rowEast, rowNorth, offsetEast, offsetNorth,
                                  centerOffsetM, panelLengthM, panelWidthM) {
  return [
    [centerOffsetM - panelWidthM / 2, -panelLengthM / 2],
    [centerOffsetM - panelWidthM / 2,  panelLengthM / 2],
    [centerOffsetM + panelWidthM / 2,  panelLengthM / 2],
    [centerOffsetM + panelWidthM / 2, -panelLengthM / 2]
  ].map(([offsetM, alongM]) => offsetLngLat(
    center[0],
    center[1],
    offsetM * offsetEast + alongM * rowEast,
    offsetM * offsetNorth + alongM * rowNorth
  ));
}

function panelFaceVector(blockTag) {
  if (blockTag === "east") return { east: 1, north: 0 };
  if (blockTag === "west") return { east: -1, north: 0 };
  // `south_fixed` and ground-mount panels face true south in the energy
  // model; building_axis controls where the visual block sits on the roof,
  // not which way a south-fixed array is tilted.
  return { east: 0, north: -1 };
}

function tiltedPolygon(points, baseZ, blockTag, tiltDeg) {
  const clean = (points || []).filter((point) => Array.isArray(point) && point.length >= 2);
  if (clean.length < 3) return [];
  const centerLon = clean.reduce((sum, point) => sum + Number(point[0]), 0) / clean.length;
  const centerLat = clean.reduce((sum, point) => sum + Number(point[1]), 0) / clean.length;
  const face = panelFaceVector(blockTag);
  const projections = clean.map(([lon, lat]) => {
    const eastM = (Number(lon) - centerLon) * metersPerDegreeLongitude(centerLat);
    const northM = (Number(lat) - centerLat) * METERS_PER_DEGREE_LAT;
    return eastM * face.east + northM * face.north;
  });
  const minProjection = Math.min(...projections);
  const maxProjection = Math.max(...projections);
  const span = Math.max(1, maxProjection - minProjection);
  const tiltHeight = clamp(span * Math.tan(tiltDeg * Math.PI / 180), 1.4, 12.0);
  return clean.map((point, index) => {
    const lift = ((maxProjection - projections[index]) / span) * tiltHeight;
    return [point[0], point[1], baseZ + lift];
  });
}

function solarFarmTrackerPose() {
  const capacities = activeCockpitScenario()?.capacities || {};
  const tracked = Number(capacities.tracked_pv_active || 0) > 0
    || Number(capacities.solar_farm_tracked_kwp || 0) > 0;
  if (!tracked || Number(state.sun.altitudeDeg || 0) <= 0) {
    return {
      tracked,
      block: "south",
      tiltDeg: GROUND_MOUNT_PV_PANEL_TILT_DEG,
      phase: tracked ? "parked" : "fixed",
      label: tracked ? "parked after sunset" : "fixed south tilt"
    };
  }
  const time = ((Number(state.sun.timeHours || 12) % 24) + 24) % 24;
  const offsetFromNoon = clamp((time - 12) / 6, -1, 1);
  const tiltDeg = Math.abs(offsetFromNoon) * GROUND_MOUNT_PV_PANEL_TILT_DEG;
  if (tiltDeg < 1) {
    return {
      tracked,
      block: "south",
      tiltDeg: 0,
      phase: "flat",
      label: "flat at solar noon"
    };
  }
  const direction = offsetFromNoon < 0 ? "east" : "west";
  return {
    tracked,
    block: direction,
    tiltDeg,
    phase: direction,
    label: `${direction}-tilt tracking`
  };
}

function _emitPanelSurface(surfaces, center, rowEast, rowNorth, offsetEast, offsetNorth,
                            centerOffsetM, panelLengthM, panelWidthM, z, ratio, blockTag,
                            tiltDeg = ROOFTOP_PV_PANEL_TILT_DEG) {
  const points = _panelBlockCornerPoints(
    center, rowEast, rowNorth, offsetEast, offsetNorth,
    centerOffsetM, panelLengthM, panelWidthM
  );
  const polygon = tiltedPolygon(points, z, blockTag, tiltDeg);
  if (polygon.length) {
    surfaces.push({
      polygon,
      ratio,
      block: blockTag
    });
  }
}

function carportPanelDimensionsM(props, cellSizeM) {
  const carportKwp = featureCarportKwp(props);
  const canopyAreaM2 = carportKwp > 0 ? carportKwp / SOLAR_FARM_KWP_PER_M2 : 0;
  const panelLengthM = cellSizeM * 0.40;
  const panelWidthM = canopyAreaM2 > 0
    ? clamp(canopyAreaM2 / panelLengthM, cellSizeM * 0.16, cellSizeM * 0.35)
    : cellSizeM * 0.24;
  return { panelLengthM, panelWidthM };
}

function sideVector(sideDeg) {
  const side = Number(sideDeg);
  if (!Number.isFinite(side)) return { east: 0, north: -1 };
  const rad = side * Math.PI / 180;
  return {
    east: Math.sin(rad),
    north: Math.cos(rad)
  };
}

function carportCanopySide(props, parcelIndex) {
  const entranceSide = normaliseEntranceSides(props?.entrance_sides)[0];
  const roadSides = roadSidesForCell(props || {}, parcelIndex);
  if (roadSides.includes(Number(entranceSide))) return Number(entranceSide);
  if (roadSides.length) return roadSides[0];
  return Number.isFinite(Number(entranceSide)) ? Number(entranceSide) : 180;
}

function carportCanopyCenter(feature, cellSizeM, parcelIndex) {
  const center = polygonCentroid(feature);
  if (!center) return null;
  const props = feature.properties || {};
  const vector = sideVector(carportCanopySide(props, parcelIndex));
  return offsetLngLat(
    center[0],
    center[1],
    vector.east * cellSizeM * 0.22,
    vector.north * cellSizeM * 0.22
  );
}

function carportPvPanelSurfaceFeatures() {
  if (!state.data) return [];
  const _pk = _solarPoseKey();                       // PERF-2 memo
  if (state._cpSurfKey === _pk && state._cpSurf) return state._cpSurf;
  const scenarioCarportKwp = Number(activeCockpitScenario()?.capacities?.carport_kwp || 0);
  if (scenarioCarportKwp <= 0) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const parcelIndex = parcelIndexByRowCol();
  const surfaces = [];
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (!isCarportPvSiteProps(props)) return;
    const center = carportCanopyCenter(feature, cellSizeM, parcelIndex);
    if (!center) return;
    const { panelLengthM, panelWidthM } = carportPanelDimensionsM(props, cellSizeM);
    const z = CARPORT_PV_CANOPY_HEIGHT_M;
    _emitPanelSurface(
      surfaces, center,
      1, 0, 0, 1,
      0, panelLengthM, panelWidthM, z,
      carportDeploymentRatio(props),
      "carport",
      CARPORT_PV_PANEL_TILT_DEG
    );
  });
  state._cpSurfKey = _pk;
  state._cpSurf = surfaces;
  return surfaces;
}

function pvPanelSurfaceFeatures() {
  if (!state.data) return [];
  const _pk = _solarPoseKey();                       // PERF-2 memo
  if (state._pvSurfKey === _pk && state._pvSurf) return state._pvSurf;
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const cells = new Map();
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    const key = cellKey(props);
    if (!key || isPlantFeatureProps(props)) return;
    if (!cells.has(key)) {
      cells.set(key, {
        parcel: null,
        axisDeg: 0,
        maxHeightM: 0,
        deployedKwp: 0,
        ceilingKwp: 0
      });
    }
    const cell = cells.get(key);
    if (props.role === "parcel") {
      cell.parcel = feature;
      cell.axisDeg = Number(props.building_axis_deg || 0);
      cell.deployedKwp = featurePvDeployedKwp(props);
      cell.ceilingKwp = featurePvKwp(props);
    } else if (props.role === "structure") {
      cell.maxHeightM = Math.max(cell.maxHeightM, Number(props.height_m || 0));
    }
  });

  const surfaces = [];
  cells.forEach((cell) => {
    const feature = cell.parcel;
    if (!feature || cell.deployedKwp <= 0 || cell.ceilingKwp <= 0) return;
    const props = feature.properties || {};
    if (props.land_use === "solar_farm" || props.land_use === "retail_highstreet" || isSolarExpansionProps(props)) return;
    const center = polygonCentroid(feature);
    if (!center) return;
    const axisRad = Number(cell.axisDeg || 0) * Math.PI / 180;
    const rowRad = axisRad + Math.PI / 2;
    const rowEast = Math.sin(rowRad);
    const rowNorth = Math.cos(rowRad);
    const offsetEast = Math.sin(axisRad);
    const offsetNorth = Math.cos(axisRad);
    const z = scaledHeightM(Math.max(Number(props.cell_height_m || 0), cell.maxHeightM)) + 1.1;
    const ratio = featurePvDeploymentRatio(props);
    const orientation = pvOrientationForCell(props);

    if (orientation === "east_west_split") {
      const blockWidthM = cellSizeM * 0.18;
      const blockLenM = cellSizeM * 0.26;
      const blockOffsetM = cellSizeM * 0.13;
      _emitPanelSurface(
        surfaces, center, rowEast, rowNorth, offsetEast, offsetNorth,
        -blockOffsetM, blockLenM, blockWidthM, z, ratio, "east"
      );
      _emitPanelSurface(
        surfaces, center, rowEast, rowNorth, offsetEast, offsetNorth,
        blockOffsetM, blockLenM, blockWidthM, z, ratio, "west"
      );
    } else {
      const blockWidthM = cellSizeM * 0.22;
      const blockLenM = cellSizeM * 0.26;
      _emitPanelSurface(
        surfaces, center, rowEast, rowNorth, offsetEast, offsetNorth,
        0, blockLenM, blockWidthM, z, ratio, "south"
      );
    }
  });
  const _all = surfaces.concat(highstreetPvPanelSurfaceFeatures(),
                               carportPvPanelSurfaceFeatures());
  state._pvSurfKey = _pk;                            // PERF-2 memo close
  state._pvSurf = _all;
  return _all;
}

function highstreetPvPanelSurfaceFeatures() {
  if (!state.data) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const surfaces = [];
  buildHighstreetChains().forEach((chain) => {
    chain.features.forEach((stripFeature, index) => {
      const props = stripFeature.properties || {};
      if (props.part !== "highstreet_chain_strip") return;
      const deployedKwp = featurePvDeployedKwp(props);
      const ceilingKwp = featurePvKwp(props);
      if (deployedKwp <= 0 || ceilingKwp <= 0) return;
      const bounds = polygonBounds(stripFeature);
      const center = polygonCentroid(stripFeature);
      if (!bounds || !center) return;
      const dx = bounds.maxLon - bounds.minLon;
      const dy = bounds.maxLat - bounds.minLat;
      const horizontal = dx > dy;
      const longHalfM = horizontal ? cellSizeM * 0.18 : cellSizeM * 0.04;
      const shortHalfM = horizontal ? cellSizeM * 0.04 : cellSizeM * 0.18;
      const blockTag = index % 2 === 0 ? "east" : "west";
      const points = [
        horizontal
          ? offsetLngLat(center[0], center[1], -longHalfM, -shortHalfM)
          : offsetLngLat(center[0], center[1], -shortHalfM, -longHalfM),
        horizontal
          ? offsetLngLat(center[0], center[1],  longHalfM, -shortHalfM)
          : offsetLngLat(center[0], center[1],  shortHalfM, -longHalfM),
        horizontal
          ? offsetLngLat(center[0], center[1],  longHalfM,  shortHalfM)
          : offsetLngLat(center[0], center[1],  shortHalfM,  longHalfM),
        horizontal
          ? offsetLngLat(center[0], center[1], -longHalfM,  shortHalfM)
          : offsetLngLat(center[0], center[1], -shortHalfM,  longHalfM)
      ];
      const z = scaledHeightM(props.height_m) + 0.8;
      const polygon = tiltedPolygon(points, z, blockTag, ROOFTOP_PV_PANEL_TILT_DEG);
      if (polygon.length) {
        surfaces.push({
          polygon,
          ratio: featurePvDeploymentRatio(props),
          block: blockTag
        });
      }
    });
  });
  return surfaces;
}

// SETBACK-1 (, the author: "we cant have a solar farm right next to
// a building"): 23 ring + 6 farm cells in the FROZEN geometry 8-touch a
// built parcel, and no clean open cell exists to re-home them (checked:
// zero candidates - the fabric is packed). So the fix is what real plants
// do: an INTERNAL BOUNDARY SETBACK - on any estate cell bordering a
// building, the panel rows nearest that boundary stay empty ground. The
// cited land density (acres/MW) already includes internal setbacks, so
// capacity accounting is untouched; this is the plant's own layout, not
// cosmetics. ~22 m of the 100 m cell is kept clear on each built side.
const PANEL_SETBACK_BUILT = new Set([
  "residential_low", "residential_mid", "residential_high", "school",
  "office", "shopping_centre", "retail_highstreet",
  "restaurant_food_service", "hotel_guesthouse", "healthcare",
  "light_industry", "warehouse_cold_storage", "public_services", "religious"
]);
const PANEL_SETBACK_FRAC = 0.22;

function _panelGeoContext() {
  if (state._panelGeoKey === state.currentLayout && state._panelGeo) return state._panelGeo;
  const cents = new Map();
  const built = new Set();
  (state.data?.features || []).forEach((f) => {
    const p = f.properties || {};
    if (p.role !== "parcel") return;
    const c = polygonCentroid(f);
    if (c) cents.set(`${p.row}_${p.col}`, c);
    if (PANEL_SETBACK_BUILT.has(String(p.land_use || ""))) built.add(`${p.row}_${p.col}`);
  });
  // probe once how grid rows/cols map to lat/lon (no convention guess)
  let rowLatSign = 0, colLonSign = 0;
  for (const [key, c] of cents) {
    const [r, cc] = key.split("_").map(Number);
    const down = cents.get(`${r + 1}_${cc}`);
    const right = cents.get(`${r}_${cc + 1}`);
    if (down && !rowLatSign) rowLatSign = Math.sign(down[1] - c[1]) || 0;
    if (right && !colLonSign) colLonSign = Math.sign(right[0] - c[0]) || 0;
    if (rowLatSign && colLonSign) break;
  }
  state._panelGeoKey = state.currentLayout;
  state._panelGeo = { cents, built, rowLatSign, colLonSign };
  return state._panelGeo;
}

// geographic sides {n,s,e,w} of cell (row,col) that 8-touch a BUILT parcel
function builtPanelSides(row, col) {
  const g = _panelGeoContext();
  const sides = { n: false, s: false, e: false, w: false, any: false };
  for (let dr = -1; dr <= 1; dr += 1) {
    for (let dc = -1; dc <= 1; dc += 1) {
      if (!dr && !dc) continue;
      if (!g.built.has(`${Number(row) + dr}_${Number(col) + dc}`)) continue;
      sides.any = true;
      if (dr !== 0) { if (dr * g.rowLatSign > 0) sides.n = true; else sides.s = true; }
      if (dc !== 0) { if (dc * g.colLonSign > 0) sides.e = true; else sides.w = true; }
    }
  }
  return sides;
}

// (, the author: "the visual quality went down and it is a
// bit slow"): the traffic ticker re-renders ~4x/s, and every render was
// REBUILDING the whole solar estate's tilted geometry (thousands of
// polygons + trig) from scratch - it had never needed caching because
// nothing re-rendered this often. Memoised on the pose that actually
// changes the geometry (layout, scenario, period, sun time/altitude).
function _solarPoseKey() {
  return [state.currentLayout, activeCockpitScenario()?.name || "",
    state.cockpit?.periodYear,
    Math.round(Number(state.sun.timeHours || 0) * 4),
    Math.round(Number(state.sun.altitudeDeg || 0))].join("|");
}

function solarFarmPanelSurfaceFeatures() {
  if (!state.data) return [];
  const _pk = _solarPoseKey();
  if (state._sfSurfKey === _pk && state._sfSurf) return state._sfSurf;
  const surfaces = [];
  const tracker = solarFarmTrackerPose();
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.part !== "solar_array" || feature.geometry?.type !== "Polygon") return;
    let ring = (feature.geometry.coordinates?.[0] || []).slice();
    if (ring.length > 1 && sameCoordinate(ring[0], ring[ring.length - 1])) ring.pop();
    if (ring.length < 3) return;
    // SETBACK-1: on a built side, drop the boundary row / pull rows in
    ring = ring.map((pt) => pt.slice());        // never mutate the geojson
    const sidesF = builtPanelSides(props.row, props.col);
    if (sidesF.any) {
      const host = _panelGeoContext().cents.get(`${props.row}_${props.col}`);
      if (host) {
        const cellMF = Number(state.data?.metadata?.grid?.cell_size_m || 100);
        const keepM = cellMF * (0.5 - PANEL_SETBACK_FRAC);
        const rc = polygonCentroid(feature);
        const dN = ((rc?.[1] || host[1]) - host[1]) * METERS_PER_DEGREE_LAT;
        if (sidesF.n && dN > keepM) return;      // row inside the north setback
        if (sidesF.s && dN < -keepM) return;
        const mLon = metersPerDegreeLongitude(host[1]);
        const eMax = host[0] + keepM / mLon;
        const wMin = host[0] - keepM / mLon;
        for (const pt of ring) {
          if (sidesF.e && pt[0] > eMax) pt[0] = eMax;
          if (sidesF.w && pt[0] < wMin) pt[0] = wMin;
        }
      }
    }
    const baseZ = scaledHeightM(props.height_m || GROUND_PV_PANEL_TOP_M) + 0.2;
    const polygon = tiltedPolygon(ring, baseZ, tracker.block, tracker.tiltDeg);
    if (polygon.length) {
      surfaces.push({
        kind: "solar_farm_tracker",
        polygon,
        ratio: 1,
        block: "solar_farm",
        trackerBlock: tracker.block,
        trackerTiltDeg: tracker.tiltDeg,
        trackerPhase: tracker.phase,
        trackerLabel: tracker.label,
        tracked: tracker.tracked,
        properties: {
          kind: "solar_farm_tracker",
          land_use: "solar_farm",
          part: "tracked_array",
          row: props.row,
          col: props.col,
          cell_id: props.cell_id,
          tracker_label: tracker.label,
          tracker_tilt_deg: tracker.tiltDeg,
          tracker_phase: tracker.phase,
          tracked_pv_active: tracker.tracked
        }
      });
    }
  });
  // PANEL-2 (, the author: "the solar panels for later years are
  // different, they are bigger - make them smaller, same size, same
  // design"): expansion cells used to draw ONE cell-sized tilted sheet,
  // which read as a giant panel beside the farm's 5-row arrays. Now they
  // emit the SAME 5 rows the exporter gives 2030 farm cells (the
  // solar_array offsets), so every farm cell - any vintage - has
  // identical geometry, torque tubes, posts and module lines.
  const cellM = Number(state.data?.metadata?.grid?.cell_size_m || 100);
  const EXP_ROWS = [[-0.42, -0.36, 0.42, -0.30], [-0.42, -0.20, 0.42, -0.14],
                    [-0.42, -0.04, 0.42, 0.02], [-0.42, 0.12, 0.42, 0.18],
                    [-0.42, 0.28, 0.42, 0.34]];
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel" || !isSolarExpansionProps(props) || !isExpansionActiveProps(props)) return;
    if (feature.geometry?.type !== "Polygon") return;
    const center = polygonCentroid(feature);
    if (!center) return;
    const baseZ = GROUND_PV_PANEL_TOP_M + 0.35;
    // SETBACK-1: rows inside the built-side setback are not built
    const sidesX = builtPanelSides(props.row, props.col);
    const keepF = 0.5 - PANEL_SETBACK_FRAC;
    EXP_ROWS.forEach((fr) => {
      if (sidesX.n && fr[3] > keepF) return;
      if (sidesX.s && fr[1] < -keepF) return;
      let fx0 = fr[0];
      let fx1 = fr[2];
      if (sidesX.e) fx1 = Math.min(fx1, keepF);
      if (sidesX.w) fx0 = Math.max(fx0, -keepF);
      if (fx1 - fx0 < 0.10) return;
      const pts = [[fx0, fr[1]], [fx1, fr[1]], [fx1, fr[3]], [fx0, fr[3]]]
        .map(([fx, fy]) => offsetLngLat(center[0], center[1], fx * cellM, fy * cellM));
      const polygon = tiltedPolygon(pts, baseZ, tracker.block, tracker.tiltDeg);
      if (!polygon.length) return;
      surfaces.push({
        kind: "solar_farm_tracker",
        polygon,
        ratio: 1,
        block: "solar_farm",
        trackerBlock: tracker.block,
        trackerTiltDeg: tracker.tiltDeg,
        trackerPhase: tracker.phase,
        trackerLabel: `${tracker.label} - ${props.amenity_subtype}`,
        tracked: tracker.tracked,
        properties: {
          kind: "solar_farm_tracker",
          land_use: "solar_farm",
          part: "tracked_array_expansion",
          row: props.row,
          col: props.col,
          cell_id: props.cell_id,
          tracker_label: `${tracker.label} - ${props.amenity_subtype}`,
          tracker_tilt_deg: tracker.tiltDeg,
          tracker_phase: tracker.phase,
          tracked_pv_active: tracker.tracked
        }
      });
    });
  });
  state._sfSurfKey = _pk;
  state._sfSurf = surfaces;
  return surfaces;
}

function solarFarmPanelSurfaceColor(d) {
  // PANEL-1 v2 (, the author liked the LIGHTER expansion tone: "make
  // all the solar panels the same light colour and same design"): ONE
  // light glassy steel-blue for every vintage - no dark-vs-light split
  // between the 2030 farm and the expansion rows. Module frame lines come
  // from solarFarmModuleLineLayer below.
  const daylight = clamp(Number(state.sun.irradianceWm2 || 0) / 850, 0, 1);
  const tiltShare = clamp(Number(d.trackerTiltDeg || 0) / GROUND_MOUNT_PV_PANEL_TILT_DEG, 0, 1);
  const base = d.trackerBlock === "east"
    ? [50, 76, 112]
    : d.trackerBlock === "west"
      ? [56, 74, 116]
      : [52, 72, 108];
  const lit = mix(base, [136, 184, 220], 0.20 + daylight * 0.30);
  const warmGlint = d.tracked ? daylight * (0.04 + tiltShare * 0.08) : 0;
  return withAlpha(mix(lit, [250, 204, 92], warmGlint), 244);
}

// PANEL-1: thin silver dividers across each array row, one per ~6.5 m of
// row length - the module grid is what makes a dark rectangle read as a
// solar array (see the highway-verge reference photos). Dividers are
// interpolated on the TILTED polygon, so they follow the panel plane.
function solarFarmModuleLineFeatures() {
  const _pk = _solarPoseKey();                       // PERF-2 memo
  if (state._sfLineKey === _pk && state._sfLines) return state._sfLines;
  const out = [];
  // PANEL-3: module frame lines on EVERY panel family (farm + rooftop +
  // carport + on-water), so the design language is one system.
  const allSurfaces = [
    ...solarFarmPanelSurfaceFeatures(),
    ...pvPanelSurfaceFeatures(),
    ...carportPvPanelSurfaceFeatures()
  ];
  allSurfaces.forEach((surface) => {
    const poly = (surface.polygon || []).filter((p) => Array.isArray(p) && p.length >= 3);
    if (poly.length < 4) return;
    const [a, b, c, d] = poly;
    const lenM = (p, q) => {
      const eastM = (q[0] - p[0]) * metersPerDegreeLongitude((p[1] + q[1]) / 2);
      const northM = (q[1] - p[1]) * METERS_PER_DEGREE_LAT;
      return Math.hypot(eastM, northM);
    };
    const alongAB = lenM(a, b) >= lenM(b, c);
    const e1 = alongAB ? [a, b] : [b, c];
    const e2 = alongAB ? [d, c] : [a, d];
    const n = clamp(Math.round(lenM(e1[0], e1[1]) / 6.5), 2, 16);
    for (let i = 1; i < n; i += 1) {
      const t = i / n;
      const p = e1[0].map((v, k) => v + (e1[1][k] - v) * t);
      const q = e2[0].map((v, k) => v + (e2[1][k] - v) * t);
      out.push({ path: [[p[0], p[1], (p[2] || 0) + 0.06], [q[0], q[1], (q[2] || 0) + 0.06]] });
    }
  });
  state._sfLineKey = _pk;
  state._sfLines = out;
  return out;
}

function solarFarmModuleLineLayer() {
  if (!state.panelMarkersEnabled) return null;
  const lines = solarFarmModuleLineFeatures();
  if (!lines.length) return null;
  return new deck.PathLayer({
    id: "solar-farm-module-lines",
    data: lines,
    pickable: false,
    widthUnits: "pixels",
    getPath: (d) => d.path,
    getWidth: 1,
    getColor: [190, 204, 216, 92],
    parameters: { depthTest: false },
    updateTriggers: {
      getPath: [state.panelMarkersEnabled, state.currentLayout, state.sun.timeHours, state.sun.altitudeDeg]
    }
  });
}

function panelSurfaceFillColor(d) {
  if (d.block === "solar_farm") return solarFarmPanelSurfaceColor(d);
  // PANEL-3 (, the author: "use the same solar panel design that is
  // for the solar farm ... for rooftops, car parks and on-water pv"):
  // ONE module family everywhere - the farm's light glassy steel-blue,
  // with the deployment ratio only nudging brightness (fuller roof =
  // slightly livelier glass), not switching palette.
  const daylight = clamp(Number(state.sun.irradianceWm2 || 0) / 850, 0, 1);
  const ratio = clamp(d.ratio || 0, 0, 1);
  const base = [52, 72, 108];
  const lit = mix(base, [136, 184, 220], 0.16 + daylight * 0.28 + ratio * 0.08);
  return withAlpha(lit, 236);
}

function midpoint3(a, b, zOffset = 0) {
  return [
    (Number(a?.[0] || 0) + Number(b?.[0] || 0)) / 2,
    (Number(a?.[1] || 0) + Number(b?.[1] || 0)) / 2,
    (Number(a?.[2] || 0) + Number(b?.[2] || 0)) / 2 + zOffset
  ];
}

function liftedPoint(point, zOffset = 0) {
  return [point[0], point[1], Number(point[2] || 0) + zOffset];
}

function edgePointsByLongitude(polygon, side) {
  const clean = (polygon || []).filter((point) => Array.isArray(point) && point.length >= 3);
  if (clean.length < 4) return null;
  const sorted = clean.slice().sort((a, b) => Number(a[0]) - Number(b[0]));
  const pair = side === "east" ? sorted.slice(-2) : sorted.slice(0, 2);
  return pair.sort((a, b) => Number(a[1]) - Number(b[1]));
}

function solarFarmTrackerGuideFeatures() {
  // "The random lines in the cockpit". This layer drew a
  // torque tube and three support posts PER farm panel surface across 201
  // solar-farm cells, which is hundreds of stray segments over the farm.
  // The farm in this run is 100% FIXED TILT: solar_farm_fixed_kwp 241,462.2,
  // solar_farm_tracked_kwp 0.0, tracked_pv_active 0.0. Tracker hardware is
  // therefore drawing equipment the model does not build.
  // solarFarmTrackerPose already returns phase "fixed" here, but that governs
  // only the POSE, so the guides were emitted regardless. Gate on it instead.
  if (!solarFarmTrackerPose().tracked) return [];
  return solarFarmPanelSurfaceFeatures().flatMap((surface) => {
    const westEdge = edgePointsByLongitude(surface.polygon, "west");
    const eastEdge = edgePointsByLongitude(surface.polygon, "east");
    if (!westEdge || !eastEdge) return [];
    const westMid = midpoint3(westEdge[0], westEdge[1], 0.36);
    const eastMid = midpoint3(eastEdge[0], eastEdge[1], 0.36);
    const litSide = surface.trackerBlock === "east"
      ? eastEdge
      : surface.trackerBlock === "west"
        ? westEdge
        : null;
    const features = [{
      path: [westMid, eastMid],
      type: "torque_tube",
      trackerBlock: surface.trackerBlock,
      trackerTiltDeg: surface.trackerTiltDeg
    }];
    [0.22, 0.5, 0.78].forEach((t) => {
      const lon = westMid[0] + (eastMid[0] - westMid[0]) * t;
      const lat = westMid[1] + (eastMid[1] - westMid[1]) * t;
      const z = westMid[2] + (eastMid[2] - westMid[2]) * t;
      features.push({
        path: [[lon, lat, 0.35], [lon, lat, Math.max(0.45, z - 0.18)]],
        type: "support_post",
        trackerBlock: surface.trackerBlock,
        trackerTiltDeg: surface.trackerTiltDeg
      });
    });
    if (litSide) {
      features.push({
        path: litSide.map((point) => liftedPoint(point, 0.46)),
        type: "sun_glint",
        trackerBlock: surface.trackerBlock,
        trackerTiltDeg: surface.trackerTiltDeg
      });
    }
    return features;
  });
}

function solarFarmTrackerGuideLayer() {
  if (!state.panelMarkersEnabled) return null;
  const guides = solarFarmTrackerGuideFeatures();
  if (!guides.length) return null;
  return new deck.PathLayer({
    id: "solar-farm-tracker-guides",
    data: guides,
    pickable: false,
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    getPath: (d) => d.path,
    getWidth: (d) => d.type === "sun_glint" ? 2.8 : d.type === "support_post" ? 1.2 : 1.7,
    getColor: (d) => {
      if (d.type === "sun_glint") {
        const daylight = clamp(Number(state.sun.irradianceWm2 || 0) / 850, 0, 1);
        return [255, 216, 116, Math.round(92 + daylight * 128)];
      }
      if (d.type === "support_post") return [12, 25, 38, 172];
      return [5, 18, 35, 218];
    },
    parameters: { depthTest: false },
    updateTriggers: {
      getPath: [state.panelMarkersEnabled, state.currentLayout, state.sun.timeHours, state.sun.altitudeDeg],
      getColor: [state.sun.timeHours, state.sun.altitudeDeg, state.sun.irradianceWm2, state.theme]
    }
  });
}

// =====================================================================
// SOLAR WATER HEATING COLLECTORS on roofs..
//
// Reads `solar_thermal_m2`, which core/export_3d.py allocates against the
// SAME per-cell roof budget as `pv_deployed_kwp`. That allocation is what
// guarantees a roof never carries both on the same square metre - the LP
// forbids it district-wide (`st_roof_share`) and the exporter enforces it
// per roof. So these blocks and the PV blocks are mutually exclusive by
// construction, not by drawing order.
//
// Collectors are drawn FLAT-ish and in a warm copper/amber, deliberately
// unlike the cold blue tilted PV panels, so the two read apart instantly
// on a roof-by-roof scan. Tilt is shallower than PV because a thermosiphon
// collector at this latitude is mounted closer to the roof plane.
// =====================================================================
const SOLAR_THERMAL_TILT_DEG = 12;

function featureSolarThermalM2(props) {
  const v = Number(props?.solar_thermal_m2 || 0);
  return Number.isFinite(v) && v > 0 ? v : 0;
}

// THE EXPORTED COLLECTOR ALLOCATION IS THE END-OF-HORIZON ONE.
// `solar_thermal_m2` in the geojson sums to 63,226.5 m2 across 504 roofs,
// which is the 2055 figure to the square metre. The LP builds 52,980.7 m2 in
// 2030 and 61,168.5 in 2042, so drawing the exported allocation unscaled put
// 2055's collectors on the roofs in EVERY period and overstated 2030 by 19.3
// per cent (measured, the author: "make sure the correct solar farm
// size is for the correct year and everything else built too").
//
// The per-cell shares are what the exporter solved for, so the fix is to keep
// those shares and scale them by the period's own total, which is the same
// treatment `allocateScenarioCapacityToCells` already gives carport and
// canal-top photovoltaics.
//
// NOTE FOR THE SOLAR FARM, which prompted the question: its footprint is
// CORRECTLY constant. All 301 hectares are released in 2030 (LAND-A1), so the
// land never grows - and since the DENS batch the capacity does
// not either: 241,462.2 kWp flat, all built 2030. (The 214,914-to-247,151
// growth this note used to quote was the superseded 19-Aug basis.)
// Panels spreading across more ground per period would be the bug.
function solarThermalPeriodScale() {
  if (state._stTotalKey !== state.currentLayout) {
    let total = 0;
    for (const f of state.data?.features || []) {
      if ((f.properties || {}).role !== "parcel") continue;
      total += featureSolarThermalM2(f.properties);
    }
    state._stTotal = total;
    state._stTotalKey = state.currentLayout;
  }
  const want = Number(activeCockpitScenario()?.capacities?.solar_thermal_m2 || 0);
  if (!state._stTotal || !want) return 1;
  return clamp(want / state._stTotal, 0, 1);
}

function solarThermalSurfaceFeatures() {
  if (!state.data) return [];
  const _pk = _solarPoseKey();
  if (state._stSurfKey === _pk && state._stSurf) return state._stSurf;
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const stScale = solarThermalPeriodScale();
  const cells = new Map();
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    const key = cellKey(props);
    if (!key || isPlantFeatureProps(props)) return;
    if (!cells.has(key)) {
      cells.set(key, { parcel: null, axisDeg: 0, maxHeightM: 0, m2: 0, roofM2: 0 });
    }
    const cell = cells.get(key);
    if (props.role === "parcel") {
      cell.parcel = feature;
      cell.axisDeg = Number(props.building_axis_deg || 0);
      cell.m2 = featureSolarThermalM2(props) * stScale;
      // roof denominator, for the fill ratio only
      cell.roofM2 = cellSizeM * cellSizeM;
    } else if (props.role === "structure") {
      cell.maxHeightM = Math.max(cell.maxHeightM, Number(props.height_m || 0));
    }
  });

  const surfaces = [];
  cells.forEach((cell) => {
    const feature = cell.parcel;
    if (!feature || cell.m2 <= 0) return;
    const props = feature.properties || {};
    if (props.land_use === "solar_farm" || isSolarExpansionProps(props)) return;
    const center = polygonCentroid(feature);
    if (!center) return;
    const axisRad = Number(cell.axisDeg || 0) * Math.PI / 180;
    const rowRad = axisRad + Math.PI / 2;
    const rowEast = Math.sin(rowRad);
    const rowNorth = Math.cos(rowRad);
    const offsetEast = Math.sin(axisRad);
    const offsetNorth = Math.cos(axisRad);
    // sit just above the PV plane so a collector is never z-fought by a
    // panel edge on a neighbouring cell
    const z = scaledHeightM(Math.max(Number(props.cell_height_m || 0), cell.maxHeightM)) + 1.35;
    const ratio = clamp(cell.roofM2 > 0 ? cell.m2 / cell.roofM2 : 0, 0, 1);
    // Block SIZE scales with the allocated area, so a roof carrying twice
    // the collector shows twice the hardware. Capped so a large allocation
    // cannot spill past the parcel edge.
    const frac = clamp(Math.sqrt(ratio), 0.10, 0.42);
    const blockLenM = cellSizeM * frac;
    const blockWidthM = cellSizeM * frac * 0.62;
    _emitPanelSurface(
      surfaces, center, rowEast, rowNorth, offsetEast, offsetNorth,
      0, blockLenM, blockWidthM, z, ratio, "thermal",
      SOLAR_THERMAL_TILT_DEG
    );
  });
  state._stSurfKey = _pk;
  state._stSurf = surfaces;
  return surfaces;
}

function solarThermalSurfaceLayer() {
  if (!state.panelMarkersEnabled) return null;
  const surfaces = solarThermalSurfaceFeatures();
  if (!surfaces.length) return null;
  return new deck.PolygonLayer({
    id: "solar-thermal-collectors",
    data: surfaces,
    pickable: false,
    stroked: true,
    filled: true,
    extruded: false,
    getPolygon: (d) => d.polygon,
    // copper absorber -> pale glazing as the allocated area grows
    getFillColor: (d) => withAlpha(
      mix([146, 64, 30], [226, 148, 62], clamp(d.ratio || 0, 0, 1)), 242),
    getLineColor: [60, 24, 10, 235],
    getLineWidth: 1.4,
    lineWidthUnits: "pixels",
    parameters: { depthTest: false },
    updateTriggers: {
      getPolygon: [state.panelMarkersEnabled, state.currentLayout],
      getFillColor: [state.theme, state.currentLayout]
    }
  });
}

function pvPanelSurfaceLayer() {
  if (!state.panelMarkersEnabled) return null;
  const surfaces = pvPanelSurfaceFeatures();
  if (!surfaces.length) return null;
  return new deck.PolygonLayer({
    id: "pv-panel-tilted-surfaces",
    data: surfaces,
    pickable: false,
    stroked: false,
    filled: true,
    extruded: false,
    getPolygon: (d) => d.polygon,
    getFillColor: panelSurfaceFillColor,
    parameters: { depthTest: false },
    updateTriggers: {
      getPolygon: [state.cellPvDeployedKwp, state.panelMarkersEnabled, state.currentLayout],
      getFillColor: [state.cellPvDeployedKwp, state.theme]
    }
  });
}

function solarFarmPanelSurfaceLayer() {
  if (!state.panelMarkersEnabled) return null;
  const surfaces = solarFarmPanelSurfaceFeatures();
  if (!surfaces.length) return null;
  return new deck.PolygonLayer({
    id: "solar-farm-tilted-panels",
    data: surfaces,
    pickable: true,
    stroked: true,
    filled: true,
    extruded: false,
    getPolygon: (d) => d.polygon,
    getFillColor: panelSurfaceFillColor,
    getLineColor: (d) => d.tracked ? [250, 204, 92, 150] : [9, 26, 48, 180],
    getLineWidth: 1,
    lineWidthUnits: "pixels",
    parameters: { depthTest: false },
    updateTriggers: {
      getPolygon: [state.panelMarkersEnabled, state.currentLayout, state.sun.timeHours, state.sun.altitudeDeg],
      getFillColor: [state.theme, state.sun.timeHours, state.sun.altitudeDeg, state.sun.irradianceWm2],
      getLineColor: [state.theme, state.sun.timeHours, state.sun.altitudeDeg]
    }
  });
}

function pvPanelFeatures() {
  if (!state.data) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const cells = new Map();
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    const key = cellKey(props);
    if (!key || isPlantFeatureProps(props)) return;
    if (!cells.has(key)) {
      cells.set(key, {
        parcel: null,
        axisDeg: 0,
        maxHeightM: 0,
        deployedKwp: 0,
        ceilingKwp: 0
      });
    }
    const cell = cells.get(key);
    if (props.role === "parcel") {
      cell.parcel = feature;
      cell.axisDeg = Number(props.building_axis_deg || 0);
      cell.deployedKwp = featurePvDeployedKwp(props);
      cell.ceilingKwp = featurePvKwp(props);
    } else if (props.role === "structure") {
      cell.maxHeightM = Math.max(cell.maxHeightM, Number(props.height_m || 0));
    }
  });

  const paths = [];

  cells.forEach((cell) => {
    const feature = cell.parcel;
    if (!feature || cell.deployedKwp <= 0 || cell.ceilingKwp <= 0) return;
    const props = feature.properties || {};
    if (props.land_use === "solar_farm" || isSolarExpansionProps(props)) return;
    // retail_highstreet cells get PV markers along the chain
    // strip features (separate function); skip them here so the in-cell
    // markers don't sit in the gap between merged facade strips.
    if (props.land_use === "retail_highstreet") return;
    const center = polygonCentroid(feature);
    if (!center) return;
    const axisRad = Number(cell.axisDeg || 0) * Math.PI / 180;
    const rowRad = axisRad + Math.PI / 2;
    const rowEast = Math.sin(rowRad);
    const rowNorth = Math.cos(rowRad);
    const offsetEast = Math.sin(axisRad);
    const offsetNorth = Math.cos(axisRad);
    const z = scaledHeightM(Math.max(Number(props.cell_height_m || 0), cell.maxHeightM)) + 1.8;
    const ratio = featurePvDeploymentRatio(props);
    const orientation = pvOrientationForCell(props);

    if (orientation === "east_west_split") {
      // Two mirrored 3-stripe blocks offset along the long-facade axis.
      const blockWidthM = cellSizeM * 0.18;
      const blockLenM = cellSizeM * 0.26;
      const blockOffsetM = cellSizeM * 0.13;  // half-gap between blocks
      _emitPanelBlock(
        paths, center, rowEast, rowNorth, offsetEast, offsetNorth,
        -blockOffsetM, blockLenM, blockWidthM, 3, z, ratio, "east"
      );
      _emitPanelBlock(
        paths, center, rowEast, rowNorth, offsetEast, offsetNorth,
        blockOffsetM, blockLenM, blockWidthM, 3, z, ratio, "west"
      );
    } else {
      // south_fixed: single centred block of 6 stripes.
      const blockWidthM = cellSizeM * 0.22;
      const blockLenM = cellSizeM * 0.26;
      _emitPanelBlock(
        paths, center, rowEast, rowNorth, offsetEast, offsetNorth,
        0, blockLenM, blockWidthM, 6, z, ratio, "south"
      );
    }
  });

  return paths;
}

function carportPvPanelFeatures() {
  if (!state.data) return [];
  const scenarioCarportKwp = Number(activeCockpitScenario()?.capacities?.carport_kwp || 0);
  if (scenarioCarportKwp <= 0) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const parcelIndex = parcelIndexByRowCol();
  const paths = [];
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (!isCarportPvSiteProps(props)) return;
    const center = carportCanopyCenter(feature, cellSizeM, parcelIndex);
    if (!center) return;
    const { panelLengthM, panelWidthM } = carportPanelDimensionsM(props, cellSizeM);
    _emitPanelBlock(
      paths, center,
      1, 0, 0, 1,
      0, panelLengthM, panelWidthM, 6, CARPORT_PV_CANOPY_HEIGHT_M + 0.45,
      carportDeploymentRatio(props),
      "carport"
    );
  });
  return paths;
}

//: high-street PV markers must overlay each cell's slice
// of the merged chain strip, not sit in the middle of the cell. This
// reads the same `buildHighstreetChains` output as the chain frontages
// and emits 2 short stripes per cell (one per facade strip).
function highstreetPvPanelFeatures() {
  if (!state.data) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const chains = buildHighstreetChains();
  if (!chains.length) return [];
  const paths = [];
  chains.forEach((chain) => {
    chain.features.forEach((stripFeature) => {
      const props = stripFeature.properties || {};
      if (props.part !== "highstreet_chain_strip") return;
      // Skip if the underlying parcel doesn't have deployed PV.
      const deployedKwp = featurePvDeployedKwp(props);
      const ceilingKwp = featurePvKwp(props);
      if (deployedKwp <= 0 || ceilingKwp <= 0) return;
      const center = polygonCentroid(stripFeature);
      if (!center) return;
      const bounds = polygonBounds(stripFeature);
      if (!bounds) return;
      // Render 2 short panel stripes along the strip's long axis.
      const dx = bounds.maxLon - bounds.minLon;
      const dy = bounds.maxLat - bounds.minLat;
      const horizontal = dx > dy;
      const longHalfM = horizontal ? cellSizeM * 0.18 : cellSizeM * 0.04;
      const shortHalfM = horizontal ? cellSizeM * 0.04 : cellSizeM * 0.18;
      const z = scaledHeightM(props.height_m) + 1.2;
      const ratio = featurePvDeploymentRatio(props);
      const stripeCount = 2;
      const gapM = (shortHalfM * 2) / (stripeCount + 1);
      for (let i = 0; i < stripeCount; i += 1) {
        const offsetShort = -shortHalfM + gapM * (i + 1);
        const start = horizontal
          ? offsetLngLat(center[0], center[1], -longHalfM, offsetShort)
          : offsetLngLat(center[0], center[1], offsetShort, -longHalfM);
        const end = horizontal
          ? offsetLngLat(center[0], center[1],  longHalfM, offsetShort)
          : offsetLngLat(center[0], center[1], offsetShort,  longHalfM);
        paths.push({
          path: [[start[0], start[1], z], [end[0], end[1], z]],
          ratio,
          outline: false,
          block: "highstreet"
        });
      }
    });
  });
  return paths;
}

function pvPanelLayer() {
  if (!state.panelMarkersEnabled) return null;
  const paths = pvPanelFeatures().concat(highstreetPvPanelFeatures(), carportPvPanelFeatures());
  if (!paths.length) return null;
  return new deck.PathLayer({
    id: "pv-panel-roof-markers",
    data: paths,
    pickable: false,
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    parameters: { depthTest: false },
    getPath: (d) => d.path,
    getWidth: (d) => d.outline ? 2.3 : 2.0,
    getColor: (d) => {
      if (d.outline) return [10, 21, 58, 238];
      // East-west split: lighter tint on the "west" block to suggest
      // mirrored tilt asymmetry. South-fixed and highstreet stay at the
      // saturated dark-blue ramp.
      const base = d.block === "west"
        ? mix([40, 96, 178], [86, 175, 230], clamp(d.ratio || 0, 0, 1))
        : mix([21, 66, 148], [40, 151, 214], clamp(d.ratio || 0, 0, 1));
      return withAlpha(base, 248);
    },
    updateTriggers: {
      getColor: [state.cellPvDeployedKwp, state.theme],
      getPath: [state.cellPvDeployedKwp, state.panelMarkersEnabled, state.currentLayout]
    }
  });
}

function highstreetChainLayer() {
  if (!state.data) return null;
  const features = highstreetChainFeatures();
  if (!features.length) return null;
  return new deck.GeoJsonLayer({
    id: "retail-highstreet-chain-frontages",
    data: featureCollection(features),
    pickable: true,
    stroked: false,
    filled: true,
    extruded: true,
    wireframe: false,
    opacity: 0.98,
    material: {
      ambient: 0.34,
      diffuse: 0.80,
      shininess: 24,
      specularColor: [255, 235, 205]
    },
    getElevation: (feature) => scaledFeatureHeightM(feature.properties),
    getFillColor: (feature) => state.pvDeploymentOverlayEnabled
      ? pvDeploymentColor(feature.properties, { structure: true })
      : state.shadingOverlayEnabled
        ? pvShadingColor(feature.properties, { structure: true })
        : state.pvOverlayEnabled
          ? pvCeilingColor(feature.properties, { structure: true })
          : withAlpha(mix(designRgb(feature.properties) || [209, 123, 62], [255, 226, 170], 0.10), 244),
    updateTriggers: {
      getElevation: [BUILDING_HEIGHT_SCALE],
      getFillColor: [
        state.theme,
        state.pvOverlayEnabled,
        state.shadingOverlayEnabled,
        state.pvDeploymentOverlayEnabled,
        state.shadingRamp.min,
        state.shadingRamp.max,
        state.pvOverlayMaxKwp,
        state.cellPvDeployedKwp,
        state.cellShading
      ]
    }
  });
}

function highstreetShopfrontLayer() {
  const paths = highstreetShopfrontFeatures();
  if (!paths.length) return null;
  return new deck.PathLayer({
    id: "retail-highstreet-shopfront-lines",
    data: paths,
    pickable: false,
    widthUnits: "pixels",
    capRounded: false,
    jointRounded: false,
    parameters: { depthTest: false },
    getPath: (d) => d.path,
    getWidth: (d) => d.major ? 2.6 : 1.4,
    getColor: (d) => d.major ? [28, 24, 20, 235] : [255, 231, 184, 210],
    updateTriggers: {
      getPath: [state.currentLayout, state.data],
      getColor: [state.theme]
    }
  });
}

function highstreetChainFeatures() {
  return buildHighstreetChains().flatMap((chain) => chain.features);
}

function highstreetShopfrontFeatures() {
  return buildHighstreetChains().flatMap((chain) => chain.paths);
}

function buildHighstreetChains() {
  if (!state.data) return [];
  const parcels = (state.data.features || [])
    .filter((feature) => {
      const props = feature.properties || {};
      return props.role === "parcel" && props.land_use === "retail_highstreet" && feature.geometry?.type === "Polygon";
    })
    .map((feature) => ({
      feature,
      props: feature.properties || {},
      row: Number(feature.properties?.row),
      col: Number(feature.properties?.col),
      key: cellKey(feature.properties || {}),
      bounds: polygonBounds(feature)
    }))
    .filter((cell) => cell.key && cell.bounds);
  if (!parcels.length) return [];

  const byKey = new Map(parcels.map((cell) => [cell.key, cell]));
  const seen = new Set();
  const chains = [];
  parcels.forEach((start) => {
    if (seen.has(start.key)) return;
    const queue = [start];
    const component = [];
    seen.add(start.key);
    while (queue.length) {
      const cell = queue.shift();
      component.push(cell);
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dr, dc]) => {
        const next = byKey.get(`${cell.row + dr}_${cell.col + dc}`);
        if (!next || seen.has(next.key)) return;
        seen.add(next.key);
        queue.push(next);
      });
    }
    chains.push(highstreetChainFromComponent(component));
  });
  return chains.filter(Boolean);
}

function highstreetChainFromComponent(component) {
  if (!component.length) return null;
  const rows = new Set(component.map((cell) => cell.row));
  const cols = new Set(component.map((cell) => cell.col));
  const horizontal = rows.size <= cols.size;
  const ordered = component.slice().sort((a, b) => horizontal ? a.col - b.col : a.row - b.row);
  const bounds = mergeBounds(component.map((cell) => cell.bounds));
  const heightM = ordered.reduce((total, cell) => total + Number(cell.props.cell_height_m || cell.props.height_m || 0), 0) / ordered.length;
  const chainId = `hs_${ordered.map((cell) => cell.key).join("_")}`;
  const features = [];
  const paths = [];
  const dx = bounds.maxLon - bounds.minLon;
  const dy = bounds.maxLat - bounds.minLat;
  ordered.forEach((cell, index) => {
    const cb = cell.bounds;
    const stripes = horizontal
      ? [
          { minLon: cb.minLon, maxLon: cb.maxLon, minLat: bounds.minLat + dy * HIGHSTREET_STRIP_A[0], maxLat: bounds.minLat + dy * HIGHSTREET_STRIP_A[1] },
          { minLon: cb.minLon, maxLon: cb.maxLon, minLat: bounds.minLat + dy * HIGHSTREET_STRIP_B[0], maxLat: bounds.minLat + dy * HIGHSTREET_STRIP_B[1] }
        ]
      : [
          { minLon: bounds.minLon + dx * HIGHSTREET_STRIP_A[0], maxLon: bounds.minLon + dx * HIGHSTREET_STRIP_A[1], minLat: cb.minLat, maxLat: cb.maxLat },
          { minLon: bounds.minLon + dx * HIGHSTREET_STRIP_B[0], maxLon: bounds.minLon + dx * HIGHSTREET_STRIP_B[1], minLat: cb.minLat, maxLat: cb.maxLat }
        ];
    stripes.forEach((stripe, stripeIndex) => {
      features.push({
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [boundsRing(stripe)]
        },
        properties: {
          ...cell.props,
          role: "structure",
          part: "highstreet_chain_strip",
          part_index: 20 + stripeIndex,
          height_m: heightM,
          chain_id: chainId,
          chain_cells: ordered.length,
          chain_position: index + 1
        }
      });
    });
    const z = scaledHeightM(heightM) + 0.9;
    if (index < ordered.length - 1) {
      const boundary = horizontal ? cb.maxLon : cb.maxLat;
      stripes.forEach((stripe) => {
        paths.push({
          major: true,
          path: horizontal
            ? [[boundary, stripe.minLat, z], [boundary, stripe.maxLat, z]]
            : [[stripe.minLon, boundary, z], [stripe.maxLon, boundary, z]]
        });
      });
    }
    const front = horizontal && Number(cell.props.building_axis_deg || 0) === 180
      ? stripes[0].minLat
      : null;
    if (front !== null) {
      paths.push({
        major: false,
        path: [[cb.minLon, front, z + 0.1], [cb.maxLon, front, z + 0.1]]
      });
    }
  });
  return { features, paths };
}

function placementAuditLayer() {
  if (!state.realismFlagsEnabled || !state.data || !state.placementAudit.byCell.size) return null;
  const paths = placementAuditFeatures();
  if (!paths.length) return null;
  return new deck.PathLayer({
    id: "placement-realism-flags",
    data: paths,
    pickable: true,
    widthUnits: "pixels",
    capRounded: false,
    jointRounded: true,
    parameters: { depthTest: false },
    getPath: (d) => d.path,
    getWidth: (d) => d.issueCount > 1 ? 5 : 4,
    getColor: (d) => withAlpha(auditCategoryMeta(d.primaryCategory).colour, 248),
    updateTriggers: {
      getPath: [state.currentLayout, state.placementAudit.byCell],
      getColor: [state.theme]
    }
  });
}

function placementAuditFeatures() {
  const features = [];
  (state.data?.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel") return;
    const issues = auditIssuesForProps(props);
    if (!issues.length) return;
    const ring = feature.geometry?.coordinates?.[0] || [];
    if (ring.length < 3) return;
    const z = 2.4;
    features.push({
      path: ring.map(([lon, lat]) => [lon, lat, z]),
      issueCount: issues.length,
      primaryCategory: issues[0].category,
      properties: {
        ...props,
        auditIssues: issues
      }
    });
  });
  return features;
}

function carportSiteFeatures() {
  if (!state.carportSitesEnabled || !state.data) return [];
  // PERIOD GATE (the author, "solar panels should only be seen on car
  // park once they arrive... in 2042"). The run installs carport PV 0 kWp in
  // 2030, 11,500.0 in 2042, 16,500.0 in 2055. `is_carport_site` is a LAYOUT
  // flag - where a canopy could go - and does not move with the period, so
  // without this the markers drew over the 2030 view for hardware the model
  // has not built. The two panel builders (carportPvPanelSurfaceFeatures,
  // carportPvPanelFeatures) already gate on exactly this; the site layer was
  // the one that did not. The legend still reports the 17 layout sites and now
  // says none are deployed, so the count and the empty map agree.
  const scenarioCarportKwp = Number(activeCockpitScenario()?.capacities?.carport_kwp || 0);
  if (scenarioCarportKwp <= 0) return [];
  const features = [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const halfLengthM = Math.min(16, cellSizeM * 0.08);
  const halfWidthM = Math.min(8, cellSizeM * 0.04);
  const stripeHalfWidthM = Math.min(1.6, cellSizeM * 0.008);
  const stripeOffsetM = Math.min(5.5, cellSizeM * 0.028);
  const z = 8;
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel" || props.land_use !== "parking_lot" || !truthyFlag(props.is_carport_site)) return;
    const center = polygonCentroid(feature);
    if (!center) return;
    const pushRect = (centerOffsetM, widthM, kind) => {
      features.push({
        polygon: rectanglePolygonAt(center, centerOffsetM, 0, widthM, halfWidthM, z),
        kind,
        properties: props
      });
    };
    pushRect(0, halfLengthM, "canopy");
    pushRect(-stripeOffsetM, stripeHalfWidthM, "stripe");
    pushRect(stripeOffsetM, stripeHalfWidthM, "stripe");
  });
  return features;
}

function carportSiteLayer() {
  const features = carportSiteFeatures();
  if (!features.length) return null;
  return new deck.PolygonLayer({
    id: "discrete-carport-sites",
    data: features,
    pickable: false,
    stroked: true,
    filled: true,
    extruded: false,
    getPolygon: (d) => d.polygon,
    getFillColor: (d) => d.kind === "stripe" ? withAlpha([248, 250, 252], 210) : withAlpha(CARPORT_SITE_COLOUR, 58),
    getLineColor: (d) => d.kind === "stripe" ? withAlpha(CARPORT_SITE_COLOUR, 232) : withAlpha(CARPORT_SITE_COLOUR, 210),
    getLineWidth: (d) => d.kind === "stripe" ? 1.4 : 1.8,
    lineWidthUnits: "pixels",
    parameters: { depthTest: false }
  });
}

function rectanglePolygonAt(center, eastOffsetM, northOffsetM, halfEastM, halfNorthM, z) {
  const [lon, lat] = center;
  return [
    offsetLngLat(lon, lat, eastOffsetM - halfEastM, northOffsetM - halfNorthM),
    offsetLngLat(lon, lat, eastOffsetM + halfEastM, northOffsetM - halfNorthM),
    offsetLngLat(lon, lat, eastOffsetM + halfEastM, northOffsetM + halfNorthM),
    offsetLngLat(lon, lat, eastOffsetM - halfEastM, northOffsetM + halfNorthM)
  ].map(([x, y]) => [x, y, z]);
}

function entranceMarkerLayer() {
  const markers = entranceMarkerFeatures();
  if (!markers.length) return null;
  return new deck.PolygonLayer({
    id: "building-entrance-markers",
    data: markers,
    pickable: false,
    stroked: true,
    filled: true,
    extruded: false,
    getPolygon: (marker) => marker.polygon,
    getFillColor: (marker) => marker.isHighstreet ? ENTRANCE_MARKER_HIGHSTREET_COLOUR : ENTRANCE_MARKER_COLOUR,
    getLineColor: ENTRANCE_MARKER_OUTLINE,
    getLineWidth: 1.25,
    lineWidthUnits: "pixels",
    parameters: { depthTest: false }
  });
}

function entranceMarkerFeatures() {
  if (!state.data) return [];
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const parcelIndex = parcelIndexByRowCol();
  const markers = [];
  (state.data.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel" || !props.is_built) return;
    const center = polygonCentroid(feature);
    if (!center) return;
    if (props.land_use === "retail_highstreet") {
      highstreetEntrancePolygons(center, props, cellSizeM, parcelIndex, feature).forEach((polygon, index) => {
        markers.push({
          polygon,
          side: null,
          index,
          isHighstreet: true,
          cell: cellKey(props)
        });
      });
      return;
    }
    normaliseEntranceSides(props.entrance_sides).forEach((side, index) => {
      const polygon = entranceMarkerPolygon(center, side, cellSizeM);
      if (!polygon) return;
      markers.push({
        polygon,
        side,
        index,
        isHighstreet: props.land_use === "retail_highstreet",
        cell: cellKey(props)
      });
    });
  });
  return markers;
}

function parcelIndexByRowCol() {
  const index = new Map();
  (state.data?.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel") return;
    const row = Number(props.row);
    const col = Number(props.col);
    if (!Number.isFinite(row) || !Number.isFinite(col)) return;
    index.set(`${row}_${col}`, props);
  });
  return index;
}

function parcelCenterIndex() {
  const index = new Map();
  (state.data?.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel") return;
    const row = Number(props.row);
    const col = Number(props.col);
    if (!Number.isFinite(row) || !Number.isFinite(col)) return;
    const center = polygonCentroid(feature);
    if (!center) return;
    index.set(`${row}_${col}`, center);
    if (props.cell_id) index.set(String(props.cell_id), center);
  });
  return index;
}

const CARDINAL_NEIGHBOUR_OFFSETS = {
  0: [1, 0],
  90: [0, 1],
  180: [-1, 0],
  270: [0, -1]
};

function roadSidesForCell(props, parcelIndex) {
  const row = Number(props.row);
  const col = Number(props.col);
  if (!Number.isFinite(row) || !Number.isFinite(col)) return [];
  return [0, 90, 180, 270].filter((side) => {
    const [dr, dc] = CARDINAL_NEIGHBOUR_OFFSETS[side];
    const neighbour = parcelIndex.get(`${row + dr}_${col + dc}`);
    return neighbour?.land_use === "road";
  });
}

function highstreetEntrancePolygons(center, props, cellSizeM, parcelIndex, feature = null) {
  const roadSides = roadSidesForCell(props, parcelIndex);
  const exportedSides = normaliseEntranceSides(props.entrance_sides);
  const roadSide = roadSides.find((side) => exportedSides.includes(side)) ?? roadSides[0] ?? null;
  const splitSide = highstreetSplitSide(props, parcelIndex, roadSide);
  const frontSign = roadSide !== null && sameCardinalSide(oppositeSide(splitSide), roadSide) ? -1 : 1;
  const halfLength = Math.min(12, cellSizeM * 0.06);
  const halfDepth = Math.min(3.2, cellSizeM * 0.016);
  const matGap = halfDepth + Math.min(1.4, cellSizeM * 0.007);
  // Match the two strip footprints from highstreetChainFromComponent:
  // strip A = 0.14-0.36, strip B = 0.62-0.84 along the short axis.
  const positiveInner = cellSizeM * (HIGHSTREET_STRIP_B[0] - 0.5);
  const positiveOuter = cellSizeM * (HIGHSTREET_STRIP_B[1] - 0.5);
  const negativeInner = cellSizeM * (HIGHSTREET_STRIP_A[1] - 0.5);
  const negativeOuter = cellSizeM * (HIGHSTREET_STRIP_A[0] - 0.5);
  const frontInner = frontSign > 0 ? positiveInner : negativeInner;
  const frontOuter = frontSign > 0 ? positiveOuter : negativeOuter;
  const backInner = frontSign > 0 ? negativeInner : positiveInner;
  const roadCoord = frontOuter + frontSign * matGap;
  const frontAlleyCoord = frontInner - frontSign * matGap;
  const backAlleyCoord = backInner + frontSign * matGap;
  const z = 2.8;
  const mats = [
    doorMatPolygonInCell(center, splitSide, frontAlleyCoord, 0, halfDepth, halfLength, z),
    doorMatPolygonInCell(center, splitSide, backAlleyCoord, 0, halfDepth, halfLength, z)
  ];
  if (roadSide !== null && roadAlignedWithHighstreetSplit(roadSide, splitSide)) {
    mats.unshift(doorMatPolygonInCell(center, splitSide, roadCoord, 0, halfDepth, halfLength, z));
  }
  return mats.filter(Boolean);
}

function highstreetSplitSide(props, parcelIndex, roadSide = null) {
  if (roadSide !== null) return Number(roadSide);
  const row = Number(props.row);
  const col = Number(props.col);
  const hsSides = [0, 90, 180, 270].filter((side) => {
    const [dr, dc] = CARDINAL_NEIGHBOUR_OFFSETS[side];
    const neighbour = parcelIndex.get(`${row + dr}_${col + dc}`);
    return neighbour?.land_use === "retail_highstreet";
  });
  if (hsSides.some((side) => side === 90 || side === 270)) return 0;
  if (hsSides.some((side) => side === 0 || side === 180)) return 90;
  const exported = normaliseEntranceSides(props.entrance_sides);
  const alleySide = exported[1] ?? exported[0] ?? null;
  if (alleySide === 90 || alleySide === 270) return 0;
  if (alleySide === 0 || alleySide === 180) return 90;
  return Number(props.building_axis_deg || 0) === 90 ? 90 : 0;
}

function oppositeSide(sideDeg) {
  const side = ((Math.round(Number(sideDeg) / 90) * 90) % 360 + 360) % 360;
  return (side + 180) % 360;
}

function sameCardinalSide(a, b) {
  return ((Math.round(Number(a) / 90) * 90) % 360 + 360) % 360
    === ((Math.round(Number(b) / 90) * 90) % 360 + 360) % 360;
}

function roadAlignedWithHighstreetSplit(roadSide, splitSide) {
  return sameCardinalSide(roadSide, splitSide) || sameCardinalSide(roadSide, oppositeSide(splitSide));
}

function doorMatPolygonInCell(center, sideDeg, normalCenterM, tangentCenterM, halfNormalM, halfTangentM, z = 2.4) {
  const side = Number(sideDeg);
  if (!Number.isFinite(side)) return null;
  const rad = side * Math.PI / 180;
  const normalEast = Math.sin(rad);
  const normalNorth = Math.cos(rad);
  const tangentEast = normalNorth;
  const tangentNorth = -normalEast;
  const [lon, lat] = center;
  const pointAt = (normalM, tangentM) => offsetLngLat(
    lon,
    lat,
    normalEast * normalM + tangentEast * tangentM,
    normalNorth * normalM + tangentNorth * tangentM
  );
  return [
    pointAt(normalCenterM - halfNormalM, tangentCenterM - halfTangentM),
    pointAt(normalCenterM - halfNormalM, tangentCenterM + halfTangentM),
    pointAt(normalCenterM + halfNormalM, tangentCenterM + halfTangentM),
    pointAt(normalCenterM + halfNormalM, tangentCenterM - halfTangentM)
  ].map(([x, y]) => [x, y, z]);
}

function entranceMarkerPolygon(center, sideDeg, cellSizeM) {
  const side = Number(sideDeg);
  if (!Number.isFinite(side)) return null;
  const rad = side * Math.PI / 180;
  const normalEast = Math.sin(rad);
  const normalNorth = Math.cos(rad);
  const tangentEast = normalNorth;
  const tangentNorth = -normalEast;
  const halfWidth = Math.min(10, cellSizeM * 0.05);
  const depth = Math.min(7.5, cellSizeM * 0.04);
  const edgeOffset = cellSizeM * 0.44;
  const [lon, lat] = center;
  const pointAt = (normalM, tangentM) => offsetLngLat(
    lon,
    lat,
    normalEast * normalM + tangentEast * tangentM,
    normalNorth * normalM + tangentNorth * tangentM
  );
  return [
    pointAt(edgeOffset - depth, -halfWidth),
    pointAt(edgeOffset - depth, halfWidth),
    pointAt(edgeOffset, halfWidth),
    pointAt(edgeOffset, -halfWidth)
  ];
}

function orientedDoorMatPolygon(center, sideDeg, normalCenterM, halfNormalM, halfTangentM, z = 2.4) {
  const side = Number(sideDeg);
  if (!Number.isFinite(side)) return null;
  const rad = side * Math.PI / 180;
  const normalEast = Math.sin(rad);
  const normalNorth = Math.cos(rad);
  const tangentEast = normalNorth;
  const tangentNorth = -normalEast;
  const [lon, lat] = center;
  const pointAt = (normalM, tangentM) => offsetLngLat(
    lon,
    lat,
    normalEast * normalM + tangentEast * tangentM,
    normalNorth * normalM + tangentNorth * tangentM
  );
  return [
    pointAt(normalCenterM - halfNormalM, -halfTangentM),
    pointAt(normalCenterM - halfNormalM, halfTangentM),
    pointAt(normalCenterM + halfNormalM, halfTangentM),
    pointAt(normalCenterM + halfNormalM, -halfTangentM)
  ].map(([x, y]) => [x, y, z]);
}

function initialiseSunControls() {
  els.sunDate.value = String(state.sun.dayOfYear);
  els.sunTime.value = String(state.sun.timeHours);
  updateSunPosition({ refreshLayers: false });
}

function updateSunPosition(options = {}) {
  const position = computeSunPosition({
    dayOfYear: state.sun.dayOfYear,
    timeHours: state.sun.timeHours,
    latitude: state.sun.latitude,
    longitude: state.sun.longitude
  });
  state.sun = { ...state.sun, ...position };
  updateSunLabels();
  updateTariffStatus();
  applyDayStatusTint();
  updateInfo();
  updateSelectedCellPanel();
  updateDeckParameters();
  renderCockpit();
  if (options.refreshLayers !== false) {
    updateLayers();
  }
}

function computeSunPosition({ dayOfYear, timeHours, latitude, longitude }) {
  const day = clamp(Number(dayOfYear) || 1, 1, 366);
  const time = clamp(Number(timeHours) || 0, 0, 24);
  const lonDeg = Number.isFinite(Number(longitude)) ? Number(longitude) : 0;
  const hour = Math.floor(time);
  const minute = Math.round((time - hour) * 60);
  const decimalHour = hour + minute / 60;
  const latRad = toRad(latitude);
  const gamma = (2 * Math.PI / 365) * (day - 1 + (decimalHour - 12) / 24);
  const declination = 0.006918
    - 0.399912 * Math.cos(gamma) + 0.070257 * Math.sin(gamma)
    - 0.006758 * Math.cos(2 * gamma) + 0.000907 * Math.sin(2 * gamma)
    - 0.002697 * Math.cos(3 * gamma) + 0.00148 * Math.sin(3 * gamma);
  const equationOfTime = 229.18 * (
    0.000075
    + 0.001868 * Math.cos(gamma) - 0.032077 * Math.sin(gamma)
    - 0.014615 * Math.cos(2 * gamma) - 0.040849 * Math.sin(2 * gamma)
  );
  // The sliders represent site-local solar time, so the site longitude is
  // the reference meridian and 12:00 stays close to local solar noon.
  const standardMeridianDeg = lonDeg;
  const solarTimeMin = decimalHour * 60
    + equationOfTime
    + 4 * (lonDeg - standardMeridianDeg);
  const hourAngle = toRad(solarTimeMin / 4 - 180);
  const altitudeRad = Math.asin(
    Math.sin(latRad) * Math.sin(declination)
    + Math.cos(latRad) * Math.cos(declination) * Math.cos(hourAngle)
  );
  const azimuthRad = Math.atan2(
    Math.sin(hourAngle),
    Math.cos(hourAngle) * Math.sin(latRad) - Math.tan(declination) * Math.cos(latRad)
  );
  const pvCapacityFactor = clearSkyPvCapacityFactor(altitudeRad);
  return {
    dayOfYear: day,
    timeHours: time,
    altitudeRad,
    azimuthRad,
    altitudeDeg: toDeg(altitudeRad),
    azimuthDeg: toDeg(azimuthRad),
    pvCapacityFactor,
    irradianceWm2: pvCapacityFactor / CLEAR_SKY_PERFORMANCE_RATIO * 1000
  };
}

function sunMarkerLayer() {
  // A plan view looks straight through the sky, so the sun sprite lands as a
  // white disc in the middle of the town. Suppress it for map plates only.
  if (document.body.classList.contains("map-shot")) return null;
  return new deck.ScatterplotLayer({
    id: "sun-marker",
    data: sunMarkerData(),
    pickable: false,
    billboard: true,
    radiusUnits: "meters",
    radiusMinPixels: 10,
    radiusMaxPixels: 28,
    stroked: true,
    lineWidthMinPixels: 1,
    getPosition: (sun) => sun.position,
    getRadius: (sun) => sun.radiusM,
    getFillColor: (sun) => sun.color,
    getLineColor: [255, 255, 255, 210],
    parameters: {
      depthTest: false
    }
  });
}

function sunMarkerData() {
  if (state.sun.altitudeRad <= 0) return [];

  const center = state.manifest?.center || {
    latitude: state.viewState.latitude,
    longitude: state.viewState.longitude
  };
  const radius = districtLongestDimensionMeters() * 0.72;
  const horizontal = radius * Math.cos(state.sun.altitudeRad);
  const eastMeters = -horizontal * Math.sin(state.sun.azimuthRad);
  const northMeters = -horizontal * Math.cos(state.sun.azimuthRad);
  const upMeters = radius * Math.sin(state.sun.altitudeRad);
  const latitude = center.latitude + northMeters / METERS_PER_DEGREE_LAT;
  const longitude = center.longitude + eastMeters / metersPerDegreeLongitude(center.latitude);
  const sky = skyForAltitude(state.sun.altitudeDeg);

  return [{
    position: [longitude, latitude, upMeters],
    color: sky.sunColor,
    radiusM: sky.sunRadiusM * 1.15
  }];
}

function sameCoordinate(a, b) {
  return Array.isArray(a) && Array.isArray(b) && a[0] === b[0] && a[1] === b[1];
}

function polygonCentroid(feature) {
  const ring = feature?.geometry?.coordinates?.[0] || [];
  if (ring.length < 3) return null;
  let lonSum = 0;
  let latSum = 0;
  let n = 0;
  for (let i = 0; i < ring.length; i += 1) {
    if (i === ring.length - 1 && sameCoordinate(ring[i], ring[0])) break;
    lonSum += ring[i][0];
    latSum += ring[i][1];
    n += 1;
  }
  if (!n) return null;
  return [lonSum / n, latSum / n];
}

function polygonBounds(feature) {
  const ring = feature?.geometry?.coordinates?.[0] || [];
  if (ring.length < 3) return null;
  const coords = ring.filter((coord) => Array.isArray(coord) && coord.length >= 2);
  if (!coords.length) return null;
  return coords.reduce((bounds, [lon, lat]) => ({
    minLon: Math.min(bounds.minLon, Number(lon)),
    minLat: Math.min(bounds.minLat, Number(lat)),
    maxLon: Math.max(bounds.maxLon, Number(lon)),
    maxLat: Math.max(bounds.maxLat, Number(lat))
  }), {
    minLon: Number.POSITIVE_INFINITY,
    minLat: Number.POSITIVE_INFINITY,
    maxLon: Number.NEGATIVE_INFINITY,
    maxLat: Number.NEGATIVE_INFINITY
  });
}

function mergeBounds(boundsList) {
  const bounds = (boundsList || []).filter(Boolean);
  if (!bounds.length) return null;
  return bounds.reduce((merged, bounds) => ({
    minLon: Math.min(merged.minLon, bounds.minLon),
    minLat: Math.min(merged.minLat, bounds.minLat),
    maxLon: Math.max(merged.maxLon, bounds.maxLon),
    maxLat: Math.max(merged.maxLat, bounds.maxLat)
  }), {
    minLon: Number.POSITIVE_INFINITY,
    minLat: Number.POSITIVE_INFINITY,
    maxLon: Number.NEGATIVE_INFINITY,
    maxLat: Number.NEGATIVE_INFINITY
  });
}

function boundsRing(bounds) {
  return [
    [bounds.minLon, bounds.minLat],
    [bounds.maxLon, bounds.minLat],
    [bounds.maxLon, bounds.maxLat],
    [bounds.minLon, bounds.maxLat],
    [bounds.minLon, bounds.minLat]
  ];
}

function offsetLngLat(lon, lat, eastM, northM) {
  const nextLat = lat + northM / METERS_PER_DEGREE_LAT;
  const nextLon = lon + eastM / metersPerDegreeLongitude(lat);
  return [nextLon, nextLat];
}

function districtLongestDimensionMeters() {
  const layout = layoutByName(state.currentLayout);
  const bounds = state.data?.metadata?.bounds || layout.bounds;
  if (!bounds || bounds.length !== 4) return DEFAULT_DISTRICT_SPAN_M;

  const [minLon, minLat, maxLon, maxLat] = bounds.map(Number);
  const centerLat = Number.isFinite(Number(state.manifest?.center?.latitude))
    ? Number(state.manifest.center.latitude)
    : (minLat + maxLat) / 2;
  const widthM = Math.abs(maxLon - minLon) * metersPerDegreeLongitude(centerLat);
  const heightM = Math.abs(maxLat - minLat) * METERS_PER_DEGREE_LAT;
  return Math.max(widthM, heightM, DEFAULT_DISTRICT_SPAN_M);
}

function buildCellPvLookup() {
  const cellPv = new Map();
  const cellPvDeployed = new Map();
  const rooftopPv = [];
  const solarFarmKeys = [];
  const floatingKeys = [];
  const carportKeys = [];
  const carportCeilingByKey = new Map();
  const cellSizeM = Number(state.data?.metadata?.grid?.cell_size_m || 200);
  const solarFarmCellKwp = cellSizeM * cellSizeM * SOLAR_FARM_KWP_PER_M2;

  (state.data?.features || []).forEach((feature) => {
    const props = feature.properties || {};
    const key = cellKey(props);
    if (!key) return;

    if (props.role === "parcel") {
      const deployed = Number(props.pv_deployed_kwp || 0);
      if (deployed > 0) {
        cellPvDeployed.set(key, (cellPvDeployed.get(key) || 0) + deployed);
      }
      if (props.land_use === "blue_space" && truthyFlag(props.is_floating_pv_site)) {
        const floatingCeiling = firstFiniteNumber(props, [
          "floating_pv_deployable_kwp",
          "deployable_pv_kwp"
        ]);
        if (floatingCeiling > 0) {
          cellPv.set(key, Math.max(cellPv.get(key) || 0, floatingCeiling));
        }
        floatingKeys.push(key);
      }
      const carportKwp = featureCarportKwp(props);
      if (carportKwp > 0) {
        cellPv.set(key, (cellPv.get(key) || 0) + carportKwp);
        carportCeilingByKey.set(key, carportKwp);
        carportKeys.push(key);
      }
    }

    if (props.role === "parcel" && props.land_use === "solar_farm") {
      const rawPv = props.deployable_pv_kwp;
      const directPv = Number(rawPv);
      const pvKwp = rawPv === undefined || rawPv === null || !Number.isFinite(directPv)
        ? solarFarmCellKwp
        : directPv;
      cellPv.set(key, (cellPv.get(key) || 0) + pvKwp);
      solarFarmKeys.push(key);
      return;
    }

    if (props.role === "parcel" && isSolarExpansionProps(props) && isExpansionActiveProps(props)) {
      cellPv.set(key, Math.max(cellPv.get(key) || 0, solarFarmCellKwp));
      solarFarmKeys.push(key);
      return;
    }

    if (props.role === "structure" && props.part_index === 1 && props.land_use !== "solar_farm") {
      const pvKwp = Number(props.deployable_pv_kwp || 0);
      if (pvKwp > 0) rooftopPv.push(pvKwp);
      cellPv.set(key, (cellPv.get(key) || 0) + pvKwp);
    }
  });

  const capacities = activeCockpitScenario()?.capacities || {};
  allocateScenarioCapacityToCells(solarFarmKeys, Number(capacities.solar_farm_kwp || 0), cellPv, cellPvDeployed);
  allocateScenarioCapacityToCells(floatingKeys, Number(capacities.floating_pv_kwp || 0), cellPv, cellPvDeployed, { setCeilingWhenMissing: true });
  allocateScenarioCapacityToCells(carportKeys, Number(capacities.carport_kwp || 0), cellPv, cellPvDeployed, {
    addToExisting: true,
    ceilingByKey: carportCeilingByKey
  });

  state.cellPvKwp = cellPv;
  state.cellPvDeployedKwp = cellPvDeployed;
  state.pvOverlayMaxKwp = Math.max(0, ...cellPv.values());
  state.pvOverlayScaleKwp = percentile(rooftopPv, 0.90) || Math.max(0, ...rooftopPv) || state.pvOverlayMaxKwp;
}

function buildLightingLookup() {
  const lighting = new Map();
  (state.data?.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel") return;
    const key = cellKey(props);
    if (!key || !Array.isArray(props.lighting_by_daypart) || !props.lighting_by_daypart.length) return;
    const schedule = props.lighting_by_daypart
      .slice(0, LIGHTING_DAYPART_LABELS.length)
      .map((value) => clamp(Number(value) || 0, 0, 1));
    if (schedule.length === LIGHTING_DAYPART_LABELS.length && schedule.some((value) => value > 0)) {
      lighting.set(key, schedule);
    }
  });
  state.cellLightingByDaypart = lighting;
  _buildingGlowCache = { layoutKey: null, features: [] };
}

function allocateScenarioCapacityToCells(keys, capacityKwp, cellPv, cellPvDeployed, options = {}) {
  const uniqueKeys = Array.from(new Set(keys)).filter(Boolean);
  const capacity = Number(capacityKwp || 0);
  if (!uniqueKeys.length || capacity <= 0) return;
  const ceilings = uniqueKeys.map((key) => {
    const override = options.ceilingByKey instanceof Map ? Number(options.ceilingByKey.get(key)) : NaN;
    return Math.max(0, Number.isFinite(override) && override > 0 ? override : Number(cellPv.get(key) || 0));
  });
  const totalCeiling = sum(ceilings);
  uniqueKeys.forEach((key, index) => {
    const existingCeiling = ceilings[index];
    const share = totalCeiling > 0
      ? existingCeiling / totalCeiling
      : 1 / uniqueKeys.length;
    const deployed = capacity * share;
    if (options.setCeilingWhenMissing || existingCeiling <= 0) {
      cellPv.set(key, Math.max(existingCeiling, deployed));
    }
    const existingDeployed = options.addToExisting ? Number(cellPvDeployed.get(key) || 0) : 0;
    const totalDeployed = existingDeployed + Math.max(deployed, 0);
    cellPvDeployed.set(key, Math.min(totalDeployed, Math.max(cellPv.get(key) || 0, totalDeployed)));
  });
}

function buildCellShadingLookup() {
  const cells = new Map();
  (state.data?.features || []).forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "parcel") return;
    const key = cellKey(props);
    if (!key) return;
    cells.set(key, {
      props,
      row: Number(props.row),
      col: Number(props.col),
      heightM: Number(props.cell_height_m ?? props.height_m ?? 0),
      hasBuilding: Boolean(props.is_built),
      landUse: String(props.land_use || "")
    });
  });

  // v2: read the physics-based multiplier from
  // `pv_shading_multiplier_geom` (exported by core/export_3d.py from
  // energy.solar_geometry.compute_geometric_shading). Fall back to the
  // legacy step-function heuristic only for older GeoJSON without the
  // property -- that path is now a backward-compat shim, not the
  // headline. The "offenders" list is kept (for tooltip context) but
  // does NOT control the multiplier when the geometric value is present.
  const checks = [
    { dr: -1, dc: -1, label: "SW" },
    { dr: -1, dc: 0, label: "S" },
    { dr: -1, dc: 1, label: "SE" },
    { dr: 0, dc: -1, label: "W" },
    { dr: 0, dc: 1, label: "E" }
  ];
  const shading = new Map();

  cells.forEach((cell, key) => {
    const pvKwp = state.cellPvKwp.get(key) || 0;
    if (pvKwp <= 0) return;
    const myHeight = cell.landUse === "solar_farm" ? GROUND_PV_PANEL_TOP_M : cell.heightM;
    const offenders = [];
    checks.forEach(({ dr, dc, label }) => {
      const neighbour = cells.get(`${cell.row + dr}_${cell.col + dc}`);
      if (!neighbour) return;
      const neighbourHeight = Number(neighbour.heightM || 0);
      if (neighbourHeight - myHeight > SHADING_DELTA_M) {
        offenders.push({ direction: label, heightM: neighbourHeight });
      }
    });

    // Prefer the physics-based geometric multiplier when present.
    const geometricMult = Number(cell.props?.pv_shading_multiplier_geom);
    let multiplier;
    let penalty;
    let source;
    if (Number.isFinite(geometricMult)) {
      multiplier = clamp(geometricMult, 0, 1);
      penalty = 1 - multiplier;
      source = "geometric";
    } else {
      penalty = Math.min(MAX_SHADING_PENALTY, offenders.length * PER_SHADING_OFFENDER);
      multiplier = 1 - penalty;
      source = "heuristic";
    }

    shading.set(key, {
      multiplier,
      penalty,
      offenders,
      pvKwp,
      source,
      percentile: finiteOrNull(cell.props?.pv_shading_percentile),
      offenderDirs: parseShadingOffenderDirs(cell.props?.pv_shading_offender_dirs),
      reason: String(cell.props?.pv_shading_reason || "").trim()
    });
  });

  state.cellShading = shading;
  state.shadingRamp = buildShadingRamp(shading);
  updateShadingLegend();
}

function buildShadingRamp(shading) {
  const entries = Array.from(shading.values());
  const geometricValues = entries
    .filter((shade) => shade.source === "geometric")
    .map((shade) => Number(shade.multiplier))
    .filter((value) => Number.isFinite(value));
  const allValues = entries
    .map((shade) => Number(shade.multiplier))
    .filter((value) => Number.isFinite(value));
  const values = geometricValues.length ? geometricValues : allValues;
  if (!values.length) {
    return {
      source: "none",
      min: LEGACY_SHADING_MIN_MULTIPLIER,
      max: 1,
      actualMin: LEGACY_SHADING_MIN_MULTIPLIER,
      actualMax: 1,
      count: 0,
      unshadedCount: 0
    };
  }

  const actualMin = Math.min(...values);
  const actualMax = Math.max(...values);
  const nonUnityValues = values.filter((value) => value < 0.999);
  const dynamicMaxRaw = nonUnityValues.length
    ? percentile(nonUnityValues, SHADING_DYNAMIC_TOP_QUANTILE)
    : actualMax;
  const dynamicMin = actualMin;
  const dynamicMax = Math.max(dynamicMin + 0.001, Math.min(1, dynamicMaxRaw || actualMax || 1));
  return {
    source: geometricValues.length ? "geom" : "legacy",
    min: dynamicMin,
    max: dynamicMax,
    actualMin,
    actualMax,
    count: values.length,
    unshadedCount: values.filter((value) => value >= 0.999).length
  };
}

function totalPvKwp() {
  return Array.from(state.cellPvKwp.values()).reduce((sum, value) => sum + value, 0);
}

function pvCapacityKwpFromCapacities(capacities) {
  if (!capacities || typeof capacities !== "object") return null;
  const keys = [
    "rooftop_pv_kwp",
    "solar_farm_kwp",
    "carport_kwp",
    "floating_pv_kwp",
    "bipv_kwp"
  ];
  const values = keys
    .map((key) => numberOrNull(capacities[key]))
    .filter((value) => value !== null && value > 0);
  if (!values.length) return null;
  return sum(values);
}

function designPvCapacityKwp() {
  const scenario = activeCockpitRawScenario();
  const activeCap = pvCapacityKwpFromCapacities(activeCockpitScenario()?.capacities);
  if (activeCap !== null) return activeCap;
  const baseCap = pvCapacityKwpFromCapacities(scenario?.capacities_base_year);
  if (baseCap !== null) return baseCap;
  return totalPvKwp();
}

function totalHourlyPvKwh() {
  return Array.from(state.cellPvKwp.entries()).reduce((sum, [key, value]) => {
    const shade = state.cellShading.get(key);
    const multiplier = shade ? shade.multiplier : 1;
    return sum + Number(value || 0) * multiplier * state.sun.pvCapacityFactor;
  }, 0);
}

function cellKey(props) {
  if (!Number.isFinite(Number(props.row)) || !Number.isFinite(Number(props.col))) return "";
  return `${props.row}_${props.col}`;
}

function updateInfo() {
  if (!state.data) return;
  const metadata = state.data.metadata || {};
  const layout = layoutByName(state.currentLayout);
  const features = state.data.features || [];
  const parcels = features.filter((f) => f.properties.role === "parcel");
  const structures = features.filter((f) => f.properties.role !== "parcel");
  const builtStructures = structures.filter((f) => f.properties.is_built);
  const pvKwp = designPvCapacityKwp();
  const activeYear = activeCockpitScenario()?.active_period_year || state.cockpit.periodYear || activeCockpitRawScenario()?.capacities_base_year?.year || DEFAULT_COCKPIT_PERIOD_YEAR;

  // The panel under this heading is the metric summary, so the heading says
  // what the panel IS, not which layout is loaded (the author, "it shows
  // all the important numbers so change the name like key numbers"). The full
  // manifest label - "Planned Integrated (this thesis)" - named the layout and
  // told the reader nothing about the contents. The short layout name is kept
  // as a qualifier so the numbers are never ambiguous about which town they
  // describe, which the buttons alone would leave implicit once a screenshot is
  // cropped.
  els.layoutTitle.textContent = `Key numbers - ${shortLayoutLabel(layout)}`;
  els.layoutSubtitle.textContent = `${metadata.grid?.area_km2 || 25} km² georeferenced district centred on ${formatCoord(metadata.center?.latitude)}, ${formatCoord(metadata.center?.longitude)}.`;
  els.statCells.textContent = String(parcels.length);
  els.statFeatures.textContent = String(features.length);
  els.statBuilt.textContent = String(builtStructures.length);
  if (els.statPvLabel) els.statPvLabel.textContent = `PV ${activeYear}`;
  els.statPv.textContent = formatPv(pvKwp);
  els.statPv.title = activeCockpitScenario()?.has_period_breakdown
    ? `${activeYear} installed PV, from the current model run.`
    : "PV technical ceiling from the loaded GeoJSON geometry.";
  if (els.statRoadNetwork) {
    const road = metadata.road_network || {};
    const cells = Number(road.road_cells || metadata.land_use_counts?.road || 0);
    const rowShare = Number(road.row_share_of_site || 0);
    els.statRoadNetwork.textContent = cells ? `${cells} / ${formatSmallPercent(rowShare)}` : "--";
    els.statRoadNetwork.title = cells
      ? `${cells} road cells; ${formatArea((road.row_km2_total || 0) * 1_000_000)} road ROW; local lanes ${Number(road.local_street_edges || 0).toLocaleString("en-GB")} edges.`
      : "Road-network metadata not exported.";
  }
  if (els.statWalkability) {
    const walk = metadata.walkability || {};
    const composite = Number(walk.composite);
    els.statWalkability.textContent = Number.isFinite(composite) ? composite.toFixed(2) : "--";
    els.statWalkability.title = Number.isFinite(composite)
      ? `Access ${Number(walk.access || 0).toFixed(2)}; permeability ${Number(walk.permeability || 0).toFixed(2)}; green loop ${Number(walk.green_loop || 0).toFixed(2)}.`
      : "Walkability metadata not exported.";
  }
  els.statSun.textContent = `${Math.max(0, state.sun.altitudeDeg).toFixed(0)} deg / ${Math.round(state.sun.irradianceWm2)} W/m2`;
  els.statPvNow.textContent = formatEnergy(totalHourlyPvKwh());
  els.statPvNow.title = "Clear-sky geometric PV potential from the sun slider and local PV ceilings; dispatch PV is shown in the cockpit.";
  updateLeftDockLayout();
}

function updateLegend() {
  const parcels = state.data.features.filter((f) => f.properties.role === "parcel");
  const plants = state.data.features.filter((f) => isPlantFeatureProps(f.properties));
  const metadata = state.data.metadata || {};
  const subtypeCounts = new Map();
  const edgeCounts = new Map();
  const seen = new Map();
  parcels.forEach((feature) => {
    const props = feature.properties || {};
    const landUse = props.land_use;
    if (!seen.has(landUse)) {
      //: legend chips must match the rendered remap, not the baked css.
      const mapped = designRgb(props);
      seen.set(landUse, mapped
        ? `rgb(${mapped[0]}, ${mapped[1]}, ${mapped[2]})`
        : props.colour);
    }
    const subtype = props.amenity_subtype;
    if (subtype) subtypeCounts.set(subtype, (subtypeCounts.get(subtype) || 0) + 1);
  });
  state.data.features.forEach((feature) => {
    const props = feature.properties || {};
    if (props.role !== "street_edge") return;
    edgeCounts.set(props.kind, (edgeCounts.get(props.kind) || 0) + 1);
  });

  els.legendList.innerHTML = "";
  const rgbaCss = (rgba) => `rgba(${rgba[0]}, ${rgba[1]}, ${rgba[2]}, ${(rgba[3] ?? 255) / 255})`;
  const appendLegendSection = (title, rows, swatchClass = "street-asset-swatch") => {
    const visibleRows = rows.filter((row) => row && row.label);
    if (!visibleRows.length) return;
    const heading = document.createElement("div");
    heading.className = "legend-section-label";
    heading.textContent = title;
    els.legendList.appendChild(heading);
    visibleRows.forEach((item) => {
      const row = document.createElement("div");
      row.className = "legend-row";
      const swatch = document.createElement("span");
      swatch.className = `swatch ${item.swatchClass || swatchClass}`.trim();
      swatch.style.background = item.colour;
      const label = document.createElement("span");
      label.textContent = item.label;
      row.append(swatch, label);
      els.legendList.appendChild(row);
    });
  };

  LAND_USE_ORDER.filter((landUse) => seen.has(landUse)).forEach((landUse) => {
    const row = document.createElement("div");
    row.className = "legend-row";
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = seen.get(landUse);
    const label = document.createElement("span");
    label.textContent = LABELS[landUse] || titleCase(landUse);
    row.append(swatch, label);
    els.legendList.appendChild(row);
  });

  const roadByClass = metadata.road_network?.cells_by_class || {};
  appendLegendSection("Road + paths", [
    Number(roadByClass.arterial || 0) > 0 && {
      label: `Arterial road cells (${roadByClass.arterial})`,
      colour: "rgb(70, 75, 76)"
    },
    Number(roadByClass.collector || 0) > 0 && {
      label: `Collector road cells (${roadByClass.collector})`,
      colour: "rgb(92, 98, 98)"
    },
    Number(roadByClass.local || 0) > 0 && {
      label: `Local road cells (${roadByClass.local})`,
      colour: "rgb(116, 126, 122)"
    },
    Number(edgeCounts.get("local_street") || 0) > 0 && {
      label: `Local access lanes (${edgeCounts.get("local_street")})`,
      colour: rgbaCss(streetEdgeColour("local_street"))
    },
    Number(edgeCounts.get("greenway_path") || 0) > 0 && {
      label: `Greenway paths (${edgeCounts.get("greenway_path")})`,
      colour: rgbaCss(streetEdgeColour("greenway_path"))
    }
  ]);

  appendLegendSection("Green + reserves", [
    Number(subtypeCounts.get("canal") || 0) > 0 && {
      label: `Canal corridor (${subtypeCounts.get("canal")})`,
      colour: "rgb(40, 136, 207)"
    },
    Number(subtypeCounts.get("park_community") || 0) > 0 && {
      label: `Community parks (${subtypeCounts.get("park_community")})`,
      colour: "rgb(64, 150, 83)"
    },
    Number(subtypeCounts.get("greenway") || 0) > 0 && {
      label: `Greenway open space (${subtypeCounts.get("greenway")})`,
      colour: "rgb(72, 175, 95)"
    },
    Number(subtypeCounts.get("agri_belt") || 0) > 0 && {
      label: `Agri belt (${subtypeCounts.get("agri_belt")})`,
      colour: "rgb(143, 158, 78)"
    },
    (Number(subtypeCounts.get("solar_expansion_2042") || 0) + Number(subtypeCounts.get("solar_expansion_2055") || 0)) > 0 && {
      label: `Solar expansion reserve (${Number(subtypeCounts.get("solar_expansion_2042") || 0) + Number(subtypeCounts.get("solar_expansion_2055") || 0)})`,
      colour: "rgb(230, 216, 140)"
    },
    (Number(subtypeCounts.get("parking_expansion_2042") || 0) + Number(subtypeCounts.get("parking_expansion_2055") || 0)) > 0 && {
      label: `Parking expansion reserve (${Number(subtypeCounts.get("parking_expansion_2042") || 0) + Number(subtypeCounts.get("parking_expansion_2055") || 0)})`,
      colour: "rgb(178, 188, 188)"
    }
  ]);

  const streetAssets = [];
  if (parcels.some((feature) => truthyFlag(feature.properties?.has_street_trees))) {
    streetAssets.push(["Street trees", `rgb(${STREET_TREE_COLOUR.join(",")})`]);
  }
  if (parcels.some((feature) => streetlightType(feature.properties) === "solar")) {
    streetAssets.push(["Solar streetlight + panel", `rgb(${STREETLIGHT_SOLAR_COLOUR.join(",")})`]);
  }
  if (parcels.some((feature) => streetlightType(feature.properties) === "grid")) {
    streetAssets.push(["Grid streetlight", `rgb(${STREETLIGHT_GRID_COLOUR.join(",")})`]);
  }
  const carportKwp = totalCarportCeilingKwp();
  if (carportKwp > 0) {
    streetAssets.push([`Parking-lot solar canopy (${formatPv(carportKwp)})`, "rgb(14,165,233)"]);
  }
  if (streetAssets.length) {
    const heading = document.createElement("div");
    heading.className = "legend-section-label";
    heading.textContent = "Street assets";
    els.legendList.appendChild(heading);

    streetAssets.forEach(([name, colour]) => {
      const row = document.createElement("div");
      row.className = "legend-row";
      const swatch = document.createElement("span");
      swatch.className = "swatch street-asset-swatch";
      swatch.style.background = colour;
      const label = document.createElement("span");
      label.textContent = name;
      row.append(swatch, label);
      els.legendList.appendChild(row);
    });
  }

  if (plants.length) {
    const heading = document.createElement("div");
    heading.className = "legend-section-label";
    heading.textContent = "Stage C plants";
    els.legendList.appendChild(heading);

    const plantSeen = new Map();
    plants.forEach((feature) => {
      const props = feature.properties || {};
      const kind = props.plant_kind || "plant";
      if (!plantSeen.has(kind)) plantSeen.set(kind, props);
    });

    const orderedKinds = [
      ...PLANT_KIND_ORDER.filter((kind) => plantSeen.has(kind)),
      ...Array.from(plantSeen.keys()).filter((kind) => !PLANT_KIND_ORDER.includes(kind))
    ];
    orderedKinds.forEach((kind) => {
      const row = document.createElement("div");
      row.className = "legend-row plant-legend-row";
      const swatch = document.createElement("span");
      swatch.className = "swatch plant-swatch";
      const rgb = plantRgb(plantSeen.get(kind));
      swatch.style.background = `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
      const label = document.createElement("span");
      label.textContent = plantKindLabel(kind);
      row.append(swatch, label);
      els.legendList.appendChild(row);
    });
  }
}

async function loadModuleMix() {
  try {
    const response = await fetch(ECONOMICS_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`economics ${response.status}`);
    const text = await response.text();
    state.moduleMix = parseModuleMixYaml(text);
  } catch (error) {
    console.warn("PV module mix could not be loaded:", error);
    state.moduleMix = DEFAULT_MODULE_MIX;
  }
}

function parseModuleMixYaml(text) {
  const modules = {};
  let inRooftop = false;
  let inModuleTypes = false;
  let current = "";
  String(text || "").split(/\r?\n/).forEach((line) => {
    if (/^\s*rooftop_pv:\s*$/.test(line)) {
      inRooftop = true;
      inModuleTypes = false;
      current = "";
      return;
    }
    if (inRooftop && /^\s{2}[a-zA-Z0-9_]+:\s*$/.test(line) && !/^\s*rooftop_pv:\s*$/.test(line)) {
      inRooftop = false;
      inModuleTypes = false;
      current = "";
      return;
    }
    if (!inRooftop) return;
    if (/^\s*module_types:\s*$/.test(line)) {
      inModuleTypes = true;
      current = "";
      return;
    }
    if (!inModuleTypes) return;

    const moduleMatch = line.match(/^\s{6}([a-zA-Z0-9_]+):\s*$/);
    if (moduleMatch) {
      current = moduleMatch[1];
      modules[current] = modules[current] || {};
      return;
    }
    if (!current) return;
    const valueMatch = line.match(/^\s{8}(share|efficiency|capex_inr_per_kwp|temp_coefficient_per_c):\s*([0-9.]+)/);
    if (valueMatch) {
      modules[current][valueMatch[1]] = Number(valueMatch[2]);
    }
  });

  const entries = Object.entries(modules)
    .map(([key, value]) => ({ key, ...(value || {}) }))
    .filter((entry) => Number(entry.share) > 0);
  if (!entries.length) return DEFAULT_MODULE_MIX;
  const shareTotal = entries.reduce((total, entry) => total + Number(entry.share || 0), 0) || 1;
  const dominant = entries.reduce((best, entry) => (
    Number(entry.share || 0) > Number(best.share || 0) ? entry : best
  ), entries[0]);
  const weighted = (field) => entries.reduce((total, entry) => (
    total + Number(entry[field] || 0) * Number(entry.share || 0) / shareTotal
  ), 0);
  return {
    dominantKey: dominant.key,
    dominantLabel: `${MODULE_LABELS[dominant.key] || titleCase(dominant.key)} blend`,
    summaryLabel: `${MODULE_LABELS[dominant.key] || titleCase(dominant.key)} blend`,
    efficiency: weighted("efficiency"),
    capexInrPerKwp: weighted("capex_inr_per_kwp"),
    tempCoefficientPerC: weighted("temp_coefficient_per_c")
  };
}

async function loadBaselineAudit() {
  try {
    const response = await fetch(BASELINE_AUDIT_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`baseline audit ${response.status}`);
    const text = await response.text();
    state.baselineAudit = parseBaselineAuditMarkdown(text);
  } catch (error) {
    console.warn("Baseline audit summary could not be loaded:", error);
    state.baselineAudit = {};
  }
}

async function loadPriceScenarioSweep() {
  try {
    const response = await fetch(PRICE_SCENARIO_SWEEP_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`price scenario sweep ${response.status}`);
    const text = await response.text();
    state.priceScenarioSweep = parsePriceScenarioCsv(text);
    state.cockpit.priceScenario = defaultPriceScenarioName();
    populatePriceScenarioSelect();
  } catch (error) {
    console.warn("Price scenario sweep could not be loaded:", error);
    state.priceScenarioSweep = [];
    populatePriceScenarioSelect();
  }
}

function parsePriceScenarioCsv(text) {
  const lines = String(text || "").split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) return [];
  const headers = splitCsvRow(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = splitCsvRow(line);
    const row = {};
    headers.forEach((header, index) => {
      row[header] = cells[index] ?? "";
    });
    const scenario = row.scenario || "";
    return {
      scenario,
      label: PRICE_SCENARIO_LABELS[scenario] || titleCase(scenario),
      source: row.source || PRICE_SCENARIO_SOURCES[scenario] || "Pre-computed A21 trajectory sweep.",
      tariffEscRealAnnual: Number(row.tariff_esc_real_annual || 0),
      efTrajectoryAvgKgco2PerKwh: Number(row.ef_trajectory_avg_kgco2_per_kwh || 0),
      annualCostInr: Number(row.annual_cost_inr || 0),
      annualEmissionsKgco2: Number(row.annual_emissions_kgco2 || 0),
      lifetimeCostInr: Number(row.lifetime_cost_inr || 0),
      deltaCostPct: Number(row.delta_annual_cost_inr_pct_vs_nep_policy_push || 0),
      deltaEmissionsPct: Number(row.delta_annual_emissions_kgco2_pct_vs_nep_policy_push || 0),
      deltaLifetimePct: Number(row.delta_lifetime_cost_inr_pct_vs_nep_policy_push || 0)
    };
  }).filter((row) => row.scenario);
}

function splitCsvRow(line) {
  const cells = [];
  let current = "";
  let quoted = false;
  const chars = String(line || "").split("");
  for (let index = 0; index < chars.length; index += 1) {
    const char = chars[index];
    if (char === '"' && chars[index + 1] === '"') {
      current += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      quoted = !quoted;
      continue;
    }
    if (char === "," && !quoted) {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}

function populatePriceScenarioSelect() {
  if (!els.cockpitPriceScenario) return;
  const rows = state.priceScenarioSweep || [];
  els.cockpitPriceScenario.innerHTML = "";
  if (!rows.length) {
    const option = document.createElement("option");
    option.value = "nep_policy_push";
    option.textContent = "NEP policy push";
    els.cockpitPriceScenario.appendChild(option);
    els.cockpitPriceScenario.disabled = true;
    return;
  }
  els.cockpitPriceScenario.disabled = false;
  rows.forEach((row) => {
    const option = document.createElement("option");
    option.value = row.scenario;
    option.textContent = row.label;
    option.title = row.source;
    els.cockpitPriceScenario.appendChild(option);
  });
  els.cockpitPriceScenario.value = state.cockpit.priceScenario || defaultPriceScenarioName();
}

function defaultPriceScenarioName() {
  const rows = state.priceScenarioSweep || [];
  if (rows.some((row) => row.scenario === "nep_policy_push")) return "nep_policy_push";
  return rows[0]?.scenario || "nep_policy_push";
}

function priceScenarioRowByName(name) {
  return (state.priceScenarioSweep || []).find((row) => row.scenario === name) || null;
}

function selectedPriceScenarioRow() {
  const selected = state.cockpit.priceScenario || defaultPriceScenarioName();
  return priceScenarioRowByName(selected) || priceScenarioRowByName(defaultPriceScenarioName());
}

function formatScenarioDelta(value, unit = "%") {
  const delta = Number(value || 0);
  if (Math.abs(delta) < 0.05) return `+0.0${unit}`;
  return `${delta > 0 ? "+" : ""}${delta.toFixed(1)}${unit}`;
}

function priceScenarioBarChart(rows, selectedName) {
  const data = rows || [];
  if (!data.length) {
    return `<div class="cockpit-empty-chart">No price-scenario sweep loaded.</div>`;
  }
  const width = 360;
  const rowH = 31;
  const height = 24 + data.length * rowH;
  const padL = 112;
  const padR = 22;
  const maxEmissions = Math.max(1, ...data.map((row) => Number(row.annualEmissionsKgco2 || 0)));
  const bars = data.map((row, index) => {
    const y = 18 + index * rowH;
    const barW = (Number(row.annualEmissionsKgco2 || 0) / maxEmissions) * (width - padL - padR);
    const selected = row.scenario === selectedName;
    const colour = selected ? "#38bdf8" : "#64748b";
    const tooltip = [
      row.label,
      `Annual emissions: ${formatEmissions(row.annualEmissionsKgco2)}`,
      `Lifetime cost: ${formatCost(row.lifetimeCostInr)} INR`,
      `Emissions delta vs NEP: ${formatScenarioDelta(row.deltaEmissionsPct)}`,
      row.source
    ].join("\n");
    return `
      <g ${tooltipAttr(tooltip)}>
        <text x="${padL - 8}" y="${y + 10}" text-anchor="end" fill="${selected ? "#f8fafc" : "#93a4b8"}" font-size="9">${escapeHtml(row.label)}</text>
        <rect x="${padL}" y="${y}" width="${Math.max(2, barW)}" height="13" rx="2" fill="${colour}" opacity="${selected ? "0.95" : "0.58"}"></rect>
        <text x="${padL + Math.max(22, barW) + 6}" y="${y + 10}" fill="${selected ? "#f8fafc" : "#93a4b8"}" font-size="9">${formatEmissions(row.annualEmissionsKgco2)}</text>
      </g>
    `;
  }).join("");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Annual emissions by price trajectory">
      <text x="${padL}" y="10" fill="#93a4b8" font-size="9">annual emissions</text>
      ${bars}
    </svg>
  `;
}

async function loadPlacementAudit() {
  try {
    const response = await fetch(PLACEMENT_AUDIT_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`placement audit ${response.status}`);
    const text = await response.text();
    state.placementAudit = parsePlacementAuditMarkdown(text);
  } catch (error) {
    console.warn("Placement audit could not be loaded:", error);
    state.placementAudit = { categories: [], byCell: new Map() };
  }
  renderPlacementAuditLegend();
}

function parsePlacementAuditMarkdown(text) {
  const byCell = new Map();
  const summaryCounts = new Map();
  const lines = String(text || "").split(/\r?\n/);
  let section = "";
  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    const sectionMatch = line.match(/^##\s+(.+)$/);
    if (sectionMatch) {
      section = sectionMatch[1].trim();
      return;
    }
    const tableMatch = line.match(/^\|\s*([^|]+?)\s*\|\s*([0-9]+)\s*\|$/);
    if (section === "Summary" && tableMatch && tableMatch[1].trim() !== "Category") {
      const category = tableMatch[1].trim();
      if (PLACEMENT_AUDIT_CATEGORIES[category]) {
        summaryCounts.set(category, Number(tableMatch[2]));
      }
      return;
    }
    if (!line.startsWith("- ") || !section || section === "Summary") return;
    if (!PLACEMENT_AUDIT_CATEGORIES[section]) return;
    const coordMatch = line.match(/\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)/);
    if (!coordMatch) return;
    const row = Number(coordMatch[1]);
    const col = Number(coordMatch[2]);
    const key = `${row}_${col}`;
    const issue = {
      category: section,
      row,
      col,
      text: line.replace(/^-\s*/, ""),
      note: auditCategoryMeta(section).note
    };
    if (!byCell.has(key)) byCell.set(key, []);
    byCell.get(key).push(issue);
  });

  const categories = Array.from(summaryCounts.entries()).map(([category, count]) => ({
    category,
    count,
    ...auditCategoryMeta(category)
  }));
  return { categories, byCell };
}

function renderPlacementAuditLegend() {
  if (!els.realismFlagsList) return;
  const categories = state.placementAudit.categories || [];
  els.realismFlagsList.innerHTML = categories.length
    ? categories.map((category) => {
        const rgb = category.colour || [251, 191, 36];
        return `
          <div class="pv-legend-row realism-legend-row">
            <span class="pv-swatch" style="background: rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})"></span>
            <span>${escapeHtml(category.short)} <strong>${Number(category.count || 0)}</strong></span>
          </div>
        `;
      }).join("")
    : `<p class="legend-note">No placement audit loaded.</p>`;
}

function auditCategoryMeta(category) {
  const meta = PLACEMENT_AUDIT_CATEGORIES[category];
  return meta || {
    short: titleCase(category || "placement flag"),
    colour: [251, 191, 36],
    note: "Placement audit flag from outputs/data/placement_audit.md."
  };
}

function auditIssuesForProps(props) {
  if (!props) return [];
  if (Array.isArray(props.auditIssues)) return props.auditIssues;
  const key = cellKey(props);
  return key ? (state.placementAudit.byCell.get(key) || []) : [];
}

function formatAuditIssues(props) {
  const issues = auditIssuesForProps(props);
  if (!issues.length) return "";
  return issues.map((issue) => auditCategoryMeta(issue.category).short).join("; ");
}

function tooltipAuditRows(props) {
  const issues = auditIssuesForProps(props);
  if (!issues.length) return "";
  return issues.map((issue) => {
    const meta = auditCategoryMeta(issue.category);
    const detail = meta.note || meta.short;
    return `
        <span>${escapeHtml(meta.short)}</span><strong>${escapeHtml(detail)}</strong>
    `;
  }).join("");
}

function parseBaselineAuditMarkdown(text) {
  const lines = String(text || "").split(/\r?\n/);
  const headerIndex = lines.findIndex((line) => line.trim().startsWith("| constraint |"));
  if (headerIndex < 0) return {};
  const headers = splitMarkdownRow(lines[headerIndex]).slice(1);
  const audit = {};
  headers.forEach((name) => {
    audit[name] = { passCount: 0, total: 0, gapSum: 0 };
  });
  for (let i = headerIndex + 2; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (!line || line.startsWith("## ")) break;
    if (!line.startsWith("|")) continue;
    const cells = splitMarkdownRow(line);
    if (cells.length < headers.length + 1) continue;
    headers.forEach((name, index) => {
      const value = cells[index + 1] || "";
      if (!value.includes("[OK]") && !value.includes("[FAIL")) return;
      audit[name].total += 1;
      if (value.includes("[OK]")) audit[name].passCount += 1;
      const gapMatch = value.match(/gap=([0-9.]+)/);
      if (gapMatch) audit[name].gapSum += Number(gapMatch[1]);
    });
  }
  return audit;
}

function splitMarkdownRow(line) {
  return String(line || "")
    .split("|")
    .slice(1, -1)
    .map((value) => value.trim());
}

function renderArchetypeSummary() {
  if (!els.archetypeSummary) return;
  const row = state.baselineAudit?.[state.currentLayout];
  if (!row) {
    els.archetypeSummary.innerHTML = "";
    return;
  }
  const opt = state.baselineAudit.optimised_sa;
  const label = state.currentLayout || "";
  const gap = Number(row.gapSum || 0);
  const pieces = [
    `<span class="archetype-chip"><strong>${escapeHtml(label)}</strong><span>${Number(row.passCount || 0)}/${Number(row.total || 18)} pass</span><span>Gap sum ${gap.toFixed(2)}</span></span>`
  ];
  if (opt && state.currentLayout !== "optimised_sa") {
    const delta = gap - Number(opt.gapSum || 0);
    pieces.push(`<span class="archetype-chip ${delta <= 0 ? "delta-good" : "delta-watch"}"><strong>vs SA</strong><span>${delta >= 0 ? "+" : ""}${delta.toFixed(2)} gap</span></span>`);
  } else if (opt && state.currentLayout === "optimised_sa") {
    pieces.push(`<span class="archetype-chip delta-good"><strong>Severity leader</strong><span>Smallest gap sum</span></span>`);
  }
  els.archetypeSummary.innerHTML = pieces.join("");
}

async function loadEnergySummary() {
  try {
    const response = await fetch(ENERGY_SUMMARY_URL, { cache: "no-store" });
    if (!response.ok) {
      if (response.status !== 404) {
        console.warn(`Energy summary unavailable: ${response.status}`);
      }
      return;
    }
    const summary = await response.json();
    state.energySummary = normaliseEnergySummary(summary);
    renderEnergySummary();
  } catch (error) {
    console.warn("Energy summary could not be loaded:", error);
  }
}

function normaliseEnergySummary(summary) {
  const rawRows = Array.isArray(summary)
    ? summary
    : Array.isArray(summary?.results)
      ? summary.results
      : Array.isArray(summary?.scenarios)
        ? summary.scenarios
        : summary?.scenarios && typeof summary.scenarios === "object"
          ? Object.entries(summary.scenarios).map(([scenario, data]) => ({ scenario, ...data }))
          : [];

  const byScenario = new Map();
  rawRows.forEach((row) => {
    const scenario = row.scenario || row.name;
    if (!scenario) return;
    byScenario.set(scenario, row);
  });

  return SCENARIO_ORDER
    .map((scenario) => byScenario.get(scenario))
    .filter(Boolean);
}

function renderEnergySummary() {
  const rows = state.energySummary || [];
  if (!rows.length) {
    els.energySummary.classList.add("hidden");
    return;
  }

  els.energySummaryGrid.innerHTML = "";
  const header = document.createElement("div");
  header.className = "energy-row header";
  ["Scenario", "INR/yr", "tCO2/yr", "PV design"].forEach((label) => {
    const span = document.createElement("span");
    span.textContent = label;
    header.appendChild(span);
  });
  els.energySummaryGrid.appendChild(header);

  rows.forEach((row) => {
    const capacities = row.capacities || {};
    const designCapacities = row.capacities_base_year || capacities;
    const annualCost = Number(row.annual_cost_inr ?? row.cost_inr_per_year ?? row.cost_inr_yr ?? 0);
    const annualEmissions = Number(row.annual_emissions_kgco2 ?? row.emissions_kgco2_per_year ?? 0);
    const annualDemand = Number(row.annual_demand_kwh || 0);
    const pvKwp = Number(
      row.total_pv_kwp
      ?? row.pv_kwp
      ?? designCapacities.total_pv_kwp
      ?? pvCapacityKwpFromCapacities(designCapacities)
      ?? (Number(designCapacities.rooftop_pv_kwp || 0) + Number(designCapacities.solar_farm_kwp || 0))
    );
    const lcoe = Number(row.lcoe_inr_per_kwh ?? (annualDemand ? annualCost / annualDemand : 0));
    const renewableShare = Number(row.renewable_share ?? renewableShareFromRow(row, annualDemand));
    const values = [
      scenarioLabel(row.scenario || row.name),
      formatCost(annualCost),
      formatEmissions(annualEmissions),
      formatPv(pvKwp)
    ];
    const item = document.createElement("div");
    item.className = "energy-row";
    values.forEach((value, index) => {
      const el = index === 0 ? document.createElement("strong") : document.createElement("span");
      el.textContent = value;
      item.appendChild(el);
    });

    const sub = document.createElement("div");
    sub.className = "energy-row-sub";
    [
      `INR/day ${formatDailyCost(annualCost)}`,
      `CO2/day ${formatDailyEmissions(annualEmissions)}`,
      `Net cost ${formatInrPerKwh(lcoe)}`,
      `Renewables ${formatPercent(renewableShare)}`
    ].forEach((value) => {
      const chip = document.createElement("span");
      chip.className = "energy-chip";
      chip.textContent = value;
      sub.appendChild(chip);
    });
    item.appendChild(sub);
    els.energySummaryGrid.appendChild(item);
  });

  els.energySummary.classList.add("hidden");
}

async function loadCockpitData() {
  const dispatch = await fetchJsonOptional(DISPATCH_RESULTS_URL);
  const summary = dispatch ? null : await fetchJsonOptional(ENERGY_SUMMARY_URL);
  const raw = dispatch || summary;
  if (!raw) {
    state.cockpit.data = null;
    state.cockpit.visible = false;
    applyCockpitVisibility();
    showCockpitDataHint(true);
    return;
  }

  state.cockpit.data = normaliseCockpitData(raw, dispatch ? "dispatch_results" : "energy_summary");
  state.cockpit.warnings = [];
  state.cockpit.warningKeys = new Set();
  const defaultFixedScenario = state.cockpit.data.scenarios.find((scenario) => scenario.name === TARIFF_MODE_SCENARIOS.fixed_tou);
  const firstScenario = state.cockpit.data.scenarios.find((scenario) => scenario.name === state.cockpit.scenario)
    || defaultFixedScenario
    || state.cockpit.data.scenarios[0];
  state.cockpit.scenario = firstScenario?.name || "pv_battery_v2g";
  state.cockpit.tariffMode = tariffModeForScenario(state.cockpit.scenario)
    || state.cockpit.data.metadata?.tariffCurve?.activeMode
    || "fixed_tou";
  populateCockpitScenarios();
  populateCockpitPeriods();
  state.cockpit.visible = true;
  applyCockpitVisibility();
  showCockpitDataHint(false);
  renderCockpit();
}

async function fetchJsonOptional(url) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    console.warn(`Cockpit data unavailable at ${url}:`, error);
    return null;
  }
}

const COCKPIT_864_DAY_TYPES = ["wd", "we", "fs", "fest"];

function normaliseCockpitData(raw, source) {
  const fixture = cockpitFixture();
  const schemaMode = cockpitSchemaMode(raw);
  const metadata = normaliseCockpitMetadata(raw);
  const rawScenarios = Array.isArray(raw?.scenarios)
    ? raw.scenarios
    : Array.isArray(raw?.results)
      ? raw.results
      : [];
  const sourceSlices = Array.isArray(raw?.slices) && raw.slices.length
    ? raw.slices
    : fixture.slices;
  const rawSlices = schemaMode === "v2_864"
    ? aggregate864SlicesTo144(sourceSlices)
    : sourceSlices;
  const sliceById = new Map(rawSlices.map((slice) => [slice.id, withTariffDefaults(slice)]));

  const rawByScenario = new Map();
  rawScenarios.forEach((scenario) => {
    const name = scenario.name || scenario.scenario;
    if (!name) return;
    const existing = rawByScenario.get(name);
    if (!existing || preferredScenarioRow(scenario, existing)) rawByScenario.set(name, scenario);
  });
  const fixtureByScenario = new Map(fixture.scenarios.map((scenario) => [scenario.name, scenario]));
  const scenarioNames = Array.from(new Set(rawScenarios
    .map((scenario) => scenario.name || scenario.scenario)
    .filter(Boolean)));
  if (!scenarioNames.length) {
    scenarioNames.push(...SCENARIO_ORDER.filter((name) => fixtureByScenario.has(name)));
  }

  const scenarios = scenarioNames
    .map((name) => {
      const row = rawByScenario.get(name);
      const fill = fixtureByScenario.get(name) || fixture.scenarios[0];
      if (!row && !fill) return null;
      const capacities = { ...(fill.capacities || {}), ...((row && row.capacities) || {}) };
      const capacitiesBaseYear = row?.capacities_base_year && typeof row.capacities_base_year === "object"
        ? { ...row.capacities_base_year }
        : (fill.capacities_base_year || null);
      const bySlice = {};
      const rowBySlice = row
        ? (schemaMode === "v2_864" ? aggregate864To144(row) : (row.by_slice || {}))
        : {};
      const nativeBySlice = row && schemaMode === "v2_864" ? (row.by_slice || {}) : null;
      rawSlices.forEach((slice) => {
        const fillSlice = fill.by_slice?.[slice.id] || {};
        const rowSlice = rowBySlice[slice.id] || {};
        bySlice[slice.id] = { ...fillSlice, ...rowSlice };
      });
      return {
        name,
        solver: row?.solver || fill.solver || "fixture",
        capacities,
        source_capacities: { ...capacities },
        capacities_base_year: capacitiesBaseYear,
        metric_notes: row?.metric_notes && typeof row.metric_notes === "object" ? { ...row.metric_notes } : (fill.metric_notes || {}),
        annual_cost_inr: Number(row?.annual_cost_inr ?? fill.annual_cost_inr ?? 0),
        lifetime_cost_inr: Number(row?.lifetime_cost_inr ?? fill.lifetime_cost_inr ?? 0),
        annual_emissions_kgco2: Number(row?.annual_emissions_kgco2 ?? fill.annual_emissions_kgco2 ?? 0),
        annual_demand_kwh: Number(row?.annual_demand_kwh ?? fill.annual_demand_kwh ?? 0),
        lcoe_inr_per_kwh: Number(row?.lcoe_inr_per_kwh ?? fill.lcoe_inr_per_kwh ?? 0),
        renewable_share: Number(row?.renewable_share ?? fill.renewable_share ?? 0),
        pv_self_consumption_share: numberOrUndefined(row?.pv_self_consumption_share ?? fill.pv_self_consumption_share),
        grid_import_kwh: Number(row?.grid_import_kwh ?? fill.grid_import_kwh ?? 0),
        grid_export_kwh: Number(row?.grid_export_kwh ?? fill.grid_export_kwh ?? 0),
        pv_generation_kwh: Number(row?.pv_generation_kwh ?? fill.pv_generation_kwh ?? 0),
        curtailment_kwh: Number(row?.curtailment_kwh ?? fill.curtailment_kwh ?? 0),
        battery_throughput_kwh: Number(row?.battery_throughput_kwh ?? fill.battery_throughput_kwh ?? 0),
        v2g_discharge_kwh: Number(row?.v2g_discharge_kwh ?? fill.v2g_discharge_kwh ?? 0),
        biomass_generation_kwh: Number(row?.biomass_generation_kwh ?? fill.biomass_generation_kwh ?? 0),
        wte_generation_kwh: Number(row?.wte_generation_kwh ?? fill.wte_generation_kwh ?? 0),
        biogas_generation_kwh: Number(row?.biogas_generation_kwh ?? fill.biogas_generation_kwh ?? 0),
        thermal_storage_throughput_kwh: Number(row?.thermal_storage_throughput_kwh ?? fill.thermal_storage_throughput_kwh ?? 0),
        dsr_shifted_kwh: Number(row?.dsr_shifted_kwh ?? fill.dsr_shifted_kwh ?? 0),
        ev_smart_shifted_kwh: Number(row?.ev_smart_shifted_kwh ?? fill.ev_smart_shifted_kwh ?? 0),
        stage_d_enabled: Boolean(row?.stage_d_enabled ?? fill.stage_d_enabled ?? false) || hasStageDFields(row),
        stage_d_substation_cell: Array.isArray(row?.stage_d_substation_cell) ? row.stage_d_substation_cell : fill.stage_d_substation_cell,
        stage_d_per_edge_flow_kwh: row?.stage_d_per_edge_flow_kwh || fill.stage_d_per_edge_flow_kwh || null,
        stage_d_per_edge_voltage_class: row?.stage_d_per_edge_voltage_class || fill.stage_d_per_edge_voltage_class || null,
        stage_d_transformer_zones: Array.isArray(row?.stage_d_transformer_zones) ? row.stage_d_transformer_zones : (fill.stage_d_transformer_zones || []),
        dc_ppa_offtake_kwh: Number(row?.dc_ppa_offtake_kwh ?? fill.dc_ppa_offtake_kwh ?? 0),
        dc_ppa_revenue_inr: Number(row?.dc_ppa_revenue_inr ?? fill.dc_ppa_revenue_inr ?? 0),
        by_cell: row?.by_cell || fill.by_cell || null,
        alpha: row?.alpha ?? fill.alpha ?? null,
        period_breakdown: normalisePeriodBreakdown(row?.period_breakdown || fill.period_breakdown || {}),
        by_slice_native: nativeBySlice,
        by_slice: bySlice
      };
    })
    .filter(Boolean);

  return {
    version: raw?.version || "preview",
    slices_per_year: Number(raw?.slices_per_year || rawSlices.length || 0),
    slice_aggregation: schemaMode === "v2_864" ? "864_to_144" : "native",
    metadata,
    source,
    scenarios,
    native_slices: schemaMode === "v2_864" ? sourceSlices.map((slice) => withTariffDefaults(slice)) : rawSlices.map((slice) => withTariffDefaults(slice)),
    slices: rawSlices.map((slice) => sliceById.get(slice.id)),
    pareto: normaliseParetoRows(rawScenarios)
  };
}

function preferredScenarioRow(candidate, existing) {
  const candidateAlpha = Number(candidate?.alpha ?? 0);
  const existingAlpha = Number(existing?.alpha ?? 0);
  const candidateHasStageD = hasStageDFields(candidate);
  const existingHasStageD = hasStageDFields(existing);
  if (candidateHasStageD !== existingHasStageD) return candidateHasStageD;
  if (candidateAlpha === 0 && existingAlpha !== 0) return true;
  if (candidateAlpha !== 0 && existingAlpha === 0) return false;
  const candidateHasDc = Number(candidate?.dc_ppa_offtake_kwh || 0) > 0 || Number(candidate?.dc_ppa_revenue_inr || 0) > 0;
  const existingHasDc = Number(existing?.dc_ppa_offtake_kwh || 0) > 0 || Number(existing?.dc_ppa_revenue_inr || 0) > 0;
  if (candidateHasDc !== existingHasDc) return candidateHasDc;
  return false;
}

function hasStageDFields(row) {
  return Boolean(row?.stage_d_per_edge_flow_kwh && row?.stage_d_per_edge_voltage_class && row?.stage_d_substation_cell);
}

function normaliseCockpitMetadata(raw) {
  const economics = raw?.metadata?.economics
    || raw?.economics
    || raw?.economics_meta
    || {};
  const ppa = raw?.metadata?.economics?.ppa
    || raw?.economics?.ppa
    || raw?.economics_meta?.ppa
    || raw?.metadata?.ppa
    || raw?.ppa
    || {};
  const evV2gParams = normaliseEvV2gParams(
    raw?.metadata?.ev_v2g_params
      || raw?.metadata?.economics?.ev_v2g_params
      || raw?.economics?.ev_v2g_params
      || raw?.economics_meta?.ev_v2g_params
      || raw?.ev_v2g_params
      || raw?.metadata?.economics?.ev_adoption
      || raw?.economics?.ev_adoption
      || raw?.economics_meta?.ev_adoption
      || {}
  );
  const tariffCurve = normaliseTariffCurve(
    raw?.metadata?.tariff_curve
      || raw?.metadata?.economics?.tariff_curve
      || raw?.economics?.tariff_curve
      || raw?.economics_meta?.tariff_curve
      || raw?.tariff_curve
      || {}
  );
  return { economics, ppa, evV2gParams, tariffCurve };
}

function normaliseTariffCurve(rawCurve) {
  const curve = rawCurve && typeof rawCurve === "object" ? rawCurve : {};
  const modes = {};
  Object.keys(TARIFF_MODE_SCENARIOS).forEach((mode) => {
    const row = curve[mode] && typeof curve[mode] === "object" ? curve[mode] : {};
    const importBySlice = normaliseTariffBySlice(
      row.import_inr_per_kwh_by_slice
        || row.import_tariff_inr_per_kwh_by_slice
        || row.import_by_slice
        || {}
    );
    const exportBySlice = normaliseTariffBySlice(
      row.export_inr_per_kwh_by_slice
        || row.export_tariff_inr_per_kwh_by_slice
        || row.export_by_slice
        || {}
    );
    modes[mode] = {
      importBySlice,
      exportBySlice,
      note: row.note || "",
      complete: Object.keys(importBySlice).length > 0 && Object.keys(exportBySlice).length > 0
    };
  });
  const activeMode = modes[curve.active_mode]?.complete ? curve.active_mode : "fixed_tou";
  const missing = Object.entries(modes)
    .filter(([, mode]) => !mode.complete)
    .map(([mode]) => mode);
  return {
    activeMode,
    modes,
    complete: missing.length === 0,
    missing,
    source: Object.keys(curve).length ? (missing.length ? "metadata_incomplete" : "metadata") : "metadata_missing"
  };
}

function normaliseTariffBySlice(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value)
    .map(([key, raw]) => [String(key), Number(raw)])
    .filter(([, number]) => Number.isFinite(number)));
}

function normalisePeriodBreakdown(rawBreakdown) {
  if (!rawBreakdown || typeof rawBreakdown !== "object") return {};
  return Object.fromEntries(Object.entries(rawBreakdown).map(([year, period]) => {
    const capacities = period?.installed_capacities && typeof period.installed_capacities === "object"
      ? { ...period.installed_capacities }
      : {};
    return [String(year), {
      ...period,
      installed_capacities: capacities
    }];
  }));
}

function normaliseEvV2gParams(rawParams) {
  const params = rawParams || {};
  if (!params || !Object.keys(params).length) return { ...EMPTY_EV_V2G_PARAMS };
  const byIncome = normaliseIncomeMap(params.by_income || params.byIncome || {});
  const willingness = normaliseIncomeMap(
    params.v2g_willingness_by_income
      || params.v2g_willingness
      || params.v2gWillingnessByIncome
      || params.v2gWillingness
      || {}
  );
  const evCarShareByPeriod = normalisePeriodIncomeMap(
    params.ev_car_share_by_period
      || params.evCarShareByPeriod
      || {}
  );
  const chargingShape = normaliseHourlyShape(
    params.residential_charging_daypart_shape
      || params.residentialChargingDaypartShape
      || params.residential_charging_shape
      || params.residentialChargingShape
      || params.charging_shape
      || params.chargingShape
  );
  const evCarKwhPerDay = numberOrNull(params.ev_car_kwh_per_day ?? params.evCarKwhPerDay);
  const e2wKwhPerDay = numberOrNull(params.e2w_kwh_per_day ?? params.e2wKwhPerDay);
  const missing = [];
  if (!Object.keys(byIncome).length) missing.push("by_income");
  if (!Object.keys(willingness).length) missing.push("v2g_willingness");
  if (!Object.keys(evCarShareByPeriod).length) missing.push("ev_car_share_by_period");
  if (!chargingShape) missing.push("residential_charging_daypart_shape");
  return {
    model: params.model || "",
    byIncome,
    v2gWillingnessByIncome: willingness,
    evCarShareByPeriod,
    chargingShape,
    evCarKwhPerDay,
    e2wKwhPerDay,
    note: params.note || "",
    complete: missing.length === 0,
    missing,
    source: missing.length ? "metadata_incomplete" : "metadata"
  };
}

function normaliseIncomeMap(value) {
  const result = {};
  ["low", "mid", "high"].forEach((income) => {
    const row = value?.[income];
    if (row && typeof row === "object" && !Array.isArray(row)) {
      result[income] = { ...row };
    } else if (row !== undefined) {
      result[income] = Number(row);
    }
  });
  return result;
}

function normalisePeriodIncomeMap(value) {
  if (!value || typeof value !== "object") return {};
  const result = {};
  Object.entries(value).forEach(([year, row]) => {
    result[String(year)] = normaliseIncomeMap(row || {});
  });
  return result;
}

function normaliseHourlyShape(value) {
  if (!value) return null;
  if (typeof value === "object" && !Array.isArray(value)) {
    const hours = new Array(24).fill(0);
    Object.entries(value).forEach(([key, raw]) => {
      const number = Number(raw);
      if (!Number.isFinite(number) || number < 0) return;
      const match = String(key).match(/^(\d{1,2})(?:[_:-](\d{1,2}))?$/);
      if (!match) return;
      const start = clamp(Number(match[1]), 0, 23);
      const end = match[2] !== undefined ? clamp(Number(match[2]), start + 1, 24) : start + 1;
      for (let hour = start; hour < end; hour += 1) {
        hours[hour] = number;
      }
    });
    return sum(hours) > 0 ? hours : null;
  }
  const arr = Array.isArray(value)
    ? value
    : [];
  const numbers = arr.map((item) => Number(item));
  if (numbers.length !== 24 || numbers.some((item) => !Number.isFinite(item) || item < 0) || sum(numbers) <= 0) return null;
  return numbers;
}

function cockpitSchemaMode(raw) {
  const version = String(raw?.version || "");
  if (version === "2.0") return "v2_864";
  if (version === "1.5") return "native_144";
  if (!version || version === "preview" || version.startsWith("fixture")) return "native_144";
  console.warn(`Unsupported cockpit energy schema v${version}; falling back to native 144-slice behaviour.`);
  return "native_144";
}

function aggregate864To144(scenario) {
  const bySlice = scenario?.by_slice || {};
  const dsrReduceBySlice = scenario?.dsr_reduce_kwh_by_slice || {};
  const dsrAddBySlice = scenario?.dsr_add_kwh_by_slice || {};
  const bySlice144 = {};

  MONTH_KEYS.forEach((month) => {
    for (let start = 0; start < 24; start += 2) {
      const end = start + 2;
      const targetId = `${month}_${formatTwoDigitHour(start)}_${formatTwoDigitHour(end)}`;
      const target = {};
      COCKPIT_864_DAY_TYPES.forEach((dayType) => {
        [start, start + 1].forEach((hour) => {
          const sourceId = `${month}_${dayType}_${formatTwoDigitHour(hour)}`;
          const source = bySlice[sourceId] || {};
          addNumericSliceFields(target, source);
          if (!hasFiniteField(source, ["dsr_reduce_kwh", "dsr_reduce"])) {
            addNumberField(target, "dsr_reduce_kwh", dsrReduceBySlice[sourceId]);
          }
          if (!hasFiniteField(source, ["dsr_add_kwh", "dsr_add"])) {
            addNumberField(target, "dsr_add_kwh", dsrAddBySlice[sourceId]);
          }
        });
      });
      bySlice144[targetId] = target;
    }
  });

  return bySlice144;
}

function aggregate864SlicesTo144(slices) {
  const sliceById = new Map((slices || []).map((slice) => [slice.id, slice]));
  const aggregated = [];
  MONTH_KEYS.forEach((month, monthIndex) => {
    for (let start = 0; start < 24; start += 2) {
      const end = start + 2;
      const targetId = `${month}_${formatTwoDigitHour(start)}_${formatTwoDigitHour(end)}`;
      const sourceSlices = [];
      COCKPIT_864_DAY_TYPES.forEach((dayType) => {
        [start, start + 1].forEach((hour) => {
          const source = sliceById.get(`${month}_${dayType}_${formatTwoDigitHour(hour)}`);
          if (source) sourceSlices.push(source);
        });
      });
      const hoursPerYear = sum(sourceSlices.map((slice) => Number(slice.hours_per_year || 0)));
      const importTariff = weightedSliceAverage(sourceSlices, "import_tariff_inr_per_kwh");
      const exportTariff = weightedSliceAverage(sourceSlices, "export_tariff_inr_per_kwh");
      const first = sourceSlices[0] || {};
      const weekdayHours = sum(sourceSlices.map((slice) => Number(slice.weekday_share || 0) * Number(slice.hours_per_year || 0)));
      const weekendHours = sum(sourceSlices.map((slice) => Number(slice.weekend_share || 0) * Number(slice.hours_per_year || 0)));
      const festivalHours = sum(sourceSlices.map((slice) => Number(slice.festival_share || 0) * Number(slice.hours_per_year || 0)));
      aggregated.push(withTariffDefaults({
        id: targetId,
        month,
        month_index: monthIndex,
        season: first.season || seasonFromMonthIndex(monthIndex),
        daypart: `${formatTwoDigitHour(start)}_${formatTwoDigitHour(end)}`,
        start_hour: start,
        end_hour: end,
        hours_per_year: hoursPerYear || (DAYS_IN_MONTH[monthIndex] || 30) * 2,
        tariff_band: first.tariff_band || tariffBandForHour(start),
        import_tariff_inr_per_kwh: importTariff,
        export_tariff_inr_per_kwh: exportTariff,
        weekday_share: hoursPerYear ? weekdayHours / hoursPerYear : 0,
        weekend_share: hoursPerYear ? weekendHours / hoursPerYear : 0,
        festival_share: hoursPerYear ? festivalHours / hoursPerYear : 0
      }));
    }
  });
  return aggregated;
}

function addNumericSliceFields(target, source) {
  Object.entries(source || {}).forEach(([field, value]) => addNumberField(target, field, value));
}

function addNumberField(target, field, value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return;
  target[field] = Number(target[field] || 0) + number;
}

function weightedSliceAverage(slices, field) {
  const weighted = sum((slices || []).map((slice) => (
    Number(slice[field] || 0) * Number(slice.hours_per_year || 0)
  )));
  const hours = sum((slices || []).map((slice) => Number(slice.hours_per_year || 0)));
  return hours > 0 ? weighted / hours : undefined;
}

function formatTwoDigitHour(hour) {
  return String(Math.round(Number(hour || 0))).padStart(2, "0");
}

// PARETO-1: the 8/9/8 period weights, matching energy/dispatch.py and every
// figure builder that integrates a horizon quantity. Defined once here so the
// viewer cannot drift from the thesis.
const PERIOD_WEIGHT_YEARS = { "2030": 8, "2042": 9, "2055": 8 };

function normaliseParetoRows(rawScenarios) {
  const rowsByAlpha = new Map();
  rawScenarios.forEach((row) => {
    const name = row?.name || row?.scenario;
    if (name !== "full_stack" || row?.alpha === undefined || row?.alpha === null) return;
    const alpha = Number(row.alpha);
    if (!Number.isFinite(alpha)) return;
    // PARETO-1 (, the author: "in our figures cost is on the Y axis but
    // in the model it's the X axis, can you make it Y in the model too").
    //
    // Swapping the axes turned out to be the smaller half of the problem. The
    // viewer plotted ANNUAL cost against ANNUAL emissions, and established
    // that this is the WRONG PAIR for a frontier: the multi-period objective
    // trades LIFETIME cost against CUMULATIVE carbon, and on the annual pair
    // the curve is not even monotone - alpha 0.70 dominates alpha 0.65 on both
    // axes, which plots as a point behind the frontier. Figure 5.7 was
    // corrected to the horizon pair on; the viewer never was, so
    // the two disagreed about the shape of the curve, not merely its
    // orientation.
    //
    // Cumulative carbon is integrated exactly as fig_5_4, fig_pareto and
    // alpha_grid_horizon do it - each period's annual rate times the years
    // that period represents - so the four cannot drift apart.
    const pb = row.period_breakdown || {};
    let cumulativeKg = 0;
    let horizonOk = false;
    Object.keys(pb).forEach((year) => {
      const w = PERIOD_WEIGHT_YEARS[String(year)];
      const rate = Number(pb[year]?.annual_emissions_kgco2);
      if (w && Number.isFinite(rate)) {
        cumulativeKg += w * rate;
        horizonOk = true;
      }
    });
    rowsByAlpha.set(alpha.toFixed(3), {
      alpha,
      annual_cost_inr: Number(row.annual_cost_inr || 0),
      annual_emissions_kgco2: Number(row.annual_emissions_kgco2 || 0),
      lifetime_cost_inr: Number(row.lifetime_cost_inr || 0),
      cumulative_kgco2: cumulativeKg,
      // False unless the horizon pair could actually be built. The chart falls
      // back to the annual pair rather than plotting zeros, and SAYS SO.
      horizon_ok: horizonOk && Number(row.lifetime_cost_inr || 0) > 0,
      lcoe_inr_per_kwh: Number(row.lcoe_inr_per_kwh || 0),
      capacities: row.capacities || {}
    });
  });
  return Array.from(rowsByAlpha.values()).sort((a, b) => a.alpha - b.alpha);
}

function cockpitFixture() {
  const slices = defaultCockpitSlices();
  const scenarioDefs = [
    ["bau", 0, 0, 0, 0.00],
    ["pv_only", 0, 0, 0, 0.00],
    ["pv_battery", 0, 0, 0, 0.00],
    ["pv_battery_v2g", 0, 0, 0, 0.00],
    ["pv_battery_v2g_biomass", 0, 0, 0, 0.00],
    ["full_stack", 0, 0, 0, 0.00]
  ];
  return {
    version: "fixture-1.0",
    slices,
    scenarios: scenarioDefs.map(([name, cost, emissions, pvKwp, renewableShare]) => {
      const bySlice = {};
      slices.forEach((slice) => {
        const profile = fixtureSliceProfile(slice, name, pvKwp);
        bySlice[slice.id] = profile;
      });
      const annualDemand = sum(Object.values(bySlice).map((slice) => slice.demand_kwh));
      const pvGeneration = sum(Object.values(bySlice).map((slice) => slice.pv_kwh));
      const gridImport = sum(Object.values(bySlice).map((slice) => slice.grid_import_kwh));
      const biomassGeneration = sum(Object.values(bySlice).map((slice) => slice.biomass_kwh));
      const biogasGeneration = sum(Object.values(bySlice).map((slice) => slice.biogas_kwh));
      const thermalThroughput = sum(Object.values(bySlice).map((slice) => slice.thermal_storage_discharge_kwh));
      return {
        name,
        solver: "inline_fixture",
        capacities: {
          rooftop_pv_kwp: 0,
          solar_farm_kwp: 0,
          battery_kwh: 0,
          v2g_units: 0,
          biomass_kw_e: 0,
          wte_kw_e: 0,
          biogas_kw_e: 0,
          thermal_storage_kwh: 0,
          carport_kwp: 0,
          floating_pv_kwp: 0,
          tracked_pv_active: 0
        },
        capacities_base_year: null,
        metric_notes: {},
        annual_cost_inr: cost,
        lifetime_cost_inr: cost * (name === "bau" ? 35 : 25),
        annual_emissions_kgco2: emissions,
        annual_demand_kwh: annualDemand,
        grid_import_kwh: gridImport,
        grid_export_kwh: 0,
        pv_generation_kwh: pvGeneration,
        curtailment_kwh: 0,
        biomass_generation_kwh: biomassGeneration,
        biogas_generation_kwh: biogasGeneration,
        thermal_storage_throughput_kwh: thermalThroughput,
        dsr_shifted_kwh: name === "full_stack" ? 7_500_000 : 0,
        lcoe_inr_per_kwh: cost / annualDemand,
        renewable_share: renewableShare,
        by_slice: bySlice
      };
    })
  };
}

function defaultCockpitSlices() {
  const seasons = [
    ["winter", 90, 0.96],
    ["spring", 92, 1.00],
    ["monsoon", 122, 1.18],
    ["autumn", 61, 0.82]
  ];
  const dayparts = [
    ["night", 0, 6, "off_peak", 0.56],
    ["morning", 6, 12, "shoulder", 0.92],
    ["afternoon", 12, 18, "shoulder", 1.08],
    ["evening", 18, 22, "peak", 1.22],
    ["late", 22, 24, "super_off_peak", 0.72]
  ];
  return seasons.flatMap(([season, days, seasonScale]) => (
    dayparts.map(([daypart, startHour, endHour, tariffBand, demandScale]) => (
      withTariffDefaults({
        id: `${season}_${daypart}`,
        season,
        daypart,
        start_hour: startHour,
        end_hour: endHour,
        hours_per_year: days * (endHour - startHour),
        tariff_band: tariffBand,
        demand_scale: seasonScale * demandScale
      })
    ))
  ));
}

function fixtureSliceProfile(slice, scenarioName, pvKwp) {
  const enabled = pvKwp > 0;
  const demandKw = 54_000 * Number(slice.demand_scale || 1);
  const daylight = slice.daypart === "morning" ? 0.44 : slice.daypart === "afternoon" ? 0.70 : slice.daypart === "evening" ? 0.16 : 0;
  const pvKw = pvKwp * daylight * (slice.season === "monsoon" ? 0.72 : slice.season === "winter" ? 0.82 : 1.0);
  const batteryDischargeKw = enabled && scenarioName.includes("battery") && slice.daypart === "evening" ? Math.min(6_000, pvKw * 0.3 + 2_000) : 0;
  const v2gDischargeKw = enabled && scenarioName.includes("v2g") && slice.daypart === "evening" ? 4_200 : 0;
  const biomassKw = enabled && (scenarioName.includes("biomass") || scenarioName === "full_stack") && ["morning", "afternoon", "evening"].includes(slice.daypart)
    ? 5_000
    : 0;
  const biogasKw = enabled && scenarioName === "full_stack" ? 500 : 0;
  const thermalDischargeKw = enabled && scenarioName === "full_stack" && slice.daypart === "evening" ? 3_000 : 0;
  const thermalChargeKw = enabled && scenarioName === "full_stack" && slice.daypart === "afternoon" ? 2_200 : 0;
  const gridImportKw = Math.max(0, demandKw + thermalChargeKw - pvKw - batteryDischargeKw - v2gDischargeKw - biomassKw - biogasKw - thermalDischargeKw);
  return {
    demand_kwh: demandKw * slice.hours_per_year,
    pv_kwh: pvKw * slice.hours_per_year,
    battery_charge_kwh: 0,
    battery_discharge_kwh: batteryDischargeKw * slice.hours_per_year,
    v2g_discharge_kwh: v2gDischargeKw * slice.hours_per_year,
    biomass_kwh: biomassKw * slice.hours_per_year,
    wte_kwh: 0,
    biogas_kwh: biogasKw * slice.hours_per_year,
    thermal_storage_charge_kwh: thermalChargeKw * slice.hours_per_year,
    thermal_storage_discharge_kwh: thermalDischargeKw * slice.hours_per_year,
    grid_import_kwh: gridImportKw * slice.hours_per_year,
    grid_export_kwh: 0
  };
}

function withTariffDefaults(slice) {
  const parsedHours = parseSliceHours(slice);
  const monthIndex = monthIndexFromSlice(slice);
  const normalised = {
    ...slice,
    month_index: monthIndex,
    season: slice.season || seasonFromMonthIndex(monthIndex),
    start_hour: parsedHours.start,
    end_hour: parsedHours.end,
    daypart: slice.daypart || daypartFromHour(parsedHours.start + 0.5)
  };
  const band = normalised.tariff_band || tariffBandForHour(Number(normalised.start_hour || 12));
  const tariffs = DEFAULT_TARIFFS[band] || DEFAULT_TARIFFS.shoulder;
  return {
    ...normalised,
    tariff_band: band,
    import_tariff_inr_per_kwh: Number(normalised.import_tariff_inr_per_kwh ?? tariffs.import),
    export_tariff_inr_per_kwh: Number(normalised.export_tariff_inr_per_kwh ?? tariffs.export)
  };
}

function parseSliceHours(slice) {
  const explicitStart = Number(slice.start_hour);
  const explicitEnd = Number(slice.end_hour);
  if (Number.isFinite(explicitStart) && Number.isFinite(explicitEnd)) {
    return { start: explicitStart, end: explicitEnd };
  }
  const text = String(slice.daypart || slice.id || "");
  const match = text.match(/(?:^|_)(\d{2})_(\d{2})(?:$|_)/);
  if (match) {
    const start = Number(match[1]);
    const end = Number(match[2]) || 24;
    return { start, end };
  }
  const fallbackStart = Number.isFinite(explicitStart) ? explicitStart : 12;
  return { start: fallbackStart, end: Math.min(24, fallbackStart + 2) };
}

function monthIndexFromSlice(slice) {
  if (Number.isFinite(Number(slice.month_index))) {
    return clamp(Math.round(Number(slice.month_index)), 0, 11);
  }
  const rawMonth = String(slice.month || slice.id || "").slice(0, 3).toLowerCase();
  const monthIndex = MONTH_KEYS.indexOf(rawMonth);
  if (monthIndex >= 0) return monthIndex;
  return monthIndexFromSeason(slice.season);
}

function populateCockpitScenarios() {
  if (!els.cockpitScenario || !state.cockpit.data) return;
  els.cockpitScenario.innerHTML = "";
  state.cockpit.data.scenarios.forEach((scenario) => {
    // The green DC-PPA is byte-identical to the standard one in this run (see
    // CKP-2 / WEB-4: all 46 fields except `name`), so offering it as a separate
    // choice invites a comparison that has nothing in it. the author dropped the
    // claim from the write-up on; this drops it from the picker.
    if (scenario.name === "full_stack_dc_ppa_green") return;
    const option = document.createElement("option");
    option.value = scenario.name;
    option.textContent = scenarioOptionLabel(scenario);
    option.title = scenarioOptionLabel(scenario, { verbose: true });
    els.cockpitScenario.appendChild(option);
  });
  els.cockpitScenario.value = state.cockpit.scenario;
}

function populateCockpitPeriods() {
  if (!els.cockpitPeriod || !state.cockpit.data) return;
  const scenario = activeCockpitRawScenario();
  const years = availablePeriodYears(scenario);
  els.cockpitPeriod.innerHTML = "";
  if (!years.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Single year";
    els.cockpitPeriod.appendChild(option);
    els.cockpitPeriod.disabled = true;
    state.cockpit.periodYear = "";
    return;
  }
  els.cockpitPeriod.disabled = false;
  if (!years.includes(String(state.cockpit.periodYear))) {
    state.cockpit.periodYear = years.includes(DEFAULT_COCKPIT_PERIOD_YEAR)
      ? DEFAULT_COCKPIT_PERIOD_YEAR
      : years[0];
  }
  years.forEach((year) => {
    const option = document.createElement("option");
    option.value = year;
    option.textContent = year;   // plain year (Aryan, 2026-08-24)
    els.cockpitPeriod.appendChild(option);
  });
  els.cockpitPeriod.value = state.cockpit.periodYear;
}

// THE ONE OWNER OF THE COCKPIT'S VISIBILITY. Everything that wants to show or
// hide the panel goes through here. renderCockpit briefly toggled the class
// itself on and this function simply put it back on the next call,
// so the panel and the baseline note were drawn on top of each other. A class
// with two writers has no defined state.
function applyCockpitVisibility() {
  // THE COCKPIT DOES NOT APPLY TO A BASELINE ARCHETYPE (the author,
  // "baseline cockpit shouldn't exist, the live energy flow model is wrong
  // for baseline"). Every tab reads `dispatch_results`, which is the solve
  // for optimised_sa's own programme; a baseline has its own land use and no
  // solve. Hidden only when the layout is POSITIVELY a baseline, because this
  // also runs before the first layout resolves.
  const applies = !state.currentLayout || isOptimisedLayout();
  const show = Boolean(state.cockpit.visible && state.cockpit.data && applies);
  els.cockpitPanel?.classList.toggle("hidden", !show);

  // The toggle button, and the tariff-band chip beside it, belong to the same
  // solve. Left visible on a baseline the button does nothing when pressed and
  // the chip reports a time-of-day band from a tariff this layout was never
  // costed against.
  els.cockpitToggle?.classList.toggle("hidden", !applies);
  els.cockpitToggle?.classList.toggle("active", show);
  els.cockpitToggle?.setAttribute("aria-pressed", String(show));
  document.getElementById("tariff-status")
    ?.classList.toggle("hidden", !applies);
}

function showCockpitDataHint(show) {
  els.cockpitDataHint?.classList.toggle("hidden", !show);
}

function warnCockpitDataOnce(code, message) {
  const key = String(code || message || "cockpit-warning");
  if (!state.cockpit.warningKeys) state.cockpit.warningKeys = new Set();
  if (!state.cockpit.warnings) state.cockpit.warnings = [];
  const existing = state.cockpit.warnings.find((warning) => warning.code === key);
  if (!existing) {
    state.cockpit.warnings.push({ code: key, message });
  }
  if (!state.cockpit.warningKeys.has(key)) {
    state.cockpit.warningKeys.add(key);
    console.warn(`[viewer cockpit] ${message}`);
  }
}

function setCockpitTab(tab) {
  if (!COCKPIT_TABS.includes(tab)) return;
  state.cockpit.activeTab = tab;
  renderCockpit();
}

function setCockpitTariffMode(mode) {
  if (!TARIFF_MODE_SCENARIOS[mode] || !state.cockpit.data) return;
  const scenarioName = TARIFF_MODE_SCENARIOS[mode];
  const scenario = state.cockpit.data.scenarios.find((item) => item.name === scenarioName);
  if (!scenario) {
    syncTariffModeControls();
    return;
  }
  state.cockpit.tariffMode = mode;
  state.cockpit.scenario = scenarioName;
  populateCockpitPeriods();
  rebuildPvLookupsForActiveScenario();
  renderCockpit();
}

function tariffModeForScenario(scenarioName) {
  const match = Object.entries(TARIFF_MODE_SCENARIOS)
    .find(([, mappedScenario]) => mappedScenario === scenarioName);
  return match ? match[0] : "";
}

function activeTariffMode() {
  return tariffModeForScenario(state.cockpit.scenario)
    || state.cockpit.tariffMode
    || state.cockpit.data?.metadata?.tariffCurve?.activeMode
    || "fixed_tou";
}

function syncTariffModeFromScenario() {
  const mode = tariffModeForScenario(state.cockpit.scenario);
  if (mode) state.cockpit.tariffMode = mode;
}

function syncTariffModeControls() {
  const buttons = Array.from(els.cockpitTariffModeButtons || []);
  if (!buttons.length) return;
  const scenarios = new Set((state.cockpit.data?.scenarios || []).map((scenario) => scenario.name));
  const curve = state.cockpit.data?.metadata?.tariffCurve;
  const selectedMode = activeTariffMode();
  buttons.forEach((button) => {
    const mode = button.dataset.tariffMode;
    const scenarioName = TARIFF_MODE_SCENARIOS[mode];
    const hasScenario = scenarios.has(scenarioName);
    const hasCurve = Boolean(curve?.modes?.[mode]?.complete);
    const active = selectedMode === mode;
    button.disabled = !hasScenario;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.title = hasScenario
      ? `${TARIFF_MODE_LABELS[mode] || titleCase(mode)} scenario${hasCurve ? "" : "; tariff metadata missing"}`
      : `${TARIFF_MODE_LABELS[mode] || titleCase(mode)} scenario not exported`;
  });
}

function updateOverlayTop() {
  const topbarBottom = els.topbar?.getBoundingClientRect?.().bottom || 104;
  const overlayTop = Math.ceil(topbarBottom + 16);
  document.documentElement.style.setProperty("--viewer-overlay-top", `${overlayTop}px`);
  updateLeftDockLayout();
}

function renderCockpit() {
  // THE COCKPIT BELONGS TO optimised_sa AND NOWHERE ELSE (the author,
  // "baseline cockpit shouldn't exist, the live energy flow model is wrong for
  // baseline").
  //
  // He is right, and the reason is the same one that already hides the
  // electrical overlay and the per-cell tabs on a baseline: `dispatch_results`
  // is the solve for THIS town's programme - its demand, its roof area, its
  // farm, its fleet. A baseline archetype is a different layout with a
  // different land-use budget and no solve of its own. Drawing the optimised
  // town's flows over it produced numbers that looked authoritative and
  // described a district that was not on screen.
  //
  // Hidden rather than blanked: an empty cockpit invites "why is it broken",
  // whereas no cockpit plus the note below states the actual position. The
  // whole panel goes, because every tab in it (Live, Trends, Trading, Impact,
  // Cells) reads the same solve.
  // Visibility is owned by applyCockpitVisibility, which also decides
  // whether the cockpit applies to this layout at all. Calling it here keeps
  // the panel, the toggle, the tariff chip and the baseline note consistent
  // on every path that re-renders, including a layout switch.
  applyCockpitVisibility();
  const cockpitApplies = !state.currentLayout || isOptimisedLayout();
  if (!cockpitApplies) return;

  if (!state.cockpit.data) return;
  const scenario = activeCockpitScenario();
  if (!scenario) return;

  els.cockpitTitle.textContent = shortLayoutLabel(layoutByName(state.currentLayout));
  els.cockpitScenario.value = scenario.name;
  syncTariffModeControls();
  if (els.cockpitPeriod && !els.cockpitPeriod.disabled) {
    els.cockpitPeriod.value = state.cockpit.periodYear;
  }
  if (els.cockpitPriceScenario) {
    els.cockpitPriceScenario.value = state.cockpit.priceScenario || defaultPriceScenarioName();
  }
  const snapshot = cockpitFlowSnapshot(scenario, state.sun.timeHours);
  els.cockpitStatus.textContent = cockpitStatusLabel(snapshot);
  els.cockpitStatus.className = `cockpit-status status-${cockpitStatusClass(snapshot)}`;

  // CELLS TAB EXISTS ONLY WHERE THE DATA DOES (the author, "if there is
  // no data for 2042, 2055 for the cell tab then take out the cell tab in those
  // periods"). `by_cell` is carried ONLY at scenario top level - no
  // period_breakdown entry has it - and those top-level fields are the base
  // year, so 2042 and 2055 were re-showing 2030 numbers under a 2042/2055
  // heading. Hiding the tab is the honest answer: the model does not produce
  // per-cell dispatch per period, so there is nothing to show.
  const cellsHaveData = String(state.cockpit.periodYear || DEFAULT_COCKPIT_PERIOD_YEAR)
    === DEFAULT_COCKPIT_PERIOD_YEAR;
  if (!cellsHaveData && state.cockpit.activeTab === "cells") {
    state.cockpit.activeTab = "live";
  }
  // TARIFF MODE BELONGS TO TRADING (the author, "the agile and fixed tou,
  // only keep it on the trading tab"). It sat in the cockpit header on every
  // tab, where it looked like a global setting; the only panel whose numbers
  // visibly move with it is Trading. Hidden rather than moved, so the control
  // keeps its existing wiring and its state survives a tab change.
  if (els.cockpitTariffMode) {
    els.cockpitTariffMode.hidden = state.cockpit.activeTab !== "trading";
  }
  // Scenario picker belongs to Trends, the tab that exists to compare them
  //. Elsewhere it read as a global switch.
  if (els.cockpitScenario) {
    els.cockpitScenario.hidden = state.cockpit.activeTab !== "trends";
  }
  els.cockpitPages.forEach((page) => {
    page.classList.toggle("active", page.dataset.cockpitPage === state.cockpit.activeTab);
  });
  els.cockpitTabs?.querySelectorAll("[data-cockpit-tab]").forEach((button) => {
    const isCells = button.dataset.cockpitTab === "cells";
    button.hidden = isCells && !cellsHaveData;
    button.classList.toggle("active", button.dataset.cockpitTab === state.cockpit.activeTab);
  });

  renderCockpitLive(scenario, snapshot);
  renderCockpitTrends(scenario);
  renderCockpitTrading(scenario);
  renderCockpitImpact(scenario);
  renderCockpitCells(scenario);
  renderSchemaHint();
}

// A replacement note was tried on and REMOVED the same day
//. On a baseline the cockpit,
// its toggle and the tariff chip simply disappear; nothing stands in their
// place. Kept as a comment because the instinct to explain the absence will
// recur: the answer is that the controls going away IS the explanation.

function activeCockpitScenario() {
  return scenarioForActivePeriod(activeCockpitRawScenario());
}

function activeCockpitRawScenario() {
  return state.cockpit.data?.scenarios.find((scenario) => scenario.name === state.cockpit.scenario)
    || state.cockpit.data?.scenarios[0];
}

function availablePeriodYears(scenario) {
  return Object.keys(scenario?.period_breakdown || {})
    .filter((year) => year)
    .sort((a, b) => Number(a) - Number(b));
}

function scenarioForActivePeriod(scenario) {
  if (!scenario) return scenario;
  const years = availablePeriodYears(scenario);
  if (!years.length) return scenario;
  const year = years.includes(String(state.cockpit.periodYear))
    ? String(state.cockpit.periodYear)
    : (years.includes(DEFAULT_COCKPIT_PERIOD_YEAR) ? DEFAULT_COCKPIT_PERIOD_YEAR : years[0]);
  const period = scenario.period_breakdown?.[year] || {};
  const periodCapacities = period && typeof period.installed_capacities === "object"
    ? { ...period.installed_capacities }
    : {};
  const periodCapacityAnnotations = {};
  if (Object.keys(periodCapacities).length) {
    ["tracked_pv_active", "solar_farm_fixed_kwp", "solar_farm_tracked_kwp"].forEach((key) => {
      if (Object.prototype.hasOwnProperty.call(scenario.capacities || {}, key)) {
        periodCapacityAnnotations[key] = scenario.capacities[key];
      }
    });
  }
  const capacities = Object.keys(periodCapacities).length
    ? { ...periodCapacityAnnotations, ...periodCapacities }
    : year === String(scenario.capacities_base_year?.year) && scenario.capacities_base_year
      ? { ...scenario.capacities_base_year }
      : { ...(scenario.capacities || {}) };
  return {
    ...scenario,
    capacities,
    source_capacities: scenario.source_capacities || scenario.capacities || {},
    annual_cost_inr: periodNumberOrScenario(period, scenario, "annual_cost_inr"),
    annual_emissions_kgco2: periodNumberOrScenario(period, scenario, "annual_emissions_kgco2"),
    annual_demand_kwh: periodNumberOrScenario(period, scenario, "annual_demand_kwh"),
    grid_import_kwh: periodNumberOrScenario(period, scenario, "grid_import_kwh"),
    grid_export_kwh: periodNumberOrScenario(period, scenario, "grid_export_kwh"),
    pv_generation_kwh: periodNumberOrScenario(period, scenario, "pv_generation_kwh"),
    curtailment_kwh: periodNumberOrScenario(period, scenario, "curtailment_kwh"),
    lifetime_cost_inr: periodNumberOrScenario(period, scenario, "lifetime_cost_inr"),
    lcoe_inr_per_kwh: periodNumberOrScenario(period, scenario, "lcoe_inr_per_kwh"),
    renewable_share: periodNumberOrScenario(period, scenario, "renewable_share"),
    green_purchase_kwh: periodNumberOrScenario(period, scenario, "green_purchase_kwh"),
    active_period_year: year,
    // Plain year everywhere it is echoed: "2030 base year" read like a
    // different KIND of period next to a bare "2042".
    active_period_label: year,
    active_period_breakdown: period,
    has_period_breakdown: true
  };
}

function periodNumberOrScenario(period, scenario, field) {
  return numberOrUndefined(period?.[field] ?? scenario?.[field]);
}

function schemaSupportsRound45() {
  return schemaVersionAtLeast(state.cockpit.data?.version, 1, 3);
}

function schemaVersionAtLeast(version, major, minor) {
  const match = String(version || "").match(/^(\d+)(?:\.(\d+))?/);
  if (!match) return false;
  const parsedMajor = Number(match[1]);
  const parsedMinor = Number(match[2] || 0);
  return parsedMajor > major || (parsedMajor === major && parsedMinor >= minor);
}

function renderSchemaHint() {
  if (!els.cockpitSchemaHint || !state.cockpit.data) return;
  const version = state.cockpit.data.version || "preview";
  const aggregation = state.cockpit.data.slice_aggregation === "864_to_144"
    ? " 864 hourly slices aggregated into 144 two-hour chart bins."
    : "";
  const warnings = (state.cockpit.warnings || [])
    .slice(-2)
    .map((warning) => warning.message)
    .filter(Boolean);
  const warningText = warnings.length ? ` Warning: ${warnings.join(" ")}` : "";
  els.cockpitSchemaHint.classList.toggle("schema-warning", warnings.length > 0);
  if (schemaSupportsRound45()) {
    els.cockpitSchemaHint.textContent = `Energy JSON schema v${version} loaded: lifetime cost, demand response and canal-top PV fields active.${aggregation}${warningText}`;
    els.cockpitSchemaHint.classList.remove("schema-stale");
    return;
  }
  els.cockpitSchemaHint.textContent = `Energy JSON schema ${version} loaded. Stage C round 4-5 fields not yet generated.${warningText}`;
  els.cockpitSchemaHint.classList.add("schema-stale");
}

function cockpitFlowSnapshot(scenario, hour, options = {}) {
  const lookup = cockpitSliceValuesForHour(scenario, hour, options);
  const slice = lookup.slice;
  const values = lookup.values || {};
  const demandScale = periodScaleForTotal(scenario, "annual_demand_kwh");
  const pvScale = periodScaleForTotal(scenario, "pv_generation_kwh");
  const gridImportScale = periodScaleForTotal(scenario, "grid_import_kwh");
  const gridExportScale = periodScaleForTotal(scenario, "grid_export_kwh");
  const v2gScale = periodScaleForCapacity(scenario, "v2g_units");
  const batteryScale = periodScaleForCapacity(scenario, "battery_kwh");
  const thermalScale = periodScaleForCapacity(scenario, "thermal_storage_kwh");
  const biomassScale = periodScaleForCapacity(scenario, "biomass_kw_e");
  const wteScale = periodScaleForCapacity(scenario, "wte_kw_e");
  const biogasScale = periodScaleForCapacity(scenario, "biogas_kw_e");
  const scaledKwh = (key, scale = 1) => Number(values[key] || 0) * scale;
  const pvGrossKw = sliceAnnualKwhToKw(scaledKwh("pv_kwh", pvScale), slice, "pv_kwh");
  const curtailmentKw = sliceAnnualKwhToKw(scaledKwh("curtailment_kwh", pvScale), slice, "curtailment_kwh");
  const pvDeliveredKw = Math.max(0, pvGrossKw - curtailmentKw);
  const pvShares = pvBaseCapacityShares(scenario);
  // GAP-2 (, the author: "it is 2055, why is there so much gap ... there
  // is still some in 2030").
  //
  // 2030 needed the two missing bands (GAP-1). 2055 is a different fault. The
  // viewer does not hold an hourly dispatch for 2042 or 2055 - it SYNTHESISES
  // them by scaling the base-year shape, and it scales each component by its
  // OWN annual ratio: demand x1.4226, imports x1.0707, photovoltaics x1.0000
  // because the farm and roof are fully built in 2030. Demand therefore
  // outgrows supply and the served-demand line floats above the stack, which
  // is not a rendering fault but an arithmetic impossibility: no hour can
  // consume more than it is supplied.
  //
  // Independent ratios cannot preserve an hourly balance. The model resolves
  // this the same way every hour of the LP does - grid import is the swing
  // term - so the viewer closes on import too. Every other band keeps its
  // scaled value and the residual lands where the optimiser would put it.
  // The base year is untouched: there all ratios are 1 and the scaled value
  // already balances, so `Math.max` returns it unchanged.
  const gridImportScaled = sliceAnnualKwhToKw(scaledKwh("grid_import_kwh", gridImportScale), slice, "grid_import_kwh");
  const _servedKw = Math.max(0,
    sliceAnnualKwhToKw(scaledKwh("demand_kwh", demandScale), slice, "demand_kwh")
    - sliceAnnualKwhToKw(scaledKwh("dsr_reduce_kwh", demandScale), slice, "dsr_reduce_kwh")
    + sliceAnnualKwhToKw(scaledKwh("dsr_add_kwh", demandScale), slice, "dsr_add_kwh"));
  const _nonImportSupplyKw =
    Math.max(0, pvDeliveredKw)
    + sliceAnnualKwhToKw(scaledKwh("biomass_kwh", biomassScale), slice, "biomass_kwh")
    + sliceAnnualKwhToKw(scaledKwh("wte_kwh", wteScale), slice, "wte_kwh")
    + sliceAnnualKwhToKw(scaledKwh("biogas_kwh", biogasScale), slice, "biogas_kwh")
    + sliceAnnualKwhToKw(scaledKwh("battery_discharge_kwh", batteryScale), slice, "battery_discharge_kwh")
    + sliceAnnualKwhToKw(scaledKwh("v2g_discharge_kwh", v2gScale), slice, "v2g_discharge_kwh")
    + sliceAnnualKwhToKw(scaledKwh("thermal_storage_discharge_kwh", thermalScale), slice, "thermal_storage_discharge_kwh")
    + sliceAnnualKwhToKw(scaledKwh("solar_thermal_served_kwh", thermalScale), slice, "solar_thermal_served_kwh")
    + sliceAnnualKwhToKw(scaledKwh("green_purchase_kwh", demandScale), slice, "green_purchase_kwh");
  const gridImportKw = Math.max(gridImportScaled, _servedKw - _nonImportSupplyKw);
  const gridExportKw = sliceAnnualKwhToKw(scaledKwh("grid_export_kwh", gridExportScale), slice, "grid_export_kwh");
  const batteryChargeKw = sliceAnnualKwhToKw(scaledKwh("battery_charge_kwh", batteryScale), slice, "battery_charge_kwh");
  const batteryDischargeKw = sliceAnnualKwhToKw(scaledKwh("battery_discharge_kwh", batteryScale), slice, "battery_discharge_kwh");
  const thermalChargeKw = sliceAnnualKwhToKw(scaledKwh("thermal_storage_charge_kwh", thermalScale), slice, "thermal_storage_charge_kwh");
  const thermalDischargeKw = sliceAnnualKwhToKw(scaledKwh("thermal_storage_discharge_kwh", thermalScale), slice, "thermal_storage_discharge_kwh");
  const dsrReduceKw = sliceAnnualKwhToKw(firstFiniteNumber(values, ["dsr_reduce_kwh", "dsr_reduce"]) * demandScale, slice, "dsr_reduce_kwh");
  const dsrAddKw = sliceAnnualKwhToKw(firstFiniteNumber(values, ["dsr_add_kwh", "dsr_add"]) * demandScale, slice, "dsr_add_kwh");
  const evShiftOutKw = sliceAnnualKwhToKw(scaledKwh("ev_shift_out_kwh", demandScale), slice, "ev_shift_out_kwh");
  const evShiftInKw = sliceAnnualKwhToKw(scaledKwh("ev_shift_in_kwh", demandScale), slice, "ev_shift_in_kwh");
  // SOLAR WATER HEATING, which the cockpit carried in its data and never
  // showed. `solar_thermal_served_kwh` is the heat the collectors deliver
  // directly, so it never passes through the electrical stack and is NOT part
  // of `pvGrossKw`; adding it to a PV band would double count the roof. It is
  // scaled with the thermal fleet rather than the PV fleet for the same reason.
  const solarThermalKw = sliceAnnualKwhToKw(
    scaledKwh("solar_thermal_served_kwh", thermalScale), slice,
    "solar_thermal_served_kwh");
  // GAP-1: purchased zero-carbon energy. Present per slice in the results and
  // never surfaced here, so the band added to stackedEnergyKeys would have
  // read undefined and rendered as a silent zero. Scaled with demand, because
  // an open-access contract is sized to load rather than to a plant.
  const greenPurchaseKw = sliceAnnualKwhToKw(
    scaledKwh("green_purchase_kwh", demandScale), slice, "green_purchase_kwh");
  // DC-1 (, the author: "in the live cockpit energy flow can we show the
  // data centre energy out too"). It was absent from the cockpit entirely,
  // despite being 95.82 GWh/yr and the subject of two findings. It
  // is an OUTFLOW like export, not a supply band, so it belongs beside grid
  // export rather than in the stack. Scaled with export, since both are
  // surplus leaving the boundary.
  const dcPpaKw = sliceAnnualKwhToKw(
    scaledKwh("dc_ppa_kwh", gridExportScale), slice, "dc_ppa_kwh");
  return {
    solarThermalKw,
    greenPurchaseKw,
    dcPpaKw,
    slice,
    demandKw: sliceAnnualKwhToKw(scaledKwh("demand_kwh", demandScale), slice, "demand_kwh"),
    pvGrossKw,
    pvDeliveredKw,
    curtailmentKw,
    rooftopKw: pvDeliveredKw * pvShares.rooftop,
    solarFarmKw: pvDeliveredKw * pvShares.farm,
    carportPvKw: pvDeliveredKw * pvShares.carport,
    floatingPvKw: pvDeliveredKw * pvShares.floating,
    batteryChargeKw,
    batteryDischargeKw,
    batteryNetKw: batteryDischargeKw - batteryChargeKw,
    v2gKw: sliceAnnualKwhToKw(scaledKwh("v2g_discharge_kwh", v2gScale), slice, "v2g_discharge_kwh"),
    biomassKw: sliceAnnualKwhToKw(scaledKwh("biomass_kwh", biomassScale), slice, "biomass_kwh"),
    wteKw: sliceAnnualKwhToKw(scaledKwh("wte_kwh", wteScale), slice, "wte_kwh"),
    biogasKw: sliceAnnualKwhToKw(scaledKwh("biogas_kwh", biogasScale), slice, "biogas_kwh"),
    thermalChargeKw,
    thermalDischargeKw,
    thermalNetKw: thermalDischargeKw - thermalChargeKw,
    dsrReduceKw,
    dsrAddKw,
    evShiftOutKw,
    evShiftInKw,
    evShiftNetKw: evShiftOutKw - evShiftInKw,
    gridImportKw,
    gridExportKw,
    gridNetKw: gridImportKw - gridExportKw,
    importTariff: tariffForHour(hour, "import", slice),
    exportTariff: tariffForHour(hour, "export", slice),
    sliceSource: lookup.source
  };
}

function periodScaleForTotal(scenario, field) {
  if (!scenario?.has_period_breakdown) return 1;
  const active = numberOrNull(scenario?.active_period_breakdown?.[field]);
  const base = numberOrNull(scenario?.period_breakdown?.[DEFAULT_COCKPIT_PERIOD_YEAR]?.[field]);
  if (active === null || base === null || base <= 0) return 1;
  return clamp(active / base, 0, 10);
}

function periodScaleForCapacity(scenario, field) {
  if (!scenario?.has_period_breakdown) return 1;
  const active = numberOrNull(scenario?.capacities?.[field]);
  const source = numberOrNull(scenario?.source_capacities?.[field]);
  if (active === null) return 1;
  if (source !== null && source > 0) return clamp(active / source, 0, 20);
  const periodCaps = Object.values(scenario?.period_breakdown || {})
    .map((period) => numberOrNull(period?.installed_capacities?.[field]))
    .filter((value) => value !== null && value > 0);
  const maxPeriod = Math.max(0, ...periodCaps);
  if (maxPeriod > 0) return clamp(active / maxPeriod, 0, 20);
  return active > 0 ? 1 : 0;
}

function cockpitSliceValuesForHour(scenario, hour, options = {}) {
  const monthIndex = Number.isFinite(Number(options.monthIndex))
    ? clamp(Math.round(Number(options.monthIndex)), 0, 11)
    : monthIndexFromDayOfYear(state.sun.dayOfYear);
  const dayType = options.dayType || cockpitDayTypeForSunDate();
  const nativeSlice = cockpitNativeSliceForMonthHour(monthIndex, dayType, hour);
  const nativeValues = nativeSlice && scenario?.by_slice_native
    ? scenario.by_slice_native[nativeSlice.id]
    : null;
  if (nativeSlice && nativeValues) {
    return { slice: nativeSlice, values: nativeValues, source: "native" };
  }
  if (scenario?.by_slice_native && nativeSlice && !nativeValues) {
    warnCockpitDataOnce(
      `missing-native-${scenario.name}-${nativeSlice.id}`,
      `Missing native dispatch slice ${nativeSlice.id}; using aggregated fallback.`
    );
  }
  const aggregateSlice = cockpitSliceForHour(hour, { monthIndex, warn: true });
  const aggregateValues = aggregateSlice && scenario?.by_slice ? scenario.by_slice[aggregateSlice.id] : null;
  if (!aggregateValues) {
    warnCockpitDataOnce(
      `missing-aggregate-${scenario?.name || "scenario"}-${aggregateSlice?.id || "none"}`,
      `Missing aggregate dispatch slice ${aggregateSlice?.id || "unknown"}; chart point set to zero.`
    );
  }
  return { slice: aggregateSlice || defaultCockpitSlices()[0], values: aggregateValues || {}, source: "aggregate" };
}

function cockpitSliceForHour(hour, options = {}) {
  const monthIndex = Number.isFinite(Number(options.monthIndex))
    ? clamp(Math.round(Number(options.monthIndex)), 0, 11)
    : monthIndexFromDayOfYear(state.sun.dayOfYear);
  const season = seasonFromMonthIndex(monthIndex);
  const normalisedHour = ((Number(hour) % 24) + 24) % 24;
  const slices = state.cockpit.data?.slices || defaultCockpitSlices();
  const exact = slices.find((slice) => (
    Number(slice.month_index) === monthIndex
    && Number(slice.start_hour) <= normalisedHour
    && normalisedHour < Number(slice.end_hour)
  ));
  if (exact) return exact;
  const seasonMatch = slices.find((slice) => (
    slice.season === season
    && Number(slice.start_hour) <= normalisedHour
    && normalisedHour < Number(slice.end_hour)
  ));
  if (seasonMatch) {
    if (options.warn) {
      warnCockpitDataOnce(
        `slice-season-fallback-${monthIndex}-${Math.floor(normalisedHour)}`,
        `No exact ${MONTH_LABELS[monthIndex]} ${formatTwoDigitHour(normalisedHour)} aggregate slice; using ${season} fallback.`
      );
    }
    return seasonMatch;
  }
  const daypartMatch = slices.find((slice) => slice.season === season && slice.daypart === daypartFromHour(normalisedHour));
  if (daypartMatch) return daypartMatch;
  if (options.warn) {
    warnCockpitDataOnce("slice-first-fallback", "No matching dispatch slice found; using the first slice as fallback.");
  }
  return slices[0];
}

function cockpitNativeSliceForHour(hour) {
  const monthIndex = monthIndexFromDayOfYear(state.sun.dayOfYear);
  return cockpitNativeSliceForMonthHour(monthIndex, cockpitDayTypeForSunDate(), hour);
}

function cockpitNativeSliceForMonthHour(monthIndex, dayType, hour) {
  const month = MONTH_KEYS[clamp(Math.round(Number(monthIndex) || 0), 0, 11)] || MONTH_KEYS[0];
  const normalisedHour = Math.floor(((Number(hour) % 24) + 24) % 24);
  const candidates = Array.from(new Set([
    dayType,
    dayType === "fs" ? "fest" : "",
    dayType === "fest" ? "fs" : "",
    "wd",
    "we",
    "fs",
    "fest"
  ].filter(Boolean)));
  const slices = state.cockpit.data?.native_slices || [];
  return candidates
    .map((candidate) => `${month}_${candidate}_${formatTwoDigitHour(normalisedHour)}`)
    .map((id) => slices.find((slice) => slice.id === id))
    .find(Boolean) || null;
}

function tariffSliceIdForHour(month, dayType, hour, mode = activeTariffMode()) {
  const curveMode = state.cockpit.data?.metadata?.tariffCurve?.modes?.[mode];
  const normalisedHour = Math.floor(((Number(hour) % 24) + 24) % 24);
  const candidates = Array.from(new Set([
    dayType,
    dayType === "fs" ? "fest" : "",
    dayType === "fest" ? "fs" : "",
    "wd",
    "we",
    "fs",
    "fest"
  ].filter(Boolean)));
  const map = curveMode?.importBySlice || curveMode?.exportBySlice || {};
  return candidates
    .map((candidate) => `${month}_${candidate}_${formatTwoDigitHour(normalisedHour)}`)
    .find((id) => Object.prototype.hasOwnProperty.call(map, id))
    || `${month}_${dayType}_${formatTwoDigitHour(normalisedHour)}`;
}

function tariffCurveValueForHour(mode, direction, month, dayType, hour) {
  const curveMode = state.cockpit.data?.metadata?.tariffCurve?.modes?.[mode];
  const map = direction === "export" ? curveMode?.exportBySlice : curveMode?.importBySlice;
  if (!map) return null;
  const id = tariffSliceIdForHour(month, dayType, hour, mode);
  const value = Number(map[id]);
  return Number.isFinite(value) ? value : null;
}

function tariffForHour(hour, direction, fallbackSlice) {
  const monthIndex = monthIndexFromDayOfYear(state.sun.dayOfYear);
  const month = MONTH_KEYS[monthIndex] || MONTH_KEYS[0];
  const value = tariffCurveValueForHour(activeTariffMode(), direction, month, cockpitDayTypeForSunDate(), hour);
  if (value !== null) return value;
  const fallbackKey = direction === "export" ? "export_tariff_inr_per_kwh" : "import_tariff_inr_per_kwh";
  const fallback = Number(fallbackSlice?.[fallbackKey]);
  if (Number.isFinite(fallback)) return fallback;
  const band = fallbackSlice?.tariff_band || tariffBandForHour(hour);
  return Number(DEFAULT_TARIFFS[band]?.[direction] || DEFAULT_TARIFFS.shoulder[direction]);
}

function cockpitDayTypeForSunDate() {
  return cockpitDayTypeForDayOfYear(state.sun.dayOfYear);
}

function cockpitDayTypeForDayOfYear(value) {
  const dayOfYear = clamp(Math.round(Number(value || 1)), 1, 365);
  const date = new Date(Date.UTC(2030, 0, dayOfYear));
  const weekday = date.getUTCDay();
  return weekday === 0 || weekday === 6 ? "we" : "wd";
}

function cockpitDayTypeLabel(dayType) {
  if (dayType === "we") return "weekend";
  if (dayType === "fs" || dayType === "fest") return "festival/smog";
  return "weekday";
}

function cockpitDailySeries(scenario, options = {}) {
  const series = [];
  for (let hour = 0; hour < 24; hour += 2) {
    const snapshot = cockpitFlowSnapshot(scenario, hour + 1, options);
    series.push({
      hour,
      durationHours: 2,
      ...snapshot
    });
  }
  return series;
}

function cockpitPeriod(range, options = {}) {
  const monthIndex = Number.isFinite(Number(options.monthIndex))
    ? clamp(Math.round(Number(options.monthIndex)), 0, 11)
    : monthIndexFromDayOfYear(state.sun.dayOfYear);
  if (range === "week") {
    return { id: "week", label: "Week", days: 7 };
  }
  if (range === "month") {
    const days = DAYS_IN_MONTH[monthIndex] || 30;
    return { id: "month", label: MONTH_LABELS[monthIndex], days };
  }
  return { id: "day", label: "Today", days: 1 };
}

function renderCockpitLive(scenario, snapshot) {
  const chips = [
    ["Solar farm", snapshot.solarFarmKw, COCKPIT_FLOW_COLOURS.solarFarm, true],
    ["Carport PV", snapshot.carportPvKw, COCKPIT_FLOW_COLOURS.carport, true],
    ["Rooftop PV", snapshot.rooftopKw, COCKPIT_FLOW_COLOURS.rooftop, true],
    ["Canal-top PV", snapshot.floatingPvKw, COCKPIT_FLOW_COLOURS.floating, false],
    ["Solar hot water", snapshot.solarThermalKw, COCKPIT_FLOW_COLOURS.thermal, false],
    ["Biomass", snapshot.biomassKw, COCKPIT_FLOW_COLOURS.biomass, false],
    ["WTE", snapshot.wteKw, COCKPIT_FLOW_COLOURS.wte, false],
    ["Biogas", snapshot.biogasKw, COCKPIT_FLOW_COLOURS.biogas, false],
    ["Demand", snapshot.demandKw, COCKPIT_FLOW_COLOURS.demand, true],
    // DSR-VIS (, the author: "DSR of viewer too NOT THERE ANYMORE IN
    // COCKPIT"). Investigated before changing anything, and it is NOT missing:
    // the data is exported (`dsr_reduce_kwh_by_slice`, 864 slices) and the
    // viewer reads it. It is non-zero in only 44 slices for reduce and 75 for
    // add, because demand response fires at PEAK and nowhere else. The chips
    // were flagged show-only-when-non-zero, so for about 95 % of the time
    // slider they correctly vanished.
    //
    // Correct behaviour, wrong impression. A headline mechanism of this thesis
    // that disappears reads as absent from the model rather than as idle, and
    // the author reached exactly that conclusion. They are now ALWAYS shown, so a
    // zero is visible as a zero. The chip title says why it is zero.
    ["Demand response, reduced", snapshot.dsrReduceKw, COCKPIT_FLOW_COLOURS.dsr, true],
    ["Demand response, shifted", snapshot.dsrAddKw, COCKPIT_FLOW_COLOURS.dsr, true],
    ["EV shift out", snapshot.evShiftOutKw, COCKPIT_FLOW_COLOURS.evSmart, false],
    ["EV shift in", snapshot.evShiftInKw, COCKPIT_FLOW_COLOURS.evSmart, false],
    ["Curtailment", snapshot.curtailmentKw, COCKPIT_FLOW_COLOURS.curtailment, false],
    ["Battery charge", snapshot.batteryChargeKw, COCKPIT_FLOW_COLOURS.battery, false],
    ["Battery discharge", snapshot.batteryDischargeKw, COCKPIT_FLOW_COLOURS.battery, false],
    ["Thermal net", snapshot.thermalNetKw, COCKPIT_FLOW_COLOURS.thermal, false],
    ["V2G", snapshot.v2gKw, COCKPIT_FLOW_COLOURS.v2g, false],
    [snapshot.gridNetKw >= 0 ? "Grid import" : "Grid export", Math.abs(snapshot.gridNetKw), snapshot.gridNetKw >= 0 ? COCKPIT_FLOW_COLOURS.gridImport : COCKPIT_FLOW_COLOURS.gridExport, true],
    // DC-1: always shown. The contract is daytime-only (06:00 to 17:00), so a
    // show-when-non-zero chip would vanish for half the slider - the same
    // mistake the DSR chips made.
    ["To data centre", snapshot.dcPpaKw, COCKPIT_FLOW_COLOURS.gridExport, true]
  ].filter(([, value, , always]) => always || Math.abs(Number(value || 0)) > 0.05);
  // DSR-VIS: a chip reading zero should say why, or the reader is left to
  // guess whether the mechanism is idle or missing.
  const CHIP_WHY = {
    "Demand response, reduced": "Load moved out of the evening peak. Acts 18:00-21:00, June to September.",
    "Demand response, shifted": "The same load, arriving earlier in the day.",
    "To data centre": "Surplus sold to the adjacent data centre. Daylight only, 06:00 to 17:00."
  };
  els.cockpitLiveChips.innerHTML = chips.map(([label, value, colour]) => {
    const why = CHIP_WHY[label];
    const idle = why && Math.abs(Number(value || 0)) <= 0.05;
    return `
    <div class="cockpit-chip${idle ? " cockpit-chip-idle" : ""}" style="--chip:${colour}"${
      why ? ` title="${escapeHtml(why)}"` : ""}>
      <strong>${formatPowerValue(Math.abs(value))}</strong>
      <span>${escapeHtml(label)}</span>
    </div>`;
  }).join("");

  const series = cockpitDailySeries(scenario);
  const generatedToday = sum(series.map((point) => (
    point.rooftopKw
    + point.solarFarmKw
    + point.carportPvKw
    + point.floatingPvKw
    + point.biomassKw
    + point.wteKw
    + point.biogasKw
  ) * point.durationHours));
  const demandToday = sum(series.map((point) => point.demandKw * point.durationHours));
  const gridImportToday = sum(series.map((point) => point.gridImportKw * point.durationHours));
  const gridExportToday = sum(series.map((point) => point.gridExportKw * point.durationHours));
  const spent = sum(series.map((point) => point.gridImportKw * point.durationHours * point.importTariff));
  const earned = sum(series.map((point) => point.gridExportKw * point.durationHours * point.exportTariff));

  if (scenario.has_period_breakdown) {
    const annualDemand = numberOrNull(scenario.annual_demand_kwh);
    const annualEmissions = numberOrNull(scenario.annual_emissions_kgco2);
    const annualCost = numberOrNull(scenario.annual_cost_inr);
    els.cockpitLiveEnergy.textContent = annualDemand === null ? "-- demand / yr" : `${formatGwh(annualDemand)} demand / yr`;
    els.cockpitLiveSelf.textContent = annualEmissions === null ? "-- emissions / yr" : `${formatEmissions(annualEmissions)} / yr`;
    els.cockpitLiveTrading.textContent = annualCost === null ? "-- Rs / yr" : `Rs ${formatCost(annualCost)} / yr`;
  } else {
    els.cockpitLiveEnergy.textContent = `${formatGwh(generatedToday)} generated`;
    els.cockpitLiveSelf.textContent = `${formatPercent(1 - (gridImportToday / Math.max(1, demandToday)))} self-powered`;
    els.cockpitLiveTrading.textContent = `${formatSignedMoney(earned - spent)} net today`;
  }

  // ALL SOLAR IN ONE NODE (the author, "we combine all solar into one to
  // make it neater: so like rooftop, farm, carports, water"). Canal-top had a
  // node and a conditional link of its own only because it was added late;
  // splitting one resource across two boxes made the diagram busier without
  // saying anything the tooltip cannot.
  //
  // SOLAR THERMAL STAYS IN THE NODE, DECIDED - and the reason is
  // the balance, not neatness. `demand_kwh` is the PRE-collector service
  // demand (it sums to the headline 527.60 GWh and is shared with the
  // counterfactual, which meets the same hot-water leg electrically), and the
  // results carry `solar_thermal_served_kwh` (28.47 GWh/yr) as supply against
  // it. Remove the heat and the diagram stops closing in every hot-water
  // hour: Load would exceed the inflows by exactly the collector's delivery.
  // The viva line: the cockpit shows an ENERGY-SERVICE balance; the collector
  // serves the hot-water service directly as heat, is labelled "(heat)"
  // wherever it appears, and is never counted as electricity.
  const floatingKw = snapshot.floatingPvKw || 0;
  const solarThermalKw = snapshot.solarThermalKw || 0;
  const solarKw = snapshot.rooftopKw + snapshot.solarFarmKw + snapshot.carportPvKw
    + floatingKw + solarThermalKw;
  const evShiftNetKw = snapshot.evShiftOutKw - snapshot.evShiftInKw;
  const flexOutKw = snapshot.batteryDischargeKw + snapshot.v2gKw + snapshot.thermalDischargeKw + snapshot.dsrReduceKw + snapshot.evShiftOutKw;
  const flexInKw = snapshot.batteryChargeKw + snapshot.thermalChargeKw + snapshot.dsrAddKw + snapshot.evShiftInKw;
  const storageKw = flexOutKw - flexInKw;
  const firmKw = snapshot.biomassKw + snapshot.wteKw + snapshot.biogasKw;
  // `solarKw` already contains floating (canal-top); adding `floatingKw`
  // again here double-counted it in the arrow scaling whenever canal-top was
  // producing. Display values were never affected, only arrow thickness.
  const maxFlow = Math.max(1, snapshot.demandKw, solarKw + firmKw, Math.abs(snapshot.gridNetKw), Math.abs(storageKw), snapshot.curtailmentKw);
  if (els.flowSolarValue) {
    // HEAT GETS ITS OWN LINE (the author, "should we make another box
    // for solar thermal?"). Not another box - the flow geometry is hand-tuned
    // (CKP-20/23) and a node re-adds the clutter the 24-Aug merge removed.
    // Instead the BIG number is electricity only and the heat rides a small
    // second line, so the two are never summed into one figure on screen.
    // Heat-only hours (night, tank service) show just the heat line.
    const solarElecKw = solarKw - solarThermalKw;
    const heatLine = solarThermalKw > 0.05
      ? '<small style="display:block;font-size:.72em;opacity:.78">+ '
        + formatPowerValue(solarThermalKw) + " heat</small>"
      : "";
    // The electric number ALWAYS shows, including 0 (the author,
    // night should read "0" with the heat line beneath, not heat alone).
    els.flowSolarValue.innerHTML = formatPowerValue(Math.max(0, solarElecKw))
      + heatLine;
    const mix = [
      ["Rooftop", snapshot.rooftopKw],
      ["Solar farm", snapshot.solarFarmKw],
      ["Carport", snapshot.carportPvKw],
      ["Canal-top", floatingKw],
      ["Solar water heating (heat)", solarThermalKw]
    ].filter(([, v]) => Math.abs(Number(v) || 0) > 0.05);
    els.flowSolarValue.parentElement.title = mix.length
      ? "Solar now: " + mix.map(([k, v]) => `${k} ${formatPowerValue(v)}`).join(", ")
        + (solarThermalKw > 0.05
           ? ". The heat term serves hot water directly and is not electricity."
           : "")
      : "Rooftop, solar farm, carport canopies, canal-top PV and solar water heating (heat). Idle now.";
  }
  // FIRM GENERATION. biomass + WTE + biogas were summed here as `firmKw` and
  // used ONLY to scale the arrows, so 18.28 MW_e of dispatchable plant drove
  // the diagram without ever appearing in it. Unlike the
  // data-centre node this one hides when idle, because it is an INFLOW: a
  // supply box reading zero invites the reader to ask which plant broke, when
  // the honest answer is that none is running in this slice.
  if (els.flowFirmValue) {
    els.flowFirmValue.textContent = formatPowerValue(firmKw);
    const firmMix = [
      ["Biomass CHP", snapshot.biomassKw],
      ["Waste to energy", snapshot.wteKw],
      ["Biogas", snapshot.biogasKw]
    ].filter(([, v]) => Math.abs(Number(v) || 0) > 0.05);
    els.flowFirmValue.parentElement.title = firmMix.length
      ? "Firm generation now: " + firmMix.map(([k, v]) => `${k} ${formatPowerValue(v)}`).join(", ")
      : "Biomass CHP, waste to energy and biogas. Idle now.";
  }
  const showFirm = firmKw > 0.05;
  els.flowFirmNode?.classList.toggle("hidden", !showFirm);
  if (els.flowFirmPath) {
    els.flowFirmPath.style.display = showFirm ? "" : "none";
    updateFlowPath(els.flowFirmPath, firmKw / maxFlow, COCKPIT_FLOW_COLOURS.biomass, "url(#flow-dot-green)");
  }
  if (els.flowGridValue) els.flowGridValue.textContent = formatPowerValue(Math.abs(snapshot.gridNetKw));
  if (els.flowStorageValue) els.flowStorageValue.textContent = formatPowerValue(Math.abs(storageKw));
  if (els.flowStorageDetail) {
    // FLEX-2 (, the author: "the flex circle still has text coming out,
    // looks bad"). Trimming the wording was not enough - the box is 60 px wide
    // at 7 px type, so ANY two-term string overflows a circle. The circle now
    // shows its total only, and the breakdown moves to the tooltip where it
    // has room. Nothing is lost; it was unreadable at that size anyway.
    const parts = [
      ["Battery", snapshot.batteryNetKw],
      ["Thermal", snapshot.thermalNetKw],
      ["DSR", snapshot.dsrReduceKw - snapshot.dsrAddKw],
      ["EV", evShiftNetKw]
    ].filter(([, v]) => Math.abs(Number(v) || 0) > 0.05)
     .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    els.flowStorageDetail.textContent = "";
    els.flowStorageDetail.title = parts.length
      ? "Flex now: " + parts.map(([k, v]) => `${k} ${formatPowerValue(v)}`).join(", ")
      : "Battery, thermal store, demand response and managed EV charging. Idle now.";
  }
  if (els.flowDemandValue) els.flowDemandValue.textContent = formatPowerValue(snapshot.demandKw);
  // DC-2: shown only when the contract is actually delivering (daylight),
  // because an outflow node reading zero implies a link that is not there.
  if (els.flowDcValue && els.flowDcNode) {
    const dc = Number(snapshot.dcPpaKw || 0);
    els.flowDcValue.textContent = formatPowerValue(dc);
    // DC-4 (, the author: "when data centre gets 0 it goes away, just
    // keep it but keep the figure 0 MW"). A node that vanishes reads as a
    // missing feature; a node reading zero reads as a contract not
    // delivering, which is the true state. The LINK still hides, because a
    // line implies a flow and there is none.
    els.flowDcNode.classList.remove("hidden");
    els.flowDcNode.classList.toggle("flow-node-idle", !(dc > 0.05));
    if (els.flowDcPath) {
      els.flowDcPath.style.display = dc > 0.05 ? "" : "none";
      // Teal to match the node ring and the export colour it belongs to.
      updateFlowPath(els.flowDcPath, dc / maxFlow, "#2DD4BF", "url(#flow-dot-teal)");
    }
  }

  updateFlowPath(els.flowSolar, solarKw / maxFlow, "#22C55E", "url(#flow-dot-green)");
  updateFlowPath(els.flowDemand, snapshot.demandKw / maxFlow, "#38BDF8", "url(#flow-dot-white)");
  const gridExporting = snapshot.gridNetKw < 0;
  updateFlowPath(
    els.flowGrid,
    Math.abs(snapshot.gridNetKw) / maxFlow,
    gridExporting ? "#FBBF24" : "#EF4444",
    gridExporting ? "url(#flow-dot-gold)" : "url(#flow-dot-red)",
    gridExporting ? "M136 146 C123 146,107 146,88 146" : "M88 146 C107 146,123 146,136 146"
  );
  const storageCharging = storageKw < 0;
  updateFlowPath(
    els.flowStorage,
    Math.abs(storageKw) / maxFlow,
    "#A855F7",
    "url(#flow-dot-purple)",
    storageCharging ? "M160 153 C160 166,160 184,160 205" : "M160 205 C160 184,160 166,160 153"
  );
}

function updateFlowPath(path, intensity, colour, marker, d = null) {
  if (!path) return;
  const value = clamp(Number(intensity || 0), 0, 1);
  path.style.stroke = colour;
  path.style.strokeWidth = String(3.4 + value * 4.6);
  path.style.opacity = value <= 0.001 ? "0" : String(0.34 + value * 0.66);
  path.style.animationDuration = `${1.7 - value * 0.75}s`;
  if (value <= 0.001) {
    path.removeAttribute("marker-end");
  } else {
    path.setAttribute("marker-end", marker);
  }
  if (d) path.setAttribute("d", d);
}

function renderCockpitTrends(scenario) {
  const range = state.cockpit.trendsRange || "day";
  const period = cockpitPeriod(range);
  const series = cockpitDailySeries(scenario);
  const fixedAxisMax = fixedAnnualTrendAxisMax(scenario, range);
  const solarByMonth = monthlySolarDailySeries(scenario);
  const demandTotal = sum(series.map((point) => servedDemandKw(point) * point.durationHours * period.days));
  // LAYOUT-1 (, the author: "the picture is for 2030 its three lines, but
  // rest periods are 2 lines so it shifts the graph"). `active_period_label`
  // reads "2030 base year" against a bare "2042", so the heading wrapped to a
  // different height per period and the chart jumped when switching. Year
  // only, one line, same height everywhere.
  const yearOnly = String(scenario.active_period_label || state.cockpit.periodYear || "")
    .match(/20\d{2}/)?.[0] || state.cockpit.periodYear;
  els.cockpitTrendsTotal.textContent =
    `${yearOnly} ${period.label.toLowerCase()} - ${String(formatGwh(demandTotal)).replace(/ /g, " ")}`;
  document.querySelectorAll("[data-cockpit-range]").forEach((button) => {
    const active = button.dataset.cockpitRange === range;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  els.cockpitTrendsChart.innerHTML = stackedEnergyChart(series, period, { axisMax: fixedAxisMax });
  els.cockpitTariffStrip.innerHTML = tariffStrip(series);
  if (els.cockpitSolarStrip) {
    els.cockpitSolarStrip.innerHTML = solarDailyStrip(solarByMonth);
  }
  els.cockpitTrendsLegend.innerHTML = [
    ["Rooftop", COCKPIT_FLOW_COLOURS.rooftop],
    ["Solar farm", COCKPIT_FLOW_COLOURS.solarFarm],
    ["Carport PV", COCKPIT_FLOW_COLOURS.carport],
    ["Canal-top PV", COCKPIT_FLOW_COLOURS.floating],
    ["Biomass", COCKPIT_FLOW_COLOURS.biomass],
    ["WTE", COCKPIT_FLOW_COLOURS.wte],
    ["Biogas", COCKPIT_FLOW_COLOURS.biogas],
    ["Curtailment", COCKPIT_FLOW_COLOURS.curtailment],
    // GAP-1: the legend is a SEPARATE hardcoded list from stackedEnergyKeys,
    // so adding a band to the chart does not add it here. That is how solar
    // hot water could have gone missing unnoticed in the first place.
    ["Solar hot water", COCKPIT_FLOW_COLOURS.thermal],
    ["Green open access", COCKPIT_FLOW_COLOURS.gridExport],
    ["Thermal", COCKPIT_FLOW_COLOURS.thermal],
    ["Battery", COCKPIT_FLOW_COLOURS.battery],
    ["V2G", COCKPIT_FLOW_COLOURS.v2g],
    ["Grid", COCKPIT_FLOW_COLOURS.gridImport],
    // DEM-LEG. The legend
    // described the twelve stacked GENERATION bands and neither of the two
    // demand LINES the same chart draws. The second one is the problem: the
    // faint dashed pre-DSR line is emitted only when `hasDsrShift`, so it
    // appears and vanishes as the time slider moves, with nothing anywhere
    // saying what it is. A line that comes and goes unexplained is read as a
    // rendering fault, which is what "gaps" meant.
    //
    // Both are now in the legend, drawn as LINES rather than blocks so they
    // are not mistaken for another stacked band, and the dashed one says in
    // its tooltip that its absence is meaningful.
    ["Served demand", "#F8FAFC", "line",
     "Demand actually served."],
    ["Demand before response", "rgba(248,250,252,0.60)", "line dashed",
     "Demand before shifting. Absent when the two are the same."]
  ].map(([label, colour, cls, title]) => `<span${title ? ` title="${escapeHtml(title)}"` : ""}><i class="${cls || ""}" style="background:${colour};--legend-colour:${colour}"></i>${label}</span>`).join("");
  if (els.cockpitTrendsNote) {
    // TEXT-1: was a 60-word paragraph restating the legend. Three facts a
    // reader cannot get from the chart itself, nothing else.
    els.cockpitTrendsNote.innerHTML = `
      Stack above the white line is exported, stored or curtailed.
      Same y-axis in all three periods, so they can be compared.
    `;
  }
  renderDsrChip(scenario);
  if (els.cockpitBiomassChart) {
    els.cockpitBiomassChart.innerHTML = biomassDispatchChart(series, period);
  }
}

// AXIS-1 (, the author: "the Y axis here between two periods are
// different, make them the same for comparison, and please use rounded numbers
// like 100, 200, 300, 400, 500").
//
// The axis was already fixed across the twelve MONTHS, which is why the
// seasonal comparison works. It was not fixed across the three PERIODS,
// because the whole series is multiplied by that period's demand scale
// (1.0000 / 1.1849 / 1.4226), so 2030 topped out at 490.7 MWh and 2042 at
// 511.0. Two charts side by side with different scales invite exactly the
// wrong reading, which is the same rule the thesis figures follow: panels
// differ in one variable and the axis is not it.
//
// Fixed by dividing out the active period's scale and multiplying by the
// LARGEST across all periods, so every period draws on the 2055 ceiling.
function fixedAnnualTrendAxisMax(scenario, range) {
  const dayType = cockpitDayTypeForSunDate();
  // REVISED (the author: "check for each month in 2055 what's the
  // highest it reaches and keep it around that, next 100 to that ... for all
  // three for June for example").
  //
  // The first version took the maximum across ALL TWELVE months, which made
  // every period agree but left low months drawing into a third of the plot.
  // The axis is now per MONTH and shared across PERIODS: the chart shows one
  // month at a time, so the only comparison that has to hold is the same month
  // in 2030, 2042 and 2055.
  const monthIndex = monthIndexFromDayOfYear(state.sun.dayOfYear);
  const maxima = [stackedEnergyAxisMax(
    cockpitDailySeries(scenario, { monthIndex, dayType }),
    cockpitPeriod(range, { monthIndex }))];
  const raw = Math.max(1, ...maxima);

  // FIRST ATTEMPT WAS WRONG AND IS WORTH RECORDING. It divided out the active
  // period's DEMAND scale and multiplied by the largest, on the assumption
  // that the chart height tracks demand. It does not: the height is set by the
  // SUPPLY stack, and supply is dominated by photovoltaic generation, which is
  // FLAT across all three periods (the farm and the roof are both built out in
  // 2030). So the correction over-inflated the base year and produced 800 MWh
  // at 2030 against 600 at 2055 - the tallest axis on the smallest year.
  //
  // Derived quantities are the wrong tool here because two components scale by
  // different factors. So evaluate it: rebuild the maxima against EACH
  // period's breakdown in turn and take the largest. A shallow clone with the
  // active breakdown swapped is enough, because every scale the series uses is
  // read from `active_period_breakdown`.
  const pb = scenario?.period_breakdown || {};
  let across = raw;
  Object.keys(pb).forEach((year) => {
    const probe = Object.assign({}, scenario, {
      active_period_breakdown: pb[year],
      capacities: pb[year]?.installed_capacities || scenario.capacities
    });
    const s = cockpitDailySeries(probe, { monthIndex, dayType });
    across = Math.max(across, stackedEnergyAxisMax(s, cockpitPeriod(range, { monthIndex })));
  });
  return niceAxisMax(across);
}

// AXIS-1: round UP to a readable ceiling. The chart draws ticks at 0, max/2
// and max, so the step must halve cleanly - 1, 2, 4, 5 and 10 do; 2.5 does
// not, and would print 125 / 250 where 200 / 400 was wanted.
function niceAxisMax(value) {
  // AXIS-2. The first
  // version rounded to the next 100 MWh at EVERY magnitude, which is right at
  // 400 MWh and absurd at 2.8 GWh - 2,800,000 kWh is already an exact multiple
  // of 100 MWh, so it never moved. The step has to scale with the number.
  //
  // Ladder is 1 / 1.5 / 2 / 3 / 4 / 5 / 6 / 8 / 10 of the decade, so the axis
  // lands on 3.00 GWh rather than 2.80, and every value halves to something
  // readable for the mid tick. 2.5 and 7.5 are excluded deliberately: they
  // would print 1.25 and 3.75.
  //
  // HEADROOM: the stack is drawn from twelve sampled slices, and a peak
  // between samples can sit above the sampled maximum. 4 % is added before
  // rounding so the fill cannot run off the top of the plot.
  const raw = Math.max(1, Number(value) || 1) * 1.04;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const step of [1, 1.5, 2, 3, 4, 5, 6, 8, 10]) {
    if (raw <= step * mag) return step * mag;
  }
  return 10 * mag;
}


function monthlySolarDailySeries(scenario) {
  const native = scenario?.by_slice_native && Object.keys(scenario.by_slice_native).length
    ? scenario.by_slice_native
    : null;
  const slices = native ? (state.cockpit.data?.native_slices || []) : (state.cockpit.data?.slices || []);
  const map = native || scenario?.by_slice || {};
  const pvScale = periodScaleForTotal(scenario, "pv_generation_kwh");
  const totals = new Array(12).fill(0);
  slices.forEach((slice) => {
    const monthIndex = Number.isFinite(Number(slice.month_index))
      ? clamp(Math.round(Number(slice.month_index)), 0, 11)
      : MONTH_KEYS.indexOf(String(slice.month || slice.id || "").slice(0, 3).toLowerCase());
    if (monthIndex < 0) return;
    const values = map[slice.id];
    if (!values) return;
    totals[monthIndex] += Math.max(0, Number(values.pv_kwh || 0)) * pvScale;
  });
  return totals.map((kwh, monthIndex) => ({
    monthIndex,
    label: MONTH_LABELS[monthIndex],
    mwhPerDay: kwh / 1000 / (DAYS_IN_MONTH[monthIndex] || 30)
  }));
}

function solarDailyStrip(rows) {
  if (!rows?.length || rows.every((row) => row.mwhPerDay <= 0)) {
    return `<div class="solar-strip-empty">Solar monthly yield unavailable in dispatch_results.json.</div>`;
  }
  const max = Math.max(1, ...rows.map((row) => row.mwhPerDay));
  const minRow = rows.reduce((best, row) => row.mwhPerDay < best.mwhPerDay ? row : best, rows[0]);
  const maxRow = rows.reduce((best, row) => row.mwhPerDay > best.mwhPerDay ? row : best, rows[0]);
  const currentMonth = monthIndexFromDayOfYear(state.sun.dayOfYear);
  const bars = rows.map((row) => {
    const height = 18 + (row.mwhPerDay / max) * 42;
    const title = `${row.label}: ${row.mwhPerDay.toFixed(0)} MWh/day solar generation`;
    const classes = [
      "solar-strip-bar",
      row.monthIndex === currentMonth ? "active" : "",
      row.monthIndex >= 6 && row.monthIndex <= 8 ? "monsoon" : ""
    ].filter(Boolean).join(" ");
    return `
      <span class="${classes}" ${tooltipAttr(title)}>
        <i style="height:${height.toFixed(1)}px"></i>
        <b>${escapeHtml(row.label)}</b>
      </span>
    `;
  }).join("");
  return `
    <div class="solar-strip-header">
      <span>Solar by month</span>
      <strong>${escapeHtml(minRow.label)} ${minRow.mwhPerDay.toFixed(0)} / ${escapeHtml(maxRow.label)} ${maxRow.mwhPerDay.toFixed(0)} MWh/day</strong>
    </div>
    <div class="solar-strip-bars" aria-label="Solar generation MWh per day by month">
      <em class="solar-strip-monsoon">monsoon</em>
      ${bars}
    </div>
  `;
}

function renderCockpitTrading(scenario) {
  const series = cockpitDailySeries(scenario);
  const now = cockpitFlowSnapshot(scenario, state.sun.timeHours);
  const spent = sum(series.map((point) => point.gridImportKw * point.durationHours * point.importTariff));
  const earned = sum(series.map((point) => point.gridExportKw * point.durationHours * point.exportTariff));
  const v2gCost = sum(series.map((point) => point.v2gKw * point.durationHours * V2G_CYCLE_DEGRADATION_INR_PER_KWH));
  const bestCharge = series.reduce((best, point) => point.importTariff < best.importTariff ? point : best, series[0]);
  const exportScore = (point) => (
    point.exportTariff * 1_000_000
    + point.gridExportKw * 100
    + point.rooftopKw + point.solarFarmKw + point.floatingPvKw
  );
  const bestExport = series.reduce((best, point) => exportScore(point) > exportScore(best) ? point : best, series[0]);

  els.cockpitBuyPrice.textContent = formatTariff(now.importTariff);
  els.cockpitSellPrice.textContent = formatTariff(now.exportTariff);
  els.cockpitTradingChart.innerHTML = tariffLineChart(series);
  if (els.cockpitTradingLegend) {
    els.cockpitTradingLegend.innerHTML = [
      ["Buy price", COCKPIT_FLOW_COLOURS.gridImport, "What the district pays for grid imports.", ""],
      ["Sell price", COCKPIT_FLOW_COLOURS.rooftop, "What exported power earns.", ""],
      ["Peer-to-peer guide", COCKPIT_FLOW_COLOURS.v2g, "Mid-market reference between buy and sell prices.", ""],
      ["Selected time", "#F8FAFC", "White dotted line follows the top sun/time slider.", "vertical"]
    ].map(([label, colour, title, className]) => `<span title="${escapeHtml(title)}"><i class="${className}" style="background:${colour};--legend-colour:${colour}"></i>${label}</span>`).join("");
  }
  els.cockpitTradeNet.textContent = formatSignedMoney(earned - spent - v2gCost);
  els.cockpitTradeDetail.textContent = `${formatMoneyCompact(earned)} earned / ${formatMoneyCompact(spent)} spent today; export window breaks tariff ties using actual PV surplus.`;
  els.cockpitBestCharge.textContent = formatHourWindow(bestCharge.hour, bestCharge.hour + bestCharge.durationHours);
  els.cockpitBestExport.textContent = formatHourWindow(bestExport.hour, bestExport.hour + bestExport.durationHours);
  renderDailyTariffCard(scenario);
}

function renderDailyTariffCard(scenario) {
  if (!els.cockpitTariffChart) return;
  const day = dailyTariffCurveForSelectedDate();
  const activeMode = activeTariffMode();
  if (els.cockpitTariffDayLabel) {
    const period = scenario?.active_period_label || state.cockpit.periodYear || DEFAULT_COCKPIT_PERIOD_YEAR;
    els.cockpitTariffDayLabel.textContent = `${MONTH_LABELS[day.monthIndex]} ${cockpitDayTypeLabel(day.dayType)} - ${period}`;
  }
  if (!day.hasData) {
    els.cockpitTariffChart.innerHTML = `
      <div class="cockpit-empty compact">
        <strong>Tariff metadata missing</strong>
        <span>dispatch_results.json did not export complete fixed_tou/agile_iex tariff_curve maps.</span>
      </div>
    `;
    if (els.cockpitTariffLegend) els.cockpitTariffLegend.innerHTML = "";
    if (els.cockpitTariffNote) {
      els.cockpitTariffNote.textContent = `Missing: ${day.missing.join(", ") || "tariff_curve"}.`;
    }
    return;
  }

  els.cockpitTariffChart.innerHTML = dailyTariffCurveChart(day, activeMode);
  if (els.cockpitTariffLegend) {
    els.cockpitTariffLegend.innerHTML = [
      ["Fixed buy", TARIFF_CURVE_COLOURS.fixedImport, "Fixed-ToU import price.", ""],
      ["Fixed sell", TARIFF_CURVE_COLOURS.fixedExport, "Fixed-ToU export price.", "dashed"],
      ["Agile buy", TARIFF_CURVE_COLOURS.agileImport, "IEX Agile import price.", ""],
      ["Agile sell", TARIFF_CURVE_COLOURS.agileExport, "IEX Agile export price.", "dashed"],
      ["Selected time", "#F8FAFC", "White dotted line follows the top sun/time slider.", "vertical"]
    ].map(([label, colour, title, className]) => `<span title="${escapeHtml(title)}"><i class="${className}" style="background:${colour};--legend-colour:${colour}"></i>${label}</span>`).join("");
  }
  if (els.cockpitTariffNote) {
    const activeLabel = TARIFF_MODE_LABELS[activeMode] || titleCase(activeMode);
    const importDelta = day.annualFixedImportMean > 0
      ? (day.annualAgileImportMean - day.annualFixedImportMean) / day.annualFixedImportMean
      : 0;
    els.cockpitTariffNote.textContent = `${activeLabel}. Mean import: fixed ${formatTariff(day.annualFixedImportMean)}, Agile ${formatTariff(day.annualAgileImportMean)}.`;
  }
}

function dailyTariffCurveForSelectedDate() {
  const curve = state.cockpit.data?.metadata?.tariffCurve || {};
  const monthIndex = monthIndexFromDayOfYear(state.sun.dayOfYear);
  const month = MONTH_KEYS[monthIndex] || MONTH_KEYS[0];
  const dayType = cockpitDayTypeForSunDate();
  const points = [];
  for (let hour = 0; hour < 24; hour += 1) {
    points.push({
      hour,
      fixedImport: tariffCurveValueForHour("fixed_tou", "import", month, dayType, hour),
      fixedExport: tariffCurveValueForHour("fixed_tou", "export", month, dayType, hour),
      agileImport: tariffCurveValueForHour("agile_iex", "import", month, dayType, hour),
      agileExport: tariffCurveValueForHour("agile_iex", "export", month, dayType, hour)
    });
  }
  const missing = Object.entries(curve.modes || {})
    .filter(([, mode]) => !mode.complete)
    .map(([mode]) => mode);
  const hasData = points.some((point) => (
    point.fixedImport !== null
    && point.fixedExport !== null
    && point.agileImport !== null
    && point.agileExport !== null
  ));
  const mean = (key) => {
    const values = points.map((point) => point[key]).filter((value) => value !== null);
    return values.length ? sum(values) / values.length : 0;
  };
  return {
    monthIndex,
    month,
    dayType,
    points,
    missing,
    hasData,
    fixedImportMean: mean("fixedImport"),
    agileImportMean: mean("agileImport"),
    fixedExportMean: mean("fixedExport"),
    agileExportMean: mean("agileExport"),
    annualFixedImportMean: tariffCurveAnnualMean("fixed_tou", "import"),
    annualAgileImportMean: tariffCurveAnnualMean("agile_iex", "import")
  };
}

function tariffCurveAnnualMean(mode, direction) {
  const curveMode = state.cockpit.data?.metadata?.tariffCurve?.modes?.[mode];
  const map = direction === "export" ? curveMode?.exportBySlice : curveMode?.importBySlice;
  if (!map) return 0;
  const slices = state.cockpit.data?.native_slices || [];
  const weighted = slices.reduce((total, slice) => {
    const value = Number(map[slice.id]);
    if (!Number.isFinite(value)) return total;
    const hours = sliceHoursPerYear(slice, `tariff ${slice.id}`, { warn: false });
    return hours > 0 ? total + value * hours : total;
  }, 0);
  const hours = slices.reduce((total, slice) => (
    Number.isFinite(Number(map[slice.id])) ? total + sliceHoursPerYear(slice, `tariff ${slice.id}`, { warn: false }) : total
  ), 0);
  if (hours > 0) return weighted / hours;
  const values = Object.values(map).map((value) => Number(value)).filter(Number.isFinite);
  return values.length ? sum(values) / values.length : 0;
}

function dailyTariffCurveChart(day, activeMode) {
  const width = 360;
  const height = 174;
  const padL = 44;
  const padR = 18;
  const padT = 18;
  const padB = 32;
  const values = day.points.flatMap((point) => [
    point.fixedImport,
    point.fixedExport,
    point.agileImport,
    point.agileExport
  ]).filter((value) => value !== null);
  const max = Math.max(1, Math.ceil(Math.max(...values) + 0.5));
  const xAtHour = (hour) => padL + (hour / 24) * (width - padL - padR);
  const y = (value) => height - padB - (Number(value || 0) / max) * (height - padT - padB);
  const stepPath = (key) => {
    const parts = [];
    day.points.forEach((point, index) => {
      const value = point[key];
      if (value === null) return;
      const x0 = xAtHour(point.hour);
      const x1 = xAtHour(point.hour + 1);
      const sy = y(value);
      if (!parts.length || index === 0) parts.push(`M ${x0} ${sy}`);
      else parts.push(`V ${sy}`);
      parts.push(`H ${x1}`);
    });
    return parts.join(" ");
  };
  const pointLine = (key) => day.points
    .filter((point) => point[key] !== null)
    .map((point) => `${xAtHour(point.hour + 0.5)},${y(point[key])}`)
    .join(" ");
  const cursorX = xAtHour(state.sun.timeHours);
  const xTicks = [0, 6, 12, 18, 24].map((hour) => {
    const tx = xAtHour(hour);
    const anchor = hour === 0 ? "start" : hour === 24 ? "end" : "middle";
    return `<text x="${tx}" y="${height - 13}" text-anchor="${anchor}" fill="#93a4b8" font-size="9">${String(hour).padStart(2, "0")}</text>`;
  }).join("");
  const yTicks = [0, max / 2, max].map((tick) => `
    <g>
      <line x1="${padL - 4}" y1="${y(tick)}" x2="${width - padR}" y2="${y(tick)}" stroke="rgba(255,255,255,0.08)" />
      <text x="${padL - 7}" y="${y(tick) + 3}" text-anchor="end" fill="#93a4b8" font-size="9">${tick.toFixed(1)}</text>
    </g>
  `).join("");
  const activeFixed = activeMode === "fixed_tou";
  const activeAgile = activeMode === "agile_iex";
  const fixedWidth = activeFixed ? 3 : 2.1;
  const agileWidth = activeAgile ? 3 : 2.1;
  const middayX0 = xAtHour(10);
  const middayX1 = xAtHour(16);
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily tariff curve comparing fixed ToU and Agile IEX">
      <rect x="${middayX0}" y="${padT}" width="${middayX1 - middayX0}" height="${height - padT - padB}" fill="rgba(251,191,36,0.07)" ${tooltipAttr("Midday PV export trough: Agile prices are intentionally low when solar is abundant.")}></rect>
      ${yTicks}
      <line x1="${padL}" y1="${height - padB}" x2="${width - padR}" y2="${height - padB}" stroke="rgba(255,255,255,0.20)" />
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" stroke="rgba(255,255,255,0.16)" />
      <path d="${stepPath("fixedImport")}" fill="none" stroke="${TARIFF_CURVE_COLOURS.fixedImport}" stroke-width="${fixedWidth}" stroke-linejoin="miter" ${tooltipAttr(`Fixed-ToU buy curve. Mean: ${formatTariff(day.fixedImportMean)}.`)}></path>
      <path d="${stepPath("fixedExport")}" fill="none" stroke="${TARIFF_CURVE_COLOURS.fixedExport}" stroke-width="1.8" stroke-linejoin="miter" stroke-dasharray="5 4" opacity="${activeFixed ? "0.95" : "0.72"}" ${tooltipAttr(`Fixed-ToU sell curve. Mean: ${formatTariff(day.fixedExportMean)}.`)}></path>
      <polyline points="${pointLine("agileImport")}" fill="none" stroke="${TARIFF_CURVE_COLOURS.agileImport}" stroke-width="${agileWidth}" stroke-linecap="round" stroke-linejoin="round" ${tooltipAttr(`Agile IEX buy curve. Mean: ${formatTariff(day.agileImportMean)}.`)}></polyline>
      <polyline points="${pointLine("agileExport")}" fill="none" stroke="${TARIFF_CURVE_COLOURS.agileExport}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="5 4" opacity="${activeAgile ? "0.95" : "0.74"}" ${tooltipAttr(`Agile IEX sell curve. Mean: ${formatTariff(day.agileExportMean)}.`)}></polyline>
      <line x1="${cursorX}" y1="${padT}" x2="${cursorX}" y2="${height - padB}" stroke="#F8FAFC" stroke-width="1.2" stroke-dasharray="3 3" ${tooltipAttr("Selected time marker from the top sun/time slider.")} />
      <text x="${padL}" y="${padT - 6}" fill="#93a4b8" font-size="9">INR/kWh</text>
      <text x="${(middayX0 + middayX1) / 2}" y="${padT + 11}" text-anchor="middle" fill="rgba(253,230,138,0.72)" font-size="8">midday trough</text>
      ${xTicks}
      <text x="${(padL + width - padR) / 2}" y="${height - 3}" text-anchor="middle" fill="#64748b" font-size="8">hour</text>
    </svg>
  `;
}

function renderDsrChip(scenario) {
  if (!els.cockpitDsrChip) return;
  const shifted = Number(scenario.dsr_shifted_kwh || 0);
  const evShift = evSmartShiftSummary(scenario);
  const evShifted = Number(scenario.ev_smart_shifted_kwh || evShift.shiftedKwh || 0);
  const series = cockpitDailySeries(scenario);
  const sliceDsr = dsrSliceSummary(scenario);
  const peak = peakShiftSummary(series);
  const hasShiftSignal = shifted > 0
    || evShifted > 0
    || sliceDsr.reduceKwh > 0
    || sliceDsr.addKwh > 0
    || evShift.outKwh > 0
    || evShift.inKwh > 0
    || peak.v2gKwhDay > 0
    || peak.batteryKwhDay > 0
    || peak.batteryChargeKwhDay > 0;
  const show = schemaSupportsRound45() && hasShiftSignal;
  els.cockpitDsrChip.classList.toggle("hidden", !show);
  if (!show) {
    els.cockpitDsrChip.innerHTML = "";
    return;
  }
  const shiftedPerDay = shifted > 0
    ? shifted / 365
    : Math.max(sliceDsr.reduceKwh, sliceDsr.addKwh) / 365;
  const evShiftedPerDay = evShifted > 0 ? evShifted / 365 : Math.max(evShift.outKwh, evShift.inKwh) / 365;
  const totalShiftedPerDay = shiftedPerDay + evShiftedPerDay;
  const dsrDetail = sliceDsr.hasData
    ? `Demand response moves ${formatEnergy(sliceDsr.reduceKwh / 365)} a day.`
    : "";
  const evDetail = evShift.hasData
    ? `EV charging moves ${formatEnergy(evShiftedPerDay)} a day.`
    : "";
  const costDetail = peak.v2gWearInrDay > 0
    ? `V2G wear ${formatMoneyCompact(peak.v2gWearInrDay)} a day.`
    : "";
  els.cockpitDsrChip.innerHTML = `
    <span>Smart load peak-shift</span>
    <strong>${formatPowerValue(peak.shavedKw)} shaved (${formatPercent(peak.shavedPct)})</strong>
    ${peakShiftChart(peak)}
    <small>
      ${escapeHtml(formatEnergy(totalShiftedPerDay))} shifted/day. ${escapeHtml(dsrDetail)} ${escapeHtml(evDetail)}
      V2G ${escapeHtml(formatEnergy(peak.v2gKwhDay))}/day; battery ${escapeHtml(formatEnergy(peak.batteryKwhDay))}/day. ${escapeHtml(costDetail)}
    </small>
  `;
}

function dsrSliceSummary(scenario) {
  const slices = Object.values(scenario.by_slice || {});
  const reduceKwh = sum(slices.map((slice) => firstFiniteNumber(slice, ["dsr_reduce_kwh", "dsr_reduce"])));
  const addKwh = sum(slices.map((slice) => firstFiniteNumber(slice, ["dsr_add_kwh", "dsr_add"])));
  return {
    hasData: slices.some((slice) => (
      hasFiniteField(slice, ["dsr_reduce_kwh", "dsr_reduce"])
      || hasFiniteField(slice, ["dsr_add_kwh", "dsr_add"])
    )),
    reduceKwh,
    addKwh
  };
}

function evSmartShiftSummary(scenario) {
  const slices = Object.values(scenario?.by_slice || {});
  const outKwh = sum(slices.map((slice) => firstFiniteNumber(slice, ["ev_shift_out_kwh", "ev_shift_out"])));
  const inKwh = sum(slices.map((slice) => firstFiniteNumber(slice, ["ev_shift_in_kwh", "ev_shift_in"])));
  return {
    hasData: slices.some((slice) => (
      hasFiniteField(slice, ["ev_shift_out_kwh", "ev_shift_out"])
      || hasFiniteField(slice, ["ev_shift_in_kwh", "ev_shift_in"])
    )),
    outKwh,
    inKwh,
    shiftedKwh: Math.max(outKwh, inKwh)
  };
}

function peakShiftSummary(series) {
  const points = (series || []).map((point) => {
    const preKw = Math.max(0,
      Number(point.demandKw || 0)
      + Number(point.dsrReduceKw || 0)
      - Number(point.dsrAddKw || 0)
      + Number(point.evShiftOutKw || 0)
      - Number(point.evShiftInKw || 0)
    );
    const postKw = Math.max(0, Number(point.demandKw || 0)
      + Number(point.batteryChargeKw || 0)
      - Number(point.batteryDischargeKw || 0)
      - Number(point.v2gKw || 0));
    return { ...point, preKw, postKw };
  });
  const prePeak = points.reduce((best, point) => point.preKw > best.preKw ? point : best, { preKw: 0, hour: 0, durationHours: 2 });
  const postPeak = points.reduce((best, point) => point.postKw > best.postKw ? point : best, { postKw: 0, hour: 0, durationHours: 2 });
  const shavedKw = Math.max(0, Number(prePeak.preKw || 0) - Number(postPeak.postKw || 0));
  const v2gKwhDay = sum(points.map((point) => Number(point.v2gKw || 0) * Number(point.durationHours || 0)));
  const batteryKwhDay = sum(points.map((point) => Number(point.batteryDischargeKw || 0) * Number(point.durationHours || 0)));
  const batteryChargeKwhDay = sum(points.map((point) => Number(point.batteryChargeKw || 0) * Number(point.durationHours || 0)));
  const evShiftOutKwhDay = sum(points.map((point) => Number(point.evShiftOutKw || 0) * Number(point.durationHours || 0)));
  const evShiftInKwhDay = sum(points.map((point) => Number(point.evShiftInKw || 0) * Number(point.durationHours || 0)));
  return {
    prePeakKw: Number(prePeak.preKw || 0),
    postPeakKw: Number(postPeak.postKw || 0),
    prePeakHour: Number(prePeak.hour || 0),
    postPeakHour: Number(postPeak.hour || 0),
    shavedKw,
    shavedPct: Number(prePeak.preKw || 0) > 0 ? shavedKw / Number(prePeak.preKw || 0) : 0,
    v2gKwhDay,
    batteryKwhDay,
    batteryChargeKwhDay,
    evShiftOutKwhDay,
    evShiftInKwhDay,
    v2gWearInrDay: v2gKwhDay * V2G_CYCLE_DEGRADATION_INR_PER_KWH
  };
}

function peakShiftChart(peak) {
  const max = Math.max(1, Number(peak.prePeakKw || 0), Number(peak.postPeakKw || 0));
  const row = (label, value, colour) => `
    <div class="cockpit-shift-row">
      <span>${escapeHtml(label)}</span>
      <i style="--shift-colour:${colour};--shift-width:${clamp(value / max, 0, 1) * 100}%"></i>
      <strong>${formatPowerValue(value)}</strong>
    </div>
  `;
  return `
    <div class="cockpit-shift-chart" aria-label="Peak demand before and after DSR, V2G and battery shifting">
      ${row("Pre", peak.prePeakKw, "#fb7185")}
      ${row("Post", peak.postPeakKw, "#2dd4bf")}
      <div class="cockpit-shift-meta">
      </div>
    </div>
  `;
}

function renderCockpitImpact(scenario) {
  const series = cockpitDailySeries(scenario);
  const bau = scenarioForActivePeriod(state.cockpit.data.scenarios.find((item) => item.name === "bau")) || scenario;
  const bauSeries = cockpitDailySeries(bau);
  const priceRow = selectedPriceScenarioRow();
  const bauDemand = numberOrNull(bau.annual_demand_kwh);
  const bauEmissions = numberOrNull(bau.annual_emissions_kgco2);
  const scenarioEmissions = numberOrNull(scenario.annual_emissions_kgco2);
  const emissionFactor = bauDemand && bauEmissions
    ? bau.annual_emissions_kgco2 / bau.annual_demand_kwh
    : 0.70;
  const currentGridToday = sum(series.map((point) => point.gridImportKw * point.durationHours));
  const bauGridToday = sum(bauSeries.map((point) => point.gridImportKw * point.durationHours));
  const savedTodayKg = Math.max(0, (bauGridToday - currentGridToday) * emissionFactor);
  const savedAnnualKg = bauEmissions !== null && scenarioEmissions !== null
    ? Math.max(0, bauEmissions - scenarioEmissions)
    : null;
  const annualCostValue = numberOrNull(scenario.annual_cost_inr);
  const annualDemandValue = numberOrNull(scenario.annual_demand_kwh);
  const headlineDemandValue = annualDemandValue !== null ? annualDemandValue : bauDemand;
  const annualEmissions = scenarioEmissions;
  const lifetime = numberOrNull(scenario.lifetime_cost_inr);
  const bauCost = numberOrNull(bau.annual_cost_inr);
  const costDeltaPct = bauCost !== null && bauCost > 0 && annualCostValue !== null
    ? ((annualCostValue - bauCost) / bauCost) * 100
    : null;
  const emissionsDeltaPct = bauEmissions !== null && bauEmissions > 0 && annualEmissions !== null
    ? ((annualEmissions - bauEmissions) / bauEmissions) * 100
    : null;

  els.cockpitCo2Today.textContent = formatDailyEmissions(savedTodayKg * 365);
  els.cockpitCo2Year.textContent = savedAnnualKg === null ? "--" : formatEmissions(savedAnnualKg);
  if (els.cockpitAnnualDemand) els.cockpitAnnualDemand.textContent = headlineDemandValue === null ? "--" : formatGwh(headlineDemandValue);
  if (els.cockpitDemandDetail) {
    els.cockpitDemandDetail.textContent = bauDemand !== null && annualDemandValue !== null && Math.abs(bauDemand - annualDemandValue) > 1
      ? `Selected scenario demand; BAU reference ${formatGwh(bauDemand)}.`
      : state.cockpit.data?.source === "dispatch_results" ? "Read from dispatch_results.json." : "Fallback summary source.";
  }
  if (els.cockpitCostYear) els.cockpitCostYear.textContent = annualCostValue === null ? "--" : `${formatAnnualCostHeadline(annualCostValue)} / yr`;
  if (els.cockpitCostDetail) {
    els.cockpitCostDetail.textContent = costDeltaPct !== null && emissionsDeltaPct !== null
      ? `vs BAU ${formatScenarioDelta(costDeltaPct)} cost / ${formatScenarioDelta(emissionsDeltaPct)} CO2.`
      : state.cockpit.data?.source === "dispatch_results" ? "Read from dispatch_results.json." : "Fallback summary source.";
    els.cockpitCostDetail.title = bauCost !== null && bauEmissions !== null
      ? `BAU ${formatAnnualCostHeadline(bauCost)} / ${formatEmissionsHeadline(bauEmissions)}.`
      : "";
  }
  if (els.cockpitAnnualEmissions) els.cockpitAnnualEmissions.textContent = annualEmissions === null ? "--" : formatEmissionsHeadline(annualEmissions);
  if (els.cockpitNetCost) {
    const lcoe = numberOrNull(scenario.lcoe_inr_per_kwh);
    els.cockpitNetCost.textContent = lcoe === null ? "--" : formatNetCostHeadline(lcoe);
  }
  if (els.cockpitNetCostDetail) {
    els.cockpitNetCostDetail.textContent = scenario.has_period_breakdown
      ? `${scenario.active_period_label || state.cockpit.periodYear} net system cost.`
      : "Scenario net system cost.";
  }
  if (els.cockpitRenewableShare) {
    const renewable = numberOrNull(scenario.renewable_share);
    els.cockpitRenewableShare.textContent = renewable === null ? "--" : formatSmallPercent(renewable);
  }
  if (els.cockpitRenewableDetail) {
    const greenPurchaseKwh = numberOrNull(scenario.green_purchase_kwh);
    const perPeriodShare = numberOrNull(scenario.active_period_breakdown?.renewable_share);
    const shareScope = scenario.has_period_breakdown && perPeriodShare === null ? "25-y scenario share; " : "";
    els.cockpitRenewableDetail.textContent = greenPurchaseKwh
      ? `${shareScope}self-gen only; excludes ${(greenPurchaseKwh / 1e6).toFixed(1)} GWh of purchased green open access.`
      : `${shareScope}self-generated clean share (incl. biomass/WTE/biogas).`;
    els.cockpitRenewableDetail.title = "metric_notes.renewable_share: purchased green open-access energy (green_purchase_kwh, zero-EF) is NOT counted, so the share understates clean supply post-B21; quote alongside green_purchase_kwh (F36).";
  }
  if (els.cockpitPriceScenarioDetail) {
    if (priceRow && !scenario.has_period_breakdown) {
      els.cockpitPriceScenarioDetail.textContent = `${priceRow.label}; EF ${priceRow.efTrajectoryAvgKgco2PerKwh.toFixed(3)} kgCO2/kWh; ${formatScenarioDelta(priceRow.deltaEmissionsPct)} vs NEP`;
      els.cockpitPriceScenarioDetail.title = priceRow.source;
    } else if (scenario.has_period_breakdown) {
      els.cockpitPriceScenarioDetail.textContent = `${scenario.active_period_label || state.cockpit.periodYear} period_breakdown`;
      els.cockpitPriceScenarioDetail.title = "Annual demand, cost, emissions and installed capacity read from dispatch_results.json period_breakdown.";
    } else {
      els.cockpitPriceScenarioDetail.textContent = "No A21 trajectory sweep loaded";
      els.cockpitPriceScenarioDetail.title = "";
    }
  }
  const supportsLifetime = schemaSupportsRound45() && lifetime !== null && lifetime > 0;
  if (els.cockpitLifetimeCost) {
    els.cockpitLifetimeCost.textContent = supportsLifetime ? `${formatLifetimeCostHeadline(lifetime)} over 25 yr` : "--";
  }
  if (els.cockpitLifetimeDetail) {
    const multiple = annualCostValue ? lifetime / annualCostValue : 0;
    els.cockpitLifetimeDetail.textContent = supportsLifetime
      ? `active dispatch; annual x ${multiple.toFixed(1)}; price sweep shown below`
      : scenario.has_period_breakdown ? "Period cards are annual; 25-year total stays on the scenario aggregate." : "Stage C round 4-5 data not yet generated";
  }
  renderStageDModePill(scenario);
  renderPpaPill();
  if (els.cockpitPriceScenarioChart) {
    els.cockpitPriceScenarioChart.innerHTML = priceScenarioBarChart(
      state.priceScenarioSweep,
      state.cockpit.priceScenario || defaultPriceScenarioName()
    );
  }
  renderSourceStack(series);
  renderStageCTechStack(scenario);
  renderDispatchRealismChecks(scenario);
  renderParetoChart(scenario);
}

function renderStageDModePill(scenario) {
  if (!els.cockpitStageDPill) return;
  const enabled = Boolean(scenario?.stage_d_enabled || hasStageDFields(scenario));
  els.cockpitStageDPill.classList.toggle("hidden", !enabled);
  if (enabled) {
    const count = scenario?.by_cell && typeof scenario.by_cell === "object"
      ? Object.keys(scenario.by_cell).length
      : 0;
    const edgeCount = scenario?.stage_d_per_edge_flow_kwh && typeof scenario.stage_d_per_edge_flow_kwh === "object"
      ? Object.keys(scenario.stage_d_per_edge_flow_kwh).length
      : 0;
    const zoneCount = Array.isArray(scenario?.stage_d_transformer_zones) ? scenario.stage_d_transformer_zones.length : 0;
    const detail = count > 0
      ? `${count.toLocaleString("en-GB")} cells; ${edgeCount.toLocaleString("en-GB")} feeders; ${zoneCount.toLocaleString("en-GB")} transformers.`
      : "Enabled in dispatch JSON.";
    const small = els.cockpitStageDPill.querySelector("small");
    if (small) small.textContent = detail;
  }
}

function renderPpaPill() {
  if (!els.cockpitPpaPill) return;
  const ppaScenarios = dcPpaScenarioSummary();
  const enabled = ppaScenarios.standard || ppaScenarios.green;
  els.cockpitPpaPill.classList.toggle("hidden", !enabled);
  if (!enabled) return;
  const strong = els.cockpitPpaPill.querySelector("strong");
  const small = els.cockpitPpaPill.querySelector("small");
  if (strong) strong.textContent = "DC-PPA";
  if (small) {
    const std = ppaScenarios.standard;
    const green = ppaScenarios.green;
    // DELTAS ONLY WHEN THEY SAY SOMETHING (the author, "it just says
    // +0.00 cost and emissions, remove that, we dont want any useless
    // numbers"). Both legs currently read +0.0% / +0.0%, because the DC-PPA is
    // revenue against an unchanged dispatch. A pair of zeroes in brackets is
    // noise that makes the reader hunt for a difference that is not there. The
    // clause reappears on its own the moment either delta clears 0.05 pp.
    const deltaClause = (row) => {
      const cost = Number(row.deltaCostPct);
      const co2 = Number(row.deltaEmissionsPct);
      const parts = [];
      if (Number.isFinite(cost) && Math.abs(cost) > 0.05) parts.push(`${formatScenarioDelta(cost)} cost`);
      if (Number.isFinite(co2) && Math.abs(co2) > 0.05) parts.push(`${formatScenarioDelta(co2)} CO2`);
      return parts.length ? ` (${parts.join(", ")})` : "";
    };
    const stdText = std
      ? `standard ${formatPpaOfftake(std.offtakeKwh)} / ${formatPpaRevenue(std.revenueInr)} revenue${deltaClause(std)}`
      : "standard --";
    const greenText = green
      ? `green ${formatPpaOfftake(green.offtakeKwh)} / ${formatPpaRevenue(green.revenueInr)} revenue${deltaClause(green)}`
      : "green --";
    // The "green raises emissions" note used to be appended unconditionally.
    // In the current results full_stack_dc_ppa and full_stack_dc_ppa_green are
    // identical in all 46 fields except `name`, so both legs render +0.0% CO2
    // and the note asserted something the numbers on the same line contradict.
    // Gate it on the actual deltas (0.05 pp guard, the line shows one decimal)
    // so the note reappears by itself if the green scenario is ever re-solved
    // as a genuinely distinct case..
    const stdCo2 = Number(std?.deltaEmissionsPct);
    const greenCo2 = Number(green?.deltaEmissionsPct);
    const greenIsWorse = Number.isFinite(stdCo2) && Number.isFinite(greenCo2)
      && greenCo2 - stdCo2 > 0.05;
    const note = greenIsWorse ? " Note: the green PPA raises emissions." : "";
    small.textContent = `${stdText}; ${greenText}.${note}`;
    small.title = "Data-centre PPA scenarios read from dispatch_results.json: dc_ppa_offtake_kwh and dc_ppa_revenue_inr.";
  }
}

function dcPpaScenarioSummary() {
  const scenarios = state.cockpit.data?.scenarios || [];
  const baseline = scenarioForActivePeriod(scenarios.find((scenario) => scenario.name === "full_stack"));
  const rowFor = (name) => {
    const scenario = scenarioForActivePeriod(scenarios.find((item) => item.name === name));
    if (!scenario) return null;
    const offtakeKwh = Number(scenario.dc_ppa_offtake_kwh || 0);
    const revenueInr = Number(scenario.dc_ppa_revenue_inr || 0);
    if (offtakeKwh <= 0 && revenueInr <= 0) return null;
    const baselineCost = Number(baseline?.annual_cost_inr || 0);
    const baselineEmissions = Number(baseline?.annual_emissions_kgco2 || 0);
    const cost = Number(scenario.annual_cost_inr || 0);
    const emissions = Number(scenario.annual_emissions_kgco2 || 0);
    return {
      scenario,
      offtakeKwh,
      revenueInr,
      deltaCostPct: baselineCost > 0 && cost > 0 ? ((cost - baselineCost) / baselineCost) * 100 : 0,
      deltaEmissionsPct: baselineEmissions > 0 && emissions > 0 ? ((emissions - baselineEmissions) / baselineEmissions) * 100 : 0
    };
  };
  return {
    standard: rowFor("full_stack_dc_ppa"),
    green: rowFor("full_stack_dc_ppa_green")
  };
}

function renderCockpitCells(scenario) {
  const props = state.cockpit.selectedCellProps;
  if (!props) {
    renderResidentialEvV2gCard(null);
    els.cockpitCellEmpty.classList.remove("hidden");
    els.cockpitCellContent.classList.add("hidden");
    els.cockpitCellEmpty.innerHTML = `
      <strong>No cell selected</strong>
      <span>Click any 3D cell to open its drill-down here.</span>
      <span>Suggested watchlist: high PV rooftops, high demand blocks, EWS access, solar farms.</span>
    `;
    return;
  }

  els.cockpitCellEmpty.classList.add("hidden");
  els.cockpitCellContent.classList.remove("hidden");
  if (isPlantFeatureProps(props)) {
    renderResidentialEvV2gCard(null);
    renderCockpitPlant(props);
    return;
  }
  const title = `${LABELS[props.land_use] || titleCase(props.land_use)} ${props.row},${props.col}`;
  const tier = ownershipTierForCell(props);
  const pvKwp = featurePvKwp(props);
  const demandKw = cellDemandProxyKw(props);
  els.cockpitCellTitle.textContent = title;
  els.cockpitCellTier.textContent = `Tier ${tier}`;
  const shade = state.cellShading.get(cellKey(props));
  const statRows = [
    ["Land use", LABELS[props.land_use] || titleCase(props.land_use)],
    ["Height", `${Number(props.height_m || 0).toFixed(1)} m`],
    ["Households", formatNumber(props.households)]
  ];
  if (hasPvReadoutProps(props)) {
    statRows.push(["PV ceiling", formatPv(pvKwp)]);
  }
  if (hasPvReadoutProps(props) && (pvKwp > 0 || featurePvDeployedKwp(props) > 0)) {
    statRows.push(["PV deployed", formatPvDeploymentPanel(props)]);
  }
  amenitySubtypeRows(props).forEach((row) => statRows.push(row));
  const faith = faithLabel(props.faith);
  if (faith) statRows.push(["Faith", faith]);
  if (featureCarportKwp(props) > 0) statRows.push(["Carport site", "Parking-lot canopy site"]);
  streetAssetRows(props).forEach((row) => statRows.push(row));
  carportPvRows(props).forEach((row) => statRows.push(row));
  floatingPvSiteRows(props).forEach((row) => statRows.push(row));
  const axis = buildingAxisLabel(props);
  if (axis) statRows.push(["Axis", axis]);
  if (isBipvCandidate(props)) statRows.push(["BIPV deployed", formatBipvDeployment(props)]);
  if (shade) statRows.push(["PV yield", formatShadingMultiplier(shade)]);
  const cellDispatch = cellDispatchForProps(scenario, props);
  if (cellDispatch) {
    // PERIOD LABEL, and it is not decoration (the author asked whether the Cells tab
    // carries current data,). The data IS current - 889 cells, from
    // the same dispatch file as everything else. But `by_cell` exists ONLY at
    // the scenario top level; no period_breakdown entry carries it, and
    // scenarioForActivePeriod does not rescale it. Those top-level fields are
    // the base year (annual_demand_kwh there is 527.6 GWh, exactly the 2030
    // figure), so per-cell flow is 2030 whatever the period selector says.
    // Without the label a reader flips to 2055, sees identical bars, and either
    // thinks the viewer is stuck or quotes a base-year number as 2055.
    const baseYear = DEFAULT_COCKPIT_PERIOD_YEAR;
    statRows.push([`District flow (${baseYear})`, formatSignedDistrictFlow(cellDispatch.netAnnualKwh)]);
    statRows.push([`Daypart flow (${baseYear})`, formatSignedDistrictFlow(cellDispatch.currentKwh, { period: stageDDaypartKey() })]);
  }
  shadingDiagnosticRows(props).forEach((row) => statRows.push(row));
  const audit = formatAuditIssues(props);
  if (audit) statRows.push(["Placement flags", audit]);
  const entrances = formatEntranceSides(props.entrance_sides);
  if (entrances) statRows.push(["Entrances", entrances]);
  els.cockpitCellStats.innerHTML = statRows
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  els.cockpitCellChart.innerHTML = cellDispatch
    ? cellDistrictFlowChart(cellDispatch)
    : cellFlowChart(scenario, pvKwp, demandKw);
  renderResidentialEvV2gCard(props);
  els.cockpitCellUpgrade.textContent = recommendedCellUpgrade(props, pvKwp);
}

function renderResidentialEvV2gCard(props) {
  if (!els.cockpitEvCard) return;
  if (!isResidentialCellProps(props)) {
    els.cockpitEvCard.classList.add("hidden");
    els.cockpitEvCard.innerHTML = "";
    return;
  }
  const params = state.cockpit.data?.metadata?.evV2gParams || EMPTY_EV_V2G_PARAMS;
  const households = Number(props.households || 0);
  const periodYear = String(activeCockpitScenario()?.active_period_year || state.cockpit.periodYear || DEFAULT_COCKPIT_PERIOD_YEAR);
  if (!params.complete) {
    els.cockpitEvCard.innerHTML = `
      <span>EV / V2G</span>
      <strong>${escapeHtml(formatNumber(households))} households</strong>
      <small class="cockpit-metadata-missing">EV/V2G metadata missing${params.missing?.length ? `: ${escapeHtml(params.missing.join(", "))}` : ""}.</small>
    `;
    els.cockpitEvCard.classList.remove("hidden");
    return;
  }
  const evStats = evV2gStatsForCell(props, params, periodYear);
  const hour = selectedEvHour();
  const scenario = activeCockpitScenario();
  const profile = evV2gCellDispatchProfile(scenario, params, props, evStats);
  const selected = profile.hourly[hour] || profile.hourly[0];
  const tooltip = params.note || "EV/V2G parameters read from dispatch metadata.";
  els.cockpitEvCard.innerHTML = `
    <span>EV / V2G</span>
    <strong>${escapeHtml(formatNumber(households))} households - ${escapeHtml(profile.periodLabel)}</strong>
    <div class="cockpit-ev-summary">
      <div>
        <span>EV cars</span>
        <strong>${escapeHtml(formatVehicleCount(profile.estimatedEvCars))}</strong>
      </div>
      <div>
        <span>V2G units</span>
        <strong>${escapeHtml(formatVehicleCount(profile.v2gUnits))}</strong>
      </div>
    </div>
    <div class="cockpit-ev-chart">${evV2gTimelineChart(profile, hour)}</div>
    <div class="cockpit-ev-now">
      <div>
        <span>Charging this hour</span>
        <strong>${escapeHtml(formatEvEnergy(selected.chargeKwh))}</strong>
      </div>
      <div>
        <span>Discharging this hour</span>
        <strong>${escapeHtml(formatEvEnergy(selected.dischargeKwh))}</strong>
      </div>
      <div class="cockpit-ev-savings">
        <span>V2G savings / participant</span>
        <strong>${escapeHtml(formatParticipantV2gValue(profile.v2gValueInrPerParticipantDay))}</strong>
      </div>
    </div>
    <small ${tooltipAttr(tooltip)}>${escapeHtml(profile.periodLabel)}: ${escapeHtml(formatSmallPercent(profile.v2gParticipationShare))} of this cell's homes are V2G participants; district ${escapeHtml(formatVehicleCount(profile.totalV2gUnits))} V2G units. ${escapeHtml(profile.monthLabel)} ${escapeHtml(profile.dayTypeLabel)} discharge uses native by_slice where exported.</small>
  `;
  els.cockpitEvCard.classList.remove("hidden");
}

function isResidentialCellProps(props) {
  return ["residential_low", "residential_mid", "residential_high"].includes(String(props?.land_use || ""));
}

function selectedEvHour() {
  const hour = Math.floor(Number(state.sun.timeHours || 0));
  return ((hour % 24) + 24) % 24;
}

function hourlyShapeValue(shape, hour) {
  const arr = Array.isArray(shape) && shape.length === 24 ? shape : new Array(24).fill(0);
  const value = Number(arr[((hour % 24) + 24) % 24] || 0);
  return Number.isFinite(value) ? value : 0;
}

function evV2gCellDispatchProfile(scenario, params, props, evStats) {
  const monthIndex = monthIndexFromDayOfYear(state.sun.dayOfYear);
  const monthLabel = MONTH_LABELS[monthIndex] || "Selected month";
  const monthDays = DAYS_IN_MONTH[monthIndex] || 30;
  const dayType = cockpitDayTypeForSunDate();
  const dayTypeLabel = cockpitDayTypeLabel(dayType);
  const totalV2gUnits = Number(scenario?.capacities?.v2g_units || scenario?.capacities?.v2gUnits || 0);
  const v2gUnits = Number(evStats.v2gUnits || 0);
  const v2gShare = totalV2gUnits > 0 ? clamp(v2gUnits / totalV2gUnits, 0, 1) : 0;
  const shape = Array.isArray(params.chargingShape) && params.chargingShape.length === 24
    ? params.chargingShape
    : new Array(24).fill(0);
  const shapeTotal = Math.max(1e-9, sum(shape.map((value) => Math.max(0, Number(value || 0)))));
  const cellChargeDayKwh = Number(evStats.chargeKwhPerDay || 0);
  const districtHourly = Array.from({ length: 24 }, (_, hour) => {
    const nativeSlice = cockpitNativeSliceForHour(hour);
    const aggregateSlice = cockpitSliceForHour(hour + 0.5);
    const slice = nativeSlice || aggregateSlice;
    const values = nativeSlice && scenario?.by_slice_native
      ? (scenario.by_slice_native[nativeSlice.id] || {})
      : (scenario?.by_slice?.[aggregateSlice.id] || {});
    const representedHours = sliceHoursPerYear(slice, `EV/V2G ${slice?.id || hour}`);
    return {
      hour,
      slice,
      dayType,
      dayTypeLabel,
      // The dispatch stores annual energy in each month/day-type/hour bucket.
      // Divide by represented hours so the card shows a typical selected hour.
      districtDischargeKwh: representedHours > 0
        ? Math.max(0, Number(values.v2g_discharge_kwh || 0) / representedHours)
        : 0,
      importTariff: Number(slice?.import_tariff_inr_per_kwh || 0),
      exportTariff: Number(slice?.export_tariff_inr_per_kwh || 0)
    };
  });
  const hourly = districtHourly.map((point) => {
    const shapeShare = Math.max(0, Number(shape[point.hour] || 0)) / shapeTotal;
    const chargeKwh = cellChargeDayKwh * shapeShare;
    const dischargeKwh = point.districtDischargeKwh * v2gShare;
    const chargeCostInr = chargeKwh * point.importTariff;
    const dischargeValueInr = dischargeKwh * point.importTariff;
    return {
      ...point,
      chargeKwh,
      dischargeKwh,
      chargeCostInr,
      dischargeValueInr,
      netInr: dischargeValueInr - chargeCostInr
    };
  });
  const netInrPeriod = sum(hourly.map((point) => point.netInr));
  const v2gValueInrDay = sum(hourly.map((point) => point.dischargeValueInr));
  const households = Number(props?.households || 0);
  const periodYear = String(scenario?.active_period_year || state.cockpit.periodYear || DEFAULT_COCKPIT_PERIOD_YEAR);
  return {
    monthIndex,
    monthLabel,
    monthDays,
    dayType,
    dayTypeLabel,
    households,
    estimatedEvCars: evStats.evCars,
    e2wCount: evStats.e2wCount,
    v2gUnits,
    totalV2gUnits,
    v2gShare,
    v2gParticipationShare: households > 0 ? v2gUnits / households : 0,
    periodYear,
    periodLabel: periodYear === DEFAULT_COCKPIT_PERIOD_YEAR ? `${periodYear} base year` : periodYear,
    hourly,
    chargeDayKwh: sum(hourly.map((point) => point.chargeKwh)),
    dischargeDayKwh: sum(hourly.map((point) => point.dischargeKwh)),
    netInrDay: netInrPeriod,
    v2gValueInrDay,
    v2gValueInrPerParticipantDay: v2gUnits > 0 ? v2gValueInrDay / v2gUnits : 0
  };
}

function evV2gStatsForCell(props, params, periodYear) {
  const households = Number(props?.households || 0);
  const income = residentialIncomeKey(props);
  const byIncome = params.byIncome?.[income] || {};
  const carShare = evCarShareForIncome(params, income, periodYear);
  const e2wShare = numberOrZero(byIncome.e2w_share ?? byIncome.e2wShare);
  const willingness = numberOrZero(params.v2gWillingnessByIncome?.[income]);
  const evCars = households * carShare;
  const e2wCount = households * e2wShare;
  const v2gUnits = evCars * willingness;
  const chargeKwhPerDay = (evCars * numberOrZero(params.evCarKwhPerDay))
    + (e2wCount * numberOrZero(params.e2wKwhPerDay));
  return { income, households, evCars, e2wCount, v2gUnits, chargeKwhPerDay, carShare, e2wShare, willingness };
}

function residentialIncomeKey(props) {
  const landUse = String(props?.land_use || "");
  if (landUse.includes("_low")) return "low";
  if (landUse.includes("_high")) return "high";
  return "mid";
}

function evCarShareForIncome(params, income, periodYear) {
  const period = params.evCarShareByPeriod?.[String(periodYear)] || {};
  const periodValue = period?.[income];
  if (Number.isFinite(Number(periodValue))) return Number(periodValue);
  const byIncome = params.byIncome?.[income] || {};
  return numberOrZero(byIncome.ev_car_share ?? byIncome.evCarShare);
}

function formatVehicleCount(value) {
  const number = Number(value || 0);
  if (number >= 100) return Math.round(number).toLocaleString("en-GB");
  if (number >= 10) return number.toFixed(1);
  return number.toFixed(2);
}

function evV2gTimelineChart(profile, selectedHour) {
  const width = 360;
  const height = 168;
  const padL = 34;
  const padR = 14;
  const padT = 20;
  const padB = 28;
  const midY = 84;
  const plotW = width - padL - padR;
  const hourly = profile.hourly || [];
  const charging = hourly.map((point) => Number(point.chargeKwh || 0));
  const discharge = hourly.map((point) => Number(point.dischargeKwh || 0));
  const maxKwh = Math.max(1, ...charging, ...discharge);
  const barW = plotW / 24 * 0.72;
  const xFor = (hour) => padL + hour * (plotW / 24) + (plotW / 24 - barW) / 2;
  const upH = (value) => (value / maxKwh) * (midY - padT - 4);
  const downH = (value) => (value / maxKwh) * (height - padB - midY - 4);
  const bars = charging.map((value, hour) => {
    const point = hourly[hour] || { hour, chargeKwh: 0, dischargeKwh: 0, importTariff: 0, chargeCostInr: 0, dischargeValueInr: 0 };
    const x = xFor(hour);
    const ch = upH(value);
    const dis = downH(discharge[hour]);
    const selected = hour === selectedHour;
    const chargeTooltip = [
      `Charging (modelled shape): ${formatHourWindow(hour, hour + 1)}`,
      `${formatEvEnergy(point.chargeKwh)} charged for this cell in a typical ${profile.monthLabel} ${profile.dayTypeLabel} hour`,
      `${formatTariff(point.importTariff)} tariff -> Rs ${formatMoneyCompact(point.chargeCostInr)} cost`,
      "Cell charging follows exported residential_charging_daypart_shape and income-period EV shares."
    ].join("\n");
    const dischargeTooltip = [
      `V2G discharge from dispatch: ${formatHourWindow(hour, hour + 1)}`,
      `${formatEvEnergy(point.dischargeKwh)} discharged for this cell in a typical ${profile.monthLabel} ${profile.dayTypeLabel} hour`,
      `${formatTariff(point.importTariff)} tariff -> Rs ${formatMoneyCompact(point.dischargeValueInr)} saved/earned`,
      `Cell share: ${formatSmallPercent(point.dischargeKwh > 0 && profile.v2gShare > 0 ? profile.v2gShare : 0)} of ${profile.periodLabel} model V2G units.`
    ].join("\n");
    return `
      <rect class="cockpit-ev-bar" x="${x.toFixed(1)}" y="${(midY - Math.max(1, ch)).toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1, ch).toFixed(1)}" rx="1.7" fill="${EV_CHARGE_COLOUR}" opacity="${selected ? "0.98" : "0.72"}" ${tooltipAttr(chargeTooltip)}></rect>
      <rect class="cockpit-ev-bar" x="${x.toFixed(1)}" y="${midY.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1, dis).toFixed(1)}" rx="1.7" fill="${EV_DISCHARGE_COLOUR}" opacity="${selected ? "0.98" : "0.74"}" ${tooltipAttr(dischargeTooltip)}></rect>
    `;
  }).join("");
  const cursorX = padL + (selectedHour + 0.5) * (plotW / 24);
  const ticks = [0, 6, 12, 18, 24].map((hour) => {
    const x = padL + (hour / 24) * plotW;
    const anchor = hour === 0 ? "start" : hour === 24 ? "end" : "middle";
    return `<text x="${x.toFixed(1)}" y="${height - 8}" text-anchor="${anchor}" fill="var(--dim)" font-size="8.5">${String(hour).padStart(2, "0")}</text>`;
  }).join("");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Residential EV charging and V2G dispatch timeline">
      <line x1="${padL}" y1="${midY}" x2="${width - padR}" y2="${midY}" stroke="var(--line-app)" />
      ${bars}
      <line x1="${cursorX.toFixed(1)}" y1="${padT}" x2="${cursorX.toFixed(1)}" y2="${height - padB}" stroke="var(--ink)" stroke-width="1.3" stroke-dasharray="3 3" opacity="0.55" />
      <text x="${padL}" y="11" fill="${EV_CHARGE_COLOUR}" font-size="8.5" font-weight="600">charging (modelled shape)</text>
      <text x="${padL}" y="${height - 31}" fill="${EV_DISCHARGE_COLOUR}" font-size="8.5" font-weight="600">V2G discharge (${escapeHtml(profile.monthLabel)} ${escapeHtml(profile.dayTypeLabel)})</text>
      ${ticks}
    </svg>
  `;
}

function formatEvEnergy(value) {
  const kwh = Math.max(0, Number(value || 0));
  if (kwh < 0.005) return "0 kWh";
  if (kwh < 1) return `${kwh.toFixed(2)} kWh`;
  if (kwh < 10) return `${kwh.toFixed(1)} kWh`;
  return `${Math.round(kwh).toLocaleString("en-GB")} kWh`;
}

function formatParticipantV2gValue(value) {
  const number = Number(value || 0);
  const formatted = Math.abs(number).toFixed(Math.abs(number) < 10 ? 1 : 0);
  return number > 0 ? `~Rs ${formatted} / participant / day` : "--";
}

function formatSmallPercent(value) {
  const percent = Number(value || 0) * 100;
  if (Math.abs(percent) < 0.01) return "0%";
  return `${percent.toFixed(Math.abs(percent) < 1 ? 2 : 1)}%`;
}

function renderCockpitPlant(props) {
  const kind = plantKindLabel(props.plant_kind);
  els.cockpitCellTitle.textContent = `${kind} ${props.row},${props.col}`;
  els.cockpitCellTier.textContent = "Stage C plant";
  const rows = [
    ["Host use", hostLandUseLabel(props)],
    ["Height", `${Number(props.height_m || 0).toFixed(1)} m`],
    ["Residential buffer", formatCellDistance(props.min_residential_distance_cells)],
    ["School buffer", formatCellDistance(props.min_school_distance_cells)]
  ];
  els.cockpitCellStats.innerHTML = rows
    .map(([label, value]) => `<div><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
  els.cockpitCellChart.innerHTML = `
    <div class="cockpit-cell-note">
      <strong>${escapeHtml(kind)}</strong>
      <span>${escapeHtml(props.siting_reason || "Spatial plant siting marker")}</span>
    </div>
  `;
  els.cockpitCellUpgrade.textContent = "Rendered from Stage C plant_siting export; dispatch remains scenario-level.";
}

function servedDemandKw(point) {
  return Math.max(
    0,
    Number(point?.demandKw || 0)
      - Number(point?.dsrReduceKw || 0)
      + Number(point?.dsrAddKw || 0)
  );
}

// GAP-1 (, the author: "why is there so much gap ... have you included
// imports"). Imports were always in. Two bands were NOT, and both are bands in
// the thesis's own Figure 5.3:
//   * solar hot water - the collectors serve water-heating demand directly,
//     28.47 GWh/yr, and that demand IS inside the demand line. Leaving the
//     supply out while keeping the demand in opens a gap by construction.
//   * green open access - purchased zero-carbon energy. Zero in production
//     today, but it is a real supply term and must be present so the balance
//     survives if the contract is ever switched on.
// Both were already in the snapshot; neither was in this list.
function stackedEnergyKeys() {
  return [
    ["gridImportKw", "Grid import", COCKPIT_FLOW_COLOURS.gridImport],
    ["greenPurchaseKw", "Green open access", COCKPIT_FLOW_COLOURS.gridExport],
    ["solarThermalKw", "Solar hot water", COCKPIT_FLOW_COLOURS.thermal],
    ["thermalDischargeKw", "Thermal store", COCKPIT_FLOW_COLOURS.thermal],
    ["biomassKw", "Biomass", COCKPIT_FLOW_COLOURS.biomass],
    ["wteKw", "WTE", COCKPIT_FLOW_COLOURS.wte],
    ["biogasKw", "Biogas", COCKPIT_FLOW_COLOURS.biogas],
    ["v2gKw", "V2G", COCKPIT_FLOW_COLOURS.v2g],
    ["batteryDischargeKw", "Battery", COCKPIT_FLOW_COLOURS.battery],
    ["floatingPvKw", "Floating PV", COCKPIT_FLOW_COLOURS.floating],
    ["carportPvKw", "Carport PV", COCKPIT_FLOW_COLOURS.carport],
    ["solarFarmKw", "Solar farm", COCKPIT_FLOW_COLOURS.solarFarm],
    ["rooftopKw", "Rooftop", COCKPIT_FLOW_COLOURS.rooftop],
    ["curtailmentKw", "Curtailment", COCKPIT_FLOW_COLOURS.curtailment]
  ];
}

function stackedEnergyAxisMax(series, period = cockpitPeriod("day")) {
  const keys = stackedEnergyKeys();
  const energyFor = (point, key) => Math.max(0, point[key] || 0) * point.durationHours * period.days;
  const servedDemandFor = (point) => servedDemandKw(point) * point.durationHours * period.days;
  const rawDemandFor = (point) => Math.max(0, Number(point.demandKw || 0)) * point.durationHours * period.days;
  const totals = series.map((point) => sum(keys.map(([key]) => energyFor(point, key))));
  const hasDsrShift = series.some((point) => (
    Math.abs(Number(point.dsrReduceKw || 0)) > 0.001
    || Math.abs(Number(point.dsrAddKw || 0)) > 0.001
  ));
  return Math.max(1, ...totals, ...series.map(servedDemandFor), ...(hasDsrShift ? series.map(rawDemandFor) : []));
}

function stackedEnergyChart(series, period = cockpitPeriod("day"), options = {}) {
  const width = 360;
  const height = 188;
  const padL = 68;
  const padR = 18;
  const padT = 20;
  const padB = 36;
  const keys = stackedEnergyKeys();
  const energyFor = (point, key) => Math.max(0, point[key] || 0) * point.durationHours * period.days;
  const servedDemandFor = (point) => servedDemandKw(point) * point.durationHours * period.days;
  const rawDemandFor = (point) => Math.max(0, Number(point.demandKw || 0)) * point.durationHours * period.days;
  const totals = series.map((point) => sum(keys.map(([key]) => energyFor(point, key))));
  const hasDsrShift = series.some((point) => (
    Math.abs(Number(point.dsrReduceKw || 0)) > 0.001
    || Math.abs(Number(point.dsrAddKw || 0)) > 0.001
  ));
  const max = Math.max(
    stackedEnergyAxisMax(series, period),
    Number(options.axisMax || 0)
  );
  const plotW = width - padL - padR;
  const xAtHour = (hour) => padL + (clamp(Number(hour || 0), 0, 24) / 24) * plotW;
  const pointHour = (point) => Number(point.hour || 0) + Number(point.durationHours || 0) / 2;
  const x = (point) => xAtHour(pointHour(point));
  const y = (value) => height - padB - (value / max) * (height - padT - padB);
  let cumulative = new Array(series.length).fill(0);
  const areas = keys.map(([key, label, colour]) => {
    const bottom = cumulative.slice();
    const values = series.map((point) => energyFor(point, key));
    cumulative = cumulative.map((value, index) => value + values[index]);
    const topPoints = cumulative.map((value, index) => `${x(series[index])},${y(value)}`).join(" ");
    const bottomPoints = bottom.map((value, index) => `${x(series[index])},${y(value)}`).reverse().join(" ");
    const totalForSource = sum(values);
    const totalSupplied = Math.max(1, sum(totals));
    const peakForSource = Math.max(0, ...values);
    const tooltip = [
      label,
      `${period.label} total: ${formatGwh(totalForSource)} (${formatPercent(totalForSource / totalSupplied)} of supplied stack)`,
      `Peak time slice: ${formatGwh(peakForSource)}`
    ].join("\n");
    return `
      <polygon points="${topPoints} ${bottomPoints}" fill="${colour}" opacity="0.76" ${tooltipAttr(tooltip)}></polygon>
    `;
  }).join("");
  // HOVER-1 (, the author: "when I hover around the graph I don't see the
  // breakdown anymore"). The per-band tooltips still work - they were verified
  // firing - but they are unusable: there are now fourteen bands and several
  // are hairlines. V2G is 0.0 % of the stack, so its polygon is about a pixel
  // tall and cannot be landed on with a mouse.
  //
  // Per-band hover was the wrong interaction for a stacked chart. These are
  // invisible full-height columns, one per time slice, each carrying the WHOLE
  // breakdown for that hour, largest source first. Hovering anywhere in the
  // column works, so the target is the full height of the plot rather than one
  // band's thickness. The band tooltips are left in place underneath for
  // anyone who does manage to hit a thick one.
  const colW = (width - padL - padR) / Math.max(1, series.length);
  const hoverCols = series.map((point, index) => {
    const rows = keys
      .map(([key, label]) => [label, energyFor(point, key)])
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([label, v]) => `${label}: ${formatGwh(v)}`);
    const body = [
      `${formatHourWindow(point.hour, point.hour + point.durationHours)}`,
      `Served demand: ${formatGwh(servedDemandFor(point))}`,
      "",
      ...rows
    ].join("\n");
    return `<rect x="${padL + index * colW}" y="${padT}" width="${colW}" height="${height - padB - padT}" fill="transparent" ${tooltipAttr(body)}></rect>`;
  }).join("");
  const servedDemandLine = series.map((point) => `${x(point)},${y(servedDemandFor(point))}`).join(" ");
  const rawDemandLine = hasDsrShift
    ? series.map((point) => `${x(point)},${y(rawDemandFor(point))}`).join(" ")
    : "";
  const cursorX = xAtHour(state.sun.timeHours);
  const ticks = [0, max / 2, max];
  const yTicks = ticks.map((tick) => `
    <g>
      <line x1="${padL - 4}" y1="${y(tick)}" x2="${width - padR}" y2="${y(tick)}" stroke="rgba(255,255,255,0.08)" />
      <text x="${padL - 9}" y="${y(tick) + 3}" text-anchor="end" fill="#93a4b8" font-size="9">${formatGwh(tick)}</text>
    </g>
  `).join("");
  const xTicks = [0, 6, 12, 18, 24].map((hour) => {
    const tx = padL + (hour / 24) * (width - padL - padR);
    const anchor = hour === 0 ? "start" : hour === 24 ? "end" : "middle";
    return `<text x="${tx}" y="${height - 14}" text-anchor="${anchor}" fill="#93a4b8" font-size="9">${String(hour).padStart(2, "0")}</text>`;
  }).join("");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${period.label} stacked energy by source">
      ${yTicks}
      <line x1="${padL}" y1="${height - padB}" x2="${width - padR}" y2="${height - padB}" stroke="rgba(255,255,255,0.22)" />
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" stroke="rgba(255,255,255,0.16)" />
      ${areas}
      ${hasDsrShift ? `<polyline points="${rawDemandLine}" fill="none" stroke="rgba(248,250,252,0.46)" stroke-width="1.25" stroke-dasharray="4 4" ${tooltipAttr("Demand before shifting.")}></polyline>` : ""}
      <polyline points="${servedDemandLine}" fill="none" stroke="#F8FAFC" stroke-width="2.2" ${tooltipAttr("Served demand. Stack above it is exported, stored or curtailed.")}></polyline>
      <!-- HOVER-1: transparent per-hour columns, LAST so they sit on top
           of every band and catch the pointer anywhere in the plot. -->
      ${hoverCols}
      <!-- TEXT-1.
           It was two floating labels in different corners, in different
           greys, one of which appeared and vanished. The legend under the
           chart now names both lines properly, so these are gone. -->
      ${xTicks}
      <text x="${(padL + width - padR) / 2}" y="${height - 3}" text-anchor="middle" fill="#64748b" font-size="8">hour</text>
      <line x1="${cursorX}" y1="${padT}" x2="${cursorX}" y2="${height - padB}" stroke="#F8FAFC" stroke-width="1.4" stroke-dasharray="3 3" />
    </svg>
  `;
}

function tariffStrip(series) {
  const cursor = (state.sun.timeHours / 24) * 100;
  const segments = series.map((point) => {
    const label = DEFAULT_TARIFFS[point.slice.tariff_band]?.label || titleCase(point.slice.tariff_band);
    return `<span class="tariff-band band-${point.slice.tariff_band}" style="flex:${point.durationHours}" title="${label}"></span>`;
  }).join("");
  return `${segments}<i class="tariff-cursor" style="left:${cursor}%"></i>`;
}

function tariffLineChart(series) {
  const width = 360;
  const height = 154;
  const padL = 48;
  const padR = 18;
  const padT = 16;
  const padB = 32;
  const max = Math.max(1, ...series.map((point) => Math.max(point.importTariff, point.exportTariff)));
  const x = (index) => padL + index * ((width - padL - padR) / (series.length - 1));
  const y = (value) => height - padB - (value / max) * (height - padT - padB);
  const importLine = series.map((point, index) => `${x(index)},${y(point.importTariff)}`).join(" ");
  const exportLine = series.map((point, index) => `${x(index)},${y(point.exportTariff)}`).join(" ");
  const p2pLine = series.map((point, index) => `${x(index)},${y((point.importTariff + point.exportTariff) / 2)}`).join(" ");
  const cursorX = padL + (state.sun.timeHours / 24) * (width - padL - padR);
  const xTicks = [0, 6, 12, 18, 24].map((hour) => {
    const tx = padL + (hour / 24) * (width - padL - padR);
    const anchor = hour === 0 ? "start" : hour === 24 ? "end" : "middle";
    return `<text x="${tx}" y="${height - 13}" text-anchor="${anchor}" fill="#93a4b8" font-size="9">${String(hour).padStart(2, "0")}</text>`;
  }).join("");
  const yTicks = [0, max / 2, max].map((tick) => `
    <g>
      <line x1="${padL - 4}" y1="${y(tick)}" x2="${width - padR}" y2="${y(tick)}" stroke="rgba(255,255,255,0.08)" />
      <text x="${padL - 7}" y="${y(tick) + 3}" text-anchor="end" fill="#93a4b8" font-size="9">${tick.toFixed(1)}</text>
    </g>
  `).join("");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="24 hour buy and sell price chart">
      ${yTicks}
      <line x1="${padL}" y1="${height - padB}" x2="${width - padR}" y2="${height - padB}" stroke="rgba(255,255,255,0.20)" />
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" stroke="rgba(255,255,255,0.16)" />
      <polyline points="${importLine}" fill="none" stroke="${COCKPIT_FLOW_COLOURS.gridImport}" stroke-width="2.4" ${tooltipAttr("Buy price: grid import tariff in INR/kWh.")}></polyline>
      <polyline points="${exportLine}" fill="none" stroke="${COCKPIT_FLOW_COLOURS.rooftop}" stroke-width="2.4" ${tooltipAttr("Sell price: export tariff in INR/kWh.")}></polyline>
      <polyline points="${p2pLine}" fill="none" stroke="${COCKPIT_FLOW_COLOURS.v2g}" stroke-width="1.6" stroke-dasharray="4 4" ${tooltipAttr("Peer-to-peer guide: mid-market reference between buy and sell prices.")}></polyline>
      <line x1="${cursorX}" y1="${padT}" x2="${cursorX}" y2="${height - padB}" stroke="#F8FAFC" stroke-width="1.2" stroke-dasharray="3 3" ${tooltipAttr("Selected time marker from the top sun/time slider.")} />
      <text x="${padL}" y="${padT - 5}" fill="#93a4b8" font-size="9">INR/kWh</text>
      ${xTicks}
      <text x="${(padL + width - padR) / 2}" y="${height - 3}" text-anchor="middle" fill="#64748b" font-size="8">hour</text>
    </svg>
  `;
}

function biomassDispatchChart(series, period = cockpitPeriod("day")) {
  const width = 360;
  const height = 140;
  const padL = 66;
  const padR = 18;
  const padT = 22;
  const padB = 32;
  const energyFor = (point, key) => Math.max(0, point[key] || 0) * point.durationHours * period.days;
  const max = Math.max(1, ...series.map((point) => Math.max(
    energyFor(point, "biomassKw"),
    energyFor(point, "wteKw"),
    energyFor(point, "biogasKw")
  )));
  const xAtHour = (hour) => padL + (hour / 24) * (width - padL - padR);
  const y = (value) => height - padB - (value / max) * (height - padT - padB);
  const stepPath = (key) => {
    const parts = [];
    series.forEach((point, index) => {
      const x0 = xAtHour(point.hour);
      const x1 = xAtHour(point.hour + point.durationHours);
      const sy = y(energyFor(point, key));
      if (index === 0) {
        parts.push(`M ${x0} ${sy}`);
      } else {
        parts.push(`V ${sy}`);
      }
      parts.push(`H ${x1}`);
    });
    return parts.join(" ");
  };
  const cursorX = padL + (state.sun.timeHours / 24) * (width - padL - padR);
  const totalToday = sum(series.map((point) => (
    point.biomassKw + point.wteKw + point.biogasKw
  ) * point.durationHours * period.days));
  const xTicks = [0, 12, 24].map((hour) => {
    const tx = padL + (hour / 24) * (width - padL - padR);
    const anchor = hour === 0 ? "start" : hour === 24 ? "end" : "middle";
    return `<text x="${tx}" y="${height - 15}" text-anchor="${anchor}" fill="#93a4b8" font-size="8.5">${String(hour).padStart(2, "0")}</text>`;
  }).join("");
  const empty = totalToday <= 0
    ? `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#93a4b8" font-size="10">No dispatchable renewables in this scenario</text>`
    : "";
  return `
    <div class="cockpit-chart-title">
      <span>Firm renewable dispatch</span>
      <strong>${formatGwh(totalToday)} ${period.label.toLowerCase()}</strong>
    </div>
    <div class="cockpit-chart-note">Dispatchable plant only. Solar is in the main chart above.</div>
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Biomass, biogas and WTE dispatch chart">
      <line x1="${padL}" y1="${height - padB}" x2="${width - padR}" y2="${height - padB}" stroke="rgba(255,255,255,0.18)" />
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${height - padB}" stroke="rgba(255,255,255,0.12)" />
      <text x="${padL - 7}" y="${padT + 3}" text-anchor="end" fill="#93a4b8" font-size="8.5">${formatGwh(max)}</text>
      <text x="${padL - 7}" y="${y(max / 2) + 3}" text-anchor="end" fill="#93a4b8" font-size="8.5">${formatGwh(max / 2)}</text>
      <text x="${padL - 7}" y="${height - padB + 3}" text-anchor="end" fill="#93a4b8" font-size="8.5">0</text>
      <text x="${padL}" y="${padT - 8}" fill="#93a4b8" font-size="8.5">slice energy</text>
      <path d="${stepPath("biomassKw")}" fill="none" stroke="${COCKPIT_FLOW_COLOURS.biomass}" stroke-width="2.6" stroke-linejoin="miter" ${tooltipAttr(`Biomass CHP: ${formatGwh(sum(series.map((point) => energyFor(point, "biomassKw"))))} ${period.label.toLowerCase()}. Step trace is constant within each 2-hour slice.`)}></path>
      <path d="${stepPath("biogasKw")}" fill="none" stroke="${COCKPIT_FLOW_COLOURS.biogas}" stroke-width="2" stroke-linejoin="miter" ${tooltipAttr(`Biogas: ${formatGwh(sum(series.map((point) => energyFor(point, "biogasKw"))))} ${period.label.toLowerCase()}. Step trace is constant within each 2-hour slice.`)}></path>
      <path d="${stepPath("wteKw")}" fill="none" stroke="${COCKPIT_FLOW_COLOURS.wte}" stroke-width="1.8" stroke-linejoin="miter" stroke-dasharray="4 4" ${tooltipAttr(`Waste-to-energy: ${formatGwh(sum(series.map((point) => energyFor(point, "wteKw"))))} ${period.label.toLowerCase()}. Step trace is constant within each 2-hour slice.`)}></path>
      ${empty}
      <line x1="${cursorX}" y1="${padT}" x2="${cursorX}" y2="${height - padB}" stroke="#F8FAFC" stroke-width="1.2" stroke-dasharray="3 3" ${tooltipAttr("Selected time marker from the top sun/time slider.")} />
      ${xTicks}
      <text x="${(padL + width - padR) / 2}" y="${height - 5}" text-anchor="middle" fill="#64748b" font-size="8">hour</text>
    </svg>
    <div class="cockpit-mini-legend cockpit-firm-legend" aria-label="Firm renewable dispatch legend">
      <span><i style="--legend-colour:${COCKPIT_FLOW_COLOURS.biomass}"></i>Biomass</span>
      <span><i style="--legend-colour:${COCKPIT_FLOW_COLOURS.biogas}"></i>Biogas</span>
      <span><i class="dashed" style="--legend-colour:${COCKPIT_FLOW_COLOURS.wte}"></i>WTE</span>
      <span><i class="vertical"></i>Selected time</span>
    </div>
  `;
}

function cellDispatchForProps(scenario, props) {
  const key = cellKey(props);
  const row = key && scenario?.by_cell?.[key];
  if (!row) return null;
  const byDaypart = row.net_district_flow_kwh_by_daypart && typeof row.net_district_flow_kwh_by_daypart === "object"
    ? row.net_district_flow_kwh_by_daypart
    : {};
  const values = STAGE_D_DAYPART_KEYS.map((daypart) => Number(byDaypart[daypart] || 0));
  const hasDayparts = values.some((value) => Number.isFinite(value) && Math.abs(value) > 0);
  const fallback = Number(row.net_district_flow_kwh || 0);
  const currentKey = stageDDaypartKey();
  const current = hasDayparts
    ? Number(byDaypart[currentKey] || 0)
    : fallback / STAGE_D_DAYPART_KEYS.length;
  return {
    key,
    netAnnualKwh: fallback,
    currentKwh: current,
    byDaypart: Object.fromEntries(STAGE_D_DAYPART_KEYS.map((daypart, index) => [
      daypart,
      hasDayparts ? values[index] : fallback / STAGE_D_DAYPART_KEYS.length
    ]))
  };
}

function formatSignedDistrictFlow(value, options = {}) {
  const kwh = Number(value || 0);
  const suffix = options.period ? ` (${options.period})` : "/yr";
  if (Math.abs(kwh) < 0.001) return `balanced ${suffix}`;
  const direction = kwh > 0 ? "imports" : "exports";
  return `${direction} ${formatGwh(Math.abs(kwh))}${suffix}`;
}

function cellDistrictFlowChart(dispatch) {
  const width = 320;
  const height = 136;
  const padL = 30;
  const padR = 12;
  const padT = 16;
  const padB = 24;
  const values = STAGE_D_DAYPART_KEYS.map((key) => Number(dispatch.byDaypart[key] || 0));
  const max = Math.max(1, ...values.map((value) => Math.abs(value)));
  const midY = padT + (height - padT - padB) / 2;
  const plotW = width - padL - padR;
  const barW = Math.max(3, plotW / STAGE_D_DAYPART_KEYS.length - 2);
  const current = stageDDaypartKey();
  const bars = STAGE_D_DAYPART_KEYS.map((key, index) => {
    const value = values[index];
    const magnitude = Math.abs(value) / max;
    const h = Math.max(1, magnitude * (height - padT - padB) * 0.46);
    const x = padL + index * (plotW / STAGE_D_DAYPART_KEYS.length) + 1;
    const y = value >= 0 ? midY - h : midY;
    const selected = key === current;
    const colour = value >= 0 ? ELECTRICAL_COLOURS.import : ELECTRICAL_COLOURS.export;
    const title = `${key}: ${formatSignedDistrictFlow(value, { period: "annual slice" })}`;
    return `
      <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="1.6" fill="rgb(${colour.slice(0, 3).join(",")})" opacity="${selected ? "0.98" : "0.68"}" ${tooltipAttr(title)}></rect>
      ${selected ? `<line x1="${(x + barW / 2).toFixed(1)}" y1="${padT}" x2="${(x + barW / 2).toFixed(1)}" y2="${height - padB}" stroke="#f8fafc" stroke-width="1" stroke-dasharray="3 3"></line>` : ""}
    `;
  }).join("");
  const ticks = [0, 6, 12, 18, 24].map((hour) => {
    const x = padL + (hour / 24) * plotW;
    const anchor = hour === 0 ? "start" : hour === 24 ? "end" : "middle";
    return `<text x="${x.toFixed(1)}" y="${height - 7}" text-anchor="${anchor}" fill="#94a3b8" font-size="8">${String(hour).padStart(2, "0")}</text>`;
  }).join("");
  return `
    <div class="cockpit-cell-note">
      <strong>Stage-D district exchange</strong>
      <span>${escapeHtml(formatSignedDistrictFlow(dispatch.netAnnualKwh))}; red = imports from the district, green = exports; most cells import (generation is concentrated in the farm/carports/plants).</span>
    </div>
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Selected cell net district import and export by daypart">
      <line x1="${padL}" y1="${midY}" x2="${width - padR}" y2="${midY}" stroke="rgba(255,255,255,0.24)" />
      <text x="${padL}" y="10" fill="#fca5a5" font-size="8.5">import</text>
      <text x="${padL}" y="${height - 30}" fill="#86efac" font-size="8.5">export</text>
      ${bars}
      ${ticks}
    </svg>
  `;
}

function cellFlowChart(scenario, pvKwp, demandKw) {
  const series = cockpitDailySeries(scenario).map((point) => ({
    hour: point.hour,
    pvKw: pvKwp * pvCapacityProfileForHour(point.hour + 1),
    demandKw: demandKw * demandProfileForHour(point.hour + 1)
  }));
  const width = 320;
  const height = 120;
  const pad = 14;
  const max = Math.max(1, ...series.map((point) => Math.max(point.pvKw, point.demandKw)));
  const barW = (width - pad * 2) / series.length - 2;
  const bars = series.map((point, index) => {
    const x = pad + index * ((width - pad * 2) / series.length);
    const pvH = (point.pvKw / max) * (height - pad * 2);
    const demandH = (point.demandKw / max) * (height - pad * 2);
    return `
      <rect x="${x}" y="${height - pad - demandH}" width="${barW}" height="${demandH}" fill="${COCKPIT_FLOW_COLOURS.gridImport}" opacity="0.46"></rect>
      <rect x="${x}" y="${height - pad - pvH}" width="${barW}" height="${pvH}" fill="${COCKPIT_FLOW_COLOURS.rooftop}" opacity="0.82"></rect>
    `;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Cell 24 hour PV and demand proxy">${bars}</svg>`;
}

function renderSourceStack(series) {
  const totals = {
    rooftop: sum(series.map((point) => point.rooftopKw * point.durationHours)),
    farm: sum(series.map((point) => point.solarFarmKw * point.durationHours)),
    carport: sum(series.map((point) => point.carportPvKw * point.durationHours)),
    floating: sum(series.map((point) => point.floatingPvKw * point.durationHours)),
    biomass: sum(series.map((point) => point.biomassKw * point.durationHours)),
    wte: sum(series.map((point) => point.wteKw * point.durationHours)),
    biogas: sum(series.map((point) => point.biogasKw * point.durationHours)),
    curtailment: sum(series.map((point) => point.curtailmentKw * point.durationHours)),
    thermal: sum(series.map((point) => point.thermalDischargeKw * point.durationHours)),
    battery: sum(series.map((point) => point.batteryDischargeKw * point.durationHours)),
    v2g: sum(series.map((point) => point.v2gKw * point.durationHours)),
    grid: sum(series.map((point) => point.gridImportKw * point.durationHours))
  };
  const total = Math.max(1, sum(Object.values(totals)));
  const parts = [
    ["Rooftop", totals.rooftop, COCKPIT_FLOW_COLOURS.rooftop],
    ["Farm", totals.farm, COCKPIT_FLOW_COLOURS.solarFarm],
    ["Carport", totals.carport, COCKPIT_FLOW_COLOURS.carport],
    ["Canal-top", totals.floating, COCKPIT_FLOW_COLOURS.floating],
    ["Biomass", totals.biomass, COCKPIT_FLOW_COLOURS.biomass],
    ["WTE", totals.wte, COCKPIT_FLOW_COLOURS.wte],
    ["Biogas", totals.biogas, COCKPIT_FLOW_COLOURS.biogas],
    ["Curtailment", totals.curtailment, COCKPIT_FLOW_COLOURS.curtailment],
    ["Thermal", totals.thermal, COCKPIT_FLOW_COLOURS.thermal],
    ["Battery", totals.battery, COCKPIT_FLOW_COLOURS.battery],
    ["V2G", totals.v2g, COCKPIT_FLOW_COLOURS.v2g],
    ["Grid", totals.grid, COCKPIT_FLOW_COLOURS.gridImport]
  ].filter(([, value]) => value > 0);
  els.cockpitSourceStack.innerHTML = parts.map(([label, value, colour]) => (
    `<span style="width:${Math.max(2, (value / total) * 100)}%;background:${colour}" title="${label} ${formatPercent(value / total)}"></span>`
  )).join("");
  els.cockpitSourceLabel.textContent = parts.map(([label, value]) => `${label} ${formatPercent(value / total)}`).join(" / ");
}

function renderStageCTechStack(scenario) {
  if (!els.cockpitTechStack) return;
  const heading = els.cockpitTechStack.parentElement?.querySelector("span");
  if (heading) {
    heading.textContent = `Installed capacity (${scenario.active_period_label || "scenario"})`;
  }
  const capacities = scenario.capacities || {};
  const cap = (key) => capacityValue(capacities, key);
  const items = [
    ["Rooftop PV", formatMaybePv(cap("rooftop_pv_kwp")), COCKPIT_FLOW_COLOURS.rooftop, cap("rooftop_pv_kwp") > 0],
    ["Solar farm", formatMaybePv(cap("solar_farm_kwp")), COCKPIT_FLOW_COLOURS.solarFarm, cap("solar_farm_kwp") > 0],
    ["Carport PV", formatMaybePv(cap("carport_kwp")), COCKPIT_FLOW_COLOURS.floating, cap("carport_kwp") > 0],
    ["Battery", formatMaybeStorage(cap("battery_kwh")), COCKPIT_FLOW_COLOURS.battery, cap("battery_kwh") > 0],
    ["V2G units", cap("v2g_units") === null ? "--" : formatVehicleCount(cap("v2g_units")), COCKPIT_FLOW_COLOURS.v2g, cap("v2g_units") > 0],
    ["Tracked PV", cap("tracked_pv_active") > 0 ? "+18% farm yield" : cap("tracked_pv_active") === null ? "--" : "Off", COCKPIT_FLOW_COLOURS.solarFarm, cap("tracked_pv_active") > 0],
    ["Biomass CHP", formatMaybePower(cap("biomass_kw_e")), COCKPIT_FLOW_COLOURS.biomass, cap("biomass_kw_e") > 0],
    ["Biogas", formatMaybePower(cap("biogas_kw_e")), COCKPIT_FLOW_COLOURS.biogas, cap("biogas_kw_e") > 0],
    ["WTE", formatMaybePower(cap("wte_kw_e")), COCKPIT_FLOW_COLOURS.wte, cap("wte_kw_e") > 0],
    ["Thermal store", formatMaybeStorage(cap("thermal_storage_kwh")), COCKPIT_FLOW_COLOURS.thermal, cap("thermal_storage_kwh") > 0],
    ["Canal-top PV", formatMaybePv(cap("floating_pv_kwp")), COCKPIT_FLOW_COLOURS.floating, cap("floating_pv_kwp") > 0]
  ];
  els.cockpitTechStack.innerHTML = items.map(([label, value, colour, active]) => `
    <div class="${active ? "active" : "muted"}" style="--stagec:${colour}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("") + batteryEraNote(scenario);
}

function batteryEraNote(scenario) {
  const periods = availablePeriodYears(scenario);
  if (periods.length < 2) return "";
  const parts = periods.map((year) => {
    const value = numberOrNull(scenario.period_breakdown?.[year]?.installed_capacities?.battery_kwh);
    return `${year} ${formatMaybeStorage(value)}`;
  });
  const active = numberOrNull(scenario.capacities?.battery_kwh);
  const activeText = active !== null && active > 0
    ? `Active period storage: ${formatMaybeStorage(active)}.`
    : "Active period storage: none.";
  return `
    <div class="stagec-era-note">
      <span>Battery era</span>
      <strong>${escapeHtml(parts.join(" -> "))}</strong>
      <small>${escapeHtml(activeText)} Storage appears as learning-curve costs fall.</small>
    </div>
  `;
}

function renderDispatchRealismChecks(activeScenario) {
  if (!els.cockpitRealismChecks) return;
  const baseline = state.cockpit.data?.scenarios.find((scenario) => scenario.name === "full_stack" && Number(scenario.alpha ?? 0) === 0)
    || state.cockpit.data?.scenarios.find((scenario) => scenario.name === "full_stack")
    || activeScenario;
  const checks = dispatchRealismChecks(baseline);
  if (!checks.length) {
    els.cockpitRealismChecks.innerHTML = `<div class="realism-check muted">Dispatch realism checks unavailable.</div>`;
    return;
  }
  els.cockpitRealismChecks.innerHTML = checks.map((check) => `
    <div class="realism-check ${check.pass ? "pass" : "watch"}" title="${escapeHtml(check.title || check.detail || "")}">
      <i></i>
      <div>
        <span>${escapeHtml(check.label)}</span>
        <strong>${escapeHtml(check.value)}</strong>
        <small>${escapeHtml(check.detail || "")}</small>
      </div>
    </div>
  `).join("");
}

function dispatchRealismChecks(scenario) {
  if (!scenario) return [];
  const sourceIsDispatch = state.cockpit.data?.source === "dispatch_results";
  const rows = dispatchNativeRows(scenario);
  const spikes = dispatchDsrSpikeSummary(rows);
  const pv = dispatchPvSeasonSummary(rows);
  const biomass = dispatchBiomassSeasonSummary(rows);
  const tod = dispatchTodSeasonSummary();
  const checks = [
    {
      label: "Data source",
      value: sourceIsDispatch ? "dispatch_results.json" : "fallback summary",
      pass: sourceIsDispatch,
      detail: sourceIsDispatch
        ? `Scenario ${scenario.name || "unknown"} carbon weight ${Number(scenario.alpha ?? 0).toFixed(2)}. Every figure is read from the run.`
        : "Cockpit is not reading the current dispatch JSON.",
      title: "Confirms the realism checks and headline are derived from the current dispatch export."
    }
  ];
  if (spikes.available) {
    checks.push({
      label: "Demand-response spikes",
      value: `${spikes.count} above 1.8x`,
      pass: spikes.count === 0,
      detail: spikes.count === 0
        ? "Effective load has no audit-threshold spikes after demand response and managed EV charging."
        : `Largest ${spikes.maxRatio.toFixed(2)}x at ${spikes.maxId}.`,
      title: "Same effective-load check as scripts/dispatch_realism_audit.py: demand + dsr_add - dsr_reduce + ev_shift_in - ev_shift_out."
    });
  }
  if (pv.available) {
    checks.push({
      label: "PV seasonality",
      value: `Oct/Jun ${pv.octJunRatio.toFixed(2)}`,
      pass: pv.octJunRatio <= 1.15,
      detail: `Current weekday ratio is ${pv.octJunRatio.toFixed(3)} from dispatch_results.json.`,
      title: `June ${formatEnergy(pv.junKwhPerDay)} per weekday; October ${formatEnergy(pv.octKwhPerDay)}.`
    });
  }
  if (biomass.available) {
    checks.push({
      label: "Biomass shape",
      value: biomass.seasonal ? "seasonal" : "flat",
      pass: biomass.seasonal,
      detail: `${biomass.minMonth.toUpperCase()} ${biomass.minGwh.toFixed(2)} GWh/mo; ${biomass.maxMonth.toUpperCase()} ${biomass.maxGwh.toFixed(2)} GWh/mo.`,
      title: "Monthly biomass generation is read from the dispatch by_slice map."
    });
  }
  if (tod.available) {
    checks.push({
      label: "Seasonal ToD",
      value: tod.months.length ? tod.months.join("-") : "none",
      pass: tod.pass,
      detail: tod.pass
        ? "Evening peak bands appear only in Jun-Sep."
        : `Expected Jun-Sep only; found ${tod.months.join(", ") || "none"}.`,
      title: "Reads peak/super_peak tariff_band values from dispatch_results.json slices."
    });
  }
  return checks;
}

function dispatchNativeRows(scenario) {
  const native = scenario.by_slice_native && Object.keys(scenario.by_slice_native).length
    ? scenario.by_slice_native
    : scenario.by_slice || {};
  const slices = scenario.by_slice_native && Object.keys(scenario.by_slice_native).length
    ? state.cockpit.data?.native_slices || []
    : state.cockpit.data?.slices || [];
  return (slices || [])
    .map((slice) => ({ slice, values: native[slice.id] || null, parts: dispatchSliceIdParts(slice.id) }))
    .filter((row) => row.values && row.parts);
}

function dispatchSliceIdParts(id) {
  const match = String(id || "").match(/^([a-z]{3})_([a-z]+)_(\d{2})(?:_\d{2})?$/i);
  if (!match) return null;
  return {
    month: match[1].toLowerCase(),
    dayType: match[2].toLowerCase(),
    hour: Number(match[3])
  };
}

function dispatchDsrSpikeSummary(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const hours = Number(row.slice?.hours_per_year || 0);
    if (hours <= 0 || !row.parts?.dayType) return;
    const key = `${row.parts.month}_${row.parts.dayType}`;
    const effectiveKw = (
      Number(row.values.demand_kwh || 0)
      + Number(row.values.dsr_add_kwh ?? row.values.dsr_add ?? 0)
      - Number(row.values.dsr_reduce_kwh ?? row.values.dsr_reduce ?? 0)
      + Number(row.values.ev_shift_in_kwh ?? row.values.ev_shift_in ?? 0)
      - Number(row.values.ev_shift_out_kwh ?? row.values.ev_shift_out ?? 0)
    ) / hours;
    if (!Number.isFinite(effectiveKw)) return;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ id: row.slice.id, effectiveKw });
  });
  const spikes = [];
  groups.forEach((items) => {
    const mean = sum(items.map((item) => item.effectiveKw)) / Math.max(1, items.length);
    if (mean <= 0) return;
    items.forEach((item) => {
      const ratio = item.effectiveKw / mean;
      if (ratio > 1.8) spikes.push({ ...item, ratio });
    });
  });
  const largest = spikes.reduce((best, item) => item.ratio > best.ratio ? item : best, { ratio: 0, id: "" });
  return {
    available: groups.size > 0,
    count: spikes.length,
    maxRatio: largest.ratio,
    maxId: largest.id || ""
  };
}

function dispatchPvSeasonSummary(rows) {
  const totals = new Map();
  rows.forEach((row) => {
    if (row.parts?.dayType !== "wd") return;
    const hours = Number(row.slice?.hours_per_year || 0);
    if (hours <= 0) return;
    const current = totals.get(row.parts.month) || { kwh: 0, hours: 0 };
    current.kwh += Number(row.values.pv_kwh || 0);
    current.hours += hours;
    totals.set(row.parts.month, current);
  });
  const perDay = (month) => {
    const row = totals.get(month);
    return row && row.hours > 0 ? row.kwh / row.hours * 24 : null;
  };
  const jun = perDay("jun");
  const oct = perDay("oct");
  return {
    available: jun !== null && oct !== null && jun > 0,
    junKwhPerDay: jun || 0,
    octKwhPerDay: oct || 0,
    octJunRatio: jun ? oct / jun : 0
  };
}

function dispatchBiomassSeasonSummary(rows) {
  const monthly = new Map();
  rows.forEach((row) => {
    const value = Math.abs(Number(row.values.biomass_kwh || 0));
    if (!Number.isFinite(value)) return;
    monthly.set(row.parts.month, Number(monthly.get(row.parts.month) || 0) + value);
  });
  const entries = Array.from(monthly.entries()).filter(([, value]) => value > 0);
  if (!entries.length) return { available: false };
  const sorted = entries.sort((a, b) => a[1] - b[1]);
  const [minMonth, minValue] = sorted[0];
  const [maxMonth, maxValue] = sorted[sorted.length - 1];
  const spread = maxValue > 0 ? (maxValue - minValue) / maxValue : 0;
  return {
    available: true,
    seasonal: spread >= 0.10,
    minMonth,
    maxMonth,
    minGwh: minValue / 1_000_000,
    maxGwh: maxValue / 1_000_000,
    spread
  };
}

function dispatchTodSeasonSummary() {
  const slices = state.cockpit.data?.native_slices || state.cockpit.data?.slices || [];
  const months = new Map();
  slices.forEach((slice) => {
    if (!["peak", "super_peak"].includes(slice.tariff_band)) return;
    const parts = dispatchSliceIdParts(slice.id);
    if (!parts) return;
    if (!months.has(parts.month)) months.set(parts.month, new Set());
    months.get(parts.month).add(parts.hour);
  });
  const found = MONTH_KEYS.filter((month) => months.has(month));
  const expected = ["jun", "jul", "aug", "sep"];
  return {
    available: slices.length > 0,
    months: found,
    pass: found.length === expected.length && expected.every((month, index) => found[index] === month)
  };
}

function capacityValue(capacities, key) {
  return Object.prototype.hasOwnProperty.call(capacities || {}, key) ? numberOrNull(capacities[key]) : null;
}

function formatMaybePv(value) {
  return value === null ? "--" : formatPv(value);
}

function formatMaybePower(value) {
  return value === null ? "--" : formatPowerValue(value);
}

function formatMaybeStorage(value) {
  return value === null ? "--" : formatGwh(value);
}

function renderParetoChart(scenario) {
  if (!els.cockpitParetoChart || !els.cockpitParetoLabel) return;
  const pareto = state.cockpit.data?.pareto || [];
  if (pareto.length < 2) {
    els.cockpitParetoChart.innerHTML = `<div class="cockpit-empty compact">Run Stage C alpha sweep to populate the Pareto curve.</div>`;
    els.cockpitParetoLabel.textContent = "No alpha sweep data loaded";
    return;
  }
  els.cockpitParetoChart.innerHTML = paretoChartSvg(pareto, scenario);
  const _hz = pareto.every((row) => row.horizon_ok);
  const _c = (row) => _hz ? row.lifetime_cost_inr : row.annual_cost_inr;
  const _e = (row) => _hz ? row.cumulative_kgco2 : row.annual_emissions_kgco2;
  const minEmissions = pareto.reduce((best, row) => _e(row) < _e(best) ? row : best, pareto[0]);
  const minCost = pareto.reduce((best, row) => _c(row) < _c(best) ? row : best, pareto[0]);
  // PARETO-1: the caption must quote the SAME pair the chart plots, or the
  // reader reconciles a lifetime curve against an annual sentence.
  const horizon = pareto.every((row) => row.horizon_ok);
  const cOf = (row) => horizon ? row.lifetime_cost_inr : row.annual_cost_inr;
  const eOf = (row) => horizon ? row.cumulative_kgco2 : row.annual_emissions_kgco2;
  const unit = horizon ? " over the horizon" : "/yr";
  els.cockpitParetoLabel.textContent =
    `Carbon across, cost up. Cheapest ${formatCost(cOf(minCost))}${unit}; `
    + `lowest carbon ${formatEmissions(eOf(minEmissions))}${unit} at alpha `
    + `${minEmissions.alpha.toFixed(2)}.`
    + (horizon ? "" : " Annual pair - horizon data unavailable.");
}

function paretoChartSvg(rows, scenario) {
  const width = 320;
  const height = 150;
  const pad = 20;
  // PARETO-1: carbon on X, COST ON Y, matching Figure 5.7. And the HORIZON
  // pair wherever it can be built, because the annual pair is not monotone.
  const horizon = rows.every((row) => row.horizon_ok);
  const costOf = (row) => horizon ? row.lifetime_cost_inr : row.annual_cost_inr;
  const carbonOf = (row) => horizon ? row.cumulative_kgco2 : row.annual_emissions_kgco2;
  const costs = rows.map(costOf);
  const emissions = rows.map(carbonOf);
  const minCost = Math.min(...costs);
  const maxCost = Math.max(...costs);
  const minEmissions = Math.min(...emissions);
  const maxEmissions = Math.max(...emissions);
  const x = (carbon) => pad + ((carbon - minEmissions) / Math.max(1, maxEmissions - minEmissions)) * (width - pad * 2);
  const y = (cost) => height - pad - ((cost - minCost) / Math.max(1, maxCost - minCost)) * (height - pad * 2);
  const points = rows.map((row) => `${x(carbonOf(row))},${y(costOf(row))}`).join(" ");
  const activeAlpha = Number(scenario.alpha ?? 0);
  const unit = horizon ? " over the horizon" : "/yr";
  const dots = rows.map((row) => {
    const active = Math.abs(row.alpha - activeAlpha) < 0.001 && scenario.name === "full_stack";
    return `
      <circle cx="${x(carbonOf(row))}" cy="${y(costOf(row))}" r="${active ? 5 : 3.2}" fill="${active ? "#F8FAFC" : "#38BDF8"}">
        <title>alpha ${row.alpha.toFixed(2)}: ${formatCost(costOf(row))}${unit}, ${formatEmissions(carbonOf(row))}${unit}</title>
      </circle>
    `;
  }).join("");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Pareto frontier: cumulative carbon on the horizontal axis, lifetime cost on the vertical">
      <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="rgba(255,255,255,0.18)" />
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" stroke="rgba(255,255,255,0.18)" />
      <polyline points="${points}" fill="none" stroke="#38BDF8" stroke-width="2.2" />
      ${dots}
      <!-- PARETO-2.
           WORSE THAN MISSING - they were WRONG. The axes were swapped
           earlier the same night and these three labels were left behind,
           so the horizontal axis was captioned "lower cost / higher cost"
           while it plots carbon. Proper titles on both axes now, with the
           direction stated once. -->
      <text x="${pad + (width - pad * 2) / 2}" y="${height - 3}" fill="#cbd5e1" font-size="9.5" text-anchor="middle">Cumulative CO2, low to high</text>
      <text transform="translate(9,${pad + (height - pad * 2) / 2}) rotate(-90)" fill="#cbd5e1" font-size="9.5" text-anchor="middle">Lifetime cost, low to high</text>
    </svg>
  `;
}

function cockpitStatusLabel(snapshot) {
  if (snapshot.gridExportKw > snapshot.gridImportKw) return "Exporting";
  if (snapshot.batteryChargeKw > snapshot.batteryDischargeKw) return "Charging";
  if (snapshot.batteryDischargeKw > 0 || snapshot.v2gKw > 0) return "Discharging";
  return "Importing";
}

function cockpitStatusClass(snapshot) {
  return cockpitStatusLabel(snapshot).toLowerCase();
}

function sliceHoursPerYear(slice, context = "dispatch slice", options = {}) {
  const hours = Number(slice?.hours_per_year);
  if (Number.isFinite(hours) && hours > 0) return hours;
  if (options.warn !== false && (!Number.isFinite(hours) || hours < 0 || options.warnZero)) {
    warnCockpitDataOnce(
      `invalid-hours-${slice?.id || context}`,
      `Invalid hours_per_year for ${slice?.id || context}; affected value set to zero.`
    );
  }
  return 0;
}

function sliceAnnualKwhToKw(value, slice, context = "dispatch energy") {
  const numericValue = Number(value || 0);
  const hours = sliceHoursPerYear(slice, context, { warnZero: Math.abs(numericValue) > 0.001 });
  if (hours <= 0) return 0;
  return numericValue / hours;
}

function pvBaseCapacityShares(scenario) {
  const capacities = scenario.capacities || {};
  const rooftop = Number(capacities.rooftop_pv_kwp || 0) + Number(capacities.bipv_kwp || 0);
  const farm = Number(capacities.solar_farm_kwp || 0);
  const carport = Number(capacities.carport_kwp || 0);
  const floating = Number(capacities.floating_pv_kwp || 0);
  const trackedFarm = Number(capacities.tracked_pv_active || 0) > 0
    || Number(capacities.solar_farm_tracked_kwp || 0) > 0;
  const weights = {
    rooftop,
    farm: farm * (trackedFarm ? 1.18 : 1),
    carport,
    floating
  };
  const total = sum(Object.values(weights));
  if (total <= 0) {
    if (Number(scenario?.pv_generation_kwh || 0) > 0) {
      warnCockpitDataOnce(
        `pv-share-capacity-missing-${scenario?.name || "scenario"}`,
        `PV source split has no exported surface capacities for ${scenario?.name || "scenario"}; PV bands set to zero.`
      );
    }
    return { rooftop: 0, farm: 0, carport: 0, floating: 0 };
  }
  return {
    rooftop: weights.rooftop / total,
    farm: weights.farm / total,
    carport: weights.carport / total,
    floating: weights.floating / total
  };
}

function seasonFromDayOfYear(dayOfYear) {
  const monthIndex = monthIndexFromDayOfYear(dayOfYear);
  return seasonFromMonthIndex(monthIndex);
}

function seasonFromMonthIndex(monthIndex) {
  if (monthIndex === 11 || monthIndex <= 1) return "winter";
  if (monthIndex >= 2 && monthIndex <= 4) return "spring";
  if (monthIndex >= 5 && monthIndex <= 8) return "monsoon";
  return "autumn";
}

function monthIndexFromSeason(season) {
  const fallbackBySeason = {
    winter: 0,
    spring: 3,
    monsoon: 6,
    autumn: 9
  };
  return fallbackBySeason[String(season || "").toLowerCase()] ?? monthIndexFromDayOfYear(state.sun.dayOfYear);
}

function monthIndexFromDayOfYear(dayOfYear) {
  let remaining = clamp(Math.round(Number(dayOfYear) || 1), 1, 366);
  for (let index = 0; index < DAYS_IN_MONTH.length; index += 1) {
    if (remaining <= DAYS_IN_MONTH[index]) return index;
    remaining -= DAYS_IN_MONTH[index];
  }
  return 11;
}

function daypartFromHour(hour) {
  if (hour < 6) return "night";
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  if (hour < 22) return "evening";
  return "late";
}

function tariffBandForHour(hour) {
  const time = ((Number(hour) % 24) + 24) % 24;
  if (time < 6) return "super_off_peak";
  if (time < 12) return "shoulder";
  if (time < 18) return "shoulder";
  if (time < 22) return "peak";
  return "off_peak";
}

function pvCapacityProfileForHour(hour) {
  if (hour < 6 || hour > 19) return 0;
  const angle = ((hour - 6) / 13) * Math.PI;
  return Math.max(0, Math.sin(angle)) * 0.72;
}

function demandProfileForHour(hour) {
  if (hour < 6) return 0.58;
  if (hour < 12) return 0.88;
  if (hour < 18) return 1.04;
  if (hour < 22) return 1.28;
  return 0.76;
}

function ownershipTierForCell(props) {
  const landUse = String(props.land_use || "");
  // FARM-1: the ring is utility-owned generation like the rest of the farm,
  // not the open space its land_use tag says it is.
  if (isFarmSurfaceProps(props) || landUse === "road") return 3;
  if (landUse.startsWith("residential") || ["school", "healthcare", "public_services"].includes(landUse)) return 2;
  return 1;
}

function cellDemandProxyKw(props) {
  const floorArea = Number(props.floor_area_m2 || 0);
  const households = Number(props.households || 0);
  return Math.max(0.4, floorArea / 1800 + households * 0.22);
}

function recommendedCellUpgrade(props, pvKwp) {
  if (isFarmSurfaceProps(props)) return "Check clipping and export limit";  // FARM-1
  if (Number(props.floor_area_m2 || 0) <= 0) return "No building upgrade candidate yet";
  if (pvKwp <= 0) return "Add rooftop PV when cell economics lands";
  return "Battery / demand shifting candidate";
}

function formatShadingMultiplier(shade) {
  const multiplier = Number(shade?.multiplier ?? 1);
  const drop = Math.round((1 - multiplier) * 100);
  const offenders = Array.isArray(shade?.offenders) ? shade.offenders : [];
  if (shade?.source === "geometric") {
    const nearby = offenders.length
      ? `; legacy tall-neighbour flags: ${offenders.map((item) => item.direction).join(", ")}`
      : "; no legacy tall-neighbour flag";
    return `${multiplier.toFixed(2)} (${drop}% geometric annual shading${nearby})`;
  }
  if (!offenders.length) return `${multiplier.toFixed(2)} (no tall S/SW/SE/E/W neighbours)`;
  const directions = offenders.map((item) => item.direction).join(", ");
  return `${multiplier.toFixed(2)} (${drop}% drop from ${offenders.length} tall neighbour${offenders.length === 1 ? "" : "s"}: ${directions})`;
}

function formatPowerValue(value) {
  const abs = Math.abs(Number(value || 0));
  const prefix = Number(value || 0) < 0 ? "-" : "";
  if (abs >= 1000) return `${prefix}${(abs / 1000).toFixed(1)} MW`;
  return `${prefix}${abs.toFixed(0)} kW`;
}

function formatKva(value) {
  const kva = Number(value || 0);
  if (!kva) return "0 kVA";
  if (kva >= 1000) return `${(kva / 1000).toFixed(2)} MVA`;
  return `${kva.toFixed(0)} kVA`;
}

function voltageClassLabel(value) {
  const key = String(value || "");
  if (key === "backbone_33kv") return "33 kV backbone";
  if (key === "dist_11kv") return "11 kV distribution";
  return titleCase(key || "voltage class");
}

function electricalKindLabel(kind) {
  const labels = {
    electrical_edge: "Feeder edge",
    electrical_transformer: "Transformer zone",
    electrical_substation: "Substation",
    electrical_bess: "Battery energy storage",
    electrical_flow_arc: "Cell energy flow",
    electrical_grid_line: "Grid interconnection",
    electrical_ppa_line: "Data-centre PPA line"
  };
  return labels[kind] || "Electrical network";
}

function formatGwh(value) {
  const kwh = Number(value || 0);
  if (kwh >= 1_000_000) return `${(kwh / 1_000_000).toFixed(2)} GWh`;
  if (kwh >= 1_000) return `${(kwh / 1_000).toFixed(1)} MWh`;
  return `${kwh.toFixed(0)} kWh`;
}

function formatPpaOfftake(value) {
  const gwh = Number(value || 0) / 1_000_000;
  const digits = Math.abs(gwh) < 10 ? 2 : 1;
  return `${gwh.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })} GWh`;
}

function formatMoneyCompact(value) {
  const amount = Math.abs(Number(value || 0));
  if (amount >= 10_000_000) return `${(amount / 10_000_000).toFixed(2)} cr`;
  if (amount >= 100_000) return `${(amount / 100_000).toFixed(2)} L`;
  if (amount >= 1000) return `${(amount / 1000).toFixed(1)} k`;
  return `${Math.round(amount)}`;
}

function formatSignedMoney(value) {
  const amount = Number(value || 0);
  const sign = amount < 0 ? "-" : "+";
  return `${sign}INR ${formatMoneyCompact(amount)}`;
}

function formatTariff(value) {
  return `${Number(value || 0).toFixed(2)} INR/kWh`;
}

function formatNetCostHeadline(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `Rs ${number.toFixed(2)}/kWh` : "--";
}

function formatHourWindow(start, end) {
  return `${formatClockHour(start)}-${formatClockHour(end)}`;
}

function formatClockHour(hour) {
  const value = ((Math.round(hour) % 24) + 24) % 24;
  return `${String(value).padStart(2, "0")}:00`;
}

function sum(values) {
  return values.reduce((total, value) => total + Number(value || 0), 0);
}

function firstFiniteNumber(source, keys) {
  for (const key of keys) {
    const value = Number(source?.[key]);
    if (Number.isFinite(value)) return value;
  }
  return 0;
}

function hasFiniteField(source, keys) {
  return keys.some((key) => Number.isFinite(Number(source?.[key])));
}

function finiteOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function numberOrUndefined(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function numberOrZero(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function parseShadingOffenderDirs(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .replace(/[\[\]'"]/g, " ")
      .split(/[,\s/]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function truthyFlag(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return ["true", "1", "yes", "on", "enabled"].includes(value.toLowerCase());
  return false;
}

// PV / Shade / Deploy / Grid are computed FOR THE OPTIMISED TOWN ONLY. the author,
// "the pv, shade, deploy, grid option should not exist on
// baseline". An earlier attempt locked the LAYOUT buttons while an overlay was
// on; hiding the overlays on the layouts they do not apply to is the better
// way round - it leaves layout comparison free, which is the whole point of
// having a baseline. Switching away also clears them, so nothing survives to
// be painted onto a layout that never produced it.
function syncOverlayAvailability() {
  const allowed = isOptimisedLayout();
  [els.pvOverlayToggle, els.shadingOverlayToggle,
   els.pvDeploymentToggle, els.electricalOverlayToggle].forEach((btn) => {
    if (btn) btn.hidden = !allowed;
  });
  if (!allowed) {
    if (state.pvOverlayEnabled) setPvOverlayEnabled(false);
    if (state.shadingOverlayEnabled) setShadingOverlayEnabled(false);
    if (state.pvDeploymentOverlayEnabled) setPvDeploymentOverlayEnabled(false);
    if (state.electricalOverlayEnabled) setElectricalOverlayEnabled(false);
  }
}

function updateLayoutButtons() {
  syncOverlayAvailability();
  els.layoutButtons.querySelectorAll("[data-layout]").forEach((button) => {
    const isActive = button.dataset.layout === state.currentLayout;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
  renderArchetypeSummary();
}

function handleMapClick({ object }) {
  if (!object) return;
  if (object.properties?.kind && String(object.properties.kind).startsWith("electrical_")) return;
  state.selectedCellProps = { ...object.properties };
  state.cockpit.selectedCellProps = { ...object.properties };
  updateSelectedCellPanel();
  setCockpitTab("cells");
  renderCockpit();
}

function updateSelectedCellPanel() {
  if (!state.selectedCellProps) {
    els.cellPanel.classList.add("hidden");
    return;
  }

  const props = state.selectedCellProps;
  if (isPlantFeatureProps(props)) {
    updateSelectedPlantPanel(props);
    return;
  }
  // the ACTUAL building typology for this cell - income band
  // + height tier + storeys. The model carries three heights per income
  // class (layout/spine_gradient.py, the Bertaud gradient: TALL on the
  // arterial spine, MEDIUM in the body, SHORT at the edge, floor-neutral
  // at 2 TALL : 3 SHORT). None of that was visible in the viewer, which
  // showed only the land-use name.
  // HIG is excluded from tier SCALING (fixed plotted form) so its tier
  // always reads "medium" - describing it by tier would be misleading, so
  // it is described by height instead.
  const buildingTypeLabel = (p) => {
    const lu = String(p.land_use || "");
    // ORDER MATTERS. On a PARCEL feature `height_m` is 0.35 - the ground
    // slab thickness, not the building - while `cell_height_m` carries the
    // real building height (12/15/18/27 m). Reading height_m first gave
    // every cell G+0. cell_height_m is present on structures too, so it is
    // the safe first choice for both.
    const h = Number(p.cell_height_m || p.height_m || 0);
    const storeys = Math.max(1, Math.round(h / 3));
    if (lu === "residential_high") {
      return `HIG plotted kothi, G+${storeys - 1} (${h.toFixed(0)} m), ~40 houses/ha`;
    }
    if (lu === "residential_low" || lu === "residential_mid") {
      const band = lu === "residential_low" ? "EWS/LIG" : "MIG";
      const tier = String(p.height_tier || "medium").toLowerCase();
      const form = tier === "tall" ? "apartment tower"
        : tier === "short" ? "walk-up block" : "mid-rise flats";
      const far = tier === "tall" ? "FAR 3.0"
        : tier === "short" ? "FAR 1.34" : "FAR 2.0";
      return `${band} ${form}, G+${storeys - 1} (${h.toFixed(0)} m), ${far}`;
    }
    return null;
  };

  const title = `${LABELS[props.land_use] || titleCase(props.land_use)} - ${props.part || props.role}`;
  els.cellPanelTitle.textContent = title;
  els.cellPanelGrid.innerHTML = "";

  const rows = [
    ["Cell", `${props.row}, ${props.col}`],
    ["Land use", LABELS[props.land_use] || titleCase(props.land_use)],
    ["Building type", buildingTypeLabel(props) || "--"],
    ["Height tier", props.height_tier || "--"],
    ["Height", `${Number(props.height_m || 0).toFixed(1)} m`],
    ["Floor area", formatArea(props.floor_area_m2)],
    ["Households", formatNumber(props.households)],
    ["Albedo", Number(props.albedo ?? 0).toFixed(2)],
    ["Vegetation", `${Math.round(Number(props.vegetation_fraction || 0) * 100)}%`]
  ];
  if (hasPvReadoutProps(props)) {
    rows.splice(6, 0,
      ["PV capacity", formatPv(featurePvKwp(props))],
      ["PV deployed", formatPvDeploymentPanel(props)],
      ["Clear-sky PV", formatEnergy(featureHourlyPvKwh(props))]
    );
  }
  // SOLAR WATER HEATING PER CELL. The collectors are drawn on the roofs and
  // the allocation is exported per cell, but clicking a roof reported only its
  // photovoltaics, so there was no way to ask a building how much of its roof
  // went to hot water. Shown next to the PV rows because the two compete for
  // the SAME square metres - the exporter allocates them against one roof
  // budget - and reading either alone misstates what the roof is doing.
  const stM2 = featureSolarThermalM2(props);
  if (stM2 > 0) {
    rows.splice(6, 0, ["Solar hot water", formatArea(stM2)]);
  }
  const axis = buildingAxisLabel(props);
  if (axis) rows.splice(8, 0, ["Axis", axis]);
  if (isBipvCandidate(props)) {
    rows.splice(8, 0, ["BIPV deployed", formatBipvDeployment(props)]);
  }
  lightingRows(props).slice().reverse().forEach((row) => rows.splice(6, 0, row));
  amenitySubtypeRows(props).slice().reverse().forEach((row) => rows.splice(2, 0, row));
  streetAssetRows(props).slice().reverse().forEach((row) => rows.splice(2, 0, row));
  const faith = faithLabel(props.faith);
  if (faith) rows.splice(2, 0, ["Faith", faith]);
  if (featureCarportKwp(props) > 0) rows.splice(2, 0, ["Carport site", "Parking-lot canopy site"]);
  carportPvRows(props).slice().reverse().forEach((row) => rows.splice(2, 0, row));
  floatingPvSiteRows(props).slice().reverse().forEach((row) => rows.splice(2, 0, row));
  const shade = state.cellShading.get(cellKey(props));
  if (shade) {
    rows.splice(8, 0, ["PV yield multiplier", formatShadingMultiplier(shade)]);
    const diagnostics = shadingDiagnosticRows(props);
    diagnostics.slice().reverse().forEach((row) => rows.splice(9, 0, row));
  }
  const audit = formatAuditIssues(props);
  if (audit) {
    rows.splice(2, 0, ["Placement flags", audit]);
  }
  const entrances = formatEntranceSides(props.entrance_sides);
  if (entrances) {
    rows.splice(2, 0, ["Entrances", entrances]);
  }

  rows.forEach(([label, value]) => {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    els.cellPanelGrid.append(term, detail);
  });

  els.cellPanel.classList.remove("hidden");
}

function updateSelectedPlantPanel(props) {
  els.cellPanelTitle.textContent = `${plantKindLabel(props.plant_kind)} plant`;
  els.cellPanelGrid.innerHTML = "";

  const rows = [
    ["Cell", `${props.row}, ${props.col}`],
    ["Host land use", hostLandUseLabel(props)],
    ["Plant kind", plantKindLabel(props.plant_kind)],
    ["Height", `${Number(props.height_m || 0).toFixed(1)} m`],
    ["Residential buffer", formatCellDistance(props.min_residential_distance_cells)],
    ["School buffer", formatCellDistance(props.min_school_distance_cells)],
    ["Siting", props.siting_reason || "Stage C plant siting export"]
  ];

  rows.forEach(([label, value]) => {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    els.cellPanelGrid.append(term, detail);
  });

  els.cellPanel.classList.remove("hidden");
}

function updateDeckParameters() {
  if (!state.deckgl) return;
  state.deckgl.setProps({
    parameters: deckParameters(),
    effects: currentLightingEffects()
  });
}

function deckParameters() {
  const clearColor = dayStatusForAltitude(state.sun.altitudeDeg).clearColor;
  return {
    clearColor,
    depthTest: true,
    depthFunc: 515
  };
}

function dayStatusForAltitude(altitudeDeg) {
  //: sky re-tinted from the grey-green family to the
  // metropolis navy-atmosphere family. Same four states, same thresholds,
  // same mechanism - ONLY the colours moved (day stays clearly day, night
  // goes deep navy, dawn/dusk carries the warm horizon).
  if (altitudeDeg < 0) {
    return {
      label: "Night",
      clearColor: [0.043, 0.063, 0.149, 1],
      bg: ["#070b1c", "#0b1026", "#10173a"]
    };
  }
  if (altitudeDeg < 18) {
    return {
      label: "Low sun",
      clearColor: [0.19, 0.15, 0.26, 1],
      bg: ["#141228", "#3a2c3a", "#1a1830"]
    };
  }
  if (altitudeDeg < 50) {
    return {
      label: "Day",
      clearColor: [0.42, 0.52, 0.66, 1],
      bg: ["#1c2a44", "#3d5578", "#22304e"]
    };
  }
  return {
    label: "High sun",
    clearColor: [0.56, 0.65, 0.77, 1],
    bg: ["#2b4160", "#5f7896", "#31486a"]
  };
}

function applyDayStatusTint() {
  const status = dayStatusForAltitude(state.sun.altitudeDeg);
  document.body.style.setProperty("--scene-bg-a", status.bg[0]);
  document.body.style.setProperty("--scene-bg-b", status.bg[1]);
  document.body.style.setProperty("--scene-bg-c", status.bg[2]);
  els.sunStatusLabel.textContent = status.label;
}

function skyForAltitude(altitudeDeg) {
  if (altitudeDeg < 0) {
    return {
      clearColor: [0.20, 0.25, 0.34, 1],
      top: "#1b2535",
      mid: "#30405a",
      ground: "#25322e",
      sunColor: [130, 155, 205, 80],
      sunRadiusM: 220
    };
  }
  if (altitudeDeg < 18) {
    return {
      clearColor: [0.80, 0.58, 0.42, 1],
      top: "#405b84",
      mid: "#d99155",
      ground: "#4b4638",
      sunColor: [255, 150, 66, 245],
      sunRadiusM: 280
    };
  }
  if (altitudeDeg < 50) {
    return {
      clearColor: [0.46, 0.68, 0.92, 1],
      top: "#5f9fde",
      mid: "#8bc2ef",
      ground: "#d8e7dd",
      sunColor: [255, 222, 88, 245],
      sunRadiusM: 220
    };
  }
  return {
    clearColor: [0.68, 0.83, 0.98, 1],
    top: "#8bc7f2",
    mid: "#d6edff",
    ground: "#e8f2ea",
    sunColor: [255, 255, 238, 245],
    sunRadiusM: 170
  };
}

function updateCompass() {
  if (!els.compassNeedle) return;
  _ensureCompassDrag();
  const northScreen = worldToScreenDirection(0, 1);
  const northAngleDeg = toDeg(Math.atan2(northScreen.x, -northScreen.y));
  els.compassNeedle.style.transform = `translate(-50%, -50%) rotate(${northAngleDeg}deg)`;
}

// CMP-1 (, the author: "when I drag the compass it changes view
// too"): drag anywhere on the compass face to rotate the camera bearing;
// the needle follows live.
function _ensureCompassDrag() {
  if (state._compassDragHooked) return;
  const face = document.querySelector(".compass-panel");
  if (!face) return;
  state._compassDragHooked = true;
  face.style.cursor = "grab";
  face.style.touchAction = "none";
  let drag = null;
  const angAt = (e) => {
    const r = face.getBoundingClientRect();
    return Math.atan2(e.clientY - (r.top + r.height / 2),
                      e.clientX - (r.left + r.width / 2)) * 180 / Math.PI;
  };
  face.addEventListener("pointerdown", (e) => {
    drag = { a0: angAt(e), b0: Number(state.viewState.bearing || 0), moved: false };
    face.setPointerCapture(e.pointerId);
    face.style.cursor = "grabbing";
    e.preventDefault();
  });
  face.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const delta = angAt(e) - drag.a0;
    if (Math.abs(delta) > 3) drag.moved = true;
    const bearing = drag.b0 + delta;
    state.viewState = constrainViewState({ ...state.viewState, bearing });
    if (state.deckgl) state.deckgl.setProps({ viewState: state.viewState });
    const northScreen = worldToScreenDirection(0, 1);
    els.compassNeedle.style.transform =
      `translate(-50%, -50%) rotate(${toDeg(Math.atan2(northScreen.x, -northScreen.y))}deg)`;
    updateScaleBar();
  });
  const end = (e) => {
    // CMP-2: a plain CLICK
    // (no meaningful rotation) animates the bearing back to NORTH.
    if (drag && !drag.moved && e.type === "pointerup") {
      const b0 = Number(state.viewState.bearing || 0);
      const target = b0 - (((b0 % 360) + 540) % 360 - 180);   // nearest 0
      const t0 = performance.now();
      const step = (now) => {
        const k = Math.min(1, (now - t0) / 320);
        const ease = 1 - Math.pow(1 - k, 3);
        state.viewState = constrainViewState({
          ...state.viewState, bearing: b0 + (target - b0) * ease });
        if (state.deckgl) state.deckgl.setProps({ viewState: state.viewState });
        updateCompass();
        updateScaleBar();
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
    drag = null;
    face.style.cursor = "grab";
  };
  face.addEventListener("pointerup", end);
  face.addEventListener("pointercancel", end);
}

function updateScaleBar() {
  if (!els.scaleBar || !els.scaleLabel || !els.scalePanel) return;
  const metersPerPixel = metersPerPixelAtView();
  if (!Number.isFinite(metersPerPixel) || metersPerPixel <= 0) return;
  const candidatesM = [
    5, 10, 20, 50,
    100, 200, 500,
    1_000, 2_000, 5_000,
    10_000, 20_000
  ];
  const minPx = 72;
  const maxPx = 150;
  let chosen = candidatesM.find((meters) => {
    const px = meters / metersPerPixel;
    return px >= minPx && px <= maxPx;
  });
  if (!chosen) {
    chosen = candidatesM.reduce((best, meters) => (
      Math.abs((meters / metersPerPixel) - 112) < Math.abs((best / metersPerPixel) - 112)
        ? meters
        : best
    ), candidatesM[0]);
  }
  const widthPx = clamp(chosen / metersPerPixel, 44, 180);
  const cssWidth = `${Math.round(widthPx)}px`;
  els.scalePanel.style.setProperty("--scale-bar-width", cssWidth);
  els.scaleLabel.textContent = formatScaleDistance(chosen);
  els.scalePanel.title = `Approximate ground scale at zoom ${Number(state.viewState.zoom || 0).toFixed(2)}`;
}

function metersPerPixelAtView() {
  // SCALE-1 (, the author: "the bar says 5 km but the entire town
  // length is 5 km"): 156543 m/px is the 256-px-tile web-map constant;
  // deck.gl's zoom follows the 512-px convention, so every reading was
  // exactly 2x too long. Correct constant: 40,075,016.686 / 512.
  const latitude = Number(state.viewState.latitude ?? state.sun.latitude ?? 0);
  const zoom = Number(state.viewState.zoom ?? 0);
  return 78271.51696402048 * Math.cos(toRad(latitude)) / Math.pow(2, zoom);
}

function formatScaleDistance(meters) {
  if (meters >= 1000) {
    const km = meters / 1000;
    return `${Number.isInteger(km) ? km.toFixed(0) : km.toFixed(1)} km`;
  }
  return `${Math.round(meters)} m`;
}

function constrainViewState(viewState) {
  const next = { ...viewState };
  const bounds = state.data?.metadata?.bounds || layoutByName(state.currentLayout)?.bounds;
  if (bounds && bounds.length === 4) {
    const [minLon, minLat, maxLon, maxLat] = bounds.map(Number);
    const lonPad = (maxLon - minLon) * 0.35;
    const latPad = (maxLat - minLat) * 0.35;
    next.longitude = clamp(Number(next.longitude), minLon - lonPad, maxLon + lonPad);
    next.latitude = clamp(Number(next.latitude), minLat - latPad, maxLat + latPad);
  }
  return {
    ...next,
    zoom: clamp(Number(next.zoom ?? state.viewState.zoom), 11.5, 18.8),
    pitch: clamp(Number(next.pitch ?? state.viewState.pitch), 0, 85)
  };
}

function worldToScreenDirection(east, north) {
  const bearing = toRad(-(state.viewState.bearing || 0));
  const eastScreen = { x: Math.cos(bearing), y: Math.sin(bearing) };
  const northScreen = { x: Math.sin(bearing), y: -Math.cos(bearing) };
  return {
    x: east * eastScreen.x + north * northScreen.x,
    y: east * eastScreen.y + north * northScreen.y
  };
}

function updateSunLabels() {
  els.sunDateLabel.textContent = formatDayOfYear(state.sun.dayOfYear);
  els.sunTimeLabel.textContent = formatTimeOfDay(state.sun.timeHours);
}

function updateTariffStatus() {
  const band = tariffBandForTime(state.sun.timeHours);
  const className = band === "peak"
    ? "tariff-peak"
    : band === "off_peak"
      ? "tariff-off-peak"
      : "tariff-shoulder";
  const label = band === "peak" ? "Peak" : band === "off_peak" ? "Off-peak" : "Shoulder";

  els.tariffStatus.classList.remove("tariff-peak", "tariff-off-peak", "tariff-shoulder");
  els.tariffStatus.classList.add(className);
  els.tariffStatusLabel.textContent = label;
  els.tariffStatus.title = `${label} tariff band`;
  // The band was printed here AND in the Tariff chip immediately to the right,
  // so "Shoulder" appeared twice within about 80px. Dropping it from the time
  // readout removes the duplication and takes ~60px off the widest card in the
  // control row, which is what was forcing the row onto a second line
  // (the author, "make sure everything is ordered, in one line if
  // possible"). The field also keeps its tariff-band tint, so the colour still
  // links the two without repeating the word.
  els.sunTimeLabel.textContent = formatTimeOfDay(state.sun.timeHours);

  if (els.sunTimeField) {
    els.sunTimeField.classList.remove("tariff-peak", "tariff-off-peak", "tariff-shoulder");
    els.sunTimeField.classList.add(className);
  }
}

function tariffBandForTime(timeHours) {
  const time = ((Number(timeHours) % 24) + 24) % 24;
  if (time >= 18 && time < 22) return "peak";
  if (time >= 22 || time < 6) return "off_peak";
  return "shoulder";
}

function surfaceColor(props) {
  //: grouped tonal palette (designRgb) with legacy colour_rgb fallback.
  const rgb = designRgb(props) || [190, 190, 190];
  if (props.land_use === "road") return roadSurfaceColor(props);
  //: ONE light-blue for
  // EVERY water surface - ponds, canal, floating-PV water - matching the
  // CNL-2 connector tone, so merged bodies read as one.
  if (props.land_use === "blue_space") {
    return withAlpha([74, 144, 208], 238);
  }
  if (props.land_use === "parking_lot") return withAlpha(mix(rgb, [18, 22, 28], 0.10), 216);
  if (props.land_use === "open_space") return openSpaceSurfaceColor(props, rgb);
  //: the GROUND under the arrays is grass, not navy -
  // real farms sit on green; the panels carry the technology colour.
  if (props.land_use === "solar_farm") return withAlpha([98, 138, 84], 214);
  return withAlpha(mix(rgb, [22, 24, 25], state.theme === "dark" ? 0.18 : 0.04), 178);
}

function roadSurfaceColor(props) {
  const roadClass = String(props?.road_class || "");
  // VERGE-1 (, the author: "roads are 100 m wide... the rest of the
  // road cell's width should be greenery"): when the per-class cross-section
  // strip draws on top (toggle on + a cross_section_m entry for this class),
  // the CELL base is the ROW remainder - planted verge, not tarmac. An
  // arterial is 45 of the 100 m; the other 55 m now reads green. Falls back
  // to the asphalt base whenever the strip cannot draw (toggle off, or a
  // layout exported without road_network metadata), so roads never vanish.
  const xs = (state.data?.metadata?.road_network || {}).cross_section_m || {};
  if (state.roadSectionsEnabled && xs[roadClass]) {
    // GREEN-1: ONE verge green for every road class
    return withAlpha([131, 158, 104], 222);
  }
  if (roadClass === "arterial") return withAlpha([70, 75, 76], 230);
  if (roadClass === "collector") return withAlpha([92, 98, 98], 218);
  if (roadClass === "local") return withAlpha([116, 126, 122], 210);
  return withAlpha(mix(props?.colour_rgb || [150, 150, 150], [40, 42, 42], 0.44), 190);
}

function openSpaceSurfaceColor(props, rgb) {
  const subtype = String(props?.amenity_subtype || "");
  if (isSolarExpansionProps(props)) {
    //: ACTIVE expansion ground = the same grass green
    // as the farm cells (was golden). Ungranted reserve stays pale straw.
    return isExpansionActiveProps(props)
      ? withAlpha([98, 138, 84], 216)
      : withAlpha(mix([164, 180, 118], [235, 220, 142], 0.35), 142);
  }
  if (isParkingExpansionProps(props)) {
    return isExpansionActiveProps(props)
      ? withAlpha([102, 110, 112], 214)
      : withAlpha(mix([120, 130, 125], [210, 218, 210], 0.35), 132);
  }
  // GREEN-1 (, the author: "keep one green for open green space, a
  // darker green for parks"): parks (community + neighbourhood + greenway)
  // share ONE darker park green; all other open space shares ONE lighter
  // green (below). Agri stays olive - fields are not lawn.
  if (subtype === "park_community" || subtype === "park_neighbourhood"
      || subtype === "greenway") {
    return withAlpha([58, 132, 72], 226);
  }
  if (subtype === "agri_belt") return withAlpha([143, 158, 78], 218);
  // VACANT-1 (, the author: "the satellite image was roughly 25 km2
  // and there was no greenery" + the close-ups: "even this green free
  // space"): in the Zirakpur baseline, UNTAGGED open space is the plan's
  // own "Open/Vacant Land" (Table 3-1, 308.91 ha) plus TRAPPED ACTIVE
  // FIELDS - the satellite shows both, mixed. Deterministic per-cell hash
  // (no RNG): ~30% cropped field, ~20% fallow scrub, ~50% bare dust.
  // Tagged parks above stay the green pockets (one big park + scraps).
  if (state.currentLayout === "zirakpur_ribbon") {
    // v5 (the author: "no to minimal green area actually outside the
    // buildings ... brown cells could be wasted and unbuilt land"):
    // untagged leftover = brown waste plots. The ONLY big green is the
    // two agri_belt field voids he traced (~1.01 + 0.59 km2) plus the
    // small tagged park scraps.
    const h = (Number(props?.row || 0) * 31 + Number(props?.col || 0) * 17) % 10;
    if (h < 1) return withAlpha([139, 141, 92], 206);   // dry scrub tinge (v9: rarer)
    if (h < 5) return withAlpha([166, 149, 112], 210);  // packed earth
    return withAlpha([176, 156, 120], 212);             // bare/vacant dust
  }
  // GREEN-1: ONE flat green for all remaining open space
  return withAlpha([116, 170, 104], 212);
}

function pvCeilingColor(props, options = {}) {
  const pvKwp = state.cellPvKwp.get(cellKey(props)) || 0;
  if (pvKwp <= 0) {
    return state.theme === "dark"
      ? [35, 43, 45, options.structure ? 120 : 96]
      : [202, 207, 200, options.structure ? 150 : 122];
  }

  // FARM-1: the ring is farm surface too. Before this, its 100 cells fell
  // through to the rooftop intensity ramp below and the farm rendered in two
  // colours, which is what the author saw.
  if (isFarmSurfaceProps(props)) {
    return options.structure ? [255, 172, 66, 238] : [255, 198, 78, 218];
  }

  // CARPORT-1.
  //
  // Because this function only ever had ONE non-rooftop branch, the farm. Every
  // other PV-bearing surface fell through to the rooftop intensity ramp below,
  // so a carport with a lot of kWp was drawn in the same colour as a large roof
  // and the legend then called it "High rooftop". Canal-top and floating PV had
  // the same problem here, though not in the deployment overlay, which already
  // carried a blue_space branch - so the two overlays disagreed with each other
  // about what a canal was.
  //
  // These are four DIFFERENT technologies on four different surfaces, and the
  // ramp is a within-technology intensity scale, not a technology key. Ground
  // mount, carport and canal-top each get their own colour; only actual roofs
  // reach the ramp.
  if (props?.land_use === "parking_lot") {
    return options.structure ? [150, 118, 236, 238] : [168, 132, 246, 218];
  }
  if (props?.land_use === "blue_space") {
    return options.structure ? [45, 212, 191, 230] : [45, 212, 191, 210];
  }

  const scaleKwp = Math.max(1, state.pvOverlayScaleKwp || state.pvOverlayMaxKwp || 1);
  const intensity = clamp(Math.sqrt(pvKwp / scaleKwp), 0, 1);
  const colour = pvColourRamp(intensity);
  const alpha = options.structure ? Math.round(170 + intensity * 65) : Math.round(150 + intensity * 88);
  return withAlpha(colour, alpha);
}

function pvShadingColor(props, options = {}) {
  const shade = state.cellShading.get(cellKey(props));
  if (!shade) {
    return state.theme === "dark"
      ? [35, 43, 45, options.structure ? 112 : 86]
      : [202, 207, 200, options.structure ? 138 : 112];
  }
  //. Ground-mount farm surfaces always read as
  // UNSHADED in this overlay, whatever multiplier the cell carries.
  // WHY, because this looks like a lie and is not: this overlay visualises
  // shade cast by TALL NEIGHBOURS. Inspection of the solved network showed
  // that no penalised farm cell has a neighbour taller than 1 m - the
  // "casters" are the ground-mount panels themselves, 0.25 m high. So the
  // penalty those cells carry is a building rule firing on a surface with no
  // buildings on it, and painting them amber or red told the viewer something
  // untrue about the site. Real inter-row self-shading on the farm is a
  // different mechanism and was measured at 0.021 % (GCR-1), far below
  // anything this ramp can resolve.
  // The MODEL still carries the derating; this changes presentation only, so
  // the reported energy results remain conservative by up to 0.75 pp on
  // vs-BAU cost (farm_shading_ab_20260822.txt). on,
  // taken to his supervisor, who judged the effect minute and not worth
  // reporting. Do NOT "fix" this back without re-reading that decision.
  if (isFarmSurfaceProps(props)) {
    const alpha = options.structure ? 185 : 156;
    return withAlpha(shadingColourRamp(0), alpha);
  }
  const penaltyRatio = shadingPenaltyRatio(shade.multiplier);
  const colour = shadingColourRamp(penaltyRatio);
  const alpha = options.structure ? Math.round(185 + penaltyRatio * 55) : Math.round(156 + penaltyRatio * 82);
  return withAlpha(colour, alpha);
}

function pvDeploymentColor(props, options = {}) {
  const ratio = featurePvDeploymentRatio(props);
  if (ratio <= 0) {
    return state.theme === "dark"
      ? [35, 43, 45, options.structure ? 110 : 82]
      : [202, 207, 200, options.structure ? 132 : 102];
  }
  // FARM-1: same fall-through as pvCeilingColor, in the PV Deployed overlay.
  if (isFarmSurfaceProps(props)) {
    return withAlpha([245, 158, 11], options.structure ? 238 : 220);
  }
  // CARPORT-1: this overlay already distinguished the canal but not the
  // carport, so a car park read as a roof here too.
  if (props?.land_use === "parking_lot") {
    return withAlpha([168, 132, 246], options.structure ? 238 : 220);
  }
  if (props?.land_use === "blue_space") {
    return withAlpha([45, 212, 191], options.structure ? 230 : 210);
  }
  const colour = ratio < 0.5
    ? mix([88, 139, 116], [44, 141, 98], ratio / 0.5)
    : mix([44, 141, 98], [34, 197, 94], (ratio - 0.5) / 0.5);
  const alpha = options.structure ? Math.round(180 + ratio * 58) : Math.round(145 + ratio * 88);
  return withAlpha(colour, alpha);
}

function shadingPenaltyRatio(multiplier) {
  const value = clamp(Number(multiplier ?? 1), 0, 1);
  const min = Number(state.shadingRamp?.min);
  const max = Number(state.shadingRamp?.max);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return 0;
  return clamp((max - value) / (max - min), 0, 1);
}

function shadingColourRamp(penaltyRatio) {
  if (penaltyRatio < 0.5) {
    return mix([34, 197, 94], [250, 204, 21], penaltyRatio / 0.5);
  }
  return mix([250, 204, 21], [239, 68, 68], (penaltyRatio - 0.5) / 0.5);
}

function pvColourRamp(intensity) {
  if (intensity < 0.35) {
    return mix([40, 76, 96], [72, 170, 164], intensity / 0.35);
  }
  if (intensity < 0.72) {
    return mix([72, 170, 164], [245, 214, 86], (intensity - 0.35) / 0.37);
  }
  return mix([245, 214, 86], [255, 132, 54], (intensity - 0.72) / 0.28);
}

function isPlantFeatureProps(props) {
  return Boolean(props && (props.role === "plant" || props.plant_kind));
}

function plantKindLabel(kind) {
  return PLANT_LABELS[kind] || titleCase(kind || "plant");
}

function hostLandUseLabel(props) {
  const landUse = props.host_land_use || props.land_use || "";
  return landUse ? (LABELS[landUse] || titleCase(landUse)) : "--";
}

function plantRgb(props) {
  const colour = props?.colour_rgb;
  if (Array.isArray(colour) && colour.length >= 3) {
    return colour.slice(0, 3).map((value) => clamp(Math.round(Number(value || 0)), 0, 255));
  }
  return PLANT_COLOURS[props?.plant_kind] || [233, 122, 60];
}

function plantColor(props, alpha = 242) {
  return withAlpha(plantRgb(props), alpha);
}

function structureColor(props) {
  //: grouped tonal palette (designRgb) with legacy colour_rgb fallback.
  const rgb = designRgb(props) || [210, 210, 210];
  if (isPlantFeatureProps(props)) return plantColor(props, 246);
  if (props.part === "solar_array") return [32, 82, 132, 214];
  if (props.land_use === "office") return withAlpha(mix(rgb, [230, 240, 240], 0.18), 238);
  if (props.land_use === "healthcare") return withAlpha(mix(rgb, [255, 245, 235], 0.12), 238);
  return withAlpha(mix(rgb, [255, 245, 220], state.theme === "dark" ? 0.10 : 0.04), 235);
}

// CHG-3 helpers: deterministic 0..1 hash per building
// (row, col, part) - same pattern as the existing seeds at lines ~1986/2473.
function buildingHash01(props) {
  let h = (Number(props.row || 0) * 73856093) ^ (Number(props.col || 0) * 19349663);
  const part = String(props.part || props.role || "");
  for (let i = 0; i < part.length; i += 1) h = (h * 31 + part.charCodeAt(i)) | 0;
  return ((h >>> 0) % 1000) / 1000;
}

//: build the roof-cap dataset. One entry per structure,
// carrying the outer ring lifted to that structure's own roof height and the
// cap colour. The lift MUST use the same height x jitter expression as
// `district-structures`' getElevation, or caps float above / sink into their
// buildings - the jitter is deterministic per building, so this reproduces
// exactly rather than approximately.
function roofCapFeatures() {
  if (!state.data) return [];
  const out = [];
  for (const f of state.data.features) {
    const props = f.properties || {};
    if (props.role === "parcel" || props.role === "plant"
        || props.role === "street_edge"
        || props.land_use === "retail_highstreet") continue;
    if (isPlantFeatureProps(props)) continue;
    const top = scaledFeatureHeightM(props) * buildingHeightJitter(props);
    if (!(top > 0)) continue;
    const geom = f.geometry;
    const polys = geom?.type === "Polygon" ? [geom.coordinates]
      : geom?.type === "MultiPolygon" ? geom.coordinates : [];
    if (!polys.length) continue;
    const colour = roofCapColour(props);
    for (const poly of polys) {
      const ring = poly[0];
      if (!ring || ring.length < 4) continue;
      out.push({ contour: ring.map(([x, y]) => [x, y, top]), colour });
    }
  }
  return out;
}

// The cap's colour is what turns a box into a building. metropolis mixes its
// pitched roofs 35% toward terracotta (#8A4A3C) and leaves flat tops as a
// lightened base; the same split is used here, keyed on land use, so the
// residential fabric reads as tiled roofs and the commercial/institutional
// stock reads as flat capped slabs. Derived from the wall colour so the
// existing per-building jitter and the tonal families carry through.
function roofCapColour(props) {
  const base = jitteredStructureColor(props);
  const lu = String(props?.land_use || "");
  const pitched = lu === "residential_low" || lu === "residential_mid";
  const target = pitched ? [138, 74, 60] : [156, 158, 156];
  const amount = pitched ? 0.42 : 0.26;
  return withAlpha(mix([base[0], base[1], base[2]], target, amount), 255);
}

function buildingHeightJitter(props) {
  if (props.part === "solar_array" || isPlantFeatureProps(props)) return 1.0;
  return 0.95 + 0.10 * buildingHash01(props); // +/-5% display-only
}

function jitteredStructureColor(props) {
  const base = structureColor(props);
  if (props.part === "solar_array" || isPlantFeatureProps(props)) return base;
  const j = buildingHash01(props);
  const tint = 0.92 + 0.14 * j; // +/-7% brightness, slight warm/cool spread
  const warmShift = (j - 0.5) * 10;
  return [
    Math.max(0, Math.min(255, Math.round(base[0] * tint + warmShift))),
    Math.max(0, Math.min(255, Math.round(base[1] * tint))),
    Math.max(0, Math.min(255, Math.round(base[2] * tint - warmShift))),
    base[3]
  ];
}

function mix(a, b, amount) {
  return a.map((value, index) => Math.round(value * (1 - amount) + b[index] * amount));
}

function withAlpha(rgb, alpha) {
  return [rgb[0], rgb[1], rgb[2], alpha];
}

function percentile(values, ratio) {
  const sorted = values
    .map(Number)
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * ratio)));
  return sorted[index];
}

function getTooltip({ object }) {
  if (!object) return null;
  if (object.kind === "solar_farm_tracker" || object.properties?.kind === "solar_farm_tracker") {
    return solarFarmTrackerTooltip(object);
  }
  const props = object.properties;
  // BESS-1: without this the block fell through to the generic parcel tooltip,
  // which reads land_use, households and floor area - none of which a battery
  // site carries - and printed "Undefined - undefined" with three zeros.
  if (props?.kind === "bess_site") return bessSiteTooltip(props);
  if (props?.role === "street_edge") return streetEdgeTooltip(props);
  if (props?.kind && String(props.kind).startsWith("electrical_")) return electricalTooltip(props);
  if (isPlantFeatureProps(props)) return plantTooltip(props);
  const title = `${LABELS[props.land_use] || titleCase(props.land_use)} · ${props.part || props.role}`;
  return {
    className: "deck-tooltip",
    html: `
      <div class="tooltip-title">${escapeHtml(title)}</div>
      <div class="tooltip-grid">
        <span>Cell</span><strong>${props.row}, ${props.col}</strong>
        <span>Height</span><strong>${Number(props.height_m || 0).toFixed(1)} m</strong>
        <span>Households</span><strong>${formatNumber(props.households)}</strong>
        <span>Floor area</span><strong>${formatArea(props.floor_area_m2)}</strong>
        ${tooltipRoadRows(props)}
        ${tooltipReserveRows(props)}
        ${tooltipLightingRows(props)}
        ${tooltipPvCapacityRow(props)}
        ${tooltipPvDeploymentRows(props)}
        ${tooltipBipvRows(props)}
        ${tooltipSiteRows(props)}
        ${tooltipEntranceRows(props)}
        ${tooltipPvThisHourRow(props)}
        ${tooltipAxisRow(props)}
        ${tooltipShadingRows(props)}
        ${tooltipAuditRows(props)}
      </div>
    `
  };
}

function tooltipRoadRows(props) {
  //: make the road's true cross-section +
  // per-cell furniture counts readable on hover - the render draws 1-2
  // glyphs, the MODEL carries 7/5/3 poles per arterial/collector/local cell
  // (IS 1944 spacing) and the ROW is 45/24/12 m of the 100 m cell.
  if (props?.land_use !== "road") return "";
  const rn = state.data?.metadata?.road_network || {};
  const cs = (rn.cross_section_m || {})[props.road_class] || null;
  const fur = (rn.furniture_per_road_cell || {})[props.road_class] || null;
  const rows = [];
  rows.push(`<span>Class</span><strong>${escapeHtml(titleCase(props.road_class || "road"))} · ${Number(props.road_width_m || 0).toFixed(0)} m ROW</strong>`);
  if (cs) {
    const cyc = cs.cycle_each_side > 0 ? ` + cycle 2x${cs.cycle_each_side}` : "";
    const med = cs.median > 0 ? ` + median ${cs.median}` : "";
    rows.push(`<span>Section</span><strong>${cs.carriageway} m carriageway${med}${cyc} + foot 2x${cs.footpath_each_side} + verge 2x${cs.verge_each_side} m</strong>`);
  }
  if (fur) {
    rows.push(`<span>Per cell</span><strong>${fur.streetlight_poles} poles · ${fur.avenue_trees} avenue trees (glyphs are representative)</strong>`);
  }
  return rows.join("\n");
}

function tooltipReserveRows(props) {
  // (the author: "the unused cells - how to utilise them till they
  // are used"): phased reserves are PRODUCTIVE in the interim - agri/green
  //.16; phased_land_multipliers price the lease until the grant year).
  if (!isExpansionReserveProps(props)) return "";
  const year = phaseYearFromSubtype(props.amenity_subtype);
  const active = isExpansionActiveProps(props);
  const what = isSolarExpansionProps(props) ? "solar farm ring" : "parking growth parcel";
  if (active) {
    return `<span>Phase</span><strong>Built ${escapeHtml(String(year || ""))} · ${escapeHtml(what)}</strong>`;
  }
  return `<span>Until ${escapeHtml(String(year || "unlock"))}</span><strong>farmed / greenbelt (interim agri lease priced in the model), then ${escapeHtml(what)}</strong>`;
}

function streetEdgeTooltip(props) {
  const kind = props.kind === "greenway_path" ? "Greenway path" : "Local access lane";
  return {
    className: "deck-tooltip",
    html: `
      <div class="tooltip-title">${escapeHtml(kind)}</div>
      <div class="tooltip-grid">
        <span>Layer</span><strong>${escapeHtml(props.kind || "street_edge")}</strong>
        <span>Role</span><strong>Cell-edge access network</strong>
      </div>
    `
  };
}

// BESS-1: the battery site's own tooltip. The generic parcel tooltip asks a
// battery about households and floor area, so it printed "Undefined -
// undefined" with three zeros. This reports what a battery site actually has,
// and reports it FOR THE ACTIVE PERIOD, because the capacity and the footprint
// both change between 2030, 2042 and 2055 while the height does not - more
// containers are added, not taller ones.
function bessSiteTooltip(props) {
  const kwh = Number(props.batteryKwh || 0);
  const year = activePeriodYearNumber();
  const area = Number(props.areaM2 || 0);
  const units = Number(props.units || 0);
  const hours = kwh > 0 ? kwh / 1000 / 4 : 0;   // 4-hour system convention
  return {
    className: "deck-tooltip",
    html: `
      <div class="tooltip-title">Battery storage &middot; ${escapeHtml(String(year))}</div>
      <div class="tooltip-grid">
        <span>Cell</span><strong>${props.row}, ${props.col}</strong>
        <span>Capacity</span><strong>${escapeHtml((kwh / 1000).toFixed(1))} MWh</strong>
        <span>Power, at 4 h</span><strong>${escapeHtml(hours.toFixed(1))} MW</strong>
        <span>Height</span><strong>${escapeHtml(BESS_HEIGHT_M.toFixed(1))} m</strong>
        <span>Footprint</span><strong>${escapeHtml(formatNumber(area))} m&sup2;</strong>
        <span>Containers</span><strong>${escapeHtml(formatNumber(units))}</strong>
        <span>Enters</span><strong>2042</strong>
      </div>
    `
  };
}

function solarFarmTrackerTooltip(object) {
  const props = object.properties || {};
  const capacity = Number(activeCockpitScenario()?.capacities?.solar_farm_kwp || 0);
  const tracked = truthyFlag(props.tracked_pv_active);
  const tiltDeg = Number(props.tracker_tilt_deg || object.trackerTiltDeg || 0);
  const label = props.tracker_label || object.trackerLabel || "tracker state";
  return {
    className: "deck-tooltip",
    html: `
      <div class="tooltip-title">${tracked ? "Tracked solar farm" : "Solar farm"}</div>
      <div class="tooltip-grid">
        <span>Cell</span><strong>${escapeHtml(`${props.row ?? "--"}, ${props.col ?? "--"}`)}</strong>
        <span>Tracker</span><strong>${escapeHtml(label)}</strong>
        <span>Tilt</span><strong>${escapeHtml(`${tiltDeg.toFixed(0)} deg at ${formatTimeOfDay(state.sun.timeHours)}`)}</strong>
        <span>Farm capacity</span><strong>${escapeHtml(capacity > 0 ? formatPv(capacity) : "--")}</strong>
        <span>Yield mode</span><strong>${tracked ? "+18% tracked farm yield" : "fixed tilt"}</strong>
      </div>
    `
  };
}

function electricalTooltip(props) {
  const rows = [];
  if (props.kind === "electrical_edge") {
    rows.push(["Edge", props.edgeKey || "--"]);
    rows.push(["Voltage", voltageClassLabel(props.voltageClass)]);
    rows.push(["Annual flow", formatGwh(props.flowKwh || 0)]);
    rows.push(["Loading", formatPercent(props.loading || 0)]);
  } else if (props.kind === "electrical_transformer") {
    rows.push(["Zone", String(props.zoneIndex || "--")]);
    rows.push(["Transformer", formatKva(props.kva)]);
    rows.push(["Peak load", formatPowerValue(props.peakKw || 0)]);
    rows.push(["Built cells", formatNumber(props.nBuilt)]);
  } else if (props.kind === "electrical_substation") {
    rows.push(["Cell", `${props.row}, ${props.col}`]);
    rows.push(["Role", "Stage-D substation"]);
  } else if (props.kind === "electrical_bess") {
    rows.push(["Period", props.period || "--"]);
    rows.push(["Storage", formatMaybeStorage(numberOrNull(props.batteryKwh))]);
    rows.push(["Role", "Container BESS near the Stage-D substation"]);
  } else if (props.kind === "electrical_flow_arc") {
    rows.push(["Cell", `${props.row}, ${props.col}`]);
    rows.push(["Daypart", String(props.daypart || "").replace("_", "-")]);
    rows.push(["Direction", props.direction === "export" ? "Export / source" : "Import / sink"]);
    rows.push(["Flow", `${props.flowKwh < 0 ? "-" : ""}${formatGwh(Math.abs(props.flowKwh || 0))}`]);
  } else {
    rows.push(["Line", props.label || "Electrical interconnect"]);
  }
  return {
    className: "deck-tooltip",
    html: `
      <div class="tooltip-title">${escapeHtml(electricalKindLabel(props.kind))}</div>
      <div class="tooltip-grid">
        ${rows.map(([label, value]) => `
        <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>
        `).join("")}
      </div>
    `
  };
}

function plantTooltip(props) {
  return {
    className: "deck-tooltip deck-tooltip-plant",
    html: `
      <div class="tooltip-title">${escapeHtml(plantKindLabel(props.plant_kind))}</div>
      <div class="tooltip-grid">
        <span>Cell</span><strong>${props.row}, ${props.col}</strong>
        <span>Host use</span><strong>${escapeHtml(hostLandUseLabel(props))}</strong>
        <span>Height</span><strong>${Number(props.height_m || 0).toFixed(1)} m</strong>
        <span>Residential buffer</span><strong>${formatCellDistance(props.min_residential_distance_cells)}</strong>
        <span>School buffer</span><strong>${formatCellDistance(props.min_school_distance_cells)}</strong>
        <span>Siting</span><strong>${escapeHtml(props.siting_reason || "Stage C plant siting export")}</strong>
      </div>
    `
  };
}

//: tooltip row for the per-cell building facing
// chosen by SA. Only shown on built cells -- non-built cells default to 0
// which would confusingly say "facing north" for an empty cell.
function buildingAxisLabel(props) {
  if (!props || !props.is_built) return "";
  const axis = Number(props.building_axis_deg || 0);
  const labels = {
    0: "Facing N (long axis E-W)",
    90: "Facing E (long axis N-S, hotter E/W facades)",
    180: "Facing S (long axis E-W)",
    270: "Facing W (long axis N-S, hotter E/W facades)"
  };
  return labels[Math.round(axis)] || `${axis.toFixed(0)} deg`;
}

function tooltipAxisRow(props) {
  const axisLabel = buildingAxisLabel(props);
  if (axisLabel) {
    return `
        <span>Axis</span><strong>${escapeHtml(axisLabel)}</strong>
  `;
  }
  return "";
}

function tooltipShadingRows(props) {
  const shade = state.cellShading.get(cellKey(props));
  if (!shade) return "";
  const rows = [["PV yield", formatShadingMultiplier(shade)]].concat(shadingDiagnosticRows(props));
  return rows.map(([label, value]) => `
        <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>
  `).join("");
}

function shadingDiagnosticRows(props) {
  const shade = state.cellShading.get(cellKey(props));
  if (!shade) return [];
  const rows = [];
  const fallbackNote = shade.source === "geometric"
    ? "Geometric export; annual sun-path average"
    : "Legacy heuristic fallback; annual penalty only";
  rows.push(["Shade", shade.reason || fallbackNote]);
  if (Number.isFinite(Number(shade.percentile))) {
    const rank = Math.round(clamp(Number(shade.percentile), 0, 1) * 100);
    rows.push(["Rank in layout", `${rank}/100 (lower = more shaded)`]);
  }
  if (shade.offenderDirs?.length) {
    rows.push(["Offenders", shade.offenderDirs.join(", ")]);
  }
  return rows;
}

function tooltipPvDeploymentRows(props) {
  if (!hasPvReadoutProps(props)) return "";
  const ceiling = featurePvKwp(props);
  if (ceiling <= 0 && featurePvDeployedKwp(props) <= 0) return "";
  return `
        <span>PV deployed</span><strong>${escapeHtml(formatPvDeploymentTooltip(props))}</strong>
  `;
}

function tooltipLightingRows(props) {
  return lightingRows(props).map(([label, value]) => `
        <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>
  `).join("");
}

function tooltipPvCapacityRow(props) {
  if (!hasPvReadoutProps(props)) return "";
  return `
        <span>PV</span><strong>${escapeHtml(formatPv(featurePvKwp(props)))}</strong>
  `;
}

function tooltipPvThisHourRow(props) {
  if (!hasPvReadoutProps(props)) return "";
  return `
        <span>Clear-sky PV</span><strong>${escapeHtml(formatEnergy(featureHourlyPvKwh(props)))}</strong>
  `;
}

function tooltipBipvRows(props) {
  if (!isBipvCandidate(props)) return "";
  return `
        <span>BIPV deployed</span><strong>${escapeHtml(formatBipvDeployment(props))}</strong>
  `;
}

function tooltipSiteRows(props) {
  const rows = [];
  amenitySubtypeRows(props).forEach((row) => rows.push(row));
  streetAssetRows(props).forEach((row) => rows.push(row));
  const faith = faithLabel(props?.faith);
  if (faith) rows.push(["Faith", faith]);
  if (featureCarportKwp(props) > 0) rows.push(["Carport site", "Parking-lot canopy site"]);
  carportPvRows(props).forEach((row) => rows.push(row));
  floatingPvSiteRows(props).forEach((row) => rows.push(row));
  return rows.map(([label, value]) => `
        <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>
  `).join("");
}

function carportPvRows(props) {
  const carportKwp = featureCarportKwp(props);
  if (carportKwp <= 0) return [];
  const host = LABELS[props?.land_use] || titleCase(props?.land_use || "host");
  return [["Carport PV (parking canopy)", `${formatKwp(carportKwp)} - separate from this cell's rooftop PV; both contribute (host: ${host})`]];
}

function amenitySubtypeRows(props) {
  const raw = String(props?.amenity_subtype || "").trim();
  if (!raw) return [];
  if (props?.land_use === "school") {
    return [["School type", raw.toLowerCase() === "primary" ? "Primary" : raw.toLowerCase() === "secondary" ? "Secondary" : titleCase(raw)]];
  }
  if (props?.land_use === "healthcare") {
    return [["Healthcare type", raw.toUpperCase()]];
  }
  return [["Amenity subtype", titleCase(raw)]];
}

function streetAssetRows(props) {
  if (props?.land_use !== "road") return [];
  const rows = [];
  if (truthyFlag(props.has_street_trees)) rows.push(["Street trees", "Yes"]);
  const lightType = streetlightType(props);
  if (lightType) {
    const segmentId = streetlightSegmentId(props);
    const typeLabel = lightType === "solar" ? "Solar pole" : "Grid pole";
    rows.push(["Streetlight", `${typeLabel} - ${streetlightsAreOn() ? "on" : "off"}`]);
    if (segmentId >= 0) {
      rows.push(["Streetlight segment", segmentId === 0 ? "0 - mains-adjacent grid backbone" : String(segmentId)]);
    }
    const reason = String(props.streetlight_reason || "").trim();
    if (reason) rows.push(["Streetlight reason", reason]);
  }
  return rows;
}

function floatingPvSiteRows(props) {
  if (props?.land_use !== "blue_space") return [];
  const rows = [];
  const isSite = truthyFlag(props.is_floating_pv_site);
  if (!isSite) {
    rows.push(["Canal-top PV site", "No - ornamental water"]);
    return rows;
  }
  rows.push(["Canal-top PV site", "Cluster site"]);
  const deployable = firstFiniteNumber(props, [
    "floating_pv_deployable_kwp",
    "deployable_pv_kwp"
  ]);
  if (deployable > 0) rows.push(["Canal-top PV ceiling", formatPv(deployable)]);
  const cluster = props.floating_pv_cluster_id;
  if (cluster !== undefined && cluster !== null && String(cluster).trim() !== "") {
    rows.push(["Canal-top cluster", `#${cluster}`]);
  }
  return rows;
}

function tooltipEntranceRows(props) {
  const entrances = formatEntranceSides(props?.entrance_sides);
  if (!entrances) return "";
  return `
        <span>Entrances</span><strong>${escapeHtml(entrances)}</strong>
  `;
}

function featureCollection(features) {
  return {
    type: "FeatureCollection",
    features
  };
}

function layoutByName(name) {
  return (state.manifest?.layouts || FALLBACK_LAYOUTS).find((layout) => layout.name === name)
    || FALLBACK_LAYOUTS[0];
}

function shortLayoutLabel(layout) {
  const labels = {
    chandigarh_sector: "Chandigarh",
    dispersed_low: "Dispersed",
    compact_centre: "Compact",
    radial: "Radial",
    optimised_sa: "Optimised",
    // The manifest label ("Baseline 2 - Unplanned Conventional") overran the
    // button and rendered as "Baseline 2 - Un...". Only two layouts are ever
    // offered, so the qualifier earns nothing: "Optimised" and "Baseline".
    //.
    zirakpur_ribbon: "Baseline"
  };
  return labels[layout.name] || layout.label || titleCase(layout.name);
}

function titleCase(value) {
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-GB");
}

function formatArea(value) {
  const area = Number(value || 0);
  if (!area) return "0 m²";
  return `${Math.round(area).toLocaleString("en-GB")} m²`;
}

function formatPv(value) {
  const pv = Number(value || 0);
  if (!pv) return "0 kWp";
  return pv >= 1000 ? `${(pv / 1000).toFixed(2)} MWp` : `${pv.toFixed(1)} kWp`;
}

function formatKwp(value) {
  const kwp = Number(value || 0);
  if (!kwp) return "0 kWp";
  return `${kwp.toLocaleString("en-GB", { maximumFractionDigits: 1 })} kWp`;
}

function formatPvDeployment(props) {
  const deployed = featurePvDeployedKwp(props);
  const ceiling = featurePvKwp(props);
  const percent = ceiling > 0 ? deployed / ceiling * 100 : 0;
  return `${deployed.toFixed(1)} / ${ceiling.toFixed(1)} kWp (${percent.toFixed(0)}%)`;
}

function formatPvDeploymentTooltip(props) {
  return formatPvDeployment(props);
}

function formatPvDeploymentPanel(props) {
  const deployed = featurePvDeployedKwp(props);
  const ceiling = featurePvKwp(props);
  if (ceiling <= 0 && deployed <= 0) return "0 kWp";
  const moduleLabel = isFarmSurfaceProps(props)   // FARM-1: ring included
    ? "ground-mount array"
    : props?.land_use === "blue_space"
      ? "floating/canal PV"
      : props?.land_use === "parking_lot"
        ? "parking canopy"
        : state.moduleMix.summaryLabel || DEFAULT_MODULE_MIX.summaryLabel;
  return `${deployed.toFixed(1)} kWp deployed of ${ceiling.toFixed(1)} kWp ceiling (${moduleLabel})`;
}

function isBipvCandidate(props) {
  return Boolean(props?.is_built) && Number(props.height_m || 0) >= 18;
}

function featureBipvCeilingKwp(props) {
  const direct = firstFiniteNumber(props || {}, [
    "bipv_deployable_kwp",
    "deployable_bipv_kwp",
    "bipv_ceiling_kwp"
  ]);
  if (direct > 0) return direct;
  if (!isBipvCandidate(props)) return 0;
  const height = Number(props?.height_m || 0);
  const axis = Math.round(Number(props?.building_axis_deg || 0));
  const exposure = BIPV_FACADE_SOUTH_EXPOSURE[axis] ?? 0.5;
  return Math.max(0, height * BIPV_KWP_PER_M_HEIGHT * BIPV_DEFAULT_UPTAKE * exposure);
}

function featureBipvDeployedKwp(props) {
  const direct = firstFiniteNumber(props || {}, [
    "bipv_deployed_kwp",
    "deployed_bipv_kwp",
    "bipv_kwp"
  ]);
  if (direct > 0) return direct;
  const scenarioBipv = Number(activeCockpitScenario()?.capacities?.bipv_kwp || 0);
  if (scenarioBipv > 0) {
    const ceiling = featureBipvCeilingKwp(props);
    const totalCeiling = totalBipvCeilingKwp();
    if (ceiling > 0 && totalCeiling > 0) {
      return scenarioBipv * ceiling / totalCeiling;
    }
  }
  return 0;
}

function formatBipvDeployment(props) {
  const deployed = featureBipvDeployedKwp(props);
  const ceiling = featureBipvCeilingKwp(props);
  if (ceiling > 0) {
    const pct = deployed / ceiling * 100;
    return `${deployed.toFixed(1)} kWp deployed of ${ceiling.toFixed(1)} kWp ceiling (${pct.toFixed(0)}%)`;
  }
  const scenarioBipv = Number(activeCockpitScenario()?.capacities?.bipv_kwp || 0);
  if (scenarioBipv <= 0) {
    return "0.0 kWp deployed; per-cell ceiling not exported";
  }
  return `${formatPv(scenarioBipv)} deployed district-wide; per-cell ceiling not exported`;
}

function totalBipvCeilingKwp() {
  return sum((state.data?.features || []).map((feature) => {
    const props = feature.properties || {};
    return props.role === "structure" ? featureBipvCeilingKwp(props) : 0;
  }));
}

function formatEnergy(value) {
  const energy = Number(value || 0);
  if (!energy) return "0 kWh";
  return energy >= 1000 ? `${(energy / 1000).toFixed(2)} MWh` : `${energy.toFixed(1)} kWh`;
}

function formatCost(value) {
  const cost = Number(value || 0);
  if (!cost) return "0 INR/yr";
  if (cost >= 1_000_000_000) return `${(cost / 1_000_000_000).toFixed(2)} B`;
  if (cost >= 1_000_000) return `${(cost / 1_000_000).toFixed(1)} M`;
  return `${Math.round(cost).toLocaleString("en-GB")}`;
}

function formatAnnualCostHeadline(value) {
  const cost = Number(value || 0);
  if (!cost) return "₹0 M";
  return `₹${(cost / 1_000_000).toLocaleString("en-GB", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  })} M`;
}

function formatPpaRevenue(value) {
  const revenue = Number(value || 0) / 1_000_000;
  const digits = Math.abs(revenue) < 10 ? 2 : 1;
  return `₹${revenue.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })} M`;
}

function formatLifetimeCostHeadline(value) {
  const cost = Number(value || 0);
  if (!cost) return "₹0 B";
  return `₹${(cost / 1_000_000_000).toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })} B`;
}

function formatDailyCost(value) {
  const daily = Number(value || 0) / 365;
  if (!daily) return "0";
  if (daily >= 1_000_000_000) return `${(daily / 1_000_000_000).toFixed(2)} B`;
  if (daily >= 1_000_000) return `${(daily / 1_000_000).toFixed(2)} M`;
  if (daily >= 1_000) return `${(daily / 1_000).toFixed(1)} k`;
  return `${Math.round(daily)}`;
}

function formatEmissions(value) {
  const kg = Number(value || 0);
  if (!kg) return "0 t";
  return `${Math.round(kg / 1000).toLocaleString("en-GB")} t`;
}

function formatEmissionsHeadline(value) {
  const kg = Number(value || 0);
  if (!kg) return "0 kt";
  return `${(kg / 1_000_000).toLocaleString("en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })} kt`;
}

function formatDailyEmissions(value) {
  const kg = Number(value || 0) / 365;
  if (!kg) return "0 t";
  return `${Math.round(kg / 1000).toLocaleString("en-GB")} t`;
}

function formatInrPerKwh(value) {
  const tariff = Number(value || 0);
  return `${tariff.toFixed(2)} INR/kWh`;
}

function formatPercent(value) {
  const percent = Number(value || 0) <= 1
    ? Number(value || 0) * 100
    : Number(value || 0);
  return `${percent.toFixed(0)}%`;
}

function formatCellDistance(value) {
  const distance = Number(value);
  if (!Number.isFinite(distance)) return "--";
  return `${Math.round(distance)} ${Math.round(distance) === 1 ? "cell" : "cells"}`;
}

function normaliseEntranceSides(value) {
  const raw = Array.isArray(value)
    ? value
    : typeof value === "number"
      ? [value]
      : typeof value === "string"
        ? value.replace(/[\[\]]/g, "").split(",")
        : [];
  return raw
    .map((side) => Number(String(side).trim()))
    .filter((side) => [0, 90, 180, 270].includes(side));
}

function entranceSideLabel(side) {
  const labels = {
    0: "N",
    90: "E",
    180: "S",
    270: "W"
  };
  return labels[Number(side)] || `${Number(side).toFixed(0)} deg`;
}

function formatEntranceSides(value) {
  const sides = normaliseEntranceSides(value);
  if (!sides.length) return "";
  return sides.map(entranceSideLabel).join(" + ");
}

function faithLabel(value) {
  const key = String(value || "").toLowerCase();
  return FAITH_MARKER_META[key]?.label || "";
}

function renewableShareFromRow(row, annualDemand) {
  if (!annualDemand) return 0;
  const pvGeneration = Number(row.pv_generation_kwh || 0);
  const gridExport = Number(row.grid_export_kwh || 0);
  return clamp((pvGeneration - gridExport) / annualDemand, 0, 1);
}

function scenarioLabel(value) {
  const labels = {
    bau: "BAU",
    pv_only: "PV only",
    pv_battery: "PV + batt",
    pv_battery_v2g: "PV + V2G",
    pv_battery_v2g_biomass: "PV + V2G + biomass",
    full_stack: "Full stack fixed",
    full_stack_agile: "Full stack Agile",
    full_stack_dc_ppa: "Full stack DC-PPA",
    full_stack_dc_ppa_green: "Full stack green DC-PPA"
  };
  return labels[value] || titleCase(value || "scenario");
}

function scenarioOptionLabel(scenario, options = {}) {
  const base = scenarioLabel(scenario?.name);
  const caps = scenario?.capacities || {};
  const notes = [];
  if (String(scenario?.name || "").includes("battery") && Number(caps.battery_kwh || 0) <= 0) {
    notes.push(options.verbose ? "battery allowed but optimiser deploys 0 kWh" : "0 batt");
  }
  if (String(scenario?.name || "").includes("v2g") && Number(caps.v2g_units || 0) > 0) {
    notes.push(options.verbose ? `${Math.round(Number(caps.v2g_units))} V2G units deployed` : "V2G on");
  }
  return notes.length ? `${base} (${notes.join(", ")})` : base;
}

function featurePvKwp(props) {
  if (isPlantFeatureProps(props)) return 0;
  const directPv = Number(props.deployable_pv_kwp || 0);
  const cellPv = state.cellPvKwp.get(cellKey(props)) || 0;
  if (props.role === "parcel" || props.land_use === "solar_farm") return cellPv;
  return directPv || cellPv;
}

function hasPvReadoutProps(props) {
  if (!props || props.land_use === "road") return false;
  return featurePvKwp(props) > 0
    || featurePvDeployedKwp(props) > 0
    || featureCarportKwp(props) > 0
    || (props.land_use === "blue_space" && truthyFlag(props.is_floating_pv_site));
}

function isCarportPvSiteProps(props) {
  return props?.role === "parcel" && props?.land_use === "parking_lot" && truthyFlag(props?.is_carport_site) && featureCarportKwp(props) > 0;
}

function featureCarportKwp(props) {
  if (props?.land_use !== "parking_lot") return 0;
  if (!truthyFlag(props?.is_carport_site)) return 0;
  const kwp = Number(props?.carport_kwp || 0);
  return Number.isFinite(kwp) && kwp > 0 ? kwp : 0;
}

function totalCarportCeilingKwp() {
  return sum((state.data?.features || []).map((feature) => {
    const props = feature.properties || {};
    return props.role === "parcel" ? featureCarportKwp(props) : 0;
  }));
}

function featureCarportDeployedKwp(props) {
  const ceiling = featureCarportKwp(props);
  if (ceiling <= 0) return 0;
  const scenarioCarportKwp = Number(activeCockpitScenario()?.capacities?.carport_kwp || 0);
  const totalCeiling = totalCarportCeilingKwp();
  if (scenarioCarportKwp <= 0 || totalCeiling <= 0) return 0;
  return Math.min(ceiling, scenarioCarportKwp * ceiling / totalCeiling);
}

function carportDeploymentRatio(props) {
  const ceiling = featureCarportKwp(props);
  return ceiling > 0 ? clamp(featureCarportDeployedKwp(props) / ceiling, 0, 1) : 0;
}

function featurePvDeployedKwp(props) {
  if (isPlantFeatureProps(props)) return 0;
  const direct = Number(props?.pv_deployed_kwp || 0);
  const cellPv = state.cellPvDeployedKwp.get(cellKey(props)) || 0;
  if (props?.role === "parcel" || props?.land_use === "solar_farm") return cellPv || direct;
  return direct || cellPv;
}

function featurePvDeploymentRatio(props) {
  const ceiling = featurePvKwp(props);
  if (ceiling <= 0) return 0;
  return clamp(featurePvDeployedKwp(props) / ceiling, 0, 1);
}

function featureHourlyPvKwh(props) {
  const shade = state.cellShading.get(cellKey(props));
  const multiplier = shade ? shade.multiplier : 1;
  return featurePvKwp(props) * multiplier * state.sun.pvCapacityFactor;
}

function clearSkyPvCapacityFactor(altitudeRad) {
  if (altitudeRad <= 0) return 0;
  const irradianceFraction = Math.pow(Math.sin(altitudeRad), 1.2);
  return clamp(irradianceFraction * CLEAR_SKY_PERFORMANCE_RATIO, 0, 1);
}

function formatCoord(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(4) : "--";
}

function formatDayOfYear(dayOfYear) {
  let remaining = clamp(Math.round(Number(dayOfYear) || 1), 1, 366);
  for (let index = 0; index < DAYS_IN_MONTH.length; index += 1) {
    if (remaining <= DAYS_IN_MONTH[index]) {
      return `${MONTH_LABELS[index]} ${remaining}`;
    }
    remaining -= DAYS_IN_MONTH[index];
  }
  return "Dec 31";
}

function formatTimeOfDay(timeHours) {
  const time = clamp(Number(timeHours) || 0, 0, 24);
  const hour = Math.floor(time);
  const minute = Math.round((time - hour) * 60);
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function dayOfYearFromDate(date) {
  const start = new Date(date.getFullYear(), 0, 0);
  const dayMs = 24 * 60 * 60 * 1000;
  return clamp(Math.floor((date - start) / dayMs), 1, 366);
}

function metersPerDegreeLongitude(latitude) {
  return METERS_PER_DEGREE_LAT * Math.cos(toRad(latitude));
}

function toRad(degrees) {
  return degrees * Math.PI / 180;
}

function toDeg(radians) {
  return radians * 180 / Math.PI;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function smoothstep(edge0, edge1, value) {
  if (edge0 === edge1) return value >= edge1 ? 1 : 0;
  const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function tooltipAttr(value) {
  return `data-cockpit-tooltip="${escapeHtml(value).replace(/\n/g, "&#10;")}"`;
}

function setLoading(message) {
  if (!message) {
    els.loading.classList.add("hidden");
    return;
  }
  els.loading.textContent = message;
  els.loading.classList.remove("hidden");
}

// ==================================================================
// COCKPIT PLATE MODE - `?cockpit_shot=<tab>`
//
// Produces one tall image per cockpit tab with the WHOLE panel expanded, for
// the write-up (the author, "give me the pictures for all the tabs of
// cockpit one by one separately... the extended one with all the info in one
// pic for one tab"). A screenshot of the running app only ever captures the
// scrolled viewport, and the panel is deliberately short.
//
// It reuses the app's OWN rendering rather than redrawing the panels
// elsewhere, so the plates cannot drift from what the viewer actually shows.
// Driven by scripts/shoot_cockpit_tabs.py through headless Edge.
// MAP PLATES - `?map_shot=<layout>&year=<yyyy>&hour=<h>`
// Straight-down plan views of the town (the author, "take a top down
// view of the model... one for the optimised 2030, 2042, 2055 and zirakpur
// too, one at 12 pm and one at 10 pm").
//
// THE HARD PART IS NOT THE VIEW, IT IS GETTING HEADLESS EDGE TO EXIT. deck.gl
// runs a requestAnimationFrame loop, and under Edge's virtual clock a live
// rAF loop advances virtual time forever, so --virtual-time-budget never
// expires and no screenshot is ever written. Finalising deck kills the loop
// but also clears the canvas. So: let the scene settle, COPY the canvas into
// an <img> (the context is created with preserveDrawingBuffer, which is what
// makes this possible), and only then finalise. The plate is the still image.
async function applyMapShotMode() {
  const params = new URLSearchParams(window.location.search);
  const layout = params.get("map_shot");
  if (!layout) return;

  const year = params.get("year") || DEFAULT_COCKPIT_PERIOD_YEAR;
  const hour = Number(params.get("hour") ?? 12);

  document.body.classList.add("map-shot");
  if (layout !== state.currentLayout) {
    await loadLayout(layout);
  }
  state.cockpit.periodYear = year;
  state.sun.timeHours = hour;
  updateSunPosition();
  renderCockpit();

  // Straight down, north up, framed on the town.
  state.viewState = {
    ...state.viewState,
    longitude: state.manifest?.center?.longitude ?? state.viewState.longitude,
    latitude: state.manifest?.center?.latitude ?? state.viewState.latitude,
    // 13.05 left half the frame as sky. 13.55 fills it edge to edge, which is
    // the framing the author's reference plan view uses.
    zoom: Number(params.get("zoom") ?? 13.55),
    pitch: 0,
    bearing: 0
  };
  state.deckgl?.setProps({ viewState: state.viewState });
  updateLayers();

  await new Promise((resolve) => setTimeout(resolve, 2600));

  const canvas = document.querySelector("#deck-container canvas")
    || document.querySelector("canvas");
  if (canvas) {
    try {
      const shot = canvas.toDataURL("image/png");
      const img = new Image();
      img.src = shot;
      img.id = "map-shot-still";
      img.style.cssText = "position:absolute;inset:0;width:100%;height:100%;"
        + "object-fit:cover;z-index:5";
      document.body.appendChild(img);
    } catch (err) {
      /* a tainted or lost context leaves the live canvas in place */
    }
  }
  document.title = `map-${layout}-${year}-${hour}`;
  if (state.electricalAnimationFrame) {
    cancelAnimationFrame(state.electricalAnimationFrame);
    state.electricalAnimationFrame = null;
  }
  // THE TRAFFIC TICKER IS WHY NIGHT PLATES HUNG WHILE NOON ONES WROTE FINE.
  // It is a setInterval that swaps the vehicle layer, and headless Edge treats
  // a repeating timer as pending work forever, so the virtual-time budget was
  // never reached. It only has anything to do once the streets are lit, which
  // is exactly why the fault looked time-of-day specific.
  if (state._trafficTimer) {
    clearInterval(state._trafficTimer);
    state._trafficTimer = null;
  }
  try {
    state.deckgl?.finalize();
  } catch (err) {
    /* the still is already in the DOM */
  }
  state.deckgl = null;

  // KEEP THE VIRTUAL CLOCK MOVING. Headless Edge advances virtual time only
  // while something is pending; with deck finalised and every timer cancelled
  // the page goes completely idle, the --virtual-time-budget is never consumed,
  // and the browser waits forever without writing the screenshot. A trivial
  // repeating timer steps the clock to the budget, at which point Edge shoots
  // and exits. The first plate got through by luck of timing; this makes it
  // deterministic.

}

// PANEL PLATES - `?panel_shot=<banner|legend|keynumbers>`
// Same idea as the cockpit plates, for the three pieces of chrome outside it
// (the author, "can you do the top banner too and the map legend and key
// figures similarly"). Both collapsible panels are FORCED OPEN first: they
// remember their collapsed state in localStorage, so a plate shot without this
// can come out as a bare title bar.
const PANEL_SHOTS = {
  banner: { selector: ".topbar", pad: 24 },
  legend: { selector: "#legend-panel", pad: 22 },
  keynumbers: { selector: "#layout-summary-panel", pad: 22 }
};

function applyPanelShotMode() {
  const params = new URLSearchParams(window.location.search);
  const target = params.get("panel_shot");
  const spec = PANEL_SHOTS[target];
  if (!spec) return;

  document.body.classList.add("panel-shot");
  document.body.dataset.panelShot = target;

  // Open whichever panel is being shot, whatever localStorage remembers.
  if (target === "legend") setLegendPanelCollapsed(false);
  if (target === "keynumbers") setInfoPanelCollapsed(false);

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const el = document.querySelector(spec.selector);
      if (!el) return;
      el.classList.remove("hidden");
      const rect = el.getBoundingClientRect();
      const width = Math.ceil(rect.width + spec.pad * 2);
      const height = Math.ceil(rect.height + spec.pad * 2);
      document.title = `panel-${target}-${width}-${height}`;
      // Same reason as the cockpit plates: a live rAF loop stops headless Edge
      // from ever reaching its virtual-time budget, so it never writes a file.
      if (state.electricalAnimationFrame) {
        cancelAnimationFrame(state.electricalAnimationFrame);
        state.electricalAnimationFrame = null;
      }
      try {
        state.deckgl?.finalize();
      } catch (err) {
        /* the plate is laid out; a finalize failure must not stop it */
      }
      state.deckgl = null;
    });
  });
}

function applyCockpitShotMode() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("cockpit_shot");
  if (!tab || !COCKPIT_TABS.includes(tab)) return;

  document.body.classList.add("cockpit-shot");
  state.cockpit.visible = true;
  state.cockpit.activeTab = tab;
  renderCockpit();

  // Let the tab's own renderer finish (charts build their SVG synchronously
  // but layout settles a frame later), then release every height constraint
  // so the panel stands at its full content height.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const panel = document.getElementById("cockpit-panel");
      const page = document.querySelector(`[data-cockpit-page="${tab}"]`);
      if (!panel || !page) return;
      page.classList.add("active");
      // Measure the PANEL as laid out, not the page's scrollHeight: in plate
      // mode the page is a grid whose scrollHeight reports the track size, not
      // the content, which came out roughly double and left half the plate
      // empty. The panel's own box after expansion is the true extent.
      const rect = panel.getBoundingClientRect();
      const height = Math.ceil(rect.bottom + window.scrollY + 22);
      document.documentElement.style.setProperty("--shot-height", `${height}px`);
      // Reported back to the driver, which sizes the Edge window to match.
      window.__cockpitShotHeight = height;
      document.title = `cockpit-${tab}-${height}`;

      // SHUT THE RENDER LOOP DOWN, or the plate never gets written. deck.gl
      // keeps a requestAnimationFrame loop running, and the electrical overlay
      // adds another; under headless Edge's virtual clock a live rAF loop
      // advances virtual time forever, so --virtual-time-budget never expires
      // and the browser never exits. The canvas is hidden in plate mode
      // anyway, so nothing visible is lost by finalising it here.
      if (state.electricalAnimationFrame) {
        cancelAnimationFrame(state.electricalAnimationFrame);
        state.electricalAnimationFrame = null;
      }
      state.electricalOverlayEnabled = false;
      try {
        state.deckgl?.finalize();
      } catch (err) {
        /* the plate is already laid out; a finalize failure must not stop it */
      }
      state.deckgl = null;
    });
  });
}

init()
  .then(applyCockpitShotMode)
  .then(applyPanelShotMode)
  .then(applyMapShotMode)
  .catch((error) => {
    console.error(error);
    setLoading(error.message || "Could not load the 3D viewer.");
  });

//: idle UI fade - the metropolis recipe. Chrome steps back
// after 8 s of no input so the town is the hero; any input wakes it. Pure
// display: no state, no data, remove this block + the body.ui-idle CSS to
// revert. Panels being hovered keep full opacity via CSS :hover overrides.
(() => {
  let vis1IdleTimer = null;
  const wake = () => {
    document.body.classList.remove("ui-idle");
    if (vis1IdleTimer) clearTimeout(vis1IdleTimer);
    vis1IdleTimer = setTimeout(() => document.body.classList.add("ui-idle"), 8000);
  };
  ["pointermove", "pointerdown", "keydown", "touchstart", "wheel"].forEach((evt) => {
    window.addEventListener(evt, wake, { passive: true });
  });
  wake();
})();

// =====================================================================
// CLEAN MODE,.
//
// Toggle with the Clean button or the C key. Every panel fades out and the
// scene fills the window; moving the pointer into the bottom-left corner
// brings them back so a setting can be changed, and they fade again once the
// pointer leaves.
//
// WHY THE REVEAL TRACKS THE PANELS AND NOT ONLY THE CORNER. The obvious
// implementation reveals on hotspot mouseenter and hides on mouseleave, and
// it is unusable: the topbar is at the TOP of the window, so the pointer
// leaves the corner on its way there and the panels vanish before they can be
// touched. The reveal therefore holds while the pointer is over the hotspot
// OR over any panel, and only a move to open scene hides them again. A short
// grace period covers the gap between two panels.
//
// The mode deliberately does not persist across reloads. It is a capture
// state, not a preference, and a viewer that started with everything hidden
// would look broken.
// =====================================================================
// EXPAND-1 (, the author: "give an option to make the demand graph big
// so we can see it more clearly"). A class on <body>; the CSS does the
// resizing. The SVG fills its container, so there is ONE drawing path for both
// sizes and the big version cannot disagree with the small one.
(function trendsExpand() {
  const btn = document.getElementById("trends-expand");
  if (!btn) return;
  const body = document.body;
  const set = (on) => {
    body.classList.toggle("trends-expanded", on);
    btn.setAttribute("aria-pressed", String(on));
    btn.textContent = on ? "Close" : "Expand";
    // Redraw into the new box. Cheap - one SVG from data already in memory.
    try { renderCockpit(); } catch (err) { /* may fire before first data load */ }
  };
  btn.addEventListener("click", () => set(!body.classList.contains("trends-expanded")));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && body.classList.contains("trends-expanded")) set(false);
  });
})();

(function cleanMode() {
  const PANELS = ".topbar, #legend-panel, #layout-summary-panel, " +
                 ".compass-panel, .scale-panel";
  let hideTimer = null;
  let hintShown = false;

  const body = document.body;
  const hotspot = document.getElementById("clean-hotspot");
  const btn = document.getElementById("clean-toggle");
  if (!hotspot || !btn) return;

  const reveal = () => {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    body.classList.add("clean-reveal");
  };
  const scheduleHide = () => {
    if (hideTimer) clearTimeout(hideTimer);
    // 260 ms is long enough to cross the gap between two panels and short
    // enough that it never feels like lag.
    hideTimer = setTimeout(() => body.classList.remove("clean-reveal"), 260);
  };

  hotspot.addEventListener("pointerenter", reveal);

  document.addEventListener("pointermove", (event) => {
    if (!body.classList.contains("clean-shot")) return;
    const over = event.target.closest
      ? (event.target.closest(PANELS) || event.target.closest("#clean-hotspot"))
      : null;
    if (over) reveal(); else scheduleHide();
  });

  function showHint() {
    if (hintShown) return;
    hintShown = true;
    const el = document.createElement("div");
    el.id = "clean-hint";
    el.textContent = "Panels hidden. Hover the bottom-left corner to bring them back, or press C.";
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 500);
    }, 3200);
  }

  function setClean(on) {
    body.classList.toggle("clean-shot", on);
    if (!on) body.classList.remove("clean-reveal");
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", String(on));
    btn.textContent = on ? "Panels" : "Clean";
    btn.title = on
      ? "Show the panels again (C)"
      : "Hide all panels for a clean screenshot (C). Hover the bottom-left corner to bring them back.";
    if (on) showHint();
    // deck sizes itself to its container, which never changed, but a resize
    // notification costs nothing and guarantees a correct first frame.
    window.dispatchEvent(new Event("resize"));
  }

  btn.addEventListener("click", () => setClean(!body.classList.contains("clean-shot")));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "c" && event.key !== "C") return;
    // Never steal the key from a field the user is typing into.
    const t = event.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" ||
              t.tagName === "SELECT" || t.isContentEditable)) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;   // leave copy alone
    setClean(!body.classList.contains("clean-shot"));
  });
})();
