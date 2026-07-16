"""
Deterministic sanity-check layer over the LLM's source-attribution output.

prompts.py::attribution_user anchors the LLM to a published CPCB baseline and
asks it to adjust the percentages for live conditions — but nothing stops it
from hallucinating an adjustment disconnected from the baseline it was given.
This module measures how far the LLM's returned breakdown actually is from
that baseline, so the API can surface a confidence signal instead of silently
trusting free-form output. It's a rule-based check, not a learned model —
appropriately scoped for what a hand-curated citation table can support; it
does not claim the LLM's numbers are scientifically correct, only that they
are (or aren't) a plausible adjustment of the cited baseline.
"""
from prompts import CPCB_SOURCE_APPORTIONMENT

# The LLM's response schema (prompts.py::attribution_user) buckets sources
# into 5 fixed categories that don't map 1:1 onto the raw CPCB breakdown's
# free-text source names — this is the many-to-one mapping between them.
_CATEGORY_MAP = {
    "traffic": {"vehicles", "transport"},
    "industrial": {"industry"},
    "construction": {"construction"},
    "biomass_burning": {"biomass burning"},
    "other": {"road dust", "marine/sea salt", "secondary aerosol", "others"},
}

_HIGH_MAX = 25
_MEDIUM_MAX = 50


def score_attribution_confidence(city: str, result: dict) -> dict:
    """
    Returns {"baseline_divergence": int|None, "attribution_confidence": str}.

    High divergence isn't automatically wrong — real conditions do shift the
    mix — but a large, unexplained divergence is exactly the case a reviewer
    should be able to interrogate, so it's surfaced as a number rather than
    hidden inside a paragraph of LLM prose.
    """
    entry = CPCB_SOURCE_APPORTIONMENT.get(city)
    if not entry:
        return {"baseline_divergence": None, "attribution_confidence": "unverified"}

    baseline_by_bucket = {bucket: 0 for bucket in _CATEGORY_MAP}
    for item in entry["breakdown"]:
        name = item["source"].lower()
        for bucket, names in _CATEGORY_MAP.items():
            if name in names:
                baseline_by_bucket[bucket] += item["pct"]
                break

    divergence = sum(
        abs((result.get(bucket) or 0) - baseline_by_bucket[bucket])
        for bucket in _CATEGORY_MAP
    )

    if divergence <= _HIGH_MAX:
        confidence = "high"
    elif divergence <= _MEDIUM_MAX:
        confidence = "medium"
    else:
        confidence = "low"

    return {"baseline_divergence": divergence, "attribution_confidence": confidence}
