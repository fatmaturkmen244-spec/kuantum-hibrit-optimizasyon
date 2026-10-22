from __future__ import annotations

from pathlib import Path

import pytest

from hybrid_quantum.maps import (
    AzureMapsUpstreamError,
    _parse_geocode_response,
    _parse_route_matrix,
    _route_matrix_payload,
)
from hybrid_quantum.models import GeoPoint, RouteLocation


def _locations() -> list[RouteLocation]:
    return [
        RouteLocation(name="İstanbul", point=GeoPoint(latitude=41.0082, longitude=28.9784)),
        RouteLocation(name="Ankara", point=GeoPoint(latitude=39.9334, longitude=32.8597)),
        RouteLocation(name="İzmir", point=GeoPoint(latitude=38.4237, longitude=27.1428)),
    ]


def test_geocode_prefers_route_point_and_keeps_display_point() -> None:
    result = _parse_geocode_response(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [28.9744, 41.0256]},
                    "properties": {
                        "address": {"formattedAddress": "Beyoğlu, İstanbul"},
                        "confidence": "High",
                        "matchCodes": ["Good"],
                        "geocodePoints": [
                            {
                                "usageTypes": ["Display"],
                                "geometry": {"coordinates": [28.9744, 41.0256]},
                            },
                            {
                                "usageTypes": ["Route"],
                                "geometry": {"coordinates": [28.9749, 41.0252]},
                            },
                        ],
                    },
                }
            ],
        },
        "Galata Kulesi",
    )
    assert result.candidates[0].point.longitude == 28.9749
    assert result.candidates[0].point.latitude == 41.0252
    assert result.candidates[0].display_point.longitude == 28.9744
    assert result.candidates[0].uses_route_point is True


def test_route_matrix_payload_uses_geojson_lon_lat() -> None:
    payload = _route_matrix_payload(_locations(), traffic="historical")
    assert payload["features"][0]["geometry"]["coordinates"] == [
        [28.9784, 41.0082],
        [32.8597, 39.9334],
        [27.1428, 38.4237],
    ]
    assert payload["features"][0]["properties"]["pointType"] == "origins"
    assert payload["features"][1]["properties"]["pointType"] == "destinations"
    assert payload["departAt"] == "any"


def test_route_matrix_uses_matrix_indices_not_response_order() -> None:
    cells = []
    for origin in reversed(range(3)):
        for destination in reversed(range(3)):
            cells.append(
                {
                    "statusCode": 200,
                    "originIndex": origin,
                    "destinationIndex": destination,
                    "distanceInMeters": (origin + 1) * 10_000 + destination,
                    "durationInSeconds": (origin + 1) * 1_000 + destination,
                }
            )
    result = _parse_route_matrix(
        {"type": "Feature", "properties": {"matrix": cells}}, _locations(), traffic="historical"
    )
    assert result.distance_meters[0][1] == 10_001
    assert result.distance_meters[1][0] == 20_000
    assert result.duration_seconds[2][1] == 3_001
    assert result.distance_meters[1][0] != result.distance_meters[0][1]


def test_route_matrix_rejects_an_incomplete_matrix() -> None:
    with pytest.raises(AzureMapsUpstreamError, match="tüm konum çiftleri"):
        _parse_route_matrix(
            {
                "type": "Feature",
                "properties": {
                    "matrix": [
                        {
                            "statusCode": 200,
                            "originIndex": 0,
                            "destinationIndex": 1,
                            "distanceInMeters": 10,
                            "durationInSeconds": 3,
                        }
                    ]
                },
            },
            _locations()[:2],
            traffic="historical",
        )


def test_browser_bundle_does_not_contain_the_server_secret_name() -> None:
    browser_bundle = Path(__file__).parents[1] / "docs" / "app.js"
    assert "AZURE_MAPS_SUBSCRIPTION_KEY" not in browser_bundle.read_text(encoding="utf-8")
