"""
Probe WAQI named city feeds to find additional Indian cities worth adding to
data/cities_fallback.json.

    python scripts/probe_waqi_cities.py

WAQI's /map/bounds/ endpoint returns only a sampled subset (24 stations for the
whole India bounding box, several of them in Nepal and Tibet), so it can't be
used to enumerate coverage. The named-feed endpoint the app already relies on is
authoritative per city, so this probes a candidate list one city at a time and
reports which have a live feed with a real current reading.

Prints a JSON block for the cities that pass. Nothing is written automatically —
the output is meant to be reviewed before being merged into the curated list,
because a slug can resolve to a same-named place abroad (services/waqi.py guards
against this at runtime, but a bad entry is better caught here).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(override=True)

WAQI_BASE = "https://api.waqi.info"
CITIES_PATH = Path(__file__).parent.parent / "data" / "cities_fallback.json"

# India bounding box — a slug that resolves outside it is a different country's
# same-named city, not ours.
LAT_MIN, LON_MIN, LAT_MAX, LON_MAX = 8.07, 68.20, 37.08, 97.40

# Candidate cities: (display name, state, slug, lat, lon).
# Chosen for population and for spread across states that the current 43-city
# list leaves thin — the north-east, the Deccan, coastal Andhra, interior MP.
CANDIDATES = [
    ("Surat", "Gujarat", "surat", 21.1702, 72.8311),
    ("Indore", "Madhya Pradesh", "indore", 22.7196, 75.8577),
    ("Nagpur", "Maharashtra", "nagpur", 21.1458, 79.0882),
    ("Thane", "Maharashtra", "thane", 19.2183, 72.9781),
    ("Visakhapatnam", "Andhra Pradesh", "visakhapatnam", 17.6868, 83.2185),
    ("Ludhiana", "Punjab", "ludhiana", 30.9010, 75.8573),
    ("Prayagraj", "Uttar Pradesh", "allahabad", 25.4358, 81.8463),
    ("Howrah", "West Bengal", "howrah", 22.5958, 88.2636),
    ("Jalandhar", "Punjab", "jalandhar", 31.3260, 75.5762),
    ("Aurangabad", "Maharashtra", "aurangabad", 19.8762, 75.3433),
    ("Solapur", "Maharashtra", "solapur", 17.6599, 75.9064),
    ("Hubballi", "Karnataka", "hubli", 15.3647, 75.1240),
    ("Bareilly", "Uttar Pradesh", "bareilly", 28.3670, 79.4304),
    ("Moradabad", "Uttar Pradesh", "moradabad", 28.8386, 78.7733),
    ("Tiruchirappalli", "Tamil Nadu", "tiruchirappalli", 10.7905, 78.7047),
    ("Salem", "Tamil Nadu", "salem", 11.6643, 78.1460),
    ("Warangal", "Telangana", "warangal", 17.9689, 79.5941),
    ("Guntur", "Andhra Pradesh", "guntur", 16.3067, 80.4365),
    ("Saharanpur", "Uttar Pradesh", "saharanpur", 29.9680, 77.5460),
    ("Gorakhpur", "Uttar Pradesh", "gorakhpur", 26.7606, 83.3732),
    ("Bikaner", "Rajasthan", "bikaner", 28.0229, 73.3119),
    ("Amravati", "Maharashtra", "amravati", 20.9374, 77.7796),
    ("Cuttack", "Odisha", "cuttack", 20.4625, 85.8830),
    ("Bhavnagar", "Gujarat", "bhavnagar", 21.7645, 72.1519),
    ("Durgapur", "West Bengal", "durgapur", 23.5204, 87.3119),
    ("Asansol", "West Bengal", "asansol", 23.6739, 86.9524),
    ("Kolhapur", "Maharashtra", "kolhapur", 16.7050, 74.2433),
    ("Ajmer", "Rajasthan", "ajmer", 26.4499, 74.6399),
    ("Kalaburagi", "Karnataka", "gulbarga", 17.3297, 76.8343),
    ("Ujjain", "Madhya Pradesh", "ujjain", 23.1793, 75.7849),
    ("Siliguri", "West Bengal", "siliguri", 26.7271, 88.3953),
    ("Jhansi", "Uttar Pradesh", "jhansi", 25.4484, 78.5685),
    ("Nellore", "Andhra Pradesh", "nellore", 14.4426, 79.9865),
    ("Jamnagar", "Gujarat", "jamnagar", 22.4707, 70.0577),
    ("Tirunelveli", "Tamil Nadu", "tirunelveli", 8.7139, 77.7567),
    ("Gaya", "Bihar", "gaya", 24.7914, 84.9994),
    ("Udaipur", "Rajasthan", "udaipur", 24.5854, 73.7125),
    ("Tiruppur", "Tamil Nadu", "tiruppur", 11.1085, 77.3411),
    ("Kozhikode", "Kerala", "kozhikode", 11.2588, 75.7804),
    ("Kurnool", "Andhra Pradesh", "kurnool", 15.8281, 78.0373),
    ("Rajahmundry", "Andhra Pradesh", "rajahmundry", 17.0005, 81.8040),
    ("Agartala", "Tripura", "agartala", 23.8315, 91.2868),
    ("Bhagalpur", "Bihar", "bhagalpur", 25.2425, 86.9842),
    ("Bhilai", "Chhattisgarh", "bhilai", 21.1938, 81.3509),
    ("Muzaffarnagar", "Uttar Pradesh", "muzaffarnagar", 29.4727, 77.7085),
    ("Mathura", "Uttar Pradesh", "mathura", 27.4924, 77.6737),
    ("Thrissur", "Kerala", "thrissur", 10.5276, 76.2144),
    ("Alwar", "Rajasthan", "alwar", 27.5530, 76.6346),
    ("Nizamabad", "Telangana", "nizamabad", 18.6725, 78.0941),
    ("Panipat", "Haryana", "panipat", 29.3909, 76.9635),
    ("Darbhanga", "Bihar", "darbhanga", 26.1542, 85.8918),
    ("Aizawl", "Mizoram", "aizawl", 23.7271, 92.7176),
    ("Karnal", "Haryana", "karnal", 29.6857, 76.9905),
    ("Bathinda", "Punjab", "bathinda", 30.2110, 74.9455),
    ("Rourkela", "Odisha", "rourkela", 22.2604, 84.8536),
    ("Imphal", "Manipur", "imphal", 24.8170, 93.9368),
    ("Shimla", "Himachal Pradesh", "shimla", 31.1048, 77.1734),
    ("Puducherry", "Puducherry", "puducherry", 11.9416, 79.8083),
    ("Vellore", "Tamil Nadu", "vellore", 12.9165, 79.1325),
    ("Dibrugarh", "Assam", "dibrugarh", 27.4728, 94.9120),
    ("Shillong", "Meghalaya", "shillong", 25.5788, 91.8933),
    ("Gangtok", "Sikkim", "gangtok", 27.3389, 88.6065),
    ("Panaji", "Goa", "panaji", 15.4909, 73.8278),
    ("Satna", "Madhya Pradesh", "satna", 24.6005, 80.8322),
    ("Sagar", "Madhya Pradesh", "sagar", 23.8388, 78.7378),
    ("Korba", "Chhattisgarh", "korba", 22.3595, 82.7501),
    ("Hisar", "Haryana", "hisar", 29.1492, 75.7217),
    ("Rohtak", "Haryana", "rohtak", 28.8955, 76.6066),
    ("Yamunanagar", "Haryana", "yamunanagar", 30.1290, 77.2674),
    ("Sonipat", "Haryana", "sonipat", 28.9931, 77.0151),
    ("Bahadurgarh", "Haryana", "bahadurgarh", 28.6926, 76.9214),
    ("Ambala", "Haryana", "ambala", 30.3752, 76.7821),
    ("Patiala", "Punjab", "patiala", 30.3398, 76.3869),
    ("Khanna", "Punjab", "khanna", 30.7046, 76.2220),
    ("Naya Raipur", "Chhattisgarh", "naya-raipur", 21.1631, 81.7870),
    ("Angul", "Odisha", "angul", 20.8400, 85.1018),
    ("Talcher", "Odisha", "talcher", 20.9494, 85.2334),
    ("Haldia", "West Bengal", "haldia", 22.0667, 88.0698),
    ("Barrackpore", "West Bengal", "barrackpore", 22.7642, 88.3776),
]


async def probe(client: httpx.AsyncClient, city: tuple, attempts: int = 3) -> dict | None:
    name, state, slug, lat, lon = city
    token = os.getenv("WAQI_TOKEN")

    data = None
    for attempt in range(attempts):
        try:
            resp = await client.get(
                f"{WAQI_BASE}/feed/{slug}/", params={"token": token}, timeout=25.0
            )
            data = resp.json()
            break
        except Exception as exc:
            if attempt == attempts - 1:
                print(f"  {name:<18} ERROR   {exc.__class__.__name__}")
                return None
            await asyncio.sleep(3 * (attempt + 1))
    if data is None:
        return None

    if data.get("status") != "ok":
        print(f"  {name:<18} no feed ({data.get('data')})")
        return None

    d = data["data"]
    aqi = d.get("aqi")
    if not isinstance(aqi, int):
        print(f"  {name:<18} feed exists but no current reading")
        return None

    geo = d.get("city", {}).get("geo") or [lat, lon]
    glat, glon = float(geo[0]), float(geo[1])
    if not (LAT_MIN <= glat <= LAT_MAX and LON_MIN <= glon <= LON_MAX):
        print(f"  {name:<18} SLUG COLLISION - resolves to {glat:.2f},{glon:.2f} (outside India)")
        return None

    pm25 = d.get("iaqi", {}).get("pm25", {}).get("v")
    print(f"  {name:<18} OK  aqi={aqi:<4} {d.get('city',{}).get('name','')[:40]}")
    return {
        "city": name, "state": state, "slug": slug,
        "lat": round(glat, 4), "lon": round(glon, 4),
        # Static last-known values, used only when the live feed later fails.
        "aqi": aqi, "pm25": pm25,
        "primary_pollutant": (d.get("dominentpol") or "pm25").upper(),
        "updated_at": d.get("time", {}).get("s", ""),
    }


async def main() -> int:
    if not os.getenv("WAQI_TOKEN"):
        print("WAQI_TOKEN not set")
        return 1

    with open(CITIES_PATH, encoding="utf-8") as f:
        existing = {c["city"] for c in json.load(f)}

    todo = [c for c in CANDIDATES if c[0] not in existing]
    print(f"Probing {len(todo)} candidate cities ({len(CANDIDATES) - len(todo)} already present)\n")

    # Sequential with a pause between calls. Six concurrent probes got every
    # request connect-timeouted — WAQI throttles hard on parallel callers, and a
    # blocked probe is indistinguishable from a city having no feed, which would
    # silently drop good cities from the results.
    good = []
    async with httpx.AsyncClient() as client:
        for i, c in enumerate(todo, 1):
            result = await probe(client, c)
            if result:
                good.append(result)
            if i % 20 == 0:
                print(f"  ... {i}/{len(todo)}")
            await asyncio.sleep(1.2)
    print(f"\n{len(good)} of {len(todo)} have a live feed with a current reading.")
    out = Path(__file__).parent.parent / "data" / "_probed_cities.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(good, f, indent=1, ensure_ascii=False)
    print(f"Written to {out} for review before merging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
