"""Azure Maps integration kept behind the server boundary.

This module deliberately never exposes an Azure Maps credential to a browser.
The public GitHub Pages laboratory can call a separately deployed API, while this
client reads its credential only from the server process environment.
"""

from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from typing import Any, Sequence

import httpx
from dotenv import load_dotenv

from .models import (
    GeoPoint,
    GeocodeCandidate,
    GeocodeResponse,
    PlaceCandidate,
    PlaceSearchResponse,
    RouteLocation,
    RouteMatrixResponse,
)


AZURE_MAPS_PUBLIC_ENDPOINT = "https://atlas.microsoft.com"
# WGS84 rectangle covering Türkiye and a small boundary margin. It is a
# query-compatible geobias for free-form Geocoding; returned candidates are
# still explicitly country-checked before they reach the browser.
TURKIYE_BBOX = "25.5,35.6,45.1,42.4"


class AzureMapsError(RuntimeError):
    """Base error whose message is safe to return to an API consumer."""


class AzureMapsConfigurationError(AzureMapsError):
    """Raised when the server has no Azure Maps credential."""


class AzureMapsRateLimitError(AzureMapsError):
    """Raised when Azure Maps asks the client to slow down."""


class AzureMapsUpstreamError(AzureMapsError):
    """Raised for an unavailable or malformed upstream Maps response."""


@dataclass(frozen=True)
class AzureMapsSettings:
    """Only server-side settings needed by the Azure Maps REST client."""

    subscription_key: str
    endpoint: str = AZURE_MAPS_PUBLIC_ENDPOINT
    geocode_api_version: str = "2026-01-01"
    poi_search_api_version: str = "1.0"
    route_api_version: str = "2025-01-01"
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls) -> "AzureMapsSettings":
        load_dotenv()
        subscription_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY", "").strip()
        if not subscription_key:
            raise AzureMapsConfigurationError(
                "Gerçek yol verisi henüz sunucuda yapılandırılmadı. "
                "AZURE_MAPS_SUBSCRIPTION_KEY yalnızca sunucu ortamına eklenmelidir."
            )
        endpoint = os.getenv("AZURE_MAPS_ENDPOINT", AZURE_MAPS_PUBLIC_ENDPOINT).strip()
        if not endpoint.startswith("https://"):
            raise AzureMapsConfigurationError("Azure Maps endpoint'i HTTPS olmalıdır.")
        return cls(subscription_key=subscription_key, endpoint=endpoint.rstrip("/"))


