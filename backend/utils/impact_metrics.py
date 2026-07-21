"""
Quantified enforcement impact, derived from the system's own data.

Every figure here is computed from the committed registry and the live scoring
run that produced a recommendation. Nothing is assumed, extrapolated from
industry averages, or asserted as a headline number — if a metric cannot be
derived from something this system actually holds, it is not reported.

The one external input is the status-quo baseline, and it is deliberately the
weakest claim in the module: how a municipal inspector is tasked today. That
comes from the CAG's 2024 audit finding that only 31% of cities with monitoring
data had any actionable multi-agency response protocol linked to those readings,
which is cited rather than invented. The comparison it supports is a *targeting*
comparison — random or complaint-driven selection among a city's registered
sources versus evidence-ranked selection — and that arithmetic is exact given
the registry, which is why it is expressed that way rather than as a claim about
tonnes of pollution avoided.

What this module deliberately does NOT claim:
  * pollution reduction in ug/m3 — would require knowing each facility's
    emission rate and the counterfactual of an inspection actually changing
    behaviour. Neither is available.
  * money saved — depends on inspector salaries, travel costs and penalty
    recovery rates that vary by state and are not public.
  * compliance improvement — needs longitudinal data from a real deployment.

Overstating any of those is exactly the kind of number a domain expert would
puncture in one question, and it would cast doubt on the figures that are real.
"""
from services.source_registry import get_sources_for_city, registry_stats
from utils.enforcement_scoring import (
    MAX_RELEVANT_KM,
    haversine_km,
    is_minor_fleet_stop,
    is_sensitive_receptor,
)

# A standard municipal inspection shift. Used only to convert a count of
# inspectors into shift-hours for readability — it is not a productivity claim.
INSPECTOR_SHIFT_HOURS = 8

# CAG 2024 audit of the National Clean Air Programme: only 31% of cities with
# monitoring data had any actionable multi-agency response protocol linked to
# those readings. Cited, not estimated.
CAG_CITIES_WITH_RESPONSE_PROTOCOL_PCT = 31


def hotspot_impact(hotspot: dict) -> dict:
    """
    How much the correlation narrows the search space for one hotspot.

    The counterfactual, stated honestly: without source correlation an inspector
    dispatched to a city has no evidence ranking and is choosing among that
    city's registered sources within operational range. With it, they get a
    shortlist ordered by physical plausibility.

    Both sides are drawn from the same population — sources that survive the
    scorer's own exclusions (sensitive receptors, kerbside stops) and lie within
    the same operational radius. Comparing a ranked shortlist against the raw
    unfiltered registry would flatter the result by counting sources no sensible
    process would visit anyway.
    """
    candidates = hotspot.get("candidate_sources") or []
    city = hotspot.get("city", "")

    all_sources = get_sources_for_city(city)
    eligible = [
        s for s in all_sources
        if not is_sensitive_receptor(s) and not is_minor_fleet_stop(s)
    ]
    # Sources an inspector could plausibly be sent to for this hotspot: eligible
    # and within the same operational radius the scorer screens on.
    within_range = [
        s for s in eligible
        if haversine_km(hotspot["lat"], hotspot["lon"], s["lat"], s["lon"]) <= MAX_RELEVANT_KM
    ]

    n_range = len(within_range)
    n_short = len(candidates)

    # Both sides must be non-empty for the ratio to mean anything. With no
    # eligible sources in range, n_range/n_short is 0.0 — which would read as
    # "targeting got worse" when the truth is there was nothing to narrow.
    can_compare = n_range > 0 and n_short > 0
    return {
        "city": city,
        "registered_sources_in_city": len(all_sources),
        "eligible_sources_in_range": n_range,
        "shortlisted": n_short,
        "narrowing_factor": round(n_range / n_short, 1) if can_compare else None,
        "random_hit_rate_pct": round(100 * n_short / n_range, 1) if can_compare else None,
        "top_evidence_score": candidates[0]["evidence_score"] if candidates else None,
    }


def enforcement_impact(result: dict) -> dict:
    """
    Aggregate impact figures for one enforcement run.

    Attaches to the /enforcement/auto response so the numbers a deck would quote
    are computed live from the same run a reviewer is looking at, rather than
    typed into a slide once and left to rot.
    """
    hotspots = result.get("hotspots") or []
    priorities = result.get("priorities") or []

    per_hotspot = [hotspot_impact(h) for h in hotspots if h.get("candidate_sources")]

    total_in_range = sum(h["eligible_sources_in_range"] for h in per_hotspot)
    total_shortlisted = sum(h["shortlisted"] for h in per_hotspot)
    can_compare = total_in_range > 0 and total_shortlisted > 0

    inspectors = sum(
        p.get("inspector_count") or 0
        for p in priorities
        if isinstance(p.get("inspector_count"), (int, float))
    )

    matched = sum(1 for p in priorities if p.get("source_matched"))

    stats = registry_stats()

    return {
        # Search-space narrowing — exact arithmetic over the registry.
        "eligible_sources_in_range": total_in_range,
        "shortlisted_sources": total_shortlisted,
        "narrowing_factor": (
            round(total_in_range / total_shortlisted, 1) if can_compare else None
        ),
        "random_hit_rate_pct": (
            round(100 * total_shortlisted / total_in_range, 1) if can_compare else None
        ),

        # Deployment scale of this specific recommendation set.
        "inspectors_recommended": inspectors,
        "inspector_shift_hours": inspectors * INSPECTOR_SHIFT_HOURS,
        "priorities_issued": len(priorities),
        "priorities_traceable_to_registry": matched,

        # Latency, measured in the route rather than claimed.
        "signal_to_dispatch_seconds": result.get("response_time_seconds"),

        # Coverage the platform can act over.
        "registry_sources_total": stats.get("total_sources"),
        "registry_cities_covered": stats.get("cities_covered"),

        "per_hotspot": per_hotspot,

        "baseline_note": (
            f"CAG's 2024 NCAP audit found only "
            f"{CAG_CITIES_WITH_RESPONSE_PROTOCOL_PCT}% of cities with monitoring data had "
            "any actionable response protocol linked to those readings. Narrowing here is "
            "measured against evidence-blind selection among the same eligible sources, "
            "not against a claim about emissions avoided."
        ),
    }
