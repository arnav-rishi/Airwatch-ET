# US EPA PM2.5 breakpoints (24-hr, μg/m³ → EPA AQI). WAQI reports on this scale,
# not CPCB's — see epa_aqi_to_pm25 below for why that matters.
_EPA_PM25_BREAKPOINTS = [
    (0.0,   12.0,    0,  50),
    (12.1,  35.4,   51, 100),
    (35.5,  55.4,  101, 150),
    (55.5, 150.4,  151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
]


def epa_aqi_to_pm25(epa_aqi: float) -> float:
    """
    Invert the US EPA PM2.5 breakpoints: EPA AQI index → PM2.5 concentration (μg/m³).

    Why this exists: WAQI's `aqi` and `iaqi.pm25.v` fields are both US EPA AQI
    *index* values, not concentrations — a live Delhi feed returning
    `iaqi.pm25: 25` means "EPA sub-index 25", i.e. roughly 6 μg/m³, NOT
    "25 μg/m³". Feeding that number straight into pm25_to_aqi() (which expects
    a concentration) silently produces a meaningless figure, and labelling the
    raw EPA index with CPCB category names understates Indian AQI badly —
    India's scale is stricter, so the same air reads far lower on EPA.

    Recovering the concentration first is what lets everything downstream —
    map categories, the enforcement hotspot ranking, the pollutant readouts,
    and the LLM prompts — speak a single consistent CPCB scale.
    """
    if epa_aqi is None or epa_aqi < 0:
        return 0.0
    for (c_lo, c_hi, i_lo, i_hi) in _EPA_PM25_BREAKPOINTS:
        if i_lo <= epa_aqi <= i_hi:
            return round(((c_hi - c_lo) / (i_hi - i_lo)) * (epa_aqi - i_lo) + c_lo, 1)
    # Above the EPA table's top (index 500) — clamp to its ceiling concentration.
    return 500.4


def pm25_to_aqi(pm25: float) -> int:
    """Convert PM2.5 concentration (μg/m³) to India CPCB AQI."""
    breakpoints = [
        (0,   30,   0,   50),
        (30,  60,   51,  100),
        (60,  90,   101, 200),
        (90,  120,  201, 300),
        (120, 250,  301, 400),
        (250, 500,  401, 500),
    ]
    for (bp_lo, bp_hi, aqi_lo, aqi_hi) in breakpoints:
        if bp_lo <= pm25 <= bp_hi:
            aqi = ((aqi_hi - aqi_lo) / (bp_hi - bp_lo)) * (pm25 - bp_lo) + aqi_lo
            return int(aqi)
    return 500 if pm25 > 500 else 0


def aqi_category(aqi: int) -> dict:
    """Return AQI category label and hex color for map rendering."""
    if aqi <= 50:
        return {"label": "Good", "color": "#00C853", "text_color": "#000"}
    elif aqi <= 100:
        return {"label": "Satisfactory", "color": "#C6E03A", "text_color": "#000"}
    elif aqi <= 200:
        return {"label": "Moderate", "color": "#FFC107", "text_color": "#000"}
    elif aqi <= 300:
        return {"label": "Poor", "color": "#FF5722", "text_color": "#fff"}
    elif aqi <= 400:
        return {"label": "Very Poor", "color": "#C62828", "text_color": "#fff"}
    else:
        return {"label": "Severe", "color": "#4A148C", "text_color": "#fff"}


def circle_radius(aqi: int) -> int:
    """Scale map circle radius by AQI severity."""
    if aqi <= 100:
        return 18000
    elif aqi <= 200:
        return 24000
    elif aqi <= 300:
        return 30000
    else:
        return 38000