class AzureMapsClient:
    """Small, testable proxy client for Azure Maps Search and Route APIs."""

    def __init__(
        self,
        settings: AzureMapsSettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings or AzureMapsSettings.from_environment()
        self._transport = transport

    @property
    def _auth_headers(self) -> dict[str, str]:
        # This header is added only from the backend process and is never
        # serialized in a response, log message, or frontend file.
        return {"subscription-key": self.settings.subscription_key}

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {**self._auth_headers, **(headers or {})}
        retry_statuses = {429, 500, 502, 503, 504}

        async with httpx.AsyncClient(
            base_url=self.settings.endpoint,
            timeout=httpx.Timeout(self.settings.timeout_seconds),
            transport=self._transport,
        ) as client:
            for attempt in range(2):
                try:
                    response = await client.request(
                        method,
                        path,
                        params=params,
                        json=json,
                        headers=request_headers,
                    )
                except httpx.RequestError as exc:
                    if attempt == 0:
                        await asyncio.sleep(0.15)
                        continue
                    raise AzureMapsUpstreamError(
                        "Konum hizmetine şu anda erişilemiyor. Lütfen tekrar deneyin."
                    ) from exc

                if response.status_code in retry_statuses and attempt == 0:
                    retry_after = response.headers.get("Retry-After", "0.15")
                    try:
                        delay = min(max(float(retry_after), 0.05), 1.0)
                    except ValueError:
                        delay = 0.15
                    await asyncio.sleep(delay)
                    continue

                if response.status_code == 429:
                    raise AzureMapsRateLimitError(
                        "Konum hizmeti kısa süreliğine yoğun. Biraz sonra yeniden deneyin."
                    )
                if response.is_error:
                    raise AzureMapsUpstreamError(
                        "Konum hizmeti isteği tamamlayamadı. Lütfen konumları kontrol edip tekrar deneyin."
                    )
                try:
                    data = response.json()
                except ValueError as exc:
                    raise AzureMapsUpstreamError(
                        "Konum hizmeti beklenmeyen bir yanıt verdi."
                    ) from exc
                if not isinstance(data, dict):
                    raise AzureMapsUpstreamError("Konum hizmeti geçerli bir yanıt vermedi.")
                return data

        raise AzureMapsUpstreamError("Konum hizmeti isteği tamamlanamadı.")

    async def geocode(self, query: str, *, top: int = 5) -> GeocodeResponse:
        data = await self._request_json(
            "GET",
            "/geocode",
            params={
                "api-version": self.settings.geocode_api_version,
                "query": query,
                "top": top,
                "bbox": TURKIYE_BBOX,
            },
            headers={"Accept-Language": "tr-TR"},
        )
        return _parse_geocode_response(data, query, country_code="TR")

    async def search_places(self, query: str, *, top: int = 5) -> PlaceSearchResponse:
        """Return a small, Turkey-only blend of address and POI candidates.

        Azure Maps' current Geocoding endpoint deliberately excludes POIs, so
        address geocoding and POI type-ahead are requested independently.  A
        temporary failure of one source still leaves the other source usable;
        only a total outage is reported to the caller.
        """

        # Keep the two small source requests sequential to reduce burst rate
        # on a public proxy. A partial source failure is still handled below,
        # so POI search remains useful when geocoding temporarily fails (and
        # vice versa).
        try:
            geocode_data: dict[str, Any] | Exception = await self._request_json(
                "GET",
                "/geocode",
                params={
                    "api-version": self.settings.geocode_api_version,
                    "query": query,
                    "top": top,
                    "bbox": TURKIYE_BBOX,
                },
                headers={"Accept-Language": "tr-TR"},
            )
        except Exception as exc:  # normalized below; no upstream detail leaks
            geocode_data = exc
        try:
            poi_data: dict[str, Any] | Exception = await self._request_json(
                "GET",
                "/search/poi/json",
                params={
                    "api-version": self.settings.poi_search_api_version,
                    "query": query,
                    "limit": top,
                    "countrySet": "TR",
                    "typeahead": "true",
                },
                headers={"Accept-Language": "tr-TR"},
            )
        except Exception as exc:  # normalized below; no upstream detail leaks
            poi_data = exc

        failures: list[AzureMapsError] = []
        successful_sources = 0
        address_candidates: list[PlaceCandidate] = []
        poi_candidates: list[PlaceCandidate] = []

        if isinstance(geocode_data, Exception):
            failures.append(_as_maps_error(geocode_data))
        else:
            try:
                geocoded = _parse_geocode_response(geocode_data, query, country_code="TR")
                address_candidates = [_place_from_geocode(candidate) for candidate in geocoded.candidates]
                successful_sources += 1
            except AzureMapsError as exc:
                failures.append(exc)

        if isinstance(poi_data, Exception):
            failures.append(_as_maps_error(poi_data))
        else:
            try:
                poi_candidates = _parse_poi_response(poi_data, query)
                successful_sources += 1
            except AzureMapsError as exc:
                failures.append(exc)

        if successful_sources == 0:
            raise _preferred_place_error(failures)

        return PlaceSearchResponse(
            query=query,
            candidates=_merge_place_candidates(poi_candidates, address_candidates, top=top),
        )

    async def route_matrix(
        self,
        locations: Sequence[RouteLocation],
        *,
        traffic: str = "historical",
    ) -> RouteMatrixResponse:
        payload = _route_matrix_payload(locations, traffic=traffic)
        data = await self._request_json(
            "POST",
            "/route/matrix",
            params={"api-version": self.settings.route_api_version},
            json=payload,
            headers={"Content-Type": "application/geo+json", "Accept-Language": "tr-TR"},
        )
        return _parse_route_matrix(data, locations, traffic=traffic)


def _parse_geocode_response(
    data: dict[str, Any], query: str, *, country_code: str | None = None
) -> GeocodeResponse:
    features = data.get("features")
    if not isinstance(features, list):
        raise AzureMapsUpstreamError("Adres çözümü geçerli konum sonuçları döndürmedi.")

    candidates: list[GeocodeCandidate] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        if country_code and _feature_country_code(feature) != country_code:
            continue
        display_point = _point_from_feature(feature)
        if display_point is None:
            continue
        properties = feature.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        route_point = _route_point(properties) or display_point
        address_data = properties.get("address")
        address_data = address_data if isinstance(address_data, dict) else {}
        label = (
            address_data.get("formattedAddress")
            or properties.get("name")
            or properties.get("freeformAddress")
            or query
        )
        match_codes = properties.get("matchCodes")
        candidates.append(
            GeocodeCandidate(
                label=str(label),
                point=route_point,
                display_point=display_point,
                address=str(address_data.get("formattedAddress") or label),
                confidence=_optional_string(properties.get("confidence")),
                match_codes=[str(code) for code in match_codes]
                if isinstance(match_codes, list)
                else [],
                uses_route_point=route_point != display_point,
            )
        )
    return GeocodeResponse(candidates=candidates)


def _as_maps_error(exc: Exception) -> AzureMapsError:
    if isinstance(exc, AzureMapsError):
        return exc
    return AzureMapsUpstreamError("Konum hizmeti isteği tamamlanamadı.")


def _preferred_place_error(failures: Sequence[AzureMapsError]) -> AzureMapsError:
    for failure in failures:
        if isinstance(failure, AzureMapsRateLimitError):
            return failure
    if failures:
        return failures[0]
    return AzureMapsUpstreamError("Konum hizmeti isteği tamamlanamadı.")


def _feature_country_code(feature: dict[str, Any]) -> str | None:
    properties = feature.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    address = properties.get("address")
    address = address if isinstance(address, dict) else {}
    return _country_code_from_address(address)


def _country_code_from_address(address: dict[str, Any]) -> str | None:
    country_region = address.get("countryRegion")
    if isinstance(country_region, dict):
        value = country_region.get("ISO", country_region.get("iso"))
    else:
        value = address.get("countryCode")
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    if normalized == "TUR":
        return "TR"
    return normalized or None


def _place_from_geocode(candidate: GeocodeCandidate) -> PlaceCandidate:
    return PlaceCandidate(
        label=_bounded_text(candidate.label, 300) or "Konum",
        point=candidate.point,
        kind="address",
        reference="geocode",
        display_point=candidate.display_point,
        address=_bounded_text(candidate.address, 500),
        confidence=_bounded_text(candidate.confidence, 40),
        uses_route_point=candidate.uses_route_point,
    )


def _parse_poi_response(data: dict[str, Any], query: str) -> list[PlaceCandidate]:
    results = data.get("results")
    if not isinstance(results, list):
        raise AzureMapsUpstreamError("Mağaza araması geçerli konum sonuçları döndürmedi.")

    candidates: list[PlaceCandidate] = []
    for result in results:
        if not isinstance(result, dict) or result.get("type") != "POI":
            continue
        poi = result.get("poi")
        poi = poi if isinstance(poi, dict) else {}
        address = result.get("address")
        address = address if isinstance(address, dict) else {}
        # The POI request is explicitly countrySet=TR.  Reject an explicit,
        # contradictory country marker as a defensive second check.
        country_code = _country_code_from_address(address)
        if country_code != "TR":
            continue

        display_point = _point_from_lat_lon(result.get("position"))
        if display_point is None:
            continue
        route_point = _poi_route_point(result) or display_point
        formatted_address = _formatted_address(address)
        label = _bounded_text(poi.get("name"), 300) or formatted_address or query
        candidates.append(
            PlaceCandidate(
                label=label,
                point=route_point,
                kind="poi",
                reference="poi",
                display_point=display_point,
                address=formatted_address,
                category=_poi_category(poi),
                score=_optional_finite_float(result.get("score")),
                uses_route_point=route_point != display_point,
            )
        )
    return candidates


def _merge_place_candidates(
    poi_candidates: Sequence[PlaceCandidate],
    address_candidates: Sequence[PlaceCandidate],
    *,
    top: int,
) -> list[PlaceCandidate]:
    """Keep POIs first while removing only exact repeated source entries."""

    candidates: list[PlaceCandidate] = []
    seen: set[tuple[str, float, float]] = set()
    for candidate in [*poi_candidates, *address_candidates]:
        key = (
            candidate.label.strip().casefold(),
            round(candidate.point.latitude, 6),
            round(candidate.point.longitude, 6),
        )
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) == top:
            break
    return candidates


