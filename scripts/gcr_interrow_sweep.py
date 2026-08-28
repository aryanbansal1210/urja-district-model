"""GCR sweep: inter-row self-shading loss vs ground-coverage ratio, derived
from the model's own sun-path machinery (Tier 3 on the same Tier 1 inputs the
building-shading table uses).

WHY (the author "solar farm, let's choose a spacing that we can
justify but also yields us good results"). The current density
(`ground_mount_kwp_per_m2: 0.0714`, GCR 0.34) sits at the very bottom of the
config's own cited fixed-tilt band (0.35-0.45 at 30.6 N) - maximally
conservative. The land is a FIXED 301-ha grant and the farm is land-bound in
every period, so annual farm energy scales with density x (1 - loss(GCR)):
the right spacing maximises that product, subject to staying inside the band
practice can justify. The model's farm yield chain carries NO inter-row term
(pv_yield_per_kwp_kwh_solar_farm: CF x shading x temperature x DC x soiling
x fog) because 0.34 was chosen to make it negligible - so densifying REQUIRES
this term to be derived and wired.

GEOMETRY (south-facing fixed-tilt rows, tilt beta, slant length L=1, pitch
P=L/GCR). For sun altitude a and azimuth az (0 = south), the profile angle
th satisfies tan th = tan a / cos az (sun behind the array plane -> no beam).
The front row's top edge shades the next collector from its bottom edge up to

    t = (H - tan th x G) / (sin beta + tan th x cos beta),  clamped to [0, L]

with H = sin beta (row height), D = cos beta (row depth), G = P - D (gap).
Limits check out: th -> 0 gives t -> H/sin beta = L (full shade); large G or
high sun gives t <= 0 (none).

LOSS MODEL. Each sun sample carries the SAME energy-proxy weight the
building-shading integration uses (slice hours x PV capacity factor,
sub-sampled - solar_geometry._sun_samples). Two figures per GCR:
  loss_geo  - shaded fraction weighted as-is (treats all irradiance as beam)
  loss_2x   - min(1, 2 x f): series-string electrical penalty, one shaded
              cell throttles its string; 2x area is the conservative rule
Both OVERSTATE the true loss because the weight includes diffuse irradiance,
which inter-row geometry barely touches - and Punjab winters are
fog/diffuse-heavy exactly when shading occurs. Conservative in the safe
direction: a density chosen under an overstated loss only looks better in
reality.

    PYTHONPATH=. python scripts/gcr_interrow_sweep.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from energy.costs import load_economics
from energy.solar_geometry import _sun_samples, sun_position

LAT, LON = 30.64, 76.82
TILT_DEG = 29.0          # pv_reference_tilt_deg - the plane the yield assumes
MODULE_EFF = 0.21        # the 21% modules the 0.0714 derivation assumes
LAND_HA = 301.0

BETA = math.radians(TILT_DEG)
H, D = math.sin(BETA), math.cos(BETA)


def shaded_fraction(alt: float, az: float, gcr: float) -> float:
    """Fraction of collector slant length shaded, [0, 1]."""
    if alt <= 0:
        return 0.0
    caz = math.cos(az)
    if caz <= 0.05:          # sun behind / parallel to the row axis: no beam
        return 0.0
    tan_th = math.tan(alt) / caz
    gap = 1.0 / gcr - D
    t = (H - tan_th * gap) / (H + tan_th * D)   # sin b + tan th cos b, L=1
    return min(1.0, max(0.0, t))


econ = load_economics(force_reload=True)
samples = _sun_samples(econ, LAT, LON)
wsum = sum(w for _, _, w in samples)
print("sun samples: %d, total energy weight %.1f" % (len(samples), wsum))

print("\nvalidation - winter solstice (doy 355) solar noon, profile angle:")
alt, az = sun_position(355, 12.0, LAT, LON)
print("  altitude %.1f deg, azimuth %.1f deg" %
      (math.degrees(alt), math.degrees(az)))
for gcr in (0.34, 0.40, 0.45, 0.55, 0.648):
    print("  GCR %.3f -> noon shaded fraction %.4f" %
          (gcr, shaded_fraction(alt, az, gcr)))

print("\n%6s %8s %9s %9s %10s %12s %12s %10s" %
      ("GCR", "P/L", "loss_geo", "loss_2x", "kWp/m2", "ceiling_kWp",
       "net_index", "vs 0.34"))
base_net = None
rows = []
for i in range(14):
    gcr = round(0.30 + 0.02 * i, 2)
    lg = sum(w * shaded_fraction(a, z, gcr) for a, z, w in samples) / wsum
    l2 = sum(w * min(1.0, 2.0 * shaded_fraction(a, z, gcr))
             for a, z, w in samples) / wsum
    dens = MODULE_EFF * gcr
    ceil_kwp = dens * LAND_HA * 10000.0
    net = ceil_kwp * (1.0 - l2)
    rows.append((gcr, lg, l2, dens, ceil_kwp, net))
if not any(abs(r[0] - 0.34) < 1e-9 for r in rows):
    pass
for gcr, lg, l2, dens, ceil_kwp, net in rows:
    if abs(gcr - 0.34) < 1e-9:
        base_net = net
for gcr, lg, l2, dens, ceil_kwp, net in rows:
    mark = "  <- current" if abs(gcr - 0.34) < 1e-9 else ""
    gain = (net / base_net - 1.0) * 100.0 if base_net else 0.0
    print("%6.2f %8.2f %8.3f%% %8.3f%% %10.4f %12.1f %12.1f %+9.1f%%%s" %
          (gcr, 1.0 / gcr, 100 * lg, 100 * l2, dens, ceil_kwp, net,
           gain, mark))

print("""
Reading the table: the land grant is fixed, so 'net_index' (ceiling x
(1 - loss_2x)) is what the town can actually harvest. Candidates:
  GCR 0.34  = 4.5 ac/MWac equiv - the current three-route number
  GCR 0.382 = 4.0 ac/MWac equiv - NREL Ong 2013 scaled to 21% modules
              (3.9 ac/MWac) and the bottom of the Indian 4-5 ac/MWac band
  GCR 0.40  = mid physics band - inside 0.35-0.45 but BELOW the Indian
              practice band (3.8 ac/MWac): weakest citation position
""")
for gcr in (0.382, 0.40):
    lg = sum(w * shaded_fraction(a, z, gcr) for a, z, w in samples) / wsum
    l2 = sum(w * min(1.0, 2.0 * shaded_fraction(a, z, gcr))
             for a, z, w in samples) / wsum
    dens = MODULE_EFF * gcr
    ceil_kwp = dens * LAND_HA * 10000.0
    net = ceil_kwp * (1.0 - l2)
    print("  GCR %.3f: loss_geo %.3f%%  loss_2x %.3f%%  density %.4f  "
          "ceiling %.1f kWp  net %+.1f%% vs 0.34"
          % (gcr, 100 * lg, 100 * l2, dens, ceil_kwp,
             (net / base_net - 1.0) * 100.0))
