from __future__ import annotations

import math
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SolverName(str, Enum):
    EXACT = "exact"
    SIMULATED_ANNEALING = "simulated_annealing"
    QUANTUM_SIMULATOR = "quantum_simulator"
    QDK_QAOA = "qdk_qaoa"


class GeoPoint(BaseModel):
    """An unambiguous WGS84 point. Azure GeoJSON uses [longitude, latitude]."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class City(BaseModel):
    """A legacy planar point or a real geographic point used by the route engine."""

    name: str = Field(min_length=1, max_length=60)
    x: float | None = None
    y: float | None = None
    location: GeoPoint | None = None

    @model_validator(mode="after")
    def has_a_complete_location(self) -> "City":
        has_x = self.x is not None
        has_y = self.y is not None
        if has_x != has_y:
            raise ValueError("x ve y koordinatları birlikte verilmelidir.")
        if not has_x and self.location is None:
            raise ValueError("Bir şehir için x/y veya latitude/longitude verilmelidir.")
        for value in (self.x, self.y):
            if value is not None and not math.isfinite(value):
                raise ValueError("Koordinatlar sonlu sayılar olmalıdır.")
        return self


class GeocodeRequest(BaseModel):
    query: str = Field(min_length=3, max_length=200)
    top: int = Field(default=5, ge=1, le=5)


class GeocodeCandidate(BaseModel):
    label: str
    point: GeoPoint
    display_point: GeoPoint | None = None
    address: str | None = None
    confidence: str | None = None
    match_codes: list[str] = Field(default_factory=list)
    uses_route_point: bool = False


class GeocodeResponse(BaseModel):
    provider: Literal["azure_maps"] = "azure_maps"
    candidates: list[GeocodeCandidate] = Field(default_factory=list)


class RouteLocation(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    point: GeoPoint


class RouteMatrixRequest(BaseModel):
    locations: list[RouteLocation] = Field(min_length=2, max_length=10)
    traffic: Literal["historical", "live"] = "historical"

    @model_validator(mode="after")
    def location_names_are_unique(self) -> "RouteMatrixRequest":
        names = [location.name.casefold() for location in self.locations]
        if len(names) != len(set(names)):
            raise ValueError("Konum adları benzersiz olmalıdır.")
        return self


class RouteMatrixResponse(BaseModel):
    provider: Literal["azure_maps"] = "azure_maps"
    traffic: Literal["historical", "live"] = "historical"
    locations: list[RouteLocation]
    distance_meters: list[list[float]]
    duration_seconds: list[list[float]]

    @model_validator(mode="after")
    def matrices_match_locations(self) -> "RouteMatrixResponse":
        size = len(self.locations)
        for label, matrix in (
            ("distance_meters", self.distance_meters),
            ("duration_seconds", self.duration_seconds),
        ):
            _validate_matrix(matrix, size, label)
        return self


class OptimizationRequest(BaseModel):
    cities: list[City] = Field(min_length=3, max_length=10)
    seed: int = 42
    annealing_iterations: int = Field(default=4_000, ge=100, le=100_000)
    quantum_layers: int = Field(default=3, ge=1, le=8)
    run_qdk: bool = False
    qdk_shots: int = Field(default=256, ge=64, le=4096)
    azure_quantum_target: str | None = Field(default=None, max_length=120)
    # A single shared matrix keeps every classical and quantum solver on the
    # same problem. It may be directed, because real road travel can be.
    precomputed_cost_matrix: list[list[float]] | None = None
    cost_unit: str = Field(default="coordinate_units", min_length=1, max_length=40)
    road_distance_meters: list[list[float]] | None = None
    road_duration_seconds: list[list[float]] | None = None
    optimization_metric: Literal["distance", "duration"] = "distance"

    @model_validator(mode="after")
    def request_is_consistent(self) -> "OptimizationRequest":
        names = [city.name.casefold() for city in self.cities]
        if len(names) != len(set(names)):
            raise ValueError("Şehir/istasyon adları benzersiz olmalıdır.")
        size = len(self.cities)
        for label, matrix in (
            ("precomputed_cost_matrix", self.precomputed_cost_matrix),
            ("road_distance_meters", self.road_distance_meters),
            ("road_duration_seconds", self.road_duration_seconds),
        ):
            if matrix is not None:
                _validate_matrix(matrix, size, label)
        return self


class RoadOptimizationRequest(RouteMatrixRequest):
    """Server-side optimization request based on an Azure Maps route matrix."""

    locations: list[RouteLocation] = Field(min_length=3, max_length=10)
    seed: int = 42
    annealing_iterations: int = Field(default=4_000, ge=100, le=100_000)
    quantum_layers: int = Field(default=3, ge=1, le=8)
    run_qdk: bool = False
    qdk_shots: int = Field(default=256, ge=64, le=4096)
    azure_quantum_target: str | None = Field(default=None, max_length=120)
    optimization_metric: Literal["distance", "duration"] = "distance"


class RouteResult(BaseModel):
    solver: SolverName
    route: list[str]
    distance: float
    runtime_ms: float
    metadata: dict[str, float | int | str] = Field(default_factory=dict)
    cost_unit: str = "coordinate_units"
    route_distance_meters: float | None = None
    route_duration_seconds: float | None = None


class OptimizationResponse(BaseModel):
    results: list[RouteResult]
    best_solver: SolverName
    explanation: str
    warnings: list[str] = Field(default_factory=list)
    cost_unit: str = "coordinate_units"
    optimization_metric: Literal["distance", "duration"] = "distance"
    routing: RouteMatrixResponse | None = None


def _validate_matrix(matrix: list[list[float]], size: int, label: str) -> None:
    if len(matrix) != size:
        raise ValueError(f"{label}, şehir sayısıyla aynı sayıda satır içermelidir.")
    for row in matrix:
        if len(row) != size:
            raise ValueError(f"{label}, kare bir matris olmalıdır.")
        for value in row:
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{label}, sonlu ve negatif olmayan değerler içermelidir.")
