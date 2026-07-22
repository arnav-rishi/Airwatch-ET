# Demo Video — Script & Shot List

**Target: 3:00–3:30.** Judges watch many of these; the enforcement chain must be
on screen before 0:45.

---

## Before you record

- [ ] **Merge the PR.** Vercel builds from `master`. Unmerged, the live URL has
      none of this.
- [ ] Verify keys live: `OPENAQ_API_KEY`, `WAQI_TOKEN`, `OPENWEATHER_API_KEY`,
      `AZURE_OPENAI_*`, `FIRMS_MAP_KEY`
- [ ] **Pre-warm the Enforcement tab once.** First load runs 6 LLM calls (~48 s).
      The attribution cache holds 10 minutes — record inside that window and the
      tab loads fast. Re-warm if you overrun.
- [ ] Check which cities have candidates today: `GET /api/intel/enforcement/auto`
      → `hotspots[].candidate_sources`. **Guwahati, Pune and Kolkata** have been
      reliable. Gwalior has sometimes had none.
- [ ] Browser at 1920×1080, zoom 100%, bookmarks bar hidden
- [ ] Close the terminal unless a shot calls for it

> **Seasonality + freshness — decide your framing.** It is monsoon: national AQI is
> genuinely low and FIRMS shows zero fires near cities. This is REAL current data —
> the top reading is ~85, not the 400s stale feeds used to imply. Name it once and
> make it a strength: "we refuse to rank a hotspot on a reading we can't confirm is
> recent." A judge who spots the low numbers unmentioned assumes something's broken;
> framed, it's rigour. Do not fake a fire or a high reading.

---

## 0:00–0:20 — The problem

**Screen:** Title card → CAG statistic

**VO:**
> India has over 900 air quality monitoring stations. In 2024, a government audit
> found that only thirty-one percent of cities with that data had any actionable
> response protocol attached to it.
>
> The measurement exists. The intervention doesn't.

**Shot:** Hold on `31%` for a beat. Don't rush the number.

---

## 0:20–0:40 — Framing the real question

**Screen:** National AQI map, live. Slow zoom toward north India.

**VO:**
> This is live CPCB data across 84 cities. Every dashboard in this space stops
> here — it tells you *where* the air is bad.
>
> But an inspector doesn't need to know Delhi is polluted. They need to know
> which of the two hundred and thirteen registered emission sources within range
> to visit first, this morning.

**Shot:** Hover one high-AQI marker so the tooltip shows the CPCB reading and
`Live · CPCB via OpenAQ` with the reading's age.

---

## 0:40–1:30 — The enforcement chain *(the core)*

**Screen:** Enforcement tab. Map with hotspot, candidates, wind axis, screening radius.

**VO:**
> This is the enforcement agent. For each hotspot it correlates the reading
> against a registry of nearly eight thousand registered
> emission sources — industries, construction sites, waste sites, diesel depots —
> each with real coordinates.
>
> The dashed cyan line is the live wind axis. The dashed circle is the
> twenty-five kilometre screening radius. Every dot is a mapped facility, sized
> by how strongly the evidence points at it.

**Shot:** Click a hotspot chip (**Guwahati** or **Pune**). Let the map redraw.

**VO (continuing):**
> Sources the wind is carrying *away* from the station are excluded outright —
> they cannot physically be causing this reading.

**Shot:** Scroll to priority #1. Expand the evidence block.

**VO:**
> Here's the recommendation: a named facility, its distance and bearing, and the
> component scores behind it. Coordinates. A link to the facility on
> OpenStreetMap. Every number is checkable.

---

## 1:30–2:05 — Dispersion physics *(the differentiator)*

**Screen:** Evidence block — stability class row.

**VO:**
> The transport score isn't a heuristic. It's a Gaussian plume model — Briggs
> urban dispersion curves, selected by Pasquill-Gifford atmospheric stability
> class, derived from live wind speed and time of day.
>
> That matters more than it sounds. On a calm clear night — a class F inversion —
> a source thirteen kilometres away ranks second, because stable air holds the
> plume together. Under windy daytime mixing, that same source drops off the
> shortlist entirely.
>
> The question isn't "is it upwind". It's "can it reach here, today".

**Shot:** Point at `Stability class E — stable (night, light wind)` and the
`km downwind / km off centreline` row.

---

## 2:05–2:25 — Satellite layer

**Screen:** Header line — `🛰 Satellite fire layer active`.

**VO:**
> Open waste burning is illegal, so it appears in no registry anywhere. We use
> NASA FIRMS satellite fire detection to find it, ranked in the same candidate
> list and weighted by the satellite's own confidence.
>
> Right now it's monsoon season — a hundred and thirty-eight active fires across
> India, none within twenty-five kilometres of a monitored city. The system says
> so explicitly rather than showing an empty panel. This layer carries real
> weight from October, when stubble burning drives the northern air crisis.

> **Note:** the honest framing *is* the strong move here. Do not fake a fire.

---

## 2:25–2:50 — Impact & rigour

**Screen:** Split — impact figures, then a terminal running `pytest tests/ -q`.

**VO:**
> Two hundred and thirteen eligible sources within range of the Delhi station
> narrow to five. That's a forty-two-fold reduction in search space, against a
> two percent chance of picking one of those five blind.
>
> Signal to dispatch-ready: under fifty seconds.
>
> Everything deterministic is tested — a hundred and sixty-two tests, no API keys, no
> network. Including the one that matters most: the forecast is scored against a
> persistence baseline, and it reports failure when it loses.

**Shot:** `162 passed` on screen. Hold two seconds.

---

## 2:50–3:15 — Close

**Screen:** Architecture diagram (`docs/ARCHITECTURE.md`, sequence view).

**VO:**
> The design decision underneath all of this: most systems ask a language model
> to decide. We ask it to narrate.
>
> Attribution, then deterministic geospatial correlation, then narration. The
> model cannot invent a facility — it selects from a ranked shortlist and cites
> the evidence it was given.
>
> Everything a judge can check is computed. Everything the model asserts is
> labelled as such.

**Screen:** Title card + repo URL.

---

## Recording notes

**Do**
- Record VO separately, then cut screen capture to it. Live narration while
  clicking always runs long.
- Let the map animate. Motion holds attention; the redraw is one of the better
  visual moments.
- Say real numbers — "213 sources", "42-fold" — not "significantly fewer".

**Don't**
- Show a loading spinner. Pre-warm the cache.
- Read the score components aloud one by one. Point; the viewer reads faster.
- Claim pollution reduction, cost savings or compliance improvement. We don't
  measure any of them, and a domain-expert judge will ask.
- Demo a city with zero candidates. Check first.

**If a live API fails mid-record:** the app degrades visibly rather than
crashing — fallback stations still render and the header shows staleness. If
Azure OpenAI is down the Enforcement tab can't populate, so re-record. Have one
good take banked before experimenting.

---

## Fallback: fully offline take

If live APIs are unreliable at record time, `pytest tests/ -q` plus
`scripts/benchmark_spatial.py` demonstrate the deterministic core — scoring,
dispersion, exclusions, impact arithmetic, spatial index — with no network at
all. Weaker as a demo, but it never fails, and it still shows the part of the
system that does the actual reasoning.
