"""
Seed the registered-emission-source registry from OpenStreetMap (Overpass API).

Run this once to (re)generate backend/data/emission_sources.json:

    python scripts/fetch_emission_sources.py

Why a seed script and not a live call: the Enforcement Agent must be able to
correlate a hotspot against a source registry during a demo without depending
on Overpass being up, fast, or un-rate-limited at that moment. Overpass is also
a shared community resource — hammering it per request would be abusive. So the
registry is fetched once, committed, and read from disk at runtime.

Source categories map onto the four emitter types named in the problem
statement: industries, construction sites, waste burning locations, and diesel
fleet movement. OSM has no "registered polluter" tag, so each category is a
best-available proxy built from established OSM tagging (see _CATEGORY_QUERIES).
That limitation is stated honestly in the registry's own metadata rather than
papered over — a production deployment would swap this for CPCB's consent-to-
operate database and the state PCB registers, which are not openly available.
"""
import json
import sys
import time
from pathlib import Path

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DATA_DIR = Path(__file__).parent.parent / "data"
CITIES_PATH = DATA_DIR / "cities_fallback.json"
OUT_PATH = DATA_DIR / "emission_sources.json"

# Half-width of the bounding box fetched around each city centre, in degrees.
# ~0.25° ≈ 27 km, which comfortably covers a metro's industrial periphery
# without pulling in neighbouring cities' sources.
BBOX_HALF_DEG = 0.25

# Per-city cap per category, so one dense metro can't dominate the file.
MAX_PER_CATEGORY = 60

# OSM tag selectors per emitter category. Each is a proxy, not an official
# register — the mapping rationale is recorded here because it's the main
# judgement call in this module.
_CATEGORY_QUERIES = {
    # Industrial estates and works — the closest OSM analogue to a CPCB
    # consent-to-operate industrial unit.
    "industry": [
        'nwr["landuse"="industrial"]',
        'nwr["man_made"="works"]',
    ],
    # Active construction. OSM tags these inconsistently (they're transient by
    # nature), so both the landuse and building forms are queried.
    "construction": [
        'nwr["landuse"="construction"]',
        'nwr["building"="construction"]',
    ],
    # Waste handling sites. Open burning isn't mapped in OSM (it's illegal and
    # unregistered by definition), so landfills and transfer stations stand in
    # as the locations where waste burning is most frequently reported.
    "waste_burning": [
        'nwr["landuse"="landfill"]',
        'nwr["amenity"="waste_transfer_station"]',
        'nwr["amenity"="waste_disposal"]',
    ],
    # Diesel fleet origins — depots and terminals concentrate heavy-duty diesel
    # movement, which is what an inspector would actually target.
    "diesel_fleet": [
        'nwr["amenity"="bus_station"]',
        'nwr["landuse"="depot"]',
        'nwr["building"="transportation"]',
    ],
}


def _build_query(lat: float, lon: float) -> str:
    """One union query per city — a single Overpass round trip for all categories."""
    bbox = (
        f"{lat - BBOX_HALF_DEG},{lon - BBOX_HALF_DEG},"
        f"{lat + BBOX_HALF_DEG},{lon + BBOX_HALF_DEG}"
    )
    clauses = "".join(
        f"{selector}({bbox});"
        for selectors in _CATEGORY_QUERIES.values()
        for selector in selectors
    )
    return f"[out:json][timeout:90];({clauses});out center tags;"


def _classify(tags: dict) -> str | None:
    """Map an OSM element's tags back to one of our emitter categories."""
    if tags.get("landuse") == "industrial" or tags.get("man_made") == "works":
        return "industry"
    if tags.get("landuse") == "construction" or tags.get("building") == "construction":
        return "construction"
    if tags.get("landuse") == "landfill" or tags.get("amenity") in (
        "waste_transfer_station", "waste_disposal"
    ):
        return "waste_burning"
    if (
        tags.get("amenity") == "bus_station"
        or tags.get("landuse") == "depot"
        or tags.get("building") == "transportation"
    ):
        return "diesel_fleet"
    return None


