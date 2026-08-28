"use strict";
/* Urja — resident energy app.
   Every figure comes from window.APP_DATA (data.js). No headline number is
   hardcoded: read field names, never values, so a regenerated snapshot
   flows straight through. */

const D = window.APP_DATA;
const MONTHS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];
const ML = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const MFULL = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DP = ["00_02","02_04","04_06","06_08","08_10","10_12","12_14","14_16","16_18","18_20","20_22","22_24"];
const DIM = [31,28,31,30,31,30,31,31,30,31,30,31];
const TIER = { residential_low:"Lower income (EWS/LIG)", residential_mid:"Middle income (MIG)", residential_high:"Higher income (HIG)" };
const TIER_SHORT = { residential_low:"EWS/LIG", residential_mid:"MIG", residential_high:"HIG" };
const INCOME = { residential_low:"low", residential_mid:"mid", residential_high:"high" };
const TIER_SWATCH = { residential_low:"#5B84B8", residential_mid:"#7C9A6E", residential_high:"#E8B54E" };
const BAND = { off_peak:"Off-peak", solar:"Solar hours", shoulder:"Shoulder", peak:"Peak", super_peak:"Super-peak" };
const BAND_COLOR = { off_peak:"var(--batt)", solar:"var(--solar)", shoulder:"var(--solar)", peak:"var(--warn)", super_peak:"var(--warn)" };
const LU_FILL = { 0:"#E8E4DC", 1:"#C9C246", 2:"#D6E1CC", 10:"#C2D6E4", 5:"#E3DACB", 7:"#E2DACE", 8:"#E2DACE",
  9:"#E2DACE", 11:"#E7E2D8", 12:"#E7E2D8", 13:"#E7E2D8", 14:"#E2DACE", 15:"#E2DACE", 16:"#E2DACE", 17:"#E2DACE", 18:"#E2DACE" };
const ICON = {
  home:"M11 2.5 2.5 9.5V19a1 1 0 0 0 1 1h15a1 1 0 0 0 1-1V9.5L11 2.5zM8.5 20v-6h5v6",
  energy:"M2.5 18.5 7 11l4 3.5 4-8.5 4.5 12.5",
  water:"M11 2.5s6 6.7 6 10.4A6 6 0 0 1 5 12.9C5 9.2 11 2.5 11 2.5z",
  trade:"M12 2.5 6 11.5h4.5L9.5 19.5 16 10h-4.5l1-7.5z",
  ev:"M3 14.5h16M5 14.5l2-6h8l2 6M6 18h2M16 18h2M3 14.5V18h16v-3.5"
};
const TABS = [["home","Home"],["energy","Energy"],["water","Hot water"],["trade","Trade"],["ev","EV"]];

/* ---------------- state ---------------- */
const store = {
  get(k, d) { try { const v = localStorage.getItem("urja." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("urja." + k, JSON.stringify(v)); } catch (e) {} }
};
const SL = D.slices, idx = {};
SL.forEach((s, i) => { idx[s.id] = i; });
const RES = D.cells.slice().sort((a, b) => (a.r - b.r) || (a.c - b.c));
const byId = {}, owner = {};
RES.forEach((c) => { byId[c.id] = c; owner[c.r + "-" + c.c] = c; });
const defaultCell = (() => {
  const pool = RES.filter((c) => c.cat === "residential_high" && c.kwp).sort((a, b) => (b.kwp / b.hh) - (a.kwp / a.hh));
  return (pool[Math.floor(pool.length / 2)] || RES[0]).id;
})();

const state = {
  tab: store.get("tab", "home"),
  cellId: byId[store.get("cell", null)] ? store.get("cell", null) : defaultCell,
  onboard: !byId[store.get("cell", null)],
  picker: false, tier: "all", sector: "all",
  m: new Date().getMonth(), dt: "wd", sim: store.get("sim", null), scrub: false,
  autopilot: store.get("ap", true), smart: store.get("smart", true), v2g: store.get("v2g", false),
  leave: store.get("leave", 8), chart: "day", viva: false, enduse: "month"
};

/* ---------------- engine ---------------- */
const at = (m, dt, dpI) => idx[MONTHS[m] + "_" + dt + "_" + DP[dpI].slice(0, 2)];
const cell = () => byId[state.cellId] || RES[0];
const cat = (c) => D.cats[c.cat];
const num = (x) => (typeof x === "number" && isFinite(x) ? x : null);

function evKw(c, i) {
  const k = cat(c);
  if (!k.ep) return 0;
  const base = k.epv !== 2 ? (c.b * k.ep[i]) / c.hh : k.ep[i];
  return base * evScale(c);   // this home's vehicle, not the tier average
}
function loadKw(c, i) {
  const k = cat(c);
  const non = (c.b * k.bp[i] + c.co * k.cp[i] + c.he * k.hp[i]) / c.hh;
  return k.epv === 2 ? non + evKw(c, i) : non;
}
function pvKw(c, i) {
  if (!c.kwp) return 0;
  const s = SL[i];
  const per = (D.pv_yield_kwh_per_kwp[i] || 0) / (s.h || 1);
  const ori = c.ori === "east_west" ? (D.pv_ew_mult[i] || 1) : 1;
  return (per * c.kwp * (c.shade || 1) * ori) / c.hh;
}
/* end-use limbs, kW per household — the appliance view */
function limbs(c, i) {
  const k = cat(c);
  return {
    base: (c.b * k.bp[i]) / c.hh,
    cool: (c.co * k.cp[i]) / c.hh,
    heat: (c.he * k.hp[i]) / c.hh,
    ev: k.epv === 2 ? evKw(c, i) : 0
  };
}
function ctx() {
  const s = state.sim, d = new Date();
  if (s) { const dpI = Math.min(11, Math.floor(s.h / 2)); return { m:s.m, dt:s.dt, dpI, frac:(s.h % 2) / 2, h:s.h, live:false }; }
  const h = d.getHours() + d.getMinutes() / 60, wd = d.getDay();
  return { m:d.getMonth(), dt:(wd === 0 || wd === 6) ? "we" : "wd", dpI:Math.min(11, Math.floor(h / 2)), frac:(h / 2) % 1, h, live:true };
}
function noise(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 1000) / 1000; }
function liveNow(c) {
  const n = ctx();
  const i0 = at(n.m, n.dt, n.dpI), i1 = at(n.m, n.dt, Math.min(11, n.dpI + 1));
  const mix = (a, b) => a + (b - a) * n.frac;
  const seed = c.id + ":" + (state.viva ? "frozen" : Math.floor(Date.now() / 120000));
  const wob = state.viva ? 1 : 0.94 + 0.12 * noise(seed);
  const load = mix(loadKw(c, i0), loadKw(c, i1)) * wob;
  const ev = mix(evKw(c, i0), evKw(c, i1)) * wob;
  const p0 = pvKw(c, i0);
  const pv = p0 <= 0 ? 0 : mix(p0, pvKw(c, i1)) * (state.viva ? 1 : 0.97 + 0.06 * noise(seed + "p"));
  return { load, pv, ev, net:load - pv, slice:SL[i0], ctx:n };
}
function curves(c, m, dt) {
  const L = [], P = [];
  for (let dp = 0; dp < 12; dp++) { const i = at(m, dt, dp); L.push(loadKw(c, i)); P.push(pvKw(c, i)); }
  const sm = (a) => { const o = []; for (let k = 0; k < 48; k++) { const x = (k + 0.5) / 4 - 0.5; const p = Math.max(0, Math.min(11, Math.floor(x))); const q = Math.max(0, Math.min(11, p + 1)); const f = Math.max(0, Math.min(1, x - p)); o.push(a[p] + (a[q] - a[p]) * f); } return o; };
  const smPv = (a) => sm(a).map((v, k) => { const dp = Math.max(0, Math.min(11, Math.floor((k + 0.5) / 4 - 0.5))); return a[dp] <= 0 ? 0 : v; });
  return { load:sm(L), pv:smPv(P) };
}
function dayTotals(c, m, dt, ap) {
  let used = 0, gen = 0, self = 0, imp = 0, expo = 0, cost = 0, earned = 0, p2p = 0;
  const lim = { base:0, cool:0, heat:0, ev:0 };
  for (let dp = 0; dp < 12; dp++) {
    const i = at(m, dt, dp), s = SL[i];
    const L = loadKw(c, i) * 2, P = pvKw(c, i) * 2, lb = limbs(c, i);
    lim.base += lb.base * 2; lim.cool += lb.cool * 2; lim.heat += lb.heat * 2; lim.ev += lb.ev * 2;
    used += L; gen += P; self += Math.min(L, P);
    const net = L - P;
    if (net > 0) { imp += net; cost += net * s.imp; }
    else {
      const sur = -net; expo += sur;
      const ok = ap && !(D.p2p.exclude_ews && c.cat === "residential_low") && s.exp < D.p2p.price_inr_kwh && D.p2p.price_inr_kwh < s.imp;
      if (ok) p2p += sur;
      earned += sur * (ok ? D.p2p.price_inr_kwh : s.exp);
    }
  }
  return { used, gen, self, imp, expo, cost, earned, p2p, net:cost - earned, lim };
}
const mtCache = {};
function monthTotals(c, m, ap) {
  const key = c.id + ":" + m + ":" + (ap ? 1 : 0);
  if (mtCache[key]) return mtCache[key];
  const wd = dayTotals(c, m, "wd", ap), we = dayTotals(c, m, "we", ap);
  const days = DIM[m], nWe = Math.round(days * 2 / 7), nWd = days - nWe, out = { days };
  Object.keys(wd).forEach((k) => {
    if (k === "lim") { out.lim = {}; Object.keys(wd.lim).forEach((j) => { out.lim[j] = wd.lim[j] * nWd + we.lim[j] * nWe; }); }
    else out[k] = wd[k] * nWd + we[k] * nWe;
  });
  return (mtCache[key] = out);
}

/* ---------------- solar water heating ----------------
   town.solar_thermal: total_m2, residential_m2, gwh_served, roofs,
   m2_per_household, m2_per_household_by_tier{residential_*}
   cells[].st  = m² of collector on this household's roof
   district.st = 864-slice series, kWh of hot water served district-wide
   Nothing else is claimed: there is no served-percentage or money-saved
   field in the snapshot, so the app shows none. */
const ST = (D.town && D.town.solar_thermal) || {};
const ST_TIER = ST.m2_per_household_by_tier || {};
const ST_SERIES = (D.district && D.district.st) || null;
const roofTot = RES.reduce((a, c) => a + (c.kwp || 0), 0);

