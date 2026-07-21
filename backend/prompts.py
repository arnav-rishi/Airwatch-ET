# ─── Source Attribution ───────────────────────────────────────────────────────

# Published CPCB / ARAI source apportionment studies for major Indian cities, as a
# structured evidence table rather than opaque prose — this is what lets the API
# response cite a specific study back to the frontend (see get_baseline_citation
# below) instead of the citation existing only inside an LLM prompt no one can see.
CPCB_SOURCE_APPORTIONMENT = {
    "Delhi": {
        "citation": "CPCB/ARAI 2021",
        "breakdown": [
            {"source": "Road dust", "pct": 28}, {"source": "Vehicles", "pct": 20},
            {"source": "Industry", "pct": 11}, {"source": "Biomass burning", "pct": 11},
            {"source": "Construction", "pct": 6}, {"source": "Secondary aerosol", "pct": 24},
        ],
    },
    "Mumbai": {
        "citation": "MPCB 2020",
        "breakdown": [
            {"source": "Transport", "pct": 30}, {"source": "Industry", "pct": 35},
            {"source": "Marine/sea salt", "pct": 18}, {"source": "Construction", "pct": 8},
            {"source": "Others", "pct": 14},
        ],
    },
    "Kolkata": {
        "citation": "WBPCB 2021",
        "breakdown": [
            {"source": "Vehicles", "pct": 25}, {"source": "Industry", "pct": 22},
            {"source": "Biomass burning", "pct": 15}, {"source": "Road dust", "pct": 18},
            {"source": "Construction", "pct": 12}, {"source": "Others", "pct": 8},
        ],
    },
    "Chennai": {
        "citation": "TNPCB 2022",
        "breakdown": [
            {"source": "Road dust", "pct": 30}, {"source": "Vehicles", "pct": 28},
            {"source": "Industry", "pct": 14}, {"source": "Construction", "pct": 15},
            {"source": "Others", "pct": 13},
        ],
    },
    "Bengaluru": {
        "citation": "KSPCB 2022",
        "breakdown": [
            {"source": "Vehicles", "pct": 35}, {"source": "Construction", "pct": 22},
            {"source": "Road dust", "pct": 20}, {"source": "Industry", "pct": 12},
            {"source": "Others", "pct": 11},
        ],
    },
    "Hyderabad": {
        "citation": "TSPCB 2021",
        "breakdown": [
            {"source": "Vehicles", "pct": 30}, {"source": "Industry", "pct": 25},
            {"source": "Road dust", "pct": 22}, {"source": "Construction", "pct": 13},
            {"source": "Others", "pct": 10},
        ],
    },
    "Ahmedabad": {
        "citation": "GPCB 2020",
        "breakdown": [
            {"source": "Industry", "pct": 30}, {"source": "Vehicles", "pct": 28},
            {"source": "Road dust", "pct": 20}, {"source": "Construction", "pct": 12},
            {"source": "Others", "pct": 10},
        ],
    },
    "Pune": {
        "citation": "MPCB 2021",
        "breakdown": [
            {"source": "Vehicles", "pct": 35}, {"source": "Construction", "pct": 20},
            {"source": "Industry", "pct": 18}, {"source": "Road dust", "pct": 17},
            {"source": "Others", "pct": 10},
        ],
    },
    "Kanpur": {
        "citation": "UPPCB 2020",
        "breakdown": [
            {"source": "Industry", "pct": 32}, {"source": "Vehicles", "pct": 24},
            {"source": "Biomass burning", "pct": 20}, {"source": "Road dust", "pct": 14},
            {"source": "Others", "pct": 10},
        ],
    },
    "Lucknow": {
        "citation": "UPPCB 2021",
        "breakdown": [
            {"source": "Vehicles", "pct": 28}, {"source": "Industry", "pct": 25},
            {"source": "Biomass burning", "pct": 22}, {"source": "Road dust", "pct": 15},
            {"source": "Others", "pct": 10},
        ],
    },
    "Patna": {
        "citation": "BSPCB 2021",
        "breakdown": [
            {"source": "Biomass burning", "pct": 28}, {"source": "Vehicles", "pct": 22},
            {"source": "Road dust", "pct": 20}, {"source": "Industry", "pct": 18},
            {"source": "Others", "pct": 12},
        ],
    },
    "Jaipur": {
        "citation": "RSPCB 2020",
        "breakdown": [
            {"source": "Road dust", "pct": 32}, {"source": "Vehicles", "pct": 26},
            {"source": "Construction", "pct": 18}, {"source": "Industry", "pct": 14},
            {"source": "Others", "pct": 10},
        ],
    },
}


