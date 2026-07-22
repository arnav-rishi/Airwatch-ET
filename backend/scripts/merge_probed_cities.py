"""
Merge probe results into data/cities_fallback.json.

    python scripts/probe_waqi_cities.py     # writes data/_probed_cities.json
    python scripts/merge_probed_cities.py   # reviews and merges

Two conversions matter here, and getting either wrong would be invisible until
it caused a bad enforcement recommendation.

SCALE. The probe records what WAQI returns, which is a US EPA AQI *index* in
both `aqi` and `iaqi.pm25.v`. cities_fallback.json stores CPCB AQI and a real
PM2.5 concentration in ug/m3 (Delhi: aqi 214, pm25 89.2). Writing EPA indices
into those fields would mix two scales inside the one file that exists to be the
common baseline — and services/waqi.py sorts fallback cities against live ones
to pick enforcement hotspots.

PLAUSIBILITY. These values become each city's permanent last-known reading, used
whenever its live feed fails. The probe found Gorakhpur reporting 999 and Sagar
670; the EPA scale tops out at 500, so both are sentinels or sensor faults. Left
in, Gorakhpur would sit at the top of the hotspot ranking forever whenever its
feed dropped, sending the entire enforcement chain to a city on the strength of
a broken sensor.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.aqi_calculator import aqi_category, epa_aqi_to_pm25, pm25_to_aqi  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
CITIES_PATH = DATA / "cities_fallback.json"
PROBED_PATH = DATA / "_probed_cities.json"

# US EPA AQI tops out at 500. Anything above is a sentinel or a fault.
EPA_MAX = 500


def convert(entry: dict) -> dict | None:
    raw_aqi = entry.get("aqi")
    if not isinstance(raw_aqi, int) or raw_aqi <= 0 or raw_aqi > EPA_MAX:
        print(f"  REJECT {entry['city']:<18} aqi={raw_aqi} — outside the EPA scale")
        return None

    raw_pm25 = entry.get("pm25")
    if isinstance(raw_pm25, (int, float)) and 0 < raw_pm25 <= EPA_MAX:
        pm25 = epa_aqi_to_pm25(raw_pm25)
    else:
        # No usable PM2.5 sub-index — derive it from the overall AQI instead.
        pm25 = epa_aqi_to_pm25(raw_aqi)

    cpcb = pm25_to_aqi(pm25)
    print(f"  keep   {entry['city']:<18} EPA {raw_aqi:<4} -> {pm25:>6.1f} ug/m3 -> CPCB {cpcb:<4} ({aqi_category(cpcb)['label']})")

    return {
        "city": entry["city"],
        "state": entry["state"],
        "slug": entry["slug"],
        "lat": entry["lat"],
        "lon": entry["lon"],
        "aqi": cpcb,
        "pm25": pm25,
        "primary_pollutant": entry.get("primary_pollutant") or "PM2.5",
        "updated_at": entry.get("updated_at", ""),
    }


def main() -> int:
    if not PROBED_PATH.exists():
        print("No probe results — run scripts/probe_waqi_cities.py first")
        return 1

    with open(CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)
    with open(PROBED_PATH, encoding="utf-8") as f:
        probed = json.load(f)

    existing = {c["city"] for c in cities}
    existing_slugs = {c["slug"] for c in cities}

    print(f"Existing: {len(cities)} cities. Probed: {len(probed)}.\n")

    added = []
    for entry in probed:
        if entry["city"] in existing:
            print(f"  skip   {entry['city']:<18} already present")
            continue
        if entry["slug"] in existing_slugs:
            print(f"  skip   {entry['city']:<18} slug '{entry['slug']}' already used")
            continue
        converted = convert(entry)
        if converted:
            added.append(converted)
            existing.add(converted["city"])
            existing_slugs.add(converted["slug"])

    merged = cities + added
    merged.sort(key=lambda c: -c["aqi"])

    with open(CITIES_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=1, ensure_ascii=False)

    print(f"\nAdded {len(added)}. Total now {len(merged)} cities.")
    print(f"States covered: {len({c['state'] for c in merged})}")
    print("\nNext: python scripts/fetch_emission_sources.py  (resumes; seeds only the new cities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
