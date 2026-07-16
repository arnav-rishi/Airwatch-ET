from utils.attribution_confidence import score_attribution_confidence

# Delhi baseline (prompts.py): Road dust 28, Vehicles 20, Industry 11,
# Biomass burning 11, Construction 6, Secondary aerosol 24
# -> bucketed: traffic=20, industrial=11, construction=6, biomass_burning=11, other=52


def test_close_match_to_baseline_is_high_confidence():
    result = {"traffic": 22, "industrial": 10, "construction": 7, "biomass_burning": 12, "other": 49}
    scored = score_attribution_confidence("Delhi", result)
    assert scored["attribution_confidence"] == "high"
    assert scored["baseline_divergence"] < 25


def test_wildly_different_output_is_low_confidence():
    result = {"traffic": 90, "industrial": 2, "construction": 2, "biomass_burning": 2, "other": 4}
    scored = score_attribution_confidence("Delhi", result)
    assert scored["attribution_confidence"] == "low"


def test_moderately_different_output_is_medium_confidence():
    result = {"traffic": 35, "industrial": 20, "construction": 6, "biomass_burning": 11, "other": 28}
    scored = score_attribution_confidence("Delhi", result)
    assert scored["attribution_confidence"] == "medium"


def test_unknown_city_is_unverified():
    result = {"traffic": 50, "industrial": 20, "construction": 10, "biomass_burning": 10, "other": 10}
    scored = score_attribution_confidence("Nowhereville", result)
    assert scored == {"baseline_divergence": None, "attribution_confidence": "unverified"}


def test_missing_keys_in_result_are_treated_as_zero_not_a_crash():
    result = {"traffic": 20}
    scored = score_attribution_confidence("Delhi", result)
    assert scored["baseline_divergence"] is not None