function thermalOf(c) {
  /* FIX. `cells[].st` is the CELL's collector area - the GeoJSON
     allocates per parcel, and a parcel holds c.hh households - so it must be
     divided by c.hh to become "your roof". Every other per-home figure in this
     app already does that (loadKw and evKw both divide by c.hh), and so did
     this function's OWN residential_m2 fallback below, which is what made the
     inconsistency visible. Left undivided it overstated a high-income
     household by 40x: 118.78 m2 for a 40-home parcel instead of 2.97, against
     a tier average of 3.83 m2/household from the same snapshot. */
  let m2 = num(c.st), derived = false;
  if (m2 != null && c.hh) m2 = m2 / c.hh;
  if (m2 == null) m2 = num(ST_TIER[c.cat]);
  if (m2 == null && num(ST.residential_m2) != null && roofTot > 0) {
    m2 = (num(ST.residential_m2) * ((c.kwp || 0) / roofTot)) / c.hh;
    derived = true;
  }
  const avg = num(ST.m2_per_household);
  return { m2, derived, avg, share:(m2 != null && num(ST.total_m2)) ? m2 / num(ST.total_m2) : null };
}

/* hot water this household's collector delivers, kWh — district.st shared out
   in proportion to collector area */
/* FIX. Three compounding errors, all in how district.st was read.
   `district.st` is built by scripts/app_data_extract.py from the LP's
   `by_slice[...]["solar_thermal_served_kwh"]`, so each of its 864 entries is
   ANNUAL kWh already apportioned to that slice. The 864 are 12 months x 3 day
   types (wd, we, fs) x 24 HOURS - slice ids run `jan_wd_00` to `jan_wd_23`.
   The old code:
     1. multiplied each value by a weekday/weekend day count, though the values
        were already annual, not per-day;
     2. read only the EVEN hours, because it indexed through the 12 two-hour
        dayparts and took `DP[i].slice(0,2)` - so half of every day was missing;
     3. read only `wd` and `we`, silently dropping the third day type `fs`,
        which is a full third of the year's slices.
   Net effect on a high-income home, with the per-household divisor also
   missing: 465,823 kWh/yr against a true 1,337. A month therefore rendered as
   "35.30 MWh of hot water" on a screen that means one household.
   Summing the month's own slices needs no day arithmetic at all. */
const ST_DAYTYPES = ["wd", "we", "fs"];

function stMonthKwh(m, share, byDp, tariffed) {
  let kwh = 0, worth = 0;
  for (let d = 0; d < ST_DAYTYPES.length; d++) {
    for (let h = 0; h < 24; h++) {
      const i = idx[MONTHS[m] + "_" + ST_DAYTYPES[d] + "_" + (h < 10 ? "0" : "") + h];
      if (i == null) continue;
      const v = (ST_SERIES[i] || 0) * share;
      kwh += v;
      if (byDp) byDp[Math.floor(h / 2)] += v;
      if (tariffed && SL[i]) worth += v * SL[i].imp;
    }
  }
  return { kwh, worth };
}

function hotWater(c, m) {
  const th = thermalOf(c);
  if (!ST_SERIES || th.share == null) return null;
  const byDp = new Array(12).fill(0);
  const cur = stMonthKwh(m, th.share, byDp, true);
  const year = [];
  for (let mm = 0; mm < 12; mm++) year.push(stMonthKwh(mm, th.share, null, false).kwh);
  return { kwh: cur.kwh, worth: cur.worth, byDp, year };
}

const tierReps = (() => {
  const out = {};
  ["residential_low","residential_mid","residential_high"].forEach((k) => {
    const pool = RES.filter((c) => c.cat === k);
    if (pool.length) out[k] = pool.sort((a, b) => (b.kwp / b.hh) - (a.kwp / a.hh))[Math.floor(pool.length / 2)];
  });
  return out;
})();

