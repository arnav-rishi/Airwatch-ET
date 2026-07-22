# AirWatch India — Architecture

Diagrams render natively on GitHub. The module graph below is extracted from the
actual imports in `backend/`, not drawn from memory.

---

## 1. System context

Where data comes from, what the platform does with it, who consumes the result.

```mermaid
flowchart TB
    subgraph EXT["External data"]
        OAQ["OpenAQ v3<br/><i>PRIMARY · timestamped CPCB</i>"]
        WAQI["WAQI<br/><i>fallback · staleness-gated</i>"]
        OWM["OpenWeatherMap<br/><i>wind speed + direction</i>"]
        FIRMS["NASA FIRMS<br/><i>VIIRS 375m active fire</i>"]
        OSM["OpenStreetMap / Overpass<br/><i>emission source registry</i>"]
        AZ["Azure OpenAI<br/><i>gpt-5-nano</i>"]
    end

    subgraph SEED["Seeded once, committed"]
        REG[("emission_sources.json<br/>7,900+ sources · 82 cities")]
        CITIES[("cities_fallback.json<br/>84 curated cities")]
    end

    subgraph API["Backend — FastAPI"]
        AQI["/api/aqi/*<br/>live stations, city detail"]
        INTEL["/api/intel/*<br/>attribution · enforcement<br/>forecast · advisory · sources"]
    end

    subgraph UI["Frontend — React + Leaflet"]
        MAP["National AQI map"]
        ENF["Enforcement tab<br/><i>map + ranked actions</i>"]
        ADV["Citizen advisory"]
    end

    USERS(["Pollution control authority<br/>· municipal inspectors"])
    CITIZEN(["Citizens"])

    OSM -.->|"offline seed<br/>scripts/fetch_emission_sources.py"| REG
    OAQ --> AQI
    WAQI --> AQI
    OWM --> INTEL
    FIRMS --> INTEL
    REG --> INTEL
    CITIES --> AQI
    AZ <--> INTEL

    AQI --> MAP
    INTEL --> ENF
    INTEL --> ADV
    ENF --> USERS
    ADV --> CITIZEN

    classDef ext fill:#1e3a5f,stroke:#3b82f6,color:#e2e8f0
    classDef seed fill:#3f2d1e,stroke:#f97316,color:#e2e8f0
    classDef api fill:#1e3f2f,stroke:#10b981,color:#e2e8f0
    classDef ui fill:#3a1e3f,stroke:#a855f7,color:#e2e8f0
    class OAQ,WAQI,OWM,FIRMS,OSM,AZ ext
    class REG,CITIES seed
    class AQI,INTEL api
    class MAP,ENF,ADV ui
```

---

## 2. The enforcement chain

The core of the project. Note where the LLM sits: **last**, and only to narrate a
shortlist it cannot alter.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as routes/intelligence
    participant W as WAQI
    participant A as Attribution Agent<br/>(LLM)
    participant REG as source_registry<br/>(spatial index)
    participant F as NASA FIRMS
    participant S as enforcement_scoring<br/>+ dispersion
    participant E as Enforcement Agent<br/>(LLM)

    C->>R: GET /api/intel/enforcement/auto
    Note over R: signal_at timestamp starts

    R->>W: live stations (cached 10 min)
    W-->>R: 84 cities, CPCB scale, timestamped
    Note over R: rank hotspots, take top 5

    par Stage 1 — attribution, concurrent
        R->>A: hotspot + weather + CPCB baseline
        A-->>R: dominant_source
    end

    Note over R,S: Stage 2 — deterministic, no LLM
    R->>REG: get_sources_near(lat, lon, 25km)
    REG-->>R: candidates across city boundaries
    R->>F: active fires near hotspot
    F-->>R: satellite detections (or none)

    R->>S: score(sources + fires, wind, stability)
    Note over S: exclude sensitive receptors<br/>exclude kerbside stops<br/>exclude downwind<br/>Gaussian plume × proximity<br/>× category × dispatchability
    S-->>R: top 5 ranked, with evidence

    Note over R,E: Stage 3 — narration only
    R->>E: ranked shortlist + evidence
    E-->>R: dispatch actions (must cite source_id)

    Note over R: reconcile source_ids<br/>compute impact metrics<br/>response_time_seconds
    R-->>C: priorities + hotspots + evidence + impact
```

---

## 3. Module dependency graph

Extracted from the `import` statements in `backend/`.

```mermaid
flowchart LR
    MAIN["main.py"]
    RA["routes/aqi"]
    RI["routes/intelligence"]

    WQ["services/waqi"]
    OA["services/openaq"]
    OW["services/openweather"]
    FR["services/firms"]
    SR["services/source_registry"]
    LLM["services/llm"]
    CA["services/cache"]
    RL["services/rate_limit"]

    AC["utils/aqi_calculator"]
    ES["utils/enforcement_scoring"]
    DI["utils/dispersion"]
    IM["utils/impact_metrics"]
    FB["utils/forecast_baseline"]
    ACF["utils/attribution_confidence"]
    PR["prompts"]

    MAIN --> RA & RI & CA & RL
    RA --> CA & OA & OW & WQ
    RI --> PR & CA & FR & LLM & OW & SR & WQ
    RI --> AC & ACF & DI & ES & FB & IM
    CA --> WQ
    WQ --> OA & AC
    OA --> AC
    ES --> DI
    IM --> SR & ES
    ACF --> PR

    classDef entry fill:#1e3a5f,stroke:#3b82f6,color:#e2e8f0
    classDef svc fill:#1e3f2f,stroke:#10b981,color:#e2e8f0
    classDef util fill:#3f2d1e,stroke:#f97316,color:#e2e8f0
    class MAIN,RA,RI entry
    class WQ,OA,OW,FR,SR,LLM,CA,RL svc
    class AC,ES,DI,IM,FB,ACF,PR util