def fetch_city(client: httpx.Client, city: dict, attempts: int = 4) -> list[dict]:
    """
    One Overpass round trip for a city, retrying on the two failure modes the
    public endpoint actually exhibits under sustained use: 429 (slot exhausted)
    and 504 (query timed out server-side). Both are transient and clear after a
    pause, so backing off is far better than dropping the city.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = client.post(
                OVERPASS_URL,
                data={"data": _build_query(city["lat"], city["lon"])},
                timeout=180.0,
            )
            if resp.status_code in (429, 504):
                raise httpx.HTTPStatusError(
                    f"transient {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            break
        except Exception as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
            backoff = 15 * (attempt + 1)
            print(f"    retry {attempt + 1}/{attempts - 1} in {backoff}s ({exc.__class__.__name__})")
            time.sleep(backoff)
    else:  # pragma: no cover - loop always breaks or raises
        raise last_exc  # type: ignore[misc]

    elements = resp.json().get("elements", [])

    per_category: dict[str, int] = {}
    sources = []
    for el in elements:
        tags = el.get("tags") or {}
        category = _classify(tags)
        if not category:
            continue
        if per_category.get(category, 0) >= MAX_PER_CATEGORY:
            continue

        centre = el.get("center") or el
        lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue

        per_category[category] = per_category.get(category, 0) + 1
        sources.append({
            # Stable OSM identity, so a finding can be traced back to the map.
            "id": f"{el.get('type')}/{el.get('id')}",
            "city": city["city"],
            "category": category,
            "name": tags.get("name") or tags.get("operator") or f"Unnamed {category} site",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "osm_url": f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        })
    return sources


def main() -> int:
    with open(CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)

    # Resume: keep sources already fetched in a previous run and re-query only
    # the cities still missing. Overpass is a shared free endpoint and a full
    # 43-city sweep is enough to exhaust its rate limit, so re-fetching what we
    # already have would be both wasteful and self-defeating.
    all_sources: list[dict] = []
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            all_sources = json.load(f).get("sources", [])
    done = {s["city"] for s in all_sources}
    if done:
        print(f"Resuming: {len(done)} cities already have sources, {len(all_sources)} total\n")

    failures: list[str] = []

    with httpx.Client(headers={"User-Agent": "AirWatch-India/1.0 (hackathon project)"}) as client:
        for i, city in enumerate(cities, 1):
            if city["city"] in done:
                print(f"[{i}/{len(cities)}] {city['city']:<20} skip (already fetched)")
                continue
            try:
                found = fetch_city(client, city)
                all_sources.extend(found)
                print(f"[{i}/{len(cities)}] {city['city']:<20} {len(found):>4} sources")
            except Exception as exc:
                failures.append(city["city"])
                print(f"[{i}/{len(cities)}] {city['city']:<20} FAILED: {exc}", file=sys.stderr)
            # Be polite to a free shared endpoint. Overpass hands out limited
            # concurrent slots; 2s was demonstrably too aggressive across a
            # 43-city sweep and got us 429'd.
            time.sleep(8)

    by_category: dict[str, int] = {}
    for s in all_sources:
        by_category[s["category"]] = by_category.get(s["category"], 0) + 1

    payload = {
        "_meta": {
            "generated_by": "backend/scripts/fetch_emission_sources.py",
            "upstream": "OpenStreetMap via Overpass API (ODbL)",
            "caveat": (
                "OSM proxies for registered emitters, not an official register. "
                "Open waste burning is unmapped by nature, so landfills and waste "
                "transfer stations stand in for it. A production deployment would "
                "use CPCB consent-to-operate and state PCB registers instead."
            ),
            "bbox_half_deg": BBOX_HALF_DEG,
            "max_per_category_per_city": MAX_PER_CATEGORY,
            "total_sources": len(all_sources),
            "by_category": by_category,
            "cities_covered": len({s["city"] for s in all_sources}),
            "failed_cities": failures,
        },
        "sources": all_sources,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)

    # Plain ASCII: this runs on Windows consoles under cp1252, where a stray
    # arrow glyph raises UnicodeEncodeError *after* the file is already written.
    print(f"\nWrote {len(all_sources)} sources to {OUT_PATH}")
    print(f"By category: {by_category}")
    if failures:
        print(f"Failed cities: {', '.join(failures)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
