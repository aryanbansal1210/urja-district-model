/* ============================================================
   DISTRICT_v3 viewer - 3D SCENE APPEARANCE CODE (extract)
   ------------------------------------------------------------
   Extracted from viewer3d/app.js, which is 487 KB and has no test
   coverage. This file is NOT the application. It is the subset that
   decides how the scene looks, given to you so the whole file does not
   have to be. Original line numbers are preserved in each header.

   Renderer: deck.gl 9 (PolygonLayer, ColumnLayer, PathLayer,
   ScatterplotLayer, GeoJsonLayer, TextLayer, BitmapLayer, ArcLayer).
   No basemap: the district is drawn from its own GeoJSON over a CSS
   sky gradient. There is no terrain, no water surface and no vegetation
   geometry - trees and greenery are flat coloured cells today.

   KNOWN ISSUE, worth reading before proposing shadows: native deck.gl
   shadows are DISABLED (`_shadow: false` in createLightingEffect). They
   caused a draw-time white-out in the browser on 2026-06-10 and were
   turned off pending debugging. Shadows currently come from a legacy
   flat-ground shadow layer instead.
   ============================================================ */



/* ==================== LIGHTING - sun, ambient, fill, shadow colour ==================== */

/* --- createLightingEffect   (app.js lines 1244-1281) --- */
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

/* --- currentLightingEffects   (app.js lines 1283-1286) --- */
function currentLightingEffects() {
  const effect = createLightingEffect();
  return effect ? [effect] : [];
}

/* --- currentSunLightDirection   (app.js lines 1288-1299) --- */
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


/* ==================== SKY - background gradient driven by sun altitude ==================== */

/* --- skyColoursForAltitude   (app.js lines 3795-3806) --- */
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

/* --- applySkyForTime   (app.js lines 3807-3818) --- */
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

/* --- civilTwilightDarkFactor   (app.js lines 3833-3839) --- */
function civilTwilightDarkFactor(hour = state.sun.timeHours) {
  const altitude = solarAltitudeForHour(hour);
  if (!Number.isFinite(altitude)) return 0;
  if (altitude <= CIVIL_TWILIGHT_ALTITUDE_DEG) return 1;
  if (altitude >= 0) return 0;
  return 1 - smoothstep(CIVIL_TWILIGHT_ALTITUDE_DEG, 0, altitude);
}


/* ==================== BUILDING FORM - height scaling and glow ==================== */

/* --- scaledHeightM   (app.js lines 1236-1238) --- */
function scaledHeightM(heightM) {
  return Number(heightM || 0) * BUILDING_HEIGHT_SCALE;
}

/* --- scaledFeatureHeightM   (app.js lines 1240-1242) --- */
function scaledFeatureHeightM(props) {
  return scaledHeightM(props?.height_m ?? props?.cell_height_m ?? 0);
}

/* --- buildingGlowColor   (app.js lines 3243-3258) --- */
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


/* ==================== NIGHT LIGHTING - streetlights and windows ==================== */

/* --- lightingScheduleForProps   (app.js lines 3265-3270) --- */
function lightingScheduleForProps(props) {
  if (Array.isArray(props?.lighting_by_daypart) && props.lighting_by_daypart.length) {
    return props.lighting_by_daypart;
  }
  return state.cellLightingByDaypart.get(cellKey(props)) || [];
}

/* --- lightingIntensityForProps   (app.js lines 3272-3276) --- */
function lightingIntensityForProps(props, index = currentLightingDaypartIndex()) {
  const schedule = lightingScheduleForProps(props);
  if (!schedule.length) return 0;
  return clamp(Number(schedule[index]) || 0, 0, 1);
}

/* --- streetlightNightFactor   (app.js lines 3841-3843) --- */
function streetlightNightFactor(hour = state.sun.timeHours) {
  return civilTwilightDarkFactor(hour);
}

/* --- streetlightType   (app.js lines 3763-3766) --- */
function streetlightType(props) {
  const value = String(props?.streetlight_type || "").toLowerCase();
  return value === "solar" || value === "grid" ? value : "";
}

/* --- streetlightSegmentColour   (app.js lines 3773-3777) --- */
function streetlightSegmentColour(segmentId) {
  if (segmentId === 0) return [248, 250, 252];
  if (segmentId < 0) return [148, 163, 184];
  return STREETLIGHT_SEGMENT_COLOURS[(segmentId - 1) % STREETLIGHT_SEGMENT_COLOURS.length];
}


/* ==================== SURFACE COLOUR ==================== */

/* --- streetEdgeColour   (app.js lines 1670-1676) --- */
function streetEdgeColour(kind) {
  //: "dark dark green"
  if (kind === "greenway_path") return state.theme === "dark" ? [14, 74, 38, 246] : [8, 58, 28, 248];
  //: local lanes ~40% opaque - they are service
  // gallis, so they should read as a hint of paving, not as roads.
  return state.theme === "dark" ? [158, 162, 158, 102] : [126, 130, 126, 102];
}

/* --- roadBandColor   (app.js lines 2509-2523) --- */
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

/* --- electricalEdgeColor   (app.js lines 2974-2984) --- */
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

/* --- electricalArcColor   (app.js lines 2986-2991) --- */
function electricalArcColor(arc) {
  const pulse = electricalPulseMultiplier(arc);
  const base = arc.isImport ? ELECTRICAL_COLOURS.import : ELECTRICAL_COLOURS.export;
  const glow = arc.isImport ? [252, 165, 165] : [134, 239, 172];
  return withAlpha(mix(base, glow, pulse - 0.72), Math.round(100 + arc.magnitude * 90 + pulse * 45));
}