/* ---------------- format ---------------- */
const f1 = (x) => { const a = Math.abs(x); return a >= 100 ? String(Math.round(x)) : a >= 10 ? x.toFixed(1) : x.toFixed(2); };
const fkwh = (x) => (Math.abs(x) >= 1000 ? (x / 1000).toFixed(2) + " MWh" : x.toFixed(1) + " kWh");
const fr = (x) => "₹" + (Math.abs(x) >= 100 ? Math.round(Math.abs(x)).toLocaleString("en-IN") : Math.abs(x).toFixed(1));
const fn0 = (x) => (x == null ? "—" : Math.round(x).toLocaleString("en-IN"));
const fm2 = (x) => (x == null ? "—" : x >= 100 ? Math.round(x).toLocaleString("en-IN") : x.toFixed(2));
const pc = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
const hhmm = (h) => String(Math.floor(h) % 24).padStart(2, "0") + ":" + String(Math.floor((h % 1) * 60)).padStart(2, "0");
const esc = (s) => String(s).replace(/[&<>"]/g, (m) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[m]));
/* SECTORS ARE ROAD-BOUNDED BLOCKS..
   The first attempt cut the grid into 25 arbitrary 10 x 10 squares. That is
   not what a sector is. In a planned Indian town a sector is the ISLAND OF
   LAND ENCLOSED BY ROADS - Chandigarh's are exactly that - so the road network
   the first layer generated already defines them, and imposing a square grid
   on top both ignored that structure and split real blocks down the middle.

   Sectors are therefore found, not invented: flood-fill the grid treating road
   cells as walls, and every connected island of non-road land is one sector.
   The frozen layout has 628 road cells, which enclose 33 blocks, 31 of them
   containing homes, holding 3 to 22 homes each. Numbering runs in reading
   order over the DRAWN map (top-left first), because that is the order a
   resident's eye takes.

   Homes inside a sector are numbered the same way. An irregular block has no
   meaningful row and column, so "Sector 7 - Home 12" replaces the "(4,5)"
   coordinate the square-grid version used. That also matches how Indian
   addresses actually read. */
let _blocks = null;
function blocks() {
  if (_blocks) return _blocks;
  const N = D.map.n, ROAD = D.map.lu_codes.road;
  const g = new Array(N * N);
  D.map.cells.forEach((mc, k) => { g[k] = mc[2]; });
  const lab = new Int32Array(N * N).fill(-1);
  let n = 0;
  for (let k = 0; k < N * N; k++) {
    if (g[k] === ROAD || lab[k] >= 0) continue;
    const q = [k]; lab[k] = n;
    while (q.length) {
      const j = q.pop(), r = (j / N) | 0, c = j % N;
      const nb = [[r - 1, c], [r + 1, c], [r, c - 1], [r, c + 1]];
      for (const [a, b] of nb) {
        if (a < 0 || b < 0 || a >= N || b >= N) continue;
        const m = a * N + b;
        if (g[m] !== ROAD && lab[m] < 0) { lab[m] = n; q.push(m); }
      }
    }
    n++;
  }
  /* Renumber by position so Sector 1 is top-left of the DRAWN map. Only blocks
     holding homes get a number; the rest are farm, water and open space and a
     resident never needs to name them. */
  const cellsOf = {};
  RES.forEach((c) => {
    const b = lab[c.r * N + c.c];
    (cellsOf[b] = cellsOf[b] || []).push(c);
  });
  const order = Object.keys(cellsOf).map(Number).sort((x, y) => {
    const cx = cellsOf[x], cy = cellsOf[y];
    const vr = (l) => Math.min.apply(null, l.map((c) => N - 1 - c.r));
    const vc = (l) => Math.min.apply(null, l.map((c) => c.c));
    return (vr(cx) - vr(cy)) || (vc(cx) - vc(cy));
  });
  const sectorOfId = {}, houseOfId = {};
  order.forEach((b, i) => {
    const list = cellsOf[b].slice().sort((a, c) =>
      ((N - 1 - a.r) - (N - 1 - c.r)) || (a.c - c.c));
    list.forEach((c, j) => { sectorOfId[c.id] = i + 1; houseOfId[c.id] = j + 1; });
  });
  _blocks = { sectorOfId, houseOfId, count: order.length };
  return _blocks;
}
const sectorOf = (c) => blocks().sectorOfId[c.id] || 0;
const houseNo = (c) => blocks().houseOfId[c.id] || 0;
const cellName = (c) => "Sector " + sectorOf(c) + " · Home " + houseNo(c);
const cellNameShort = (c) => "S" + sectorOf(c) + "/" + houseNo(c);
const TIER_LETTER = { residential_low: "E", residential_mid: "M", residential_high: "H" };
const sector = sectorOf;      // single definition; see blocks() above
const signed = (x, unit) => (x == null ? "—" : (x > 0 ? "+" : "") + x.toFixed(1) + (unit || ""));

/* svg helpers */
function areaChart(cv, W, H) {
  const base = H - 16, top = 6;
  const max = Math.max(0.25, Math.max.apply(null, cv.load), Math.max.apply(null, cv.pv)) * 1.12;
  const X = (i) => (i / (cv.load.length - 1)) * W;
  const Y = (v) => base - (v / max) * (base - top);
  const line = (a) => a.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(v).toFixed(1)).join("");
  return { line, X, Y, base, max, loadLine:line(cv.load), pvLine:line(cv.pv),
    pvFill:line(cv.pv) + "L" + W + "," + base + "L0," + base + "Z",
    loadFill:line(cv.load) + "L" + W + "," + base + "L0," + base + "Z" };
}

/* ---------------- render ---------------- */
function render() {
  const c = cell(), n = ctx();
  /* Switching to a home whose tier has no electric vehicle while standing ON
     the EV tab would otherwise leave the tab rendered with its own nav entry
     gone - visible, unreachable and about a vehicle the household does not
     own. Fall back to Home BEFORE anything renders. */
  if (state.tab === "ev" && !hasEv(c)) state.tab = "home";
  const _clk = document.getElementById("clock");
  if (_clk) _clk.textContent = hhmm(n.h);   // element removed from the shell
  document.body.classList.toggle("viva", state.viva);
  document.getElementById("hdr").innerHTML = header(c, n);
  document.getElementById("main").innerHTML = '<div class="stack">' + (
    state.tab === "home" ? tabHome(c, n) :
    state.tab === "energy" ? tabEnergy(c) :
    state.tab === "water" ? tabWater(c) :
    state.tab === "trade" ? tabTrade(c) : tabEv(c)) + "</div>";
  const tabs = TABS.filter(([k]) => k !== "ev" || hasEv(c));
  document.getElementById("nav").innerHTML = tabs.map(([k, label]) =>
    `<button data-act="tab" data-arg="${k}" class="${state.tab === k ? "on" : ""}">
      <svg width="21" height="21" viewBox="0 0 22 22" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${ICON[k]}"/></svg>
      <span>${label}</span></button>`).join("");
  document.getElementById("sheet").innerHTML = state.onboard ? firstRun() : state.picker ? picker() : "";
}

function header(c, n) {
  const eligible = !(D.p2p.exclude_ews && c.cat === "residential_low");
  return `<div style="min-width:0">
      <div class="eyebrow">${state.viva ? esc(D.town.name) : n.h < 12 ? "Good morning" : n.h < 17 ? "Good afternoon" : "Good evening"}</div>
      <button class="homebtn" data-act="picker">
        <span>${cellName(c)}</span>
        <span class="tierchip">${TIER_SHORT[c.cat]}</span>
        ${state.viva ? "" : '<svg width="11" height="11" viewBox="0 0 12 12" fill="none" style="opacity:.4"><path d="M3 4.5 6 8l3-3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'}
      </button>
    </div>
    <div class="hdr-actions">
      ${state.viva ? '<button class="pill" data-act="viva">Exit viva</button>' :
        `<button class="pill hdr-live" data-act="scrub"><span class="dot ${n.live ? "" : "sim"}"></span>${n.live ? "Live" : ML[n.m] + " " + hhmm(n.h)}</button>`}
    </div>${eligible ? "" : ""}`;
  /* THE VIVA-MODE BUTTON WAS REMOVED FROM THE HEADER, (the author: "i
     dont need that option"). It was a monitor glyph that turned the tab into a
     projector-friendly card layout, and on a phone it read as a mystery icon
     whose only visible effect was an "Exit viva" pill.
     THE MODE ITSELF IS KEPT, on the `v` key, because it is genuinely useful on
     a desktop for capturing clean screenshots for the thesis - and the Exit
     pill above still renders once you are in it, so there is always a way out
     for anyone without a keyboard. */
}

function scrubber(n) {
  if (!state.scrub || state.viva) return "";
  const hour = Math.floor(n.h);
  return `<div class="card tight">
    <div class="spread" style="align-items:baseline;margin-bottom:10px">
      <span class="label">Preview any hour</span>
      <button data-act="live" style="font-size:12px;font-weight:600;color:var(--grid)">Back to live</button>
    </div>
    <div class="row" style="margin-bottom:10px"><span class="med" style="min-width:74px">${hhmm(hour)}</span>
      <input type="range" min="0" max="23" step="1" value="${hour}" data-act="hour"></div>
    <div class="chips" style="padding-bottom:2px">${ML.map((l, m) =>
      `<button class="chip ${m === n.m ? "on" : ""}" data-act="simmonth" data-arg="${m}">${l}</button>`).join("")}</div>
    <div style="display:flex;gap:6px;margin-top:8px">
      <button class="chip" style="flex:1;justify-content:center;text-align:center;${n.dt === "wd" ? "background:var(--ink);color:var(--canvas);border-color:var(--ink)" : ""}" data-act="simdt" data-arg="wd">Weekday</button>
      <button class="chip" style="flex:1;justify-content:center;text-align:center;${n.dt === "we" ? "background:var(--ink);color:var(--canvas);border-color:var(--ink)" : ""}" data-act="simdt" data-arg="we">Weekend</button>
    </div></div>`;
}

/* ---------------- HOME ---------------- */
function tabHome(c, n) {
  const lv = liveNow(c), s = lv.slice;
  const ap = state.autopilot && !(D.p2p.exclude_ews && c.cat === "residential_low");
  const today = dayTotals(c, n.m, n.dt, ap);
  const mt = monthTotals(c, n.m, ap), mtOff = monthTotals(c, n.m, false);
  const importing = lv.net > 0.005, exporting = lv.net < -0.005;
  const selfPct = lv.load > 0 ? Math.round((Math.min(lv.load, lv.pv) / lv.load) * 100) : 0;
  const cv = curves(c, n.m, n.dt), ch = areaChart(cv, 326, 150);
  const nowI = Math.max(0, Math.min(47, Math.round((n.h / 24) * 47)));
  const th = thermalOf(c);
  const eligible = !(D.p2p.exclude_ews && c.cat === "residential_low");
  return scrubber(n) + `
  <div class="card hero" style="padding:0">
    <div class="glow"></div>
    <div class="spread" style="position:relative;padding:20px 20px 4px">
      <div>
        <div class="label">${exporting ? "Sending to the grid" : importing ? "Drawing from the grid" : "Running on solar"}</div>
        <div style="display:flex;align-items:baseline;gap:5px;margin-top:2px">
          <span class="big" style="font-size:44px">${f1(Math.abs(lv.net))}</span>
          <span style="font-size:15px;font-weight:600;color:var(--dim)">kW</span>
        </div>
        <div style="font-size:12px;font-weight:600;color:var(--solar);margin-top:3px">${selfPct}% of use from solar</div>
      </div>
      <div style="text-align:right;font-size:12px;line-height:1.5;color:var(--dim)">
        <div style="font-weight:600;color:var(--ink)">${BAND[s.band] || esc(s.band)}</div>
        <div>buy ${fr(s.imp)}/kWh</div>
        <div>sell ${fr(ap && s.exp < D.p2p.price_inr_kwh && D.p2p.price_inr_kwh < s.imp ? D.p2p.price_inr_kwh : s.exp)}/kWh</div>
      </div>
    </div>
    <div class="flow">
      <svg viewBox="0 0 340 312">
        <path d="M170 104 C170 88 170 74 170 52" stroke="var(--line)" stroke-width="9" fill="none" stroke-linecap="round"/>
        <path d="M146 157 C122 180 104 194 78 218" stroke="var(--line)" stroke-width="9" fill="none" stroke-linecap="round"/>
        <path d="M194 157 C218 180 236 194 262 218" stroke="var(--line)" stroke-width="9" fill="none" stroke-linecap="round"/>
        ${lv.pv > 0.01 ? '<path class="dash rev" d="M170 104 C170 88 170 74 170 52" stroke="var(--solar)" stroke-width="5" fill="none" stroke-linecap="round" style="animation-duration:1.1s"/>' : ""}
        ${importing ? '<path class="dash rev" d="M146 157 C122 180 104 194 78 218" stroke="var(--grid)" stroke-width="5" fill="none" stroke-linecap="round"/>' : ""}
        ${exporting ? '<path class="dash" d="M146 157 C122 180 104 194 78 218" stroke="var(--good)" stroke-width="5" fill="none" stroke-linecap="round"/>' : ""}
        ${lv.ev > 0.005 ? '<path class="dash" d="M194 157 C218 180 236 194 262 218" stroke="var(--batt)" stroke-width="5" fill="none" stroke-linecap="round" style="animation-duration:1.7s"/>' : ""}

        <g fill="none" stroke="var(--ink)" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round">
          <path d="M141 130 170 106 199 130"/>
          <path d="M147 130v32h46v-32"/>
          <path d="M164 162v-18h12v18"/>
        </g>
      </svg>

      <div class="centre" style="top:69%">
        <div style="font-size:26px;font-weight:600;letter-spacing:-.03em;line-height:1">${f1(lv.load)} <span style="font-size:13px;color:var(--dim)">kW</span></div>
        <div class="hint" style="letter-spacing:.08em;margin-top:3px">IN USE NOW</div>
      </div>

      <div class="node wide" style="left:50%;top:8%">
        <svg width="19" height="19" viewBox="0 0 22 22" fill="none" style="opacity:${lv.pv > 0.01 ? 1 : 0.3}">
          <g stroke="var(--solar)" stroke-width="1.5" stroke-linecap="round"><path d="M15.5 2.5v1.8M19.4 6.4h-1.8M18.3 3.6 17 4.9M12.7 3.6 14 4.9M12.9 8.2a2.6 2.6 0 0 1 5.2 0"/></g>
          <path d="M3 16.5 5.6 9.4h9.2l2.6 7.1z" fill="var(--solar)"/>
          <path d="M8.2 9.4 7 16.5M11.8 9.4 13 16.5M4.4 12.9h11.2" stroke="var(--card)" stroke-width="1.1"/>
        </svg>
        <b>${f1(lv.pv)} kW</b><span class="hint">ROOFTOP</span>
      </div>
      <div class="node" style="left:16%;top:80%">
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="${exporting ? "var(--good)" : "var(--grid)"}" stroke-width="1.6" stroke-linecap="round"><path d="M5 17l5-14 5 14M6.6 12h6.8M5.6 8h8.8"/></svg>
        <b style="margin-top:2px">${f1(Math.abs(lv.net))} kW</b><span class="hint">${exporting ? "EXPORT" : "GRID"}</span>
      </div>
      <div class="node" style="left:84%;top:80%">
        <svg width="18" height="18" viewBox="0 0 22 20" fill="none" stroke="var(--batt)" stroke-width="1.6" stroke-linecap="round"><path d="M3 13h16M5 13l2-6h8l2 6M6 16.5h2M14 16.5h2"/></svg>
        <b style="margin-top:2px">${f1(lv.ev)} kW</b><span class="hint">EV</span>
      </div>
    </div>
  </div>

  <div class="grid2">
    <div class="card tight">
      <div class="label">Today's bill</div>
      <div class="med" style="margin-top:5px">${fr(today.net)}</div>
      <div class="note" style="margin-top:2px">${today.net >= 0 ? "after " + fr(today.earned) + " sold" : "credit — you sold more than you drew"}</div>
    </div>
    <div class="card tight">
      <div class="label">Sold today</div>
      <div class="med" style="margin-top:5px;color:var(--good)">${fr(today.earned)}</div>
      <div class="note" style="margin-top:2px">${fkwh(today.expo)} exported</div>
    </div>
  </div>

  <button class="card" data-act="tab" data-arg="water" style="display:${th.m2 == null && ST.total_m2 == null ? "none" : "block"};width:100%">
    <div class="row">
      <span style="flex:none;width:40px;height:40px;border-radius:14px;background:rgba(78,124,168,.12);display:flex;align-items:center;justify-content:center">
        <svg width="19" height="19" viewBox="0 0 22 22" fill="none" stroke="var(--water)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${ICON.water}"/></svg>
      </span>
      <span class="grow" style="flex:1;min-width:0">
        <span class="h" style="display:block">Sun heats your water first</span>
        <span class="note" style="display:block;margin-top:2px">${fm2(th.m2)} m² of collector on your roof${th.avg ? ", against a " + fm2(th.avg) + " m² district average" : ""}</span>
      </span>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="flex:none;opacity:.4"><path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </div>
  </button>

  <div class="card">
    <div class="spread" style="align-items:baseline;margin-bottom:10px">
      <span class="h">Today, hour by hour</span>
      <span class="note">${n.dt === "wd" ? "Weekday" : "Weekend"} · ${MFULL[n.m]}</span>
    </div>
    <svg viewBox="0 0 326 150" style="width:100%;display:block">
      <path d="${ch.pvFill}" fill="var(--solar)" opacity=".16"/>
      <path d="${ch.pvLine}" fill="none" stroke="var(--solar)" stroke-width="2.2" stroke-linejoin="round"/>
      <path d="${ch.loadLine}" fill="none" stroke="var(--ink)" stroke-width="2.2" stroke-linejoin="round"/>
      <line x1="0" y1="${ch.base}" x2="326" y2="${ch.base}" stroke="var(--line)"/>
      <line x1="${ch.X(nowI).toFixed(1)}" y1="4" x2="${ch.X(nowI).toFixed(1)}" y2="${ch.base}" stroke="var(--dim)" stroke-dasharray="2 3"/>
      <circle cx="${ch.X(nowI).toFixed(1)}" cy="${ch.Y(cv.load[nowI]).toFixed(1)}" r="3.6" fill="var(--ink)"/>
      <circle cx="${ch.X(nowI).toFixed(1)}" cy="${ch.Y(cv.pv[nowI]).toFixed(1)}" r="3.6" fill="var(--solar)"/>
      ${[["00",0],["06",78],["12",158],["18",238],["24",311]].map(([t, x]) => `<text x="${x}" y="148" font-size="10" font-weight="600" fill="var(--dim)">${t}</text>`).join("")}
    </svg>
    <div class="legend"><span><i class="swatch" style="background:var(--ink)"></i>Use</span><span><i class="swatch" style="background:var(--solar)"></i>Rooftop</span>
      <span style="margin-left:auto">peak ${f1(ch.max / 1.12)} kW</span></div>
  </div>

  <button class="cta" data-act="tab" data-arg="trade">
    <span class="ico"><svg width="17" height="17" viewBox="0 0 18 18" fill="none"><path d="M9 1.5 4 10h4l-1 6.5L13 8H9l1-6.5z" fill="var(--solar)"/></svg></span>
    <span style="flex:1;min-width:0">
      <span style="display:block;font-size:14px;font-weight:600">${ap ? "Autopilot is selling your surplus" : eligible ? "Turn on trading autopilot" : "Feed-in credit is automatic"}</span>
      <span style="display:block;font-size:12px;opacity:.7;margin-top:1px">${ap ? fr(mt.earned - mtOff.earned) + " more this month than feed-in alone" : eligible ? "Neighbours pay " + fr(D.p2p.price_inr_kwh) + "/kWh, the grid pays " + fr(D.p2p.export_inr_kwh) : "EWS/LIG homes are exempt from trading"}</span>
    </span>
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="flex:none;opacity:.6"><path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </button>`;
}

/* ---------------- ENERGY ---------------- */
function tabEnergy(c) {
  const ap = state.autopilot && !(D.p2p.exclude_ews && c.cat === "residential_low");
  const m = state.m, mt = monthTotals(c, m, ap);
  const cv = curves(c, m, state.dt), ch = areaChart(cv, 326, 160);
  const EF = (D.grid && D.grid.ef_kgco2_per_kwh) || 0;
  const yearly = ML.map((l, i) => monthTotals(c, i, ap));
  const yMax = Math.max.apply(null, yearly.map((t) => Math.max(t.used, t.gen))) * 1.1 || 1;
  const lim = mt.lim, limTot = lim.base + lim.cool + lim.heat + lim.ev || 1;
  const th = thermalOf(c);
  const uses = [
    { k:"base", label:"Lights, plugs, kitchen", v:lim.base, color:"var(--ink)", note:"" },
    { k:"cool", label:"Cooling", v:lim.cool, color:"var(--grid)", note:"" },
    { k:"heat", label:"Water & space heating", v:lim.heat, color:"var(--warn)", note:th.m2 != null ? fm2(th.m2) + " m² of solar collector heats water before this meter reads anything" : "" },
    { k:"ev", label:"EV charging", v:lim.ev, color:"var(--batt)", note:"" }
  ].filter((u) => u.v > 0.001).sort((a, b) => b.v - a.v);
  return scrubber(ctx()) + `
  <div class="chips">${ML.map((l, i) => `<button class="chip ${i === m ? "on" : ""}" data-act="month" data-arg="${i}">${l}</button>`).join("")}</div>
  <div class="card">
    <div class="spread">
      <div>
        <div class="label">${MFULL[m]} · self-sufficient</div>
        <div style="display:flex;align-items:baseline;gap:4px;margin-top:3px">
          <span class="big">${mt.used > 0 ? Math.round((mt.self / mt.used) * 100) : 0}</span>
          <span style="font-size:16px;font-weight:600;color:var(--dim)">%</span>
        </div>
      </div>
      <div class="seg">
        <button class="${state.chart === "day" ? "on" : ""}" data-act="chart" data-arg="day">Day</button>
        <button class="${state.chart === "year" ? "on" : ""}" data-act="chart" data-arg="year">Year</button>
      </div>
    </div>
    ${state.chart === "day" ? `
      <svg viewBox="0 0 326 160" style="width:100%;display:block;margin-top:10px">
        <path d="${ch.pvFill}" fill="var(--solar)" opacity=".16"/>
        <path d="${ch.loadFill}" fill="var(--ink)" opacity=".06"/>
        <path d="${ch.pvLine}" fill="none" stroke="var(--solar)" stroke-width="2.2" stroke-linejoin="round"/>
        <path d="${ch.loadLine}" fill="none" stroke="var(--ink)" stroke-width="2.2" stroke-linejoin="round"/>
        <line x1="0" y1="${ch.base}" x2="326" y2="${ch.base}" stroke="var(--line)"/>
        <text x="0" y="158" font-size="10" font-weight="600" fill="var(--dim)">00</text>
        <text x="158" y="158" font-size="10" font-weight="600" fill="var(--dim)">12</text>
        <text x="311" y="158" font-size="10" font-weight="600" fill="var(--dim)">24</text>
      </svg>` : `
      <svg viewBox="0 0 326 160" style="width:100%;display:block;margin-top:10px">
        ${yearly.map((t, i) => {
          const uh = Math.max(2, (t.used / yMax) * 124), gh = Math.max(2, (t.gen / yMax) * 124);
          return `<rect x="${i * 27 + 3}" y="${(138 - uh).toFixed(1)}" width="9" height="${uh.toFixed(1)}" rx="3" fill="var(--ink)" opacity=".82"/>
                  <rect x="${i * 27 + 14}" y="${(138 - gh).toFixed(1)}" width="9" height="${gh.toFixed(1)}" rx="3" fill="var(--solar)"/>
                  <text x="${i * 27 + 11.5}" y="154" font-size="9" font-weight="600" text-anchor="middle" fill="${i === m ? "var(--ink)" : "var(--dim)"}">${ML[i][0]}</text>`;
        }).join("")}
        <line x1="0" y1="138" x2="326" y2="138" stroke="var(--line)"/>
      </svg>`}
    <div class="legend"><span><i class="swatch" style="background:var(--ink)"></i>Use</span><span><i class="swatch" style="background:var(--solar)"></i>Rooftop</span></div>
  </div>

  <div class="card flush">
    <div class="rowitem" style="padding-bottom:10px;border-bottom:0">
      <span class="grow">Where it goes</span>
      <span class="note">${MFULL[m]}, ${fkwh(limTot)}</span>
    </div>
    ${uses.map((u) => `
      <div class="rowitem" style="align-items:flex-start;flex-direction:column;gap:7px">
        <div class="row" style="width:100%">
          <span class="swatch" style="background:${u.color}"></span>
          <span class="grow">${u.label}</span>
          <span style="font-size:13.5px;font-weight:600">${fkwh(u.v)}</span>
          <span style="width:38px;text-align:right" class="note">${Math.round((u.v / limTot) * 100)}%</span>
        </div>
        <div class="hbar" style="width:100%"><i style="width:${((u.v / limTot) * 100).toFixed(1)}%;background:${u.color}"></i></div>
        ${u.note ? `<span class="note">${u.note}</span>` : ""}
      </div>`).join("")}
  </div>

  <div class="card flush">
    ${[["Used", fkwh(mt.used), (mt.used / mt.days).toFixed(1) + "/day", "var(--ink)"],
       ["Generated", fkwh(mt.gen), (c.kwp / c.hh).toFixed(1) + " kWp", "var(--solar)"],
       ["Used on site", fkwh(mt.self), Math.round(mt.self / Math.max(1, mt.gen) * 100) + "% of gen", "var(--good)"],
       ["Bought", fkwh(mt.imp), fr(mt.cost), "var(--grid)"],
       ["Sold", fkwh(mt.expo), fr(mt.earned), "var(--batt)"]]
      .map(([l, v, note, col]) => `<div class="rowitem"><span class="swatch" style="background:${col}"></span>
        <span class="grow">${l}</span><span style="font-size:13.5px;font-weight:600">${v}</span>
        <span style="width:56px;text-align:right" class="note">${note}</span></div>`).join("")}
    <div class="tot"><span class="grow">${MFULL[m]} net bill</span><span style="font-size:17px;font-weight:600">${fr(mt.net)}</span></div>
  </div>

  <div class="card">
    <div class="h">CO₂ you kept out of the grid</div>
    <div class="sub" style="margin-top:3px">Every kWh you generate displaces grid power at ${EF.toFixed(3)} kg CO₂/kWh — the factor in this snapshot. The town as a whole runs ${signed(D.town.vs_bau_co2_pct, "%")} on emissions against business as usual.</div>
    <div style="display:flex;align-items:baseline;gap:5px;margin-top:10px">
      <span style="font-size:32px;font-weight:600;letter-spacing:-.03em;color:var(--good)">${fn0((mt.self + mt.expo) * EF)}</span>
      <span style="font-size:14px;font-weight:600;color:var(--dim)">kg this month</span>
    </div>
  </div>`;
}

/* ---------------- HOT WATER ---------------- */
function tabWater(c) {
  const th = thermalOf(c), hw = hotWater(c, state.m);
  if (th.m2 == null && ST.total_m2 == null) {
    return scrubber(ctx()) + `<div class="card">
      <div class="label">Solar water heating</div>
      <div class="h" style="font-size:19px;margin-top:6px">Not in this data snapshot</div>
      <div class="sub" style="margin-top:6px">The model file loaded here is stamped ${esc(String((D.meta && D.meta.generated) || "unknown"))} and carries no collector fields. This screen fills itself in — your own collector area, the tier comparison and the heat it delivers — as soon as a snapshot with <b>town.solar_thermal</b>, <b>cells[].st</b> and <b>district.st</b> is dropped in. Nothing here is typed in by hand.</div>
    </div>`;
  }
  const tiers = ["residential_high","residential_mid","residential_low"].map((k) => ({
    k, label:TIER_SHORT[k],
    m2:num(ST_TIER[k]) != null ? num(ST_TIER[k]) : (tierReps[k] ? thermalOf(tierReps[k]).m2 : null),
    mine:k === c.cat
  }));
  const maxM2 = Math.max.apply(null, tiers.map((t) => t.m2 || 0).concat([th.avg || 0])) || 1;
  const mine = th.m2, lowest = tiers[tiers.length - 1].m2;
  const ratio = mine != null && lowest ? mine / lowest : null;
  const vsAvg = mine != null && th.avg ? mine / th.avg : null;
  const ap = state.autopilot && !(D.p2p.exclude_ews && c.cat === "residential_low");
  const mt = monthTotals(c, state.m, ap);
  const heatKwh = mt.lim.heat;
  const cmpMax = Math.max(heatKwh, hw ? hw.kwh : 0) || 1;
  const yMax = hw ? Math.max.apply(null, hw.year) * 1.1 || 1 : 1;
  const dpMax = hw ? Math.max.apply(null, hw.byDp) || 1 : 1;
  return scrubber(ctx()) + `
  <div class="card hero" style="padding:20px">
    <div class="glow" style="inset:-40% 28% 48% 28%;background:radial-gradient(circle at 50% 40%,rgba(78,124,168,.16),transparent 68%)"></div>
    <div class="label">Solar water heating</div>
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin-top:6px">
      <div>
        <div style="display:flex;align-items:baseline;gap:5px">
          <span class="big" style="font-size:46px">${fm2(mine)}</span>
          <span style="font-size:17px;font-weight:600;color:var(--dim)">m²</span>
        </div>
        <div class="sub" style="margin-top:4px;max-width:200px">of collector on your roof${th.derived ? ", estimated from your roof area" : ""}</div>
      </div>
      <div style="text-align:right">
        <div class="label">${TIER_SHORT[c.cat]} tier</div>
        <div class="med" style="margin-top:3px">${vsAvg ? (vsAvg >= 1 ? vsAvg.toFixed(1) + "×" : (vsAvg * 100).toFixed(0) + "%") : "—"}</div>
        <div class="note" style="margin-top:2px;max-width:120px">the ${fm2(th.avg)} m² district average</div>
      </div>
    </div>
    <div class="sub serif" style="margin-top:14px;font-size:13.5px;line-height:1.55">The collector sits in the loop before the meter: the sun heats your tank first, and the electric element only tops up what is left.</div>
  </div>

  ${hw ? `<div class="card">
    <div class="spread" style="align-items:baseline">
      <span class="h">Heat off your roof</span>
      <span class="note">${MFULL[state.m]}</span>
    </div>
    <div style="display:flex;align-items:baseline;gap:6px;margin-top:8px">
      <span class="big" style="font-size:34px;color:var(--water)">${fkwh(hw.kwh)}</span>
      <span class="note">of hot water, worth ${fr(hw.worth)} at this month's tariffs</span>
    </div>
    <div class="bars" style="height:74px;margin-top:16px">
      ${hw.byDp.map((v, i) => `<div class="col"><div class="bar" style="height:${Math.max(3, (v / dpMax) * 58).toFixed(0)}px;background:${v > dpMax * 0.02 ? "var(--water)" : "var(--line)"}"></div><span class="cl">${DP[i].slice(0, 2)}</span></div>`).join("")}
    </div>
    <div class="sub" style="margin-top:10px">Delivery follows the sun, not your shower: the tank carries the afternoon's heat into the evening.</div>
  </div>

  <div class="card">
    <div class="h">Collector heat against electric heating</div>
    <div class="sub" style="margin-top:3px">Two measured quantities, side by side — the snapshot does not say which share of your hot water the collector covers, so the app does not either.</div>
    <div style="display:flex;flex-direction:column;gap:12px;margin-top:14px">
      <div>
        <div class="row" style="margin-bottom:5px"><span class="grow" style="font-size:13px;font-weight:600">Collector heat delivered</span>
          <span style="font-size:13.5px;font-weight:600">${fkwh(hw.kwh)}</span></div>
        <div class="hbar"><i style="width:${((hw.kwh / cmpMax) * 100).toFixed(1)}%;background:var(--water)"></i></div>
      </div>
      <div>
        <div class="row" style="margin-bottom:5px"><span class="grow" style="font-size:13px;font-weight:600">Electric water &amp; space heating</span>
          <span style="font-size:13.5px;font-weight:600">${fkwh(heatKwh)}</span></div>
        <div class="hbar"><i style="width:${((heatKwh / cmpMax) * 100).toFixed(1)}%;background:var(--warn)"></i></div>
      </div>
    </div>
    <div class="bars" style="height:78px;margin-top:18px">
      ${hw.year.map((v, i) => `<div class="col"><div class="bar" style="height:${Math.max(3, (v / yMax) * 62).toFixed(0)}px;background:${i === state.m ? "var(--water)" : "rgba(78,124,168,.35)"}"></div><span class="cl" style="color:${i === state.m ? "var(--ink)" : "var(--dim)"}">${ML[i][0]}</span></div>`).join("")}
    </div>
    <div class="note" style="margin-top:8px">Collector heat by month — winter costs more to make and the sun gives less of it.</div>
  </div>` : ""}

  <div class="card">
    <div class="h">Collector area is not shared equally</div>
    <div class="sub" style="margin-top:3px">Area is allocated by roof, so an HIG roof carries many times what an EWS/LIG roof does. Per household, m²:</div>
    <div style="display:flex;flex-direction:column;gap:12px;margin-top:14px">
      ${tiers.map((t) => `
        <div>
          <div class="row" style="margin-bottom:5px">
            <span class="grow" style="font-size:13px;font-weight:600">${t.label}${t.mine ? " · your tier" : ""}</span>
            <span style="font-size:13.5px;font-weight:600">${fm2(t.m2)} m²</span>
          </div>
          <div class="hbar"><i style="width:${(((t.m2 || 0) / maxM2) * 100).toFixed(1)}%;background:${t.mine ? "var(--ink)" : TIER_SWATCH[t.k]}"></i></div>
        </div>`).join("")}
      ${th.avg ? `<div>
        <div class="row" style="margin-bottom:5px"><span class="grow" style="font-size:13px;font-weight:600;color:var(--dim)">District average</span>
          <span style="font-size:13.5px;font-weight:600;color:var(--dim)">${fm2(th.avg)} m²</span></div>
        <div class="hbar"><i style="width:${((th.avg / maxM2) * 100).toFixed(1)}%;background:var(--line);border:1px solid var(--dim);box-sizing:border-box"></i></div>
      </div>` : ""}
    </div>
    ${ratio ? `<div class="sub" style="margin-top:13px">Your ${fm2(mine)} m² is ${ratio >= 2 ? ratio.toFixed(1) + "×" : (ratio * 100).toFixed(0) + "% of"} the ${fm2(lowest)} m² an EWS/LIG household carries. The average hides that gap; this is your own figure.</div>` : ""}
  </div>

  <div class="card flush">
    <div class="rowitem" style="border-bottom:0;padding-bottom:8px">
      <span class="grow">Across ${esc(D.town.name)}</span>
      <span class="note">${esc(String(D.town.period))}</span>
    </div>
    ${[["Collector built", ST.total_m2 != null ? fn0(ST.total_m2) + " m²" : "—", "district total"],
       ["On homes", ST.residential_m2 != null ? fn0(ST.residential_m2) + " m²" : "—", ST.total_m2 ? Math.round((ST.residential_m2 / ST.total_m2) * 100) + "% of it" : ""],
       ["Roofs carrying one", ST.roofs != null ? fn0(ST.roofs) : "—", "buildings"],
       ["Hot water served", ST.gwh_served != null ? Number(ST.gwh_served).toFixed(2) + " GWh" : "—", "per year"]]
      .map(([l, v, note]) => `<div class="rowitem"><span class="grow">${l}</span>
        <span style="font-size:13.5px;font-weight:600">${v}</span>
        <span style="max-width:120px;text-align:right" class="note">${esc(note)}</span></div>`).join("")}
    <div class="tot"><span class="grow">Town emissions vs business as usual</span>
      <span style="font-size:17px;font-weight:600">${signed(D.town.vs_bau_co2_pct, "%")}</span></div>
  </div>`;
}

/* ---------------- TRADE ---------------- */
function tabTrade(c) {
  const eligible = !(D.p2p.exclude_ews && c.cat === "residential_low");
  const ap = state.autopilot && eligible;
  const m = state.m, mt = monthTotals(c, m, ap), mtOff = monthTotals(c, m, false);
  const p2pP = D.p2p.price_inr_kwh, feed = D.p2p.export_inr_kwh;
  const windows = DP.map((dp, i) => {
    const s = SL[at(m, state.dt, i)];
    const sur = Math.max(0, (pvKw(c, at(m, state.dt, i)) - loadKw(c, at(m, state.dt, i))) * 2);
    const clears = sur > 0.01 && s.exp < p2pP && p2pP < s.imp;
    return { label:dp.slice(0, 2), h:Math.max(6, Math.min(52, 6 + sur * 9)), bg:clears ? (ap ? "var(--good)" : "var(--solar)") : "var(--line)" };
  });
  const ledger = [
    ["P2P", "Sold to neighbours", fkwh(mt.p2p) + " at " + fr(p2pP) + "/kWh", "+" + fr(mt.p2p * p2pP), "rgba(110,143,94,.14)", "var(--good)", "var(--good)"],
    ["GRID", "Fed to the grid", fkwh(Math.max(0, mt.expo - mt.p2p)) + " at " + fr(feed) + "/kWh", "+" + fr(Math.max(0, mt.expo - mt.p2p) * feed), "rgba(91,132,184,.14)", "var(--grid)", "var(--good)"],
    ["BUY", "Bought from the grid", fkwh(mt.imp) + " across " + mt.days + " days", "−" + fr(mt.cost), "rgba(27,25,22,.07)", "var(--ink)", "var(--ink)"],
    ["SUN", "Used straight off the roof", fkwh(mt.self) + " never touched a meter", fr(mt.self * (SL[at(m, state.dt, 6)].imp || 0)) + " avoided", "rgba(232,181,78,.16)", "var(--solar)", "var(--dim)"]
  ];
  return scrubber(ctx()) + `
  <div class="dark">
    <div class="spread">
      <div style="min-width:0">
        <div class="label">Autopilot</div>
        <div style="font-size:19px;font-weight:600;letter-spacing:-.02em;margin-top:3px">${ap ? "Selling to neighbours" : eligible ? "Off — feed-in only" : "Not applicable"}</div>
      </div>
      <button class="switch dark-track ${ap ? "on" : ""}" data-act="ap" ${eligible ? "" : "disabled"}><i></i></button>
    </div>
    <div style="display:flex;align-items:baseline;gap:6px;margin-top:16px">
      <span class="big" style="font-size:42px">${fr(mt.earned - mtOff.earned)}</span>
      <span style="font-size:13px;font-weight:600;opacity:.65">extra per month vs feed-in</span>
    </div>
    <div style="display:flex;gap:8px;margin-top:16px">
      <div class="tile" style="flex:1"><div class="label">Neighbour price</div><div style="font-size:19px;font-weight:600;margin-top:2px">${fr(p2pP)}</div></div>
      <div class="tile" style="flex:1"><div class="label">Feed-in</div><div style="font-size:19px;font-weight:600;margin-top:2px">${fr(feed)}</div></div>
    </div>
  </div>
  ${eligible ? "" : `<div class="card tight"><div class="sub"><b style="color:var(--ink)">EWS/LIG homes are exempt from trading.</b> Your rooftop is credited at the ${fr(feed)} feed-in rate and your bill is capped by the lifeline tariff — nothing to opt into.</div></div>`}

  <div class="card flush">
    <div style="padding:16px 18px 12px"><div class="h">Wallet · ${MFULL[m]}</div>
      <div class="note" style="margin-top:2px">${mt.days} days · ${fkwh(mt.p2p)} traded peer-to-peer</div></div>
    <div style="display:flex;border-top:1px solid var(--line);border-bottom:1px solid var(--line)">
      <div style="flex:1;padding:14px 18px;border-right:1px solid var(--line)"><div class="label">Earned</div>
        <div style="font-size:20px;font-weight:600;margin-top:3px;color:var(--good)">${fr(mt.earned)}</div></div>
      <div style="flex:1;padding:14px 18px"><div class="label">Bought</div>
        <div style="font-size:20px;font-weight:600;margin-top:3px">${fr(mt.cost)}</div></div>
    </div>
    ${ledger.map(([tag, label, sub, amt, bg, fg, ac]) => `
      <div class="rowitem">
        <span style="flex:none;width:32px;height:32px;border-radius:11px;background:${bg};color:${fg};display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">${tag}</span>
        <span style="flex:1;min-width:0"><span style="display:block;font-size:13px;font-weight:600">${label}</span>
          <span class="note" style="display:block;margin-top:1px">${sub}</span></span>
        <span style="font-size:13.5px;font-weight:600;color:${ac}">${amt}</span>
      </div>`).join("")}
  </div>

  <div class="card">
    <div class="h">When a trade clears</div>
    <div class="sub" style="margin-top:3px">A neighbour buys your surplus only when ${fr(feed)} feed-in &lt; ${fr(p2pP)} P2P &lt; the tariff they would otherwise pay.</div>
    <div class="bars" style="margin-top:14px;height:60px">
      ${windows.map((w) => `<div class="col"><div class="bar" style="height:${w.h}px;background:${w.bg}"></div><span class="cl">${w.label}</span></div>`).join("")}
    </div>
    <div class="legend"><span><i class="swatch" style="background:var(--good)"></i>Clears</span>
      <span><i class="swatch" style="background:var(--line)"></i>No surplus</span>
      <span style="margin-left:auto">${windows.filter((w) => w.bg !== "var(--line)").length} of 12 windows clear</span></div>
  </div>`;
}

/* WHAT THIS HOUSEHOLD ACTUALLY DRIVES..

   THE MODEL CANNOT ANSWER THIS, AND THAT IS THE POINT. Ownership enters the
   model as a FRACTION OF ENERGY, not a flag on a home: costs.py returns
   `ev_cars_per_household(income) * car_kwh + e2w_share(income) * e2w_kwh`, so
   every EWS/LIG household is charged 0.05 of a scooter every day. Nobody owns
   a scooter; everybody owns a twentieth of one. Tiers are homogeneous by
   design (thesis 3.2) and there is no ownership process anywhere (3.9.4).

   Three ways to present that, and only one is both useful and honest:
     (a) show the fraction - model-exact and meaningless to a resident;
     (b) hide the screen below some tier threshold - implies EWS/LIG owns NO
         electric vehicle, which is false, 5 % do;
     (c) DRAW one household from the tier's own share, and say that is what
         it is. Chosen.

   THE PRINCIPLE THAT MAKES (c) DEFENSIBLE: average the continuous, sample the
   discrete. A home really can carry 2.97 m2 of collector, so area stays an
   average. A home cannot own 0.05 of a scooter, so ownership is sampled.

   THE DRAW IS DETERMINISTIC, NOT RANDOM. It is a hash of the cell id, so a
   given home shows the same vehicle on every load, every device and every
   rebuild. Nothing shuffles between sessions. Across all 393 homes the drawn
   shares track the model's: HIG 16.1 % against 19 %, MIG 17.6 % against 20 %,
   EWS/LIG 6.8 % against 5 %, the gaps being sampling noise on small counts.

   ONE DRAW, NOT TWO. The pre-redesign app drew a car, then drew a scooter
   only if that missed, which silently shrank the scooter share to
   (1 - car) x e2w - 11.2 % instead of 12 % for HIG. A single uniform split
   across [car | scooter | none] gives the exact marginals. */
function noise(seed) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  h = Math.imul(h ^ (h >>> 15), 2246822507);
  h = Math.imul(h ^ (h >>> 13), 3266489909);
  return ((h ^= h >>> 16) >>> 0) / 4294967295;
}
function evOwnership(c) {
  const P = D.ev.params, inc = INCOME[c.cat];
  const by = (P.by_income || {})[inc] || {};
  const car = num(by.ev_car_share) || 0, e2w = num(by.e2w_share) || 0;
  return { car, e2w, none: Math.max(0, 1 - car - e2w) };
}
/* STRATIFIED, NOT THRESHOLDED. A plain `noise < share` test is unbiased but
   noisy on small counts: it handed HIG 7 cars where the share implies 15.7,
   two standard deviations light, and the district's representative households
   then carried 101 kWh/day of charging against the 161 the shares imply.
   Ranking each tier by its hash and taking the first round(share x n) gives
   the EXACT count the model specifies while staying just as deterministic -
   the ranking is fixed, so a home's vehicle never changes. */
