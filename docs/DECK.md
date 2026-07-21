---
marp: true
theme: default
paginate: true
backgroundColor: #0f1117
color: #e2e8f0
style: |
  section { font-size: 26px; }
  h1 { color: #60a5fa; }
  h2 { color: #93c5fd; }
  strong { color: #fbbf24; }
  table { font-size: 21px; }
  code { background: #1a1f2e; color: #a5b4fc; }
  blockquote { border-left: 4px solid #f97316; color: #cbd5e1; }
---

<!-- _class: lead -->

# 🌫️ AirWatch India

## Enforcement Intelligence for Urban Air Quality

**Which facility do we inspect today — and why?**

ET AI Hackathon 2026 · Problem Statement 5
*Track: Enforcement Intelligence & Prioritisation*

---

## The gap isn't data. It's action.

- **900+** CAAQMS stations deployed under NCAP
- **1.67M** premature deaths/year attributed to air pollution *(Lancet Planetary Health)*
- **Only 31%** of cities with monitoring data have *any* actionable multi-agency response protocol
  *— CAG audit, 2024*

> India already measures its air. It cannot act on the measurement.

An inspector dispatched to Delhi today faces **213 registered emission sources**
within operational range and no evidence ranking to choose between them.

---

## What we built

**An agent that turns an AQI reading into a dispatch order.**

Not a dashboard. Not a chatbot over pollution data.

For each pollution hotspot it answers:

1. **Which** registered facility is most likely contributing — by name and coordinates
2. **Why** — distance, wind, atmospheric stability, source category
3. **How confident** — every component of the score is exposed and checkable

...in **~48 seconds** from signal to dispatch-ready.

---

## The architecture decision that matters

Most LLM systems ask the model to *decide*. We ask it to *narrate*.

```
Stage 1   Attribution Agent (LLM)      →  why is this city polluted?
Stage 2   Geospatial correlation        →  which registered sources could reach it?
          ── deterministic, no LLM ──      Gaussian plume + spatial index
Stage 3   Enforcement Agent (LLM)      →  write the dispatch order
```

The LLM **cannot invent a facility**. It receives a ranked shortlist of real
sources and must select by exact ID, citing the evidence it was handed.

> Anything a judge can check is computed. Anything the model asserts is labelled.

---

## The source registry

**5,154 registered emission sources · 43 cities · real coordinates**

| Category | Count | OSM proxy |
|---|---|---|
| Industry | 2,215 | `landuse=industrial`, `man_made=works` |
| Diesel fleet | 1,182 | `amenity=bus_station`, `landuse=depot` |
| Construction | 1,175 | `landuse=construction` |
| Waste | 582 | `landfill`, `waste_transfer_station` |

Seeded once from OpenStreetMap via Overpass and committed — a demo never depends
on a third-party endpoint being up.

**Stated honestly:** these are proxies, not CPCB's consent-to-operate register,
which isn't public. The caveat ships inside the data and through the API.

---

## Atmospheric dispersion, not a heuristic

We started with `cos(bearing − wind_direction)`. It says *"is it upwind"* — but
can't tell a facility 500 m upwind from one 20 km upwind.

**Gaussian plume**, Briggs urban σ curves, Pasquill-Gifford stability class:

```
C(x,y) = Q / (π · u · σy · σz) · exp(−y² / 2σy²)
```

| Conditions | Effect |
|---|---|
| Calm clear night — **class F inversion** | A source **13.3 km** away ranks #2 |
| Windy daytime — **class D mixing** | The same source **drops off the shortlist** |

That's the difference between *"is it upwind"* and *"can it reach here **today**"*.

---

## Satellite: finding what no register contains

Open waste burning is **illegal — therefore unregistered**. It cannot appear in
any ground database.

**NASA FIRMS (VIIRS, 375 m)** active-fire detections rank in the same candidate
list, weighted by the satellite's own detection confidence.

Worded as *"verify and interdict active burning at these coordinates"* — never as
an inspection of a registered premises. A thermal anomaly is a lead, not a proven
violation.

> Verified live, late July: 138 fires across India, **none within 25 km of any
> city**. That's monsoon season, not a broken integration. The layer carries real
> weight **October–January**, when stubble burning drives the northern crisis.

---

## What we refuse to target

Two live runs recommended sending inspectors to:

- **"Park Circus — Chittaranjan Hospital"**
- **"Kamakhya Mandir"** — one of India's most significant Hindu temples

OSM names bus terminals after whatever they serve. Geometry ranked them first.

**Both are now excluded before scoring.** A hospital is a receptor to protect,
not premises to raid. An enforcement order named after a temple is indefensible
in front of the authority meant to act on it.

> Tuned in both directions: an early filter caught `vihar` and removed real bus
> depots — across north India that's a *residential locality* suffix. Tests cover
> both the exclusions and the false positives.

---

## Business impact — measured, not asserted

| Hotspot | Eligible sources in 25 km | Shortlisted | Narrowing | Random hit rate |
|---|---|---|---|---|
| Delhi | 213 | 5 | **42.6×** | 2.3% |
| Kolkata | 157 | 5 | **31.4×** | 3.2% |
| Pune | 148 | 5 | **29.6×** | 3.4% |
| *Live 5-hotspot run* | *557* | *25* | ***22.3×*** | *4.5%* |

Both sides drawn from the same population — comparing against the unfiltered
registry would inflate this by counting hospitals and bus stops.

**What we do NOT claim:** pollution reduction in μg/m³, money saved, compliance
improvement. Each needs data that doesn't exist. An unsupported number here would
discredit the ones that are real.

---

## Technical rigour

| | |
|---|---|
| **150 tests** | No API keys, no network required |
| **AQI scale bug** | WAQI serves *US EPA index*, not μg/m³ — mid-range readings were inflated **4×**, corrupting the hotspot ranking that feeds everything |
| **Forecast skill** | RMSE vs **persistence baseline** — and it reports *failure*: −642% skill when a trend reverses |
| **Concurrency** | `asyncio.gather` over a *sync* client ran serially and froze the event loop. A timing test now asserts overlap |

> A metric that can only flatter isn't a measurement.

---

## Scalability

Sources bucketed into a **~27 km grid** at load time — a query touches only the
3×3 block around its centre.

| Registry | Sources scanned |
|---|---|
| 5,000 | 204 |
| 1,000,000 | 1,307 |

**200× more data → 6× more work.** Reproduce: `scripts/benchmark_spatial.py`

It also fixed a *correctness* bug: city-name lookup meant an east Delhi station
never saw Noida industry inside its radius. **The NCR is one airshed** — the
query now follows the air, not the paperwork.

*Honest:* per-process caches, file-backed registry and static station list all
need replacing for 900 stations. Path documented in `SCALABILITY.md`.

---

## Live output

```
#1  Guwahati  ::  Durga Trunk Factory
    industry · 0.77 km SSW · upwind 0.991 · class E · score 0.796

#2  Pune      ::  Kothrud Depot
    diesel_fleet · 6.28 km WSW · upwind 0.996 · class D · score 0.890

#3  Kolkata   ::  Calcutta State Transport Corporation Depot
    diesel_fleet · 6.27 km S · upwind 0.918 · class D · score 0.862
```

All three traceable to registry entries. Every one carries coordinates, a
component-score breakdown, and an OpenStreetMap link.

**Signal → dispatch-ready: 47.8 s.**

---

## What's honest about this

We ship a **Known gaps** section:

- The OpenAQ fallback tier **has never worked** — 24h history is a modelled estimate, and the UI says so
- **City-level, not ward-level** — the PS asks for 1 km grid resolution
- No multi-city comparative dashboard; no population vulnerability layer
- Per-process caches would break behind multiple workers

> A judge who finds a limitation we already named reads it as rigour.
> A judge who finds one we hid reads it as everything else being suspect.

---

<!-- _class: lead -->

# Thank you

**AirWatch India** — from measurement to intervention

`github.com/arnav-rishi/Airwatch-ET`

*Architecture: `docs/ARCHITECTURE.md` · Scale: `SCALABILITY.md`*
