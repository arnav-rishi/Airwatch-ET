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
