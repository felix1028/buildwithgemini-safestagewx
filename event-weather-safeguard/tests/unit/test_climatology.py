# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from app.climatology import (
    calculate_percentile,
    determine_us_region,
    get_regional_enso_teleconnection,
    generate_histogram_bins,
    evaluate_climatological_hazards,
    get_climatology_full_report,
    format_climatology_for_agent,
)


def test_calculate_percentile():
    data = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p10 = calculate_percentile(data, 10)
    p50 = calculate_percentile(data, 50)
    p90 = calculate_percentile(data, 90)

    assert p10 == 19.0 or p10 == 20.0 or 10.0 <= p10 <= 25.0
    assert p50 == 55.0 or p50 == 50.0 or 45.0 <= p50 <= 60.0
    assert p90 == 91.0 or p90 == 90.0 or 85.0 <= p90 <= 100.0


def test_determine_us_region():
    # Savannah, GA
    assert determine_us_region(32.0008, -80.9735) == "Southeast"
    # Austin, TX
    assert determine_us_region(30.2672, -97.7431) == "Gulf Coast"
    # Chicago, IL
    assert determine_us_region(41.8781, -87.6298) == "Midwest / Ohio Valley"
    # Seattle, WA
    assert determine_us_region(47.6062, -122.3321) == "Pacific Northwest"
    # Los Angeles, CA
    assert determine_us_region(34.0522, -118.2437) == "California"


def test_regional_enso_teleconnection():
    # La Niña in August in Southeast
    la_nina_aug = get_regional_enso_teleconnection("Southeast", 8, "La Niña Advisory")
    assert "Heightened" in la_nina_aug["tropical_impact"]
    assert "hurricane" in la_nina_aug["tropical_impact"].lower() or "tropical" in la_nina_aug["tropical_impact"].lower()

    # El Niño in August in Southeast
    el_nino_aug = get_regional_enso_teleconnection("Southeast", 8, "El Niño Advisory")
    assert "Reduced" in el_nino_aug["tropical_impact"] or "shear" in el_nino_aug["tropical_impact"].lower()

    # El Niño in Winter in Southeast
    el_nino_jan = get_regional_enso_teleconnection("Southeast", 1, "El Niño Advisory")
    assert "wetter" in el_nino_jan["precipitation_anomaly"].lower()


def test_generate_histogram_bins():
    data = [70.0, 72.0, 75.0, 80.0, 85.0, 88.0, 92.0, 95.0, 98.0]
    bins = generate_histogram_bins(data, num_bins=4)
    assert len(bins["labels"]) == 4
    assert len(bins["counts"]) == 4
    assert sum(bins["counts"]) == len(data)


def test_evaluate_climatological_hazards():
    mock_metrics = {
        "season_window": "August",
        "temp_high": {
            "p10": 82.0,
            "median": 91.0,
            "p90": 96.5,
            "pct_over_90": 65.0,
            "pct_over_95": 25.0,
        },
        "temp_low": {
            "p10": 70.0,
            "median": 75.0,
            "p90": 80.0,
            "pct_freezing": 0.0,
        },
        "precip": {
            "rain_day_prob_pct": 45.0,
            "heavy_rain_prob_pct": 14.0,
            "p90_wet_day_volume_inches": 0.85,
        },
        "wind": {
            "median_gust_mph": 18.0,
            "p90_gust_mph": 31.5,
            "pct_days_over_25mph": 28.0,
            "pct_days_over_35mph": 6.0,
        },
    }
    mock_enso = {"tropical_impact": "Heightened Atlantic Tropical Cyclone", "enso_phase": "La Niña"}

    hazards = evaluate_climatological_hazards(mock_metrics, mock_enso, structure_type="Stage Scaffolding", attendee_count=250)
    categories = [h["category"] for h in hazards]

    assert "HEAT" in categories
    assert "FLOORING" in categories
    assert "WIND" in categories
    assert "TROPICAL" in categories


@pytest.mark.asyncio
async def test_get_climatology_full_report_integration():
    report = await get_climatology_full_report(
        lat=32.0008,
        lon=-80.9735,
        target_date_str="2026-08-13",
        location_name="Savannah, GA",
        attendee_count=100,
    )
    assert report["latitude"] == 32.0008
    assert report["longitude"] == -80.9735
    assert report["region"] == "Southeast"
    assert "annual_position_desc" in report
    assert len(report["annual_curve"]) >= 12
    assert "temp_high" in report["metrics"]
    assert "p90" in report["metrics"]["temp_high"]
    assert "precip" in report["metrics"]
    assert "wind" in report["metrics"]
    assert "enso" in report
    assert len(report["hazards"]) >= 1

    formatted = format_climatology_for_agent(report)
    assert "Long-Term Climatology" in formatted
    assert "ENSO" in formatted