let _veh = null;
function vehAssign() {
  if (_veh) return _veh;
  _veh = {};
  const byTier = {};
  RES.forEach((c) => { (byTier[c.cat] = byTier[c.cat] || []).push(c); });
  Object.keys(byTier).forEach((cat) => {
    const list = byTier[cat].slice().sort((a, b) =>
      noise(a.id + ":veh") - noise(b.id + ":veh"));
    const o = evOwnership(list[0]);
    const nCar = Math.round(o.car * list.length);
    const nE2w = Math.round(o.e2w * list.length);
    list.forEach((c, i) => {
      _veh[c.id] = i < nCar ? "car" : i < nCar + nE2w ? "e2w" : "none";
    });
  });
  return _veh;
}
function evDraw(c) { return vehAssign()[c.id] || "none"; }

/* THIS HOUSEHOLD'S OWN CHARGING, NOT THE TIER AVERAGE. (the author:
   "if someone picks that cell it basically shows that this house has EV, dont
   worry about averaging").

   `cats[].ep` carries the tier's EXPECTED charging load - 0.54 kWh/day for
   HIG, being 7 % of a car plus 12 % of a two-wheeler. Showing a home that owns
   a car its tier's 0.54 while the EV screen showed a full 6.0 was the
   contradiction: four screens said "average home", one said "home with a car".
   The load is therefore scaled to the vehicle this home actually has, so every
   screen - flow, energy, bill - describes the same household.

   THE DISTRICT TOTALS ARE UNAFFECTED. They come from the solved model, which
   used the shares. This scales one household's DISPLAY, and because the
   assignment above hits the exact counts, summing all 393 representative homes
   still reproduces the tier shares. */
