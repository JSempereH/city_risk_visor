import pytest
from fastapi.testclient import TestClient

from app.hazard import psha
from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("city", ["san_jose", "guatemala", "santo_domingo", "lomas_centinela"])
def test_disaggregation_all_three_cities(city):
    for years in (475, 975, 2475):
        response = client.get(f"/api/scenarios/{city}/disaggregation", params={"return_period_years": years})
        assert response.status_code == 200
        body = response.json()
        assert body["imt"] == "PGA"
        assert 4.0 < body["mean_magnitude"] < 9.0
        assert body["mean_distance_km"] > 0
        assert len(body["bins"]) > 0
        # Bin fractions sum to ~1 (normalized in psha.disaggregation()).
        assert sum(b["fraction"] for b in body["bins"]) == pytest.approx(1.0, abs=1e-6)


def test_disaggregation_rarer_event_has_higher_controlling_magnitude():
    # A longer return period is dominated by rarer, larger events, the
    # same DSHA-vs-PSHA logic as docs/psha_plan.md, now visible
    # per-bin rather than just in the aggregate hazard curve.
    mags = [
        client.get("/api/scenarios/san_jose/disaggregation", params={"return_period_years": years}).json()[
            "mean_magnitude"
        ]
        for years in (475, 975, 2475)
    ]
    assert mags == sorted(mags)


def test_disaggregation_invalid_return_period_400():
    response = client.get("/api/scenarios/san_jose/disaggregation", params={"return_period_years": 100})
    assert response.status_code == 400


def test_disaggregation_unsupported_city_404():
    response = client.get("/api/scenarios/nowhere/disaggregation", params={"return_period_years": 475})
    assert response.status_code == 404


def test_psha_module_disagg_supported_cities():
    assert psha.DISAGG_SUPPORTED_CITIES == frozenset({"san_jose", "guatemala", "santo_domingo", "lomas_centinela"})