def _format_baseline(entry: dict) -> str:
    parts = ", ".join(f"{b['source']} {b['pct']}%" for b in entry["breakdown"])
    return f"{parts} ({entry['citation']})"


def get_baseline_citation(city: str) -> str | None:
    """The study name/year backing a city's CPCB baseline, if one exists —
    surfaced in the /attribution API response so the frontend can show a real,
    checkable citation next to the AI's numbers instead of a bare percentage."""
    entry = CPCB_SOURCE_APPORTIONMENT.get(city)
    return entry["citation"] if entry else None


ATTRIBUTION_SYSTEM = """You are an air quality analyst for Indian cities with deep expertise in
pollution source attribution. You are given a city's current AQI, meteorological conditions,
time of day, day of week, AND published CPCB source apportionment baselines for that city.
Use the CPCB baseline as your scientific anchor, then adjust percentages based on the
current meteorological context and time-of-day traffic patterns.
Always respond with ONLY a valid JSON object - no preamble, no markdown fences.
The percentages must sum to 100."""


def attribution_user(req) -> str:
    entry = CPCB_SOURCE_APPORTIONMENT.get(req.city)
    baseline = (
        _format_baseline(entry) if entry
        else "No published CPCB source apportionment available - estimate based on city type and conditions."
    )
    return f"""Estimate the current pollution source attribution for the following city:

City: {req.city}, {req.state}
Current AQI: {req.aqi} (PM2.5: {req.pm25} μg/m³)
Time: {req.hour_of_day}:00 hrs, {req.day_of_week}
Live Weather: {req.weather_desc}, wind {req.wind_speed_kmh} km/h, humidity {req.humidity_pct}%

Published CPCB Source Apportionment Baseline for this city:
{baseline}

Instructions:
1. Start from the CPCB baseline percentages above
2. Adjust for the current time of day (e.g. traffic higher at 8am and 6pm, lower at 2am)
3. Adjust for the day of week (weekdays vs weekends have different traffic patterns)
4. Adjust for wind speed (high wind disperses road dust more than industrial emissions)
5. Your output must reflect these real contextual adjustments, not just repeat the baseline

Respond ONLY with this JSON:
{{
  "traffic": <integer percentage>,
  "industrial": <integer percentage>,
  "construction": <integer percentage>,
  "biomass_burning": <integer percentage>,
  "other": <integer percentage>,
  "dominant_source": "<name of the highest contributor>",
  "cpcb_baseline_used": true,
  "reasoning": "<2 sentences: what baseline says AND how current conditions changed it>"
}}"""


# ─── Enforcement Intelligence ─────────────────────────────────────────────────

ENFORCEMENT_SYSTEM = """You are an enforcement intelligence officer for India's Central
Pollution Control Board. You generate prioritised, evidence-backed field enforcement
recommendations for pollution control authorities. Always respond with ONLY valid JSON -
no preamble, no markdown fences.

You do NOT choose where to inspect. Two upstream systems have already done that:

1. A Source Attribution Agent reasoned over each city's live weather, time of day and
   published CPCB baseline to produce a "dominant_source".
2. A deterministic geospatial correlation engine (utils/enforcement_scoring.py) then
   ranked the actual registered emission sources near each hotspot — by distance,
   by whether the source lies UPWIND of the monitoring station given the live wind
   direction, and by whether its category matches the attributed dominant source.

Each candidate below is therefore a real, mapped facility with real coordinates and an
evidence score you can cite. Your job is to turn that ranked shortlist into dispatchable
enforcement actions.

Hard rules:
- Every priority MUST name one of the candidate facilities given to you, using its exact
  label and "id". Never invent a facility, an area, or a zone name.
- Some candidates are unnamed in the source register and are given a positional label
  ("Unregistered industry site 2.0 km NW of Kolkata centre"). Use that label verbatim and
  include the coordinates in your action — an inspector navigates to it by position.
- Your rationale MUST cite the concrete evidence supplied: the distance in km, the upwind
  alignment, and the attributed dominant source. That is the evidentiary basis - do not
  substitute generic reasoning about the city.
- If a candidate is upwind of the hotspot, say so explicitly; it is the strongest single
  piece of evidence that this facility can physically be contributing to the reading."""