const _evDay = {};
function evProfileDailyKwh(c) {
  /* The profile's OWN daily energy for this category, measured rather than
     assumed. Scaling against the share arithmetic (0.07 x 6 + 0.12 x 1 = 0.54)
     left a car showing 7.17 kWh/day instead of 6.0, because `cats[].ep` also
     carries the period uplift the demand model applies. Measuring the profile
     removes that 19 % error and makes the flow agree with the EV screen. */
  if (_evDay[c.cat] != null) return _evDay[c.cat];
  const k = cat(c);
  let tot = 0;
  for (let h = 0; h < 24; h++) {
    const i = idx["jan_wd_" + (h < 10 ? "0" : "") + h];
    if (i == null) continue;
    tot += k.epv !== 2 ? (c.b * k.ep[i]) / c.hh : k.ep[i];
  }
  _evDay[c.cat] = tot;
  return tot;
}
function evScale(c) {
  const P = D.ev.params, veh = evVehicle(c);
  const mine = veh === "car" ? (num(P.ev_car_kwh_per_day) || 0)
             : veh === "e2w" ? (num(P.e2w_kwh_per_day) || 0) : 0;
  if (!mine) return 0;
  const day = evProfileDailyKwh(c);
  return day > 0 ? mine / day : 0;
}
/* The override is keyed BY HOME. A single global would have applied one
   choice to every household the moment it was touched. */
