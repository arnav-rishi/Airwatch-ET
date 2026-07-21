"""
Reproduce the scalability figures in SCALABILITY.md.

    python scripts/benchmark_spatial.py

Compares the linear scan the scorer used originally against the spatial grid
index, over synthetic registries distributed across India's bounding box rather
than clustered around one metro. The distribution matters: clustering everything
near the query point makes the index look far worse than it is, because there is
nothing for it to exclude.
"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import services.source_registry as reg  # noqa: E402
from services.source_registry import _cell, get_sources_near  # noqa: E402
from utils.enforcement_scoring import score_sources  # noqa: E402

# India bounding box — a national registry spans the country, not one city.
LAT_RANGE = (8.07, 37.08)
LON_RANGE = (68.20, 97.40)

QUERY_LAT, QUERY_LON = 28.6139, 77.2090  # Delhi
SIZES = (5_000, 50_000, 200_000, 1_000_000)
LOCAL_SOURCES = 200  # guarantee the query point has real neighbours


def build(n: int, template: list[dict]):
    """Synthesise a registry of n sources plus a local cluster, with its index."""
    sources, cells = [], {}

    def add(src):
        sources.append(src)
        cells.setdefault(_cell(src["lat"], src["lon"]), []).append(src)

    for i in range(n):
        s = dict(random.choice(template))
        s["id"] = f"synthetic/{i}"
        s["lat"] = random.uniform(*LAT_RANGE)
        s["lon"] = random.uniform(*LON_RANGE)
        add(s)

    for i in range(LOCAL_SOURCES):
        s = dict(random.choice(template))
        s["id"] = f"local/{i}"
        s["lat"] = QUERY_LAT + random.uniform(-0.2, 0.2)
        s["lon"] = QUERY_LON + random.uniform(-0.2, 0.2)
        add(s)

    return sources, cells


def main() -> int:
    random.seed(42)  # deterministic, so the numbers in SCALABILITY.md reproduce

    template = [s for v in reg._by_city.values() for s in v]
    if not template:
        print("Registry not loaded - run scripts/fetch_emission_sources.py first")
        return 1

    hotspot = {"city": "Delhi", "lat": QUERY_LAT, "lon": QUERY_LON, "aqi": 380}
    scoring = dict(wind_direction_deg=315, wind_speed_kmh=10, limit=5)

    print(f"{'registry':>10}{'linear ms':>12}{'indexed ms':>12}{'speedup':>10}"
          f"{'scanned':>10}{'cells':>8}")
    print("-" * 62)

    original_cells = reg._by_cell
    try:
        for n in SIZES:
            sources, cells = build(n, template)

            start = time.perf_counter()
            score_sources(hotspot, sources, **scoring)
            linear_ms = (time.perf_counter() - start) * 1000

            reg._by_cell = cells
            start = time.perf_counter()
            near = get_sources_near(QUERY_LAT, QUERY_LON, 25)
            score_sources(hotspot, near, **scoring)
            indexed_ms = (time.perf_counter() - start) * 1000

            speedup = linear_ms / indexed_ms if indexed_ms else float("inf")
            print(f"{n:>10}{linear_ms:>12.1f}{indexed_ms:>12.1f}"
                  f"{speedup:>9.0f}x{len(near):>10}{len(cells):>8}")
    finally:
        reg._by_cell = original_cells

    print("\nLinear cost grows with the whole registry; indexed cost grows only")
    print("with local source density, which geography bounds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