def enforcement_user(req) -> str:
    blocks = []
    for c in req.top_cities:
        header = (
            f"CITY: {c['city']} - AQI {c['aqi']} ({c.get('label','')}), "
            f"PM2.5 {c.get('pm25') if c.get('pm25') is not None else '-'} μg/m³"
        )
        if c.get("dominant_source"):
            header += f"\n  Attribution Agent dominant_source: {c['dominant_source']}"
        if c.get("wind_direction") is not None:
            header += (
                f"\n  Live wind: from {c['wind_direction']}°"
                f" at {c.get('wind_speed_kmh', '?')} km/h"
            )

        candidates = c.get("candidate_sources") or []
        if candidates:
            lines = []
            for s in candidates:
                align = s.get("upwind_alignment")
                if align is None:
                    wind_note = "wind direction unavailable"
                elif align > 0.6:
                    wind_note = f"directly UPWIND (alignment {align})"
                elif align > 0.2:
                    wind_note = f"partially upwind (alignment {align})"
                else:
                    wind_note = f"crosswind (alignment {align})"
                lines.append(
                    f"    - [{s['id']}] {s.get('dispatch_label') or s['name']} | "
                    f"category: {s['category']} | "
                    f"{s['distance_km']} km {s.get('compass_from_hotspot', '')} of station | "
                    f"{wind_note} | evidence score {s['evidence_score']} | "
                    f"coords {s['lat']},{s['lon']}"
                )
            header += "\n  Ranked registered emission sources near this hotspot:\n" + "\n".join(lines)
        else:
            header += (
                "\n  No registered emission sources on file within range for this city - "
                "do NOT fabricate one; if you must rank this city, say the evidence is "
                "AQI-only in the rationale."
            )
        blocks.append(header)

    cities_text = "\n\n".join(blocks)

    return f"""Current pollution hotspots in India, each with its geospatially correlated
candidate emission sources:

{cities_text}

Generate today's top 3 enforcement action priorities, drawing each one from the ranked
candidate facilities above. Prefer facilities with a high evidence score and clear upwind
alignment. Recommend an inspector count proportional to the facility's size and the
hotspot's severity.

Respond ONLY with this exact JSON (all 3 priority objects must be present):
{{
  "generated_at": "<today's date YYYY-MM-DD>",
  "priorities": [
    {{
      "rank": 1,
      "city": "<city name>",
      "source_id": "<exact id of the chosen candidate facility>",
      "target_facility": "<exact name of the chosen candidate facility>",
      "action": "<specific enforcement action at that facility>",
      "violation_type": "<type of violation to inspect for>",
      "inspector_count": <number>,
      "aqi_at_decision": <aqi value>,
      "rationale": "<2 sentences citing distance, upwind alignment and dominant source>"
    }},
    {{ ...same shape, "rank": 2... }},
    {{ ...same shape, "rank": 3... }}
  ]
}}"""


# ─── AQI Forecast ─────────────────────────────────────────────────────────────