function evVehicle(c) {
  return evDraw(c);      // fixed per home; the app does not ask
}
function hasEv(c) {
  return evVehicle(c) !== "none";
}

function evChooser(c) {
  const o = evOwnership(c), veh = evVehicle(c);
  const pc = (x) => (x * 100).toFixed(0) + "%";
  const what = veh === "car" ? "an electric car" : "an electric two-wheeler";
  const share = veh === "car" ? o.car : o.e2w;
  return `<div class="card tight">
    <div class="label">This household</div>
    <div class="h" style="margin-top:6px;font-size:15px">Has ${what}</div>
    <div class="sub" style="margin-top:7px">Every figure below is this home's
      own. ${pc(share)} of ${TIER[c.cat]} homes have one, and the district
      totals use that share.</div>
  </div>`;
}

/* ---------------- EV ---------------- */
/* WHAT THIS HOUSEHOLD ACTUALLY DRIVES..

   THE MODEL CANNOT ANSWER THIS, AND THAT IS THE POINT. Ownership enters the
   model as a FRACTION OF ENERGY, not a flag on a home: costs.py returns
   `ev_cars_per_household(income) * car_kwh + e2w_share(income) * e2w_kwh`, so
   every EWS/LIG household is charged 0.05 of a scooter every day. Nobody owns
   a scooter; everybody owns a twentieth of one. Tiers are homogeneous by
   design (thesis 3.2) and there is no ownership process anywhere (3.9.4).

   Three ways to present that, and only one is both useful and honest:
     (a) show the fraction - model-exact and meaningless to a resident;
     (b) hide the screen below some tier threshold - implies EWS/LIG owns NO
         electric vehicle, which is false, 5 % do;
     (c) DRAW one household from the tier's own share, and say that is what
         it is. Chosen.

   THE PRINCIPLE THAT MAKES (c) DEFENSIBLE: average the continuous, sample the
   discrete. A home really can carry 2.97 m2 of collector, so area stays an
   average. A home cannot own 0.05 of a scooter, so ownership is sampled.

   THE DRAW IS DETERMINISTIC, NOT RANDOM. It is a hash of the cell id, so a
   given home shows the same vehicle on every load, every device and every
   rebuild. Nothing shuffles between sessions. Across all 393 homes the drawn
   shares track the model's (HIG 16.1 % against 19 %, MIG 17.6 % against 20 %,
   EWS/LIG 6.8 % against 5 %; the gaps are sampling noise on small counts).

   ONE DRAW, NOT TWO. The pre-redesign app drew a car, then drew a scooter
   only if that missed, which silently shrank the scooter share to
   (1 - car) x e2w - 11.2 % instead of 12 % for HIG. A single uniform split
   across [car | scooter | none] gives the exact marginals. */
