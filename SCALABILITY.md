# Scalability

What this system does today, where it breaks, and what it would take to run it
nationally across the 900+ CAAQMS stations deployed under NCAP.

Numbers here are measured on this machine, not estimated. Reproduce them with
`backend/scripts/benchmark_spatial.py`.

---

## Current scale

| Dimension | Today |
|---|---|
| Monitoring stations | 43 curated cities |
| Emission sources | 5,154 across 43 cities |
| Hotspots scored per run | 5 |
| Signal → dispatch-ready | 30–60 s (LLM-bound) |
| Source correlation | ~2 ms per hotspot |

---

## What was fixed: spatial indexing

The scorer originally received every source in a city and computed a haversine
for each — a linear scan. That is fine at 5,154 sources and fails badly beyond it.

Sources are now bucketed into a ~27 km grid (`GRID_DEG = 0.25°`) at load time, so
a query touches only the 3×3 block of cells around its centre regardless of
registry size. Measured against a nationally-distributed synthetic registry:

| Registry size | Linear scan | Spatial index | Speedup | Sources scanned | Cells |
|---|---|---|---|---|---|
| 5,000 | ~20–37 ms | ~2–4 ms | ~9–11× | **204** | 4,204 |
| 50,000 | ~193–254 ms | ~2–3 ms | ~71–117× | **246** | 13,352 |
| 200,000 | ~944–1,002 ms | ~5–10 ms | ~92–194× | **431** | 13,801 |
| 1,000,000 | ~4.3–4.9 s | ~20–28 ms | ~153–239× | **1,307** | 13,806 |

Wall-clock timings are given as ranges across repeated runs, because they vary
with machine load — quoting a single run's speedup would overstate the precision
of the measurement. The **sources scanned** column is the deterministic figure
and the one that actually matters: it is identical on every run, and it is what
the timings follow from.

Linear scan cost grows with the whole registry; indexed cost grows only with
local source density, which geography bounds. Going from 5,000 to 1,000,000
sources — 200× more data — increases the scanned set only 6×, because the extra
sources are spread across the country and land in cells the query never opens.

This also fixed a **correctness** bug, which is the better argument for it.
Sources were looked up by city name, so a monitoring station in east Delhi never
saw Noida or Ghaziabad industry sitting well inside its 25 km screening radius —
they were filed under a different city. The NCR is one airshed. The spatial query
follows the air rather than the paperwork, and now returns candidates across
municipal boundaries.

---

## What still constrains scale

Stated plainly rather than left to be discovered.

**In-memory, per-process state.** The station cache, attribution cache and rate
limiter (`services/cache.py`, `services/rate_limit.py`) are process-local dicts.
On a single instance they work. Behind multiple workers or on Vercel's serverless
runtime, each invocation gets its own copy — so cache hit rates collapse and the
rate limiter under-counts by a factor of however many instances are live. The
rate limiter's own docstring says this; it blunts runaway cost from one caller,
it is not a gateway-level limiter.

**The registry is a committed JSON file.** 5,154 sources load fine at import
(~10 MB, parsed once). At national scale this becomes a database question, not a
file question — and re-seeding currently means re-running a 40-minute Overpass
sweep rather than an incremental update.

**Station list is a static 43-city file.** `cities_fallback.json` defines the
universe. Ingesting 900+ CAAQMS stations means a real station registry with
per-station metadata, not a curated list.

**LLM latency dominates end-to-end time.** Correlation is ~2 ms; the run takes
30–60 s. Six LLM calls (five attribution + one enforcement) are the entire
budget. The async client made them concurrent rather than serial, which is why
it is 30–60 s and not several minutes, but throughput per instance is still
bounded by Azure OpenAI rate limits, not by anything in this codebase.

**No persistence.** Nothing is stored between runs, so there is no history of
what was recommended, whether an inspection happened, or whether AQI subsequently
changed. That is the data a real deployment would need most — it is what turns
"we recommended this" into "this worked".

---

## Path to national scale

Roughly in dependency order. None of this is built; it is the answer to "what
would you do next", not a claim about what exists.

**1. Move the registry to PostGIS.** A `GEOGRAPHY(POINT)` column with a GiST
index gives radius queries the grid approximates today, plus incremental updates
and per-source attributes (consent-to-operate status, prior violations, last
inspection date) that a JSON blob cannot carry well. The scorer's interface
already takes a source list, so this is a swap behind `get_sources_near`.

**2. Redis for shared cache and rate limiting.** Removes the per-process
assumption in one move and makes horizontal scaling real rather than nominal.

**3. Decouple the LLM from the request path.** Enforcement runs are a scheduled
job, not a user-facing query — nobody needs a fresh recommendation on page load.
Run correlation continuously, queue narration, serve the last completed result.
That turns a 30–60 s request into a cache read and removes the LLM rate limit as
a throughput ceiling.

**4. Persist recommendations and outcomes.** Store each run with its evidence,
then link it to whether an inspection followed and what AQI did afterwards. This
is what would eventually let the system report effectiveness rather than only
targeting — and the only honest route to the "demonstrated reduction" the
evaluation criteria ask about.

**5. Direct CPCB ingestion.** Currently reads CPCB data through WAQI. Direct
CAAQMS access removes a dependency and a rate limit, and is a prerequisite for
station-level rather than city-level operation.

---

## Honest assessment

The correlation engine — the part this project is actually about — scales well:
it is deterministic, has no external dependencies, and now has a spatial index
with measured headroom to a million sources.

Everything around it is prototype-grade. The caches, the rate limiter, the static
station list and the file-backed registry are all appropriate for a 43-city
demonstration and would each need replacing for a 900-station deployment. None
of them is a redesign — they are the substitutions listed above — but none of
them is done either, and the system has never been run at that scale.