# The forecast is a hybrid: utils/forecast_baseline.py computes a deterministic
# statistical forecast (persistence + trend + wind-dispersion physics) with no
# LLM call, and the LLM below is anchored to it as a starting point it must
# explain or justify diverging from — not asked to invent numbers from a blank
# page. See routes/intelligence.py::get_forecast for how the two are combined.
FORECAST_SYSTEM = """You are a predictive air quality modeller for Indian cities.
You are given a deterministic statistical baseline forecast (computed from recent
AQI trend and wind-dispersion physics, not by you) — treat it as your starting
point of record, not a suggestion. Explain it, and adjust it only where you have
a concrete meteorological or diurnal-traffic reason the baseline wouldn't
capture — if you deviate from the baseline by more than a few points at any
hour, your narrative must state the specific reason why. Always respond with
ONLY valid JSON."""


def forecast_user(req, baseline: list[dict]) -> str:
    history_text = " → ".join(
        f"{h['hour']}:{h['aqi']}" for h in req.history_24h[-8:]
    )
    forecast_text = "\n".join(
        f"  {f['time']}: {f['temp_c']}°C, wind {f['wind_speed_kmh']} km/h, {f['description']}"
        for f in req.weather_forecast[:4]
    )
    baseline_text = ", ".join(f"{b['hour']}: {b['predicted_aqi']}" for b in baseline)
    return f"""City: {req.city}
Current AQI: {req.current_aqi}
Last 8 hours AQI trend: {history_text}

Statistical baseline forecast (deterministic, already computed — your starting point):
{baseline_text}

Upcoming weather forecast:
{forecast_text}

Reconcile your forecast with the statistical baseline above. Only diverge from
it where you have a specific, stated meteorological or diurnal-traffic reason —
typical diurnal traffic patterns for Indian cities and weather-induced
dispersion/stagnation are valid reasons; inventing an unrelated number is not.

Respond ONLY with:
{{
  "city": "{req.city}",
  "forecast": [
    {{"hour": "HH:00", "predicted_aqi": <integer>, "confidence": "high|medium|low"}},
    ... (6 entries, 2-hr intervals, matching the baseline's hours above)
  ],
  "narrative": "<3-sentence summary of what to expect, and where/why you diverged from the statistical baseline, if at all>",
  "peak_hour": "<HH:00>",
  "peak_aqi": <integer>
}}"""


# ─── Citizen Health Advisory - Multilingual Query Support ────────────────────

ADVISORY_SYSTEM = """You are a public health communication officer generating citizen-facing
air quality advisories for Indian cities. You support both:
(A) Structured advisory generation: output a formatted advisory in the specified language
(B) Free-text query answering: a citizen has sent a message in any Indian language -
    detect the language and respond in the SAME language and script.

Rules for ALL responses:
- Clear, empathetic, jargon-free language
- For Tamil, Kannada, Hindi, Bengali, or any regional script: respond ENTIRELY in that script
- For English: 7th-grade reading level
- Never include JSON - plain text only
- Under 130 words"""


def advisory_user(req) -> str:
    if req.user_query and req.user_query.strip():
        return f"""A citizen has sent the following message about air quality in {req.city}:

"{req.user_query}"

Current real-time conditions in {req.city}:
- AQI: {req.aqi} - Category: {req.aqi_category}
- Data source: Live CPCB monitoring station

Instructions:
1. Detect the language of the citizen's message above
2. Respond ENTIRELY in that same language and script - do not switch to English
3. Directly answer their specific question using the AQI data
4. Include: current air quality status, who is most at risk, 2-3 practical things
   they should do or avoid today
5. Close with one reassuring note
6. If message is English, respond in English"""

    lang_map = {
        "english": "English",
        "tamil":   "Tamil (தமிழ்)",
        "kannada": "Kannada (ಕನ್ನಡ)",
        "hindi":   "Hindi (हिंदी)",
    }
    lang = lang_map.get(req.language, "English")
    return f"""Generate a citizen health advisory for:

City: {req.city}
Current AQI: {req.aqi} - Category: {req.aqi_category} (live CPCB data)
Output language: {lang}

The advisory must include:
1. Clear statement of today's air quality level
2. Who is most at risk (elderly, children, pregnant women, people with asthma/COPD)
3. 3 specific actionable recommendations (what to do / avoid today)
4. One positive closing note

Keep it under 120 words total. Write in {lang} ONLY - do not use any other language."""