function noise(seed) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  h = Math.imul(h ^ (h >>> 15), 2246822507);
  h = Math.imul(h ^ (h >>> 13), 3266489909);
  return ((h ^= h >>> 16) >>> 0) / 4294967295;
}
function tabEv(c) {
  const P = D.ev.params, m = state.m, inc = INCOME[c.cat];
  const veh = evVehicle(c);
  const pack = veh === "car" ? P.battery_kwh.ev_car : P.battery_kwh.e2w;
  const need = veh === "car" ? P.ev_car_kwh_per_day : P.e2w_kwh_per_day;
  const shape = P.residential_charging_daypart_shape;
  const tariffs = DP.map((dp, i) => SL[at(m, state.dt, i)]);
  const okWin = DP.map((d, i) => i).filter((i) => i >= 8 || (i * 2 + 2) <= state.leave);
  const raw = DP.map((dp, i) => (okWin.indexOf(i) >= 0 ? (shape[DP[i]] || 0) : 0));
  const rawSum = raw.reduce((a, b) => a + b, 0) || 1;
  const alloc = raw.map((v) => (need * v) / rawSum);
  const shiftRes = (D.ev.smart_charging && D.ev.smart_charging.shift_res) || 0;
  const fee = (D.ev.smart_charging && D.ev.smart_charging.fee_inr_kwh) || 0;
  let plan = alloc.slice();
  if (state.smart) {
    let moved = 0;
    plan = alloc.map((v) => { const keep = v * (1 - shiftRes); moved += v - keep; return keep; });
    const dest = tariffs.map((t, i) => ({ i, imp:t.imp })).sort((a, b) => a.imp - b.imp)
      .map((o) => o.i).filter((i) => okWin.indexOf(i) >= 0).slice(0, 3);
    dest.forEach((i) => { plan[i] += moved / dest.length; });
  }
  const cost = (a) => a.reduce((s, v, i) => s + v * tariffs[i].imp, 0);
  const dumb = cost(alloc), smart = cost(plan) + (state.smart ? need * fee : 0);
  const offKwh = plan.reduce((a, v, i) => a + (tariffs[i].band === "off_peak" ? v : 0), 0);
  const offShare = need > 0 ? offKwh / need : 0;
  const peakT = Math.max.apply(null, tariffs.map((t) => t.imp));
  const minT = Math.min.apply(null, tariffs.map((t) => t.imp));
  const v2gPack = D.ev.v2g_pack_kwh_day, deg = D.ev.v2g_degradation_inr_kwh;
  const planMax = Math.max.apply(null, plan) || 1;
  const ring = 2 * Math.PI * 31;
  return scrubber(ctx()) + evChooser(c) + `
  <div class="card">
    <div class="spread">
      <div>
        <div class="label">Charged off-peak by ${hhmm(state.leave)}</div>
        <div style="display:flex;align-items:baseline;gap:4px;margin-top:3px">
          <span class="big">${Math.round(offShare * 100)}</span><span style="font-size:16px;font-weight:600;color:var(--dim)">%</span>
        </div>
        <div class="note" style="margin-top:3px">${offKwh.toFixed(1)} of tonight's ${need} kWh land in off-peak · ${pack} kWh ${veh === "car" ? "car" : "scooter"} pack</div>
      </div>
      <svg viewBox="0 0 74 74" style="width:74px;flex:none">
        <circle cx="37" cy="37" r="31" fill="none" stroke="var(--line)" stroke-width="8"/>
        <circle cx="37" cy="37" r="31" fill="none" stroke="var(--batt)" stroke-width="8" stroke-linecap="round"
          stroke-dasharray="${(ring * offShare).toFixed(1)} ${ring.toFixed(1)}" transform="rotate(-90 37 37)"/>
        <g stroke="var(--batt)" stroke-width="1.7" fill="none" stroke-linecap="round" transform="translate(20 30)"><path d="M2 10h30M4 10l3.5-8h21l3.5 8M6 15h3M25 15h3"/></g>
      </svg>
    </div>
    <div style="display:flex;gap:8px;margin-top:16px">
      <div class="tile light" style="flex:1"><div class="label">Tonight's charge</div><div style="font-size:19px;font-weight:600;margin-top:2px">${fr(smart)}</div></div>
      <div class="tile light" style="flex:1"><div class="label">Smart saving</div><div style="font-size:19px;font-weight:600;margin-top:2px;color:var(--good)">${fr(Math.max(0, dumb - smart))}</div></div>
    </div>
  </div>

  <div class="card">
    <div class="spread" style="align-items:baseline;margin-bottom:12px">
      <span class="h">Charging plan</span>
      <span class="note">${need} kWh over ${state.smart ? "cheapest hours" : "arrival hours"}</span>
    </div>
    <div class="bars" style="height:96px">
      ${plan.map((v, i) => `<div class="col"><div class="bar" style="height:${Math.max(3, (v / planMax) * 78).toFixed(0)}px;background:${v < 0.02 ? "var(--line)" : (BAND_COLOR[tariffs[i].band] || "var(--solar)")}"></div>
        <span class="cl" style="color:${v > 0.02 ? "var(--ink)" : "var(--dim)"}">${DP[i].slice(0, 2)}</span></div>`).join("")}
    </div>
    <div class="legend"><span><i class="swatch" style="background:var(--batt)"></i>Off-peak</span>
      <span><i class="swatch" style="background:var(--solar)"></i>Solar / shoulder</span>
      <span><i class="swatch" style="background:var(--warn)"></i>Peak</span></div>
  </div>

  <div class="card flush">
    <button class="rowitem" style="width:100%" data-act="smart">
      <span style="flex:1;min-width:0"><span style="display:block;font-size:13.5px;font-weight:600">Smart charging</span>
        <span class="note" style="display:block;margin-top:2px">${state.smart ? "Shifting " + Math.round(shiftRes * 100) + "% of the charge into off-peak" : "Charging as soon as you plug in"}</span></span>
      <span class="switch ${state.smart ? "on" : ""}"><i></i></span>
    </button>
    <button class="rowitem" style="width:100%;border-bottom:0" data-act="v2g">
      <span style="flex:1;min-width:0"><span style="display:block;font-size:13.5px;font-weight:600">Sell back at peak (V2G)</span>
        <span class="note" style="display:block;margin-top:2px">${state.v2g ? v2gPack + " kWh/day at " + fr(peakT) + " less " + fr(deg) + " wear = " + fr(v2gPack * (peakT - deg)) + "/day" : "Willingness in " + inc + "-income homes: " + Math.round((P.v2g_willingness_by_income[inc] || 0) * 100) + "%"}</span></span>
      <span class="switch ${state.v2g ? "on" : ""}"><i></i></span>
    </button>
  </div>

  <div class="card">
    <div class="h" style="margin-bottom:10px">Leave the house at</div>
    <div class="row"><span class="med" style="min-width:74px">${hhmm(state.leave)}</span>
      <input type="range" min="4" max="12" step="1" value="${state.leave}" data-act="leave"></div>
    <div class="sub" style="margin-top:10px">Charge finishes by ${hhmm(state.leave)}. ${state.smart ? "Off-peak import is " + fr(minT) + "/kWh against " + fr(peakT) + " at peak." : "Turn on smart charging to move it into the cheap hours."}</div>
  </div>`;
}

/* ---------------- picker + first run ---------------- */
function picker() {
  const N = D.map.n, w = 300 / N, t = (w - 0.9).toFixed(2);
  const inSect = (o) => state.sector === "all" || sectorOf(o) === state.sector;
  const rects = D.map.cells.map((mc, k) => {
    const r = Math.floor(k / N), c = k % N, own = owner[r + "-" + c];
    const dim = own && ((state.tier !== "all" && own.cat !== state.tier)
                        || !inSect(own));
    const fill = own ? (own.id === state.cellId ? "var(--ink)" : dim ? "#DFDAD1" : TIER_SWATCH[own.cat]) : (LU_FILL[mc[2]] || "#E5E0D6");
    return `<rect x="${(c * w + 0.45).toFixed(2)}" y="${((N - 1 - r) * w + 0.45).toFixed(2)}" width="${t}" height="${t}" rx="1.3" fill="${fill}"${own ? ` data-act="pick" data-arg="${own.id}" style="cursor:pointer"` : ""}/>`;
  }).join("");
  /* Sectors that actually contain homes, so the filter never offers an empty
     one. 22 of the 25 do. */
  const sectors = Array.from(new Set(RES.map(sectorOf)))
    .filter((n) => n > 0).sort((a, b) => a - b);
  /* NO .slice(0, 14). The list used to stop at fourteen homes with no way to
     reach the rest, which is what made most of the town unselectable. The
     sector filter is what makes a full list navigable instead. */
  /* Sorted by sector, then by home number, so a sector reads Home 1, 2, 3...
     from the top. RES itself is in grid order, which interleaved sectors and
     scattered the home numbers. */
  const list = RES.filter((c) => (state.tier === "all" || c.cat === state.tier)
                                 && inSect(c))
    .sort((a, b) => (sectorOf(a) - sectorOf(b)) || (houseNo(a) - houseNo(b)));
  return `<div class="overlay" data-act="closepicker"><div class="sheet" data-stop="1">
    <div class="sheet-head">
      <div class="spread">
        <div>
          <div style="font-size:19px;font-weight:600;letter-spacing:-.02em">Choose your home</div>
          <div class="sub" style="margin-top:3px">Tap any coloured cell — every residential cell in the master plan is a real home. One representative household per cell.</div>
        </div>
        ${state.onboard ? "" : '<button class="close" data-act="closepicker"><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 3l6 6M9 3l-6 6"/></svg></button>'}
      </div>
      <div style="display:flex;gap:5px;margin-top:12px">
        ${[["all", "All " + RES.length], ["residential_high", "HIG"], ["residential_mid", "MIG"], ["residential_low", "EWS/LIG"]]
          .map(([k, l]) => `<button class="chip ${state.tier === k ? "on" : ""}" data-act="tier" data-arg="${k}">${l}</button>`).join("")}
      </div>
      <div class="chips" style="margin-top:8px">
        <button class="chip ${state.sector === "all" ? "on" : ""}" data-act="sector" data-arg="all">All sectors</button>
        ${sectors.map((n) => `<button class="chip ${state.sector === n ? "on" : ""}" data-act="sector" data-arg="${n}">Sector ${n}</button>`).join("")}
      </div>
    </div>
    <div class="sheet-body">
      <div style="padding:10px;border-radius:24px;background:var(--soft);border:1px solid var(--line)">
        <svg viewBox="0 0 300 300" class="townmap">${rects}</svg>
        <div class="legend" style="padding:0 4px">
          <span><i class="swatch" style="background:${TIER_SWATCH.residential_low}"></i>EWS/LIG</span>
          <span><i class="swatch" style="background:${TIER_SWATCH.residential_mid}"></i>Mid</span>
          <span><i class="swatch" style="background:${TIER_SWATCH.residential_high}"></i>HIG</span>
          <span><i class="swatch" style="background:#C9C246"></i>Solar farm</span>
          <span><i class="swatch" style="background:#D6E1CC"></i>Parks</span>
          <span><i class="swatch" style="background:#C2D6E4"></i>Water</span>
        </div>
      </div>
      <div class="label" style="margin:18px 0 4px">${state.tier === "all" ? "Nearest homes" : TIER[state.tier] + " homes"}</div>
      ${list.map((c) => {
        const th = thermalOf(c);
        return `<button class="cellbtn ${c.id === state.cellId ? "on" : ""}" data-act="pick" data-arg="${c.id}">
          <span class="av" style="background:${TIER_SWATCH[c.cat]}">${TIER_LETTER[c.cat] || "H"}</span>
          <span style="flex:1;min-width:0"><span style="display:block;font-size:13.5px;font-weight:600">${cellName(c)}</span>
            <span class="note" style="display:block;margin-top:1px">${hasEv(c) ? `<span style="color:var(--solar);font-weight:600">${evVehicle(c) === "car" ? "⚡ EV car" : "⚡ Scooter"}</span> · ` : ""}${TIER[c.cat]} · ${c.hh} homes · ${fm2(th.m2)} m² collector</span></span>
          <span style="text-align:right"><span style="display:block;font-size:13px;font-weight:600">${(c.kwp / c.hh).toFixed(1)} kWp</span>
            <span class="note" style="display:block">rooftop</span></span>
        </button>`;
      }).join("")}
    </div></div></div>`;
}