def _formatted_address(address: dict[str, Any]) -> str | None:
    return _bounded_text(
        address.get("freeformAddress") or address.get("formattedAddress"), 500
    )


def _poi_category(poi: dict[str, Any]) -> str | None:
    categories = poi.get("categories")
    if isinstance(categories, list):
        for category in categories:
            text = _bounded_text(category, 160)
            if text:
                return text
    classifications = poi.get("classifications")
    if isinstance(classifications, list):
        for classification in classifications:
            if not isinstance(classification, dict):
                continue
            text = _bounded_text(classification.get("name"), 160)
            if text:
                return text
    return None


def _poi_route_point(result: dict[str, Any]) -> GeoPoint | None:
    entry_points = result.get("entryPoints")
    if not isinstance(entry_points, list):
        return None
    fallback: GeoPoint | None = None
    for entry_point in entry_points:
        if not isinstance(entry_point, dict):
            continue
        point = _point_from_lat_lon(entry_point.get("position"))
        if point is None:
            continue
        if str(entry_point.get("type", "")).casefold() == "main":
            return point
        fallback = fallback or point
    return fallback


def _point_from_lat_lon(position: object) -> GeoPoint | None:
    if not isinstance(position, dict):
        return None
    try:
        latitude = float(position.get("lat", position.get("latitude")))
        longitude = float(position.get("lon", position.get("longitude")))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    try:
        return GeoPoint(latitude=latitude, longitude=longitude)
    except ValueError:
        return None


