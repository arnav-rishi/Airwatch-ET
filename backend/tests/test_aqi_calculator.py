from utils.aqi_calculator import pm25_to_aqi, aqi_category, circle_radius


def test_pm25_to_aqi_boundaries():
    assert pm25_to_aqi(0) == 0
    assert pm25_to_aqi(30) == 50
    assert pm25_to_aqi(60) == 100
    assert pm25_to_aqi(250) == 400


def test_aqi_category_labels():
    assert aqi_category(25)["label"] == "Good"
    assert aqi_category(150)["label"] == "Moderate"
    assert aqi_category(450)["label"] == "Severe"


def test_circle_radius_scales_with_severity():
    assert circle_radius(50) < circle_radius(150) < circle_radius(350)