function firstRun() {
  const t = D.town;
  return `<div class="first">
    <div style="flex:1;display:flex;flex-direction:column;justify-content:center">
      <svg viewBox="0 0 120 120" style="width:100px;margin-bottom:24px">
        <circle cx="60" cy="60" r="52" fill="none" stroke="var(--line)" stroke-width="8"/>
        <circle cx="60" cy="60" r="52" fill="none" stroke="var(--solar)" stroke-width="8" stroke-linecap="round"
          stroke-dasharray="${(2 * Math.PI * 52 * (t.renewable_share || 0)).toFixed(0)} ${(2 * Math.PI * 52).toFixed(0)}" transform="rotate(-90 60 60)"/>
        <path d="M60 38 40 56v22h40V56z" fill="none" stroke="var(--ink)" stroke-width="4" stroke-linejoin="round"/>
        <path d="M55 78V66h10v12" fill="none" stroke="var(--ink)" stroke-width="3.4" stroke-linejoin="round"/>
      </svg>
      <div style="font-size:34px;font-weight:600;letter-spacing:-.035em">Urja</div>
      <div class="sub" style="font-size:16px;margin-top:10px">Your rooftop, your hot water and your bill — the same model the town runs on, for one house at a time.</div>
      <div style="display:flex;flex-direction:column;gap:14px;margin-top:26px">
        ${[["var(--solar)", "Live flow.", "Watch solar, house and grid trade places through the day."],
           ["var(--water)", "Solar water heating.", ST.total_m2 != null ? fn0(ST.total_m2) + " m² of collector across " + fn0(ST.roofs) + " roofs — yours included." : "The sun heats your water before any electricity is used."],
           ["var(--good)", "Autopilot.", "Sell surplus to a neighbour at " + fr(D.p2p.price_inr_kwh) + " instead of " + fr(D.p2p.export_inr_kwh) + "."],
           ["var(--grid)", fn0(t.population / 1000) + "k residents.", esc(t.name) + " runs on " + pc(t.renewable_share) + " renewables at " + fr(t.net_cost_inr_kwh) + "/kWh, " + signed(t.vs_bau_cost_pct, "%") + " on cost against business as usual."]]
          .map(([col, b, s]) => `<div style="display:flex;gap:12px;align-items:flex-start">
            <span style="flex:none;width:24px;height:24px;border-radius:8px;background:${col};opacity:.2"></span>
            <span style="font-size:13.5px;line-height:1.45"><b>${b}</b> <span style="color:var(--dim)">${s}</span></span></div>`).join("")}
      </div>
    </div>
    <button class="cta" data-act="startpick" style="justify-content:center;font-size:15px;font-weight:600;padding:17px">Choose my home</button>
  </div>`;
}

/* ---------------- events ---------------- */
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  const act = el.dataset.act, arg = el.dataset.arg;
  if (act === "closepicker" && e.target.closest("[data-stop]") && !e.target.closest('[data-act="closepicker"]')) return;
  switch (act) {
    case "tab": state.tab = arg; store.set("tab", arg); break;
    case "picker": if (!state.viva) state.picker = true; break;
    case "closepicker": state.picker = false; break;
    case "startpick": state.onboard = false; state.picker = true; break;
    case "pick": state.cellId = arg; store.set("cell", arg); state.picker = false; state.onboard = false; break;
    case "tier": state.tier = arg; break;
    case "sector": state.sector = arg === "all" ? "all" : +arg; break;
    case "month": state.m = +arg; break;
    case "chart": state.chart = arg; break;
    case "scrub": state.scrub = !state.scrub; break;
    case "live": state.sim = null; state.scrub = false; store.set("sim", null); break;
    case "simmonth": setSim({ m:+arg }); break;
    case "simdt": setSim({ dt:arg }); break;
    case "ap": state.autopilot = !state.autopilot; store.set("ap", state.autopilot); break;
    case "smart": state.smart = !state.smart; store.set("smart", state.smart); break;
    case "v2g": state.v2g = !state.v2g; store.set("v2g", state.v2g); break;
    case "viva": state.viva = !state.viva; break;
    default: return;
  }
  render();
});
document.addEventListener("input", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  if (el.dataset.act === "hour") setSim({ h:+el.value });
  else if (el.dataset.act === "leave") { state.leave = +el.value; store.set("leave", state.leave); }
  else return;
  render();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "v" || e.key === "V") { state.viva = !state.viva; render(); }
  else if (e.key === "Escape" && (state.viva || state.picker)) { state.viva = false; state.picker = false; render(); }
});
function setSim(patch) {
  const n = ctx();
  state.sim = Object.assign({ m:n.m, dt:n.dt, h:Math.floor(n.h) }, state.sim || {}, patch);
  state.scrub = true;
  store.set("sim", state.sim);
}

render();
setInterval(() => { if (!state.viva && !state.picker) render(); }, 30000);

/* ============================================================================
   DATA VINTAGE CHECK - ported back from the pre-redesign app.js, 2026-08-19.
   ----------------------------------------------------------------------------
   WHY THIS EXISTS. This app is cache-first so it works with no signal, which
   means it shows what it CACHED, not what is on the server. Regenerate data.js
   and a phone can keep serving the previous model run indefinitely, with no
   symptom at all. That has already happened once: sw.js advertised the
   2026-08-14 pin, data.js had moved to the 2026-08-15 regen, and app.js
   separately carried a hardcoded "-56% CO2" against a real -60.8%. Three
   sources of truth, two of them wrong, nothing visibly broken.

   THE CONTRACT. sw.js's VERSION ends in `-dataYYYYMMDD`, which must be the date
   stamped inside data.js by scripts/app_data_extract.py. This reads the version
   back at runtime and compares the two. A trailing letter is allowed for a
   second same-day extract (`-data20260819b`), so only the eight digits are
   compared.

   DESIGN: SILENT WHEN HEALTHY. A resident app should not carry a permanent
   "up to date" badge, but it must shout when it is wrong. Nothing renders
   unless the check actually fails, and nothing renders when the check simply
   cannot run - nagging a genuinely offline user about being offline is noise.
   ========================================================================== */
function dataVintageCheck() {
  const dataDate = String((D.meta && D.meta.generated) || "").replace(/-/g, "");
  if (!dataDate) return;

  // Network-first ON PURPOSE: a cached sw.js would defeat the whole check.
  fetch("sw.js", { cache: "reload" })
    .then((r) => (r.ok ? r.text() : ""))
    .then((t) => {
      const v = (t.match(/VERSION\s*=\s*"([^"]+)"/) || [])[1] || "";
      if (!v) return;                       // offline or blocked - stay quiet
      const stamped = (v.match(/data(\d{8})/) || [])[1];
      if (stamped === dataDate) return;     // healthy - stay quiet
      showVintageBanner(
        stamped
          ? "This app is showing model data from " + fmtStamp(dataDate) +
            ", but its offline cache was published for " + fmtStamp(stamped) + "."
          : "This app's offline cache carries no data stamp, so its vintage " +
            "cannot be verified.");
    })
    .catch(() => {});                       // offline - stay quiet
}

function fmtStamp(s) {
  return s && s.length === 8 ? s.slice(6, 8) + "/" + s.slice(4, 6) + "/" + s.slice(0, 4) : s;
}

function showVintageBanner(msg) {
  if (document.getElementById("dv-banner")) return;
  const bar = document.createElement("div");
  bar.id = "dv-banner";
  bar.setAttribute("role", "alert");
  bar.style.cssText =
    "flex:none;margin:0 20px 10px;padding:12px 14px;border-radius:16px;" +
    "background:#F6E4DC;border:1px solid #D8A48B;color:#7A3B22;" +
    "font-size:12.5px;line-height:1.5;display:flex;gap:10px;align-items:flex-start";
  bar.innerHTML =
    '<span style="flex:1">' + esc(msg) +
    ' The numbers below may be out of date.</span>' +
    '<button id="dv-fix" style="flex:none;padding:7px 11px;border-radius:99px;' +
    'background:#7A3B22;color:#FCFBF7;font-size:12px;font-weight:600">Update</button>';
  const main = document.getElementById("main");
  if (main && main.parentNode) main.parentNode.insertBefore(bar, main);
  const btn = document.getElementById("dv-fix");
  if (btn) btn.addEventListener("click", async () => {
    btn.textContent = "Updating";
    try {
      for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister();
      for (const k of await caches.keys()) await caches.delete(k);
    } catch (e) { /* fall through to the reload anyway */ }
    location.reload();
  });
}

dataVintageCheck();