```

`utils/` has no dependency on `services/` except `impact_metrics`, which needs the
registry to compute a denominator. That keeps the scoring and dispersion logic
free of I/O, which is why 162 tests run without network access or API keys.

---

## 4. Evidence scoring pipeline

What happens to a single candidate source.

```mermaid
flowchart TB
    START(["Source from spatial index"]) --> SENS{"Hospital, school<br/>or place of worship?"}
    SENS -->|yes| DROP1["EXCLUDED<br/><i>receptor, not a target</i>"]
    SENS -->|no| STOP{"Kerbside bus stop?<br/><i>node + no depot/terminal in name</i>"}
    STOP -->|yes| DROP2["EXCLUDED<br/><i>nothing to inspect</i>"]
    STOP -->|no| DIST{"Within 25 km?"}
    DIST -->|no| DROP3["EXCLUDED<br/><i>out of range</i>"]
    DIST -->|yes| WIND{"Downwind of station?"}
    WIND -->|yes| DROP4["EXCLUDED<br/><i>plume blows away</i>"]
    WIND -->|no| SCORE

    subgraph SCORE["Weighted evidence score"]
        P["Proximity 0.35<br/><i>linear falloff to 25 km</i>"]
        T["Atmospheric transport 0.28<br/><i>Gaussian plume, Briggs urban σ</i>"]
        CT["Category match 0.18<br/><i>vs Attribution Agent</i>"]
        ID["Dispatchability 0.12<br/><i>named facility?</i>"]
        SV["Severity 0.07<br/><i>hotspot AQI</i>"]
    end

    SCORE --> SAT{"Satellite detection?"}
    SAT -->|yes| SCALE["× detection confidence<br/><i>a thermal anomaly may not be a fire</i>"]
    SAT -->|no| RANK
    SCALE --> RANK["Rank, take top 5"]
    RANK --> OUT(["To Enforcement Agent<br/>with coordinates, σy,<br/>stability class, OSM link"])

    classDef drop fill:#3f1e1e,stroke:#ef4444,color:#e2e8f0
    classDef ok fill:#1e3f2f,stroke:#10b981,color:#e2e8f0
    class DROP1,DROP2,DROP3,DROP4 drop
    class OUT,RANK ok
```

---

## 5. AQI scale conversion

Why every reading passes through a conversion before use.

```mermaid
flowchart LR
    W["WAQI feed<br/><code>aqi: 36</code><br/><code>iaqi.pm25.v: 25</code>"]
    W --> N{"These are<br/>US EPA <i>index</i> values,<br/>not μg/m³"}
    N --> INV["epa_aqi_to_pm25()<br/><i>invert EPA breakpoints</i>"]
    INV --> CONC["PM2.5 ≈ 6 μg/m³<br/><i>a real concentration</i>"]
    CONC --> CPCB["pm25_to_aqi()<br/><i>India CPCB breakpoints</i>"]
    CPCB --> OUT["CPCB AQI + category<br/><i>+ aqi_epa_raw retained</i>"]

    BAD["Old path:<br/>pm25_to_aqi(25)<br/>= CPCB 41"]:::bad
    W -.->|"treated index as<br/>concentration"| BAD

    classDef bad fill:#3f1e1e,stroke:#ef4444,color:#e2e8f0
```

Live stations arrived on the EPA scale while static fallback cities sat on CPCB,
and the **hotspot ranking sorted both together** — so the top-5 feeding the entire
enforcement chain was ranked on mixed units. Mid-range readings were distorted
roughly 4×: an EPA index of 100 (truly "Satisfactory", 35.4 μg/m³) rendered as
CPCB 234 "Poor".

---

## 6. Deployment

```mermaid
flowchart LR
    subgraph V["Vercel"]
        FE["airwatch-frontend<br/><i>React static build</i>"]
        BE["airwatch-backend<br/><i>FastAPI serverless</i>"]
    end
    GH[("GitHub<br/>master")] --> FE & BE
    FE -->|"VITE_API_URL"| BE
    BE --> EXT(["WAQI · OWM · FIRMS · Azure OpenAI"])
```

> ⚠️ Vercel builds from `master`. The enforcement work is on
> `feature/enforcement-intelligence` — **merge before demoing**, or the live URL
> serves none of it.

Per-process in-memory caches and the rate limiter do not survive serverless
invocation boundaries. See [SCALABILITY.md](../SCALABILITY.md) for what that costs
and what would replace them.
