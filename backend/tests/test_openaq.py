"""
Tests for the OpenAQ v3 source (services/openaq.py) — now the primary AQI feed.

The bug this whole module exists to fix: readings were presented as live without
any staleness check, and WAQI's feeds were years old. These tests pin the two
things that keep that from recurring — age is computed and carried, and
implausible/negative sensor values are rejected — plus the median-not-max choice
that stops one faulty station dominating a city.
"""
from datetime import datetime, timedelta, timezone

from services.openaq import (
    MAX_PLAUSIBLE_PM25,
    MAX_READING_AGE_HOURS,
    _city_station,
    _median,
    _parse_reading,
)

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _row(lat, lon, value, hours_ago):
    stamp = (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
    return {
        "value": value,
        "coordinates": {"latitude": lat, "longitude": lon},
        "datetime": {"utc": stamp},
        "locationsId": 1,
    }


# ─── Parsing & staleness ──────────────────────────────────────────────────────

def test_reading_carries_its_age():
    r = _parse_reading(_row(28.6, 77.2, 55.0, hours_ago=3), NOW)
    assert r is not None
    assert r["pm25"] == 55.0
    assert r["age_hours"] == 3.0


def test_reading_outside_india_is_rejected():
    # Seoul — a real row from the global feed we page through.
    assert _parse_reading(_row(37.5, 127.0, 20.0, 1), NOW) is None


def test_negative_value_is_rejected_as_a_fault():
    assert _parse_reading(_row(28.6, 77.2, -5.0, 1), NOW) is None


def test_implausibly_high_value_is_rejected():
    """A lone station at 520 ug/m3 in monsoon is a stuck sensor, not air quality."""
    assert _parse_reading(_row(19.9, 75.3, MAX_PLAUSIBLE_PM25 + 1, 1), NOW) is None
    assert _parse_reading(_row(19.9, 75.3, MAX_PLAUSIBLE_PM25 - 1, 1), NOW) is not None


def test_missing_or_bad_timestamp_is_rejected():
    row = _row(28.6, 77.2, 40.0, 1)
    del row["datetime"]
    assert _parse_reading(row, NOW) is None


# ─── City aggregation ─────────────────────────────────────────────────────────

# Delhi, and points a few hundred metres away — all comfortably inside India.
DEL_LAT, DEL_LON = 28.6139, 77.2090


def test_city_uses_median_not_max():
    """
    A single faulty station must not define a city. Median of four where one is
    an outlier stays near the honest cluster; max would hand the city to the fault.
    """
    city = {"city": "Testville", "state": "TS", "lat": DEL_LAT, "lon": DEL_LON}
    readings = [
        _clean(_row(DEL_LAT + 0.001, DEL_LON + 0.001, 30.0, 1), NOW),
        _clean(_row(DEL_LAT + 0.002, DEL_LON + 0.002, 32.0, 1), NOW),
        _clean(_row(DEL_LAT + 0.003, DEL_LON + 0.003, 34.0, 1), NOW),
        _clean(_row(DEL_LAT + 0.004, DEL_LON + 0.004, 300.0, 1), NOW),  # outlier
    ]
    station = _city_station(city, readings)
    assert 30 <= station["pm25"] <= 40         # median, not dragged to 300
    assert station["pm25_max"] == 300.0        # but the worst is still reported
    assert station["station_count"] == 4


def test_city_with_only_stale_readings_is_dropped():
    city = {"city": "Oldtown", "state": "TS", "lat": DEL_LAT, "lon": DEL_LON}
    readings = [_clean(_row(DEL_LAT + 0.001, DEL_LON + 0.001, 40.0, MAX_READING_AGE_HOURS + 5), NOW)]
    assert _city_station(city, readings) is None


def test_city_with_no_nearby_readings_is_dropped():
    city = {"city": "Remote", "state": "TS", "lat": 13.08, "lon": 80.27}  # Chennai
    readings = [_clean(_row(DEL_LAT, DEL_LON, 40.0, 1), NOW)]             # Delhi, far away
    assert _city_station(city, readings) is None


def test_city_station_is_on_the_cpcb_scale():
    city = {"city": "Testville", "state": "TS", "lat": DEL_LAT, "lon": DEL_LON}
    station = _city_station(city, [_clean(_row(DEL_LAT + 0.001, DEL_LON + 0.001, 90.0, 1), NOW)])
    assert station["aqi_scale"] == "CPCB"
    assert station["source"] == "openaq_live"
    assert station["age_hours"] <= MAX_READING_AGE_HOURS


def test_median_helper():
    assert _median([1, 2, 3]) == 2
    assert _median([1, 2, 3, 4]) == 2.5
    assert _median([5]) == 5


def _clean(row, now):
    """Parse a row the way fetch_india_readings would, for aggregation tests."""
    return _parse_reading(row, now)
