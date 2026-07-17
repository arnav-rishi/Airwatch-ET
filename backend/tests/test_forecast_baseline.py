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
    assert result == {"mae": None, "n": 0}
