# ─── Source Attribution ───────────────────────────────────────────────────────

# Published CPCB / ARAI source apportionment studies for major Indian cities.
CPCB_SOURCE_APPORTIONMENT = {
    "Delhi":      "Road dust 28%, Vehicles 20%, Industry 11%, Biomass burning 11%, Construction 6%, Secondary aerosol 24% (CPCB/ARAI 2021)",
    "Mumbai":     "Transport 30%, Industry 35%, Marine/sea salt 18%, Construction 8%, Others 14% (MPCB 2020)",
    "Kolkata":    "Vehicles 25%, Industry 22%, Biomass burning 15%, Road dust 18%, Construction 12%, Others 8% (WBPCB 2021)",
    "Chennai":    "Road dust 30%, Vehicles 28%, Industry 14%, Construction 15%, Others 13% (TNPCB 2022)",
    "Bengaluru":  "Vehicles 35%, Construction 22%, Road dust 20%, Industry 12%, Others 11% (KSPCB 2022)",
    "Hyderabad":  "Vehicles 30%, Industry 25%, Road dust 22%, Construction 13%, Others 10% (TSPCB 2021)",
    "Ahmedabad":  "Industry 30%, Vehicles 28%, Road dust 20%, Construction 12%, Others 10% (GPCB 2020)",
    "Pune":       "Vehicles 35%, Construction 20%, Industry 18%, Road dust 17%, Others 10% (MPCB 2021)",
    "Kanpur":     "Industry 32%, Vehicles 24%, Biomass burning 20%, Road dust 14%, Others 10% (UPPCB 2020)",
    "Lucknow":    "Vehicles 28%, Industry 25%, Biomass burning 22%, Road dust 15%, Others 10% (UPPCB 2021)",
    "Patna":      "Biomass burning 28%, Vehicles 22%, Road dust 20%, Industry 18%, Others 12% (BSPCB 2021)",
    "Jaipur":     "Road dust 32%, Vehicles 26%, Construction 18%, Industry 14%, Others 10% (RSPCB 2020)",
}

ATTRIBUTION_SYSTEM = """You are an air quality analyst for Indian cities with deep expertise in
pollution source attribution. You are given a city's current AQI, meteorological conditions,
time of day, day of week, AND published CPCB source apportionment baselines for that city.
Use the CPCB baseline as your scientific anchor, then adjust percentages based on the
current meteorological context and time-of-day traffic patterns.
Always respond with ONLY a valid JSON object - no preamble, no markdown fences.
The percentages must sum to 100."""


def attribution_user(req) -> str:
    baseline = CPCB_SOURCE_APPORTIONMENT.get(
        req.city,
        "No published CPCB source apportionment available - estimate based on city type and conditions."
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
Pollution Control Board. Given real-time AQI data from multiple cities, you generate
prioritised, evidence-backed field enforcement recommendations for pollution control
authorities. Always respond with ONLY valid JSON - no preamble, no markdown fences."""


def enforcement_user(req) -> str:
    cities_text = "\n".join(
        f"- {c['city']}: AQI {c['aqi']} ({c.get('label','')}) | PM2.5: {c.get('pm25') or '-'} μg/m³"
        for c in req.top_cities
    )
    return f"""Current top pollution cities in India:

{cities_text}

Generate today's top 3 enforcement action priorities. For each, specify: which city,
what type of violation to inspect (industrial stack, construction dust, diesel generators,
waste burning, etc.), the specific zone or area type most likely to yield results,
recommended inspector count, and the evidentiary basis for prioritising this action.

Respond ONLY with this exact JSON (all 3 priority objects must be present):
{{
  "generated_at": "<today's date YYYY-MM-DD>",
  "priorities": [
    {{
      "rank": 1,
      "city": "<city name>",
      "action": "<specific enforcement action>",
      "violation_type": "<type of violation>",
      "target_zone": "<area or zone type>",
      "inspector_count": <number>,
      "aqi_at_decision": <aqi value>,
      "rationale": "<2-sentence evidence-backed justification>"
    }},
    {{
      "rank": 2,
      "city": "<city name>",
      "action": "<specific enforcement action>",
      "violation_type": "<type of violation>",
      "target_zone": "<area or zone type>",
      "inspector_count": <number>,
      "aqi_at_decision": <aqi value>,
      "rationale": "<2-sentence evidence-backed justification>"
    }},
    {{
      "rank": 3,
      "city": "<city name>",
      "action": "<specific enforcement action>",
      "violation_type": "<type of violation>",
      "target_zone": "<area or zone type>",
      "inspector_count": <number>,
      "aqi_at_decision": <aqi value>,
      "rationale": "<2-sentence evidence-backed justification>"
    }}
  ]
}}"""


# ─── AQI Forecast ─────────────────────────────────────────────────────────────

FORECAST_SYSTEM = """You are a predictive air quality modeller for Indian cities.
Using historical AQI trends and meteorological forecasts, you predict AQI for the
next 24 hours at hourly intervals. Always respond with ONLY valid JSON."""


def forecast_user(req) -> str:
    history_text = " → ".join(
        f"{h['hour']}:{h['aqi']}" for h in req.history_24h[-8:]
    )
    forecast_text = "\n".join(
        f"  {f['time']}: {f['temp_c']}°C, wind {f['wind_speed_kmh']} km/h, {f['description']}"
        for f in req.weather_forecast[:4]
    )
    return f"""City: {req.city}
Current AQI: {req.current_aqi}
Last 8 hours AQI trend: {history_text}

Upcoming weather forecast:
{forecast_text}

Predict AQI for the next 12 hours (at 2-hour intervals).
Factor in: typical diurnal traffic patterns for Indian cities, weather-induced
dispersion or stagnation, and the current trend trajectory.

Respond ONLY with:
{{
  "city": "{req.city}",
  "forecast": [
    {{"hour": "HH:00", "predicted_aqi": <integer>, "confidence": "high|medium|low"}},
    ... (6 entries, 2-hr intervals)
  ],
  "narrative": "<3-sentence summary of what to expect and why>",
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
