"""
Full HTTP integration test suite for AirWatch India backend.
Run against a live server:  python test_endpoints.py
Exits non-zero if any test fails.
"""
import io
import sys
import httpx

# Force UTF-8 stdout so non-ASCII sample text (Hindi/Tamil) never crashes printing.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8001"
results = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))


def main():
    with httpx.Client(base_url=BASE, timeout=90.0) as c:
        # 1. Health
        try:
            r = c.get("/health")
            check("health 200", r.status_code == 200, f"status={r.status_code}")
            check("health body ok", r.json().get("status") == "ok", str(r.json()))
        except Exception as e:
            check("health reachable", False, repr(e))
            print("\nServer not reachable — aborting.")
            sys.exit(1)

        # 2. Live AQI
        r = c.get("/api/aqi/live")
        check("aqi/live 200", r.status_code == 200, f"status={r.status_code}")
        data = r.json()
        stations = data.get("stations", [])
        check("aqi/live has stations", len(stations) > 5, f"count={len(stations)}")
        check("station has aqi int", all(isinstance(s.get("aqi"), int) for s in stations),
              "some aqi non-int" if stations else "no stations")

        # 3. Enforcement auto (LLM)
        r = c.get("/api/intel/enforcement/auto")
        check("enforcement 200", r.status_code == 200,
              f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            j = r.json()
            check("enforcement has 3 priorities", len(j.get("priorities", [])) == 3,
                  f"got {len(j.get('priorities', []))}")
            check("enforcement priority shape",
                  all({"rank", "city", "action", "rationale"} <= set(p) for p in j.get("priorities", [])),
                  "missing fields")

        # 4. Advisory — structured (English)
        payload = {"city": "Delhi", "aqi": 153, "aqi_category": "Moderate",
                   "language": "english", "user_query": ""}
        r = c.post("/api/intel/advisory", json=payload)
        check("advisory(en) 200", r.status_code == 200,
              f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            adv = r.json().get("advisory", "")
            check("advisory(en) non-empty", len(adv) > 30, f"len={len(adv)}")

        # 5. Advisory — free-text Hindi query
        payload = {"city": "Delhi", "aqi": 153, "aqi_category": "Moderate",
                   "language": "auto", "user_query": "आज बाहर जाना सुरक्षित है?"}
        r = c.post("/api/intel/advisory", json=payload)
        check("advisory(hi) 200", r.status_code == 200,
              f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            adv = r.json().get("advisory", "")
            has_devanagari = any('ऀ' <= ch <= 'ॿ' for ch in adv)
            check("advisory(hi) replied in Hindi", has_devanagari, f"sample={adv[:60]!r}")

        # 6. Attribution (LLM JSON)
        payload = {"city": "Delhi", "state": "Delhi", "aqi": 153, "pm25": 65.0,
                   "hour_of_day": 9, "day_of_week": "Monday", "weather_desc": "haze",
                   "wind_speed_kmh": 8.0, "humidity_pct": 60.0}
        r = c.post("/api/intel/attribution", json=payload)
        check("attribution 200", r.status_code == 200,
              f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            j = r.json()
            total = sum(j.get(k, 0) for k in
                        ["traffic", "industrial", "construction", "biomass_burning", "other"])
            check("attribution sums ~100", 95 <= total <= 105, f"sum={total}")

    print("\n" + "=" * 50)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"RESULT: {passed}/{total} passed")
    if passed != total:
        print("FAILURES:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
        sys.exit(1)
    print("ALL TESTS PASSED ✅")


if __name__ == "__main__":
    main()
