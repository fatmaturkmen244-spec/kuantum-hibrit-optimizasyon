from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from hybrid_quantum.maps import (
    AzureMapsClient,
    AzureMapsSettings,
    AzureMapsUpstreamError,
    _parse_geocode_response,
    _parse_poi_response,
    _parse_route_matrix,
    _route_matrix_payload,
)
from hybrid_quantum.models import (
    GeoPoint,
    PlaceCandidate,
    PlaceSearchRequest,
    PlaceSearchResponse,
    RouteLocation,
)


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


def test_places_client_merges_tr_address_and_poi_results_without_external_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/geocode":
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [29.014, 40.991]},
                            "properties": {
                                "address": {
                                    "formattedAddress": "Kadıköy, İstanbul",
                                    "countryRegion": {"ISO": "TR"},
                                },
                                "confidence": "High",
                                "geocodePoints": [
                                    {
                                        "usageTypes": ["Route"],
                                        "geometry": {
                                            "coordinates": [29.0142, 40.9908]
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
            )
        if request.url.path == "/search/poi/json":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "type": "POI",
                            "score": 0.91,
                            "poi": {
                                "name": "Örnek Market Kadıköy",
                                "categories": ["Grocery Store"],
                            },
                            "address": {
                                "freeformAddress": "Caferağa, Kadıköy, İstanbul",
                                "countryCode": "TR",
                            },
                            "position": {"lat": 40.989, "lon": 29.025},
                            "entryPoints": [
                                {
                                    "type": "main",
                                    "position": {"lat": 40.9888, "lon": 29.0253},
                                }
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404)

    maps_client = AzureMapsClient(
        AzureMapsSettings(subscription_key="test-server-only-key"),
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(maps_client.search_places("Kadıköy market", top=3))

    assert result.query == "Kadıköy market"
    assert result.country == "TR"
    assert [candidate.kind for candidate in result.candidates] == ["poi", "address"]
    assert result.candidates[0].reference == "poi"
    assert result.candidates[0].category == "Grocery Store"
    assert result.candidates[0].uses_route_point is True
    assert result.candidates[0].point.longitude == 29.0253
    assert result.candidates[1].reference == "geocode"
    assert result.candidates[1].point.longitude == 29.0142

    poi_request = next(request for request in requests if request.url.path == "/search/poi/json")
    geocode_request = next(request for request in requests if request.url.path == "/geocode")
    assert geocode_request.url.params["bbox"] == "25.5,35.6,45.1,42.4"
    assert poi_request.url.params["countrySet"] == "TR"
    assert poi_request.url.params["typeahead"] == "true"
    assert poi_request.headers["subscription-key"] == "test-server-only-key"


def test_places_client_rejects_non_turkey_geocoding_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/geocode":
            return httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [-73.98, 40.75]},
                            "properties": {
                                "address": {
                                    "formattedAddress": "New York, NY",
                                    "countryRegion": {"ISO": "US"},
                                }
                            },
                        }
                    ],
                },
            )
        return httpx.Response(200, json={"results": []})

    maps_client = AzureMapsClient(
        AzureMapsSettings(subscription_key="test-server-only-key"),
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(maps_client.search_places("New York", top=5))
    assert result.candidates == []


def test_poi_parser_requires_an_explicit_turkey_country_code() -> None:
    candidates = _parse_poi_response(
        {
            "results": [
                {
                    "type": "POI",
                    "poi": {"name": "Countryless Market"},
                    "address": {"freeformAddress": "Belirsiz adres"},
                    "position": {"lat": 40.99, "lon": 29.02},
                }
            ]
        },
        "market",
    )
    assert candidates == []


def test_place_search_request_rejects_blank_or_client_scope_override() -> None:
    with pytest.raises(ValidationError, match="Konum araması"):
        PlaceSearchRequest(query="   ")
    with pytest.raises(ValidationError):
        PlaceSearchRequest(query="Kadıköy", country="DE")


def test_places_endpoint_returns_only_normalized_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    from hybrid_quantum import api

    class FakeMapsClient:
        async def search_places(self, query: str, *, top: int) -> PlaceSearchResponse:
            assert query == "Bostancı market"
            assert top == 2
            return PlaceSearchResponse(
                query=query,
                candidates=[
                    PlaceCandidate(
                        label="Örnek Market",
                        kind="poi",
                        reference="poi",
                        address="Bostancı, İstanbul",
                        point=GeoPoint(latitude=40.960, longitude=29.093),
                    )
                ],
            )

    monkeypatch.setattr(api, "_maps_client", lambda _request: FakeMapsClient())
    client = TestClient(api.app)
    response = client.post(
        "/maps/places",
        json={"query": " Bostancı market ", "top": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Bostancı market"
    assert payload["country"] == "TR"
    assert payload["candidates"][0] == {
        "label": "Örnek Market",
        "point": {"latitude": 40.96, "longitude": 29.093},
        "kind": "poi",
        "reference": "poi",
        "display_point": None,
        "address": "Bostancı, İstanbul",
        "category": None,
        "confidence": None,
        "score": None,
        "uses_route_point": False,
    }


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