def _bounded_text(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned[:max_length] if cleaned else None


def _optional_finite_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _route_matrix_payload(
    locations: Sequence[RouteLocation], *, traffic: str
) -> dict[str, Any]:
    coordinates = [[location.point.longitude, location.point.latitude] for location in locations]
    return {
        "type": "FeatureCollection",
        "travelMode": "driving",
        "traffic": traffic,
        "departAt": "now" if traffic == "live" else "any",
        "optimizeRoute": "fastest",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "MultiPoint", "coordinates": coordinates},
                "properties": {"pointType": "origins"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "MultiPoint", "coordinates": coordinates},
                "properties": {"pointType": "destinations"},
            },
        ],
    }


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _point_from_coordinates(coordinates: object) -> GeoPoint | None:
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
        return None
    try:
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    try:
        return GeoPoint(latitude=latitude, longitude=longitude)
    except ValueError:
        return None


def _point_from_feature(feature: dict[str, Any]) -> GeoPoint | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return None
    return _point_from_coordinates(geometry.get("coordinates"))


def _route_point(properties: dict[str, Any]) -> GeoPoint | None:
    """Prefer Azure Maps' routing snap point over its display point when present."""
    points = properties.get("geocodePoints")
    if not isinstance(points, list):
        return None
    for point in points:
        if not isinstance(point, dict):
            continue
        usage_types = point.get("usageTypes")
        if not isinstance(usage_types, list) or "Route" not in usage_types:
            continue
        geometry = point.get("geometry")
        if isinstance(geometry, dict):
            parsed = _point_from_coordinates(geometry.get("coordinates"))
            if parsed:
                return parsed
        parsed = _point_from_coordinates(point.get("coordinates"))
        if parsed:
            return parsed
    return None


def _parse_route_matrix(
    payload: dict[str, Any],
    locations: Sequence[RouteLocation],
    *,
    traffic: str,
) -> RouteMatrixResponse:
    properties = payload.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    items = properties.get("matrix")
    if not isinstance(items, list):
        raise AzureMapsUpstreamError("Sürüş matrisi geçerli bir formatta dönmedi.")

    size = len(locations)
    distances = [[0.0 for _ in range(size)] for _ in range(size)]
    durations = [[0.0 for _ in range(size)] for _ in range(size)]
    resolved_pairs: set[tuple[int, int]] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            origin = int(item["originIndex"])
            destination = int(item["destinationIndex"])
        except (KeyError, TypeError, ValueError):
            raise AzureMapsUpstreamError("Sürüş matrisi konum indisleri geçersiz.") from None
        if not (0 <= origin < size and 0 <= destination < size):
            raise AzureMapsUpstreamError("Sürüş matrisi beklenmeyen bir konum indisi içeriyor.")
        if origin == destination:
            continue
        if item.get("statusCode") != 200:
            raise AzureMapsUpstreamError(
                "Bazı konum çiftleri için yol hesaplanamadı. Konumları kontrol edin."
            )
        try:
            distance = float(item["distanceInMeters"])
            duration_key = "durationTrafficInSeconds" if traffic == "live" else "durationInSeconds"
            duration = float(item.get(duration_key, item["durationInSeconds"]))
        except (KeyError, TypeError, ValueError):
            raise AzureMapsUpstreamError("Sürüş matrisi eksik mesafe veya süre verisi içeriyor.") from None
        if not (math.isfinite(distance) and distance >= 0 and math.isfinite(duration) and duration >= 0):
            raise AzureMapsUpstreamError("Sürüş matrisi geçersiz mesafe veya süre içeriyor.")
        distances[origin][destination] = distance
        durations[origin][destination] = duration
        resolved_pairs.add((origin, destination))

    expected_pairs = {(origin, destination) for origin in range(size) for destination in range(size) if origin != destination}
    if resolved_pairs != expected_pairs:
        raise AzureMapsUpstreamError("Sürüş matrisi tüm konum çiftleri için tamamlanamadı.")

    return RouteMatrixResponse(
        locations=list(locations),
        traffic=traffic,
        distance_meters=distances,
        duration_seconds=durations,
    )
