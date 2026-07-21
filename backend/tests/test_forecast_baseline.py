from utils.forecast_baseline import compute_baseline_forecast, backtest_baseline


def _history(n=24, start=150, step=0):
    return [{"hour": f"{i}:00", "aqi": start + step * i, "pm25": 0} for i in range(n)]


def test_flat_history_forecasts_flat_with_neutral_wind():
    history = _history(start=150, step=0)
    forecast = compute_baseline_forecast(history, current_aqi=150, weather_forecast=[])
    assert len(forecast) == 6
    for point in forecast:
        assert point["predicted_aqi"] == 150


def test_rising_trend_is_extrapolated_upward():
    history = _history(start=100, step=2)  # steadily rising ~2 AQI/hour
    forecast = compute_baseline_forecast(history, current_aqi=146, weather_forecast=[])
    assert forecast[-1]["predicted_aqi"] > forecast[0]["predicted_aqi"]


def test_high_wind_forecasts_lower_than_low_wind():
    history = _history(start=150, step=0)
    calm = compute_baseline_forecast(history, current_aqi=150, weather_forecast=[{"wind_speed_kmh": 2}])
    windy = compute_baseline_forecast(history, current_aqi=150, weather_forecast=[{"wind_speed_kmh": 30}])
    assert windy[0]["predicted_aqi"] < calm[0]["predicted_aqi"]


def test_forecast_never_goes_negative():
    history = _history(start=5, step=-2)  # sharply falling toward/below zero
    forecast = compute_baseline_forecast(history, current_aqi=1, weather_forecast=[])
    assert all(point["predicted_aqi"] >= 0 for point in forecast)


def test_backtest_reports_mae_on_sufficient_history():
    history = _history(start=150, step=0)
    result = backtest_baseline(history, holdout=6)
    assert result["n"] == 6
    assert result["mae"] == 0.0  # flat history -> perfect persistence forecast


def test_backtest_returns_none_on_insufficient_history():
    history = _history(n=4, start=150, step=0)
    result = backtest_baseline(history, holdout=6)
    assert result["mae"] is None
    assert result["n"] == 0
    assert result["persistence_rmse"] is None
    assert result["skill_vs_persistence"] is None


# ─── Skill against the persistence benchmark ──────────────────────────────────
# "RMSE versus persistence baseline" is named directly in the evaluation
# criteria. Persistence — "it will stay exactly as it is now" — is the naive
# benchmark any forecast must beat to have demonstrated skill at all.

def test_backtest_reports_both_rmse_figures():
    result = backtest_baseline(_history(start=100, step=3), holdout=6)
    assert result["rmse"] is not None
    assert result["persistence_rmse"] is not None


def test_trend_model_beats_persistence_on_a_trending_series():
    """
    A steadily rising series is exactly where persistence fails and a trend
    model should win — skill must come out clearly positive.
    """
    result = backtest_baseline(_history(start=100, step=3), holdout=6)
    assert result["rmse"] < result["persistence_rmse"]
    assert result["skill_vs_persistence"] > 0.5


def test_skill_is_negative_when_the_model_loses_to_persistence():
    """
    The number has to be able to say "worse than doing nothing", or it isn't a
    real measurement. A series that rises then abruptly reverses punishes the
    extrapolated trend while persistence stays close.
    """
    values = [100, 110, 120, 130, 140, 150, 160, 170, 180] + [180, 178, 176, 174, 172, 170]
    history = [{"hour": f"{i}:00", "aqi": v, "pm25": 0} for i, v in enumerate(values)]

    result = backtest_baseline(history, holdout=6)
    assert result["rmse"] > result["persistence_rmse"]
    assert result["skill_vs_persistence"] < 0


def test_skill_is_none_when_persistence_is_already_perfect():
    """
    A perfectly flat series gives persistence zero error. There's nothing to
    improve on, so a skill score would be meaningless — report None rather than
    dividing by zero or implying an achievement.
    """
    result = backtest_baseline(_history(start=150, step=0), holdout=6)
    assert result["persistence_rmse"] == 0.0
    assert result["skill_vs_persistence"] is None


def test_rmse_penalises_large_errors_more_than_mae():
    """Sanity check that RMSE isn't accidentally computing MAE."""
    values = [100] * 10 + [100, 100, 100, 100, 100, 300]
    history = [{"hour": f"{i}:00", "aqi": v, "pm25": 0} for i, v in enumerate(values)]
    result = backtest_baseline(history, holdout=6)
    assert result["rmse"] > result["mae"]
