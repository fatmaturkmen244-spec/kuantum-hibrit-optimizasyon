from __future__ import annotations

import math
import unicodedata
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SolverName(str, Enum):
    EXACT = "exact"
    SIMULATED_ANNEALING = "simulated_annealing"
    QUANTUM_SIMULATOR = "quantum_simulator"
    QDK_QAOA = "qdk_qaoa"


def _maxcut_label_key(value: str) -> str:
    """Return a Turkish-safe comparison key for a Max-Cut vertex label."""

    lowered = value.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


class MaxCutEdge(BaseModel):
    """One weighted, undirected edge in a Max-Cut graph."""

    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    weight: float = Field(default=1.0, gt=0, le=1_000_000)

    @field_validator("source", "target")
    @classmethod
    def edge_labels_are_clean(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Kenar uçları boş olamaz.")
        if any(character in cleaned for character in "\r\n\t"):
            raise ValueError("Kenar uçları satır sonu veya sekme içeremez.")
        return cleaned

    @field_validator("weight")
    @classmethod
    def edge_weight_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Kenar ağırlığı sonlu bir sayı olmalıdır.")
        return float(value)

    @model_validator(mode="after")
    def edge_is_not_a_self_loop(self) -> "MaxCutEdge":
        if _maxcut_label_key(self.source) == _maxcut_label_key(self.target):
            raise ValueError("Max-Cut grafında bir kenar kendisine bağlanamaz.")
        return self


class MaxCutGraph(BaseModel):
    """A deliberately small weighted graph suitable for the local simulator."""

    nodes: list[str] = Field(min_length=2, max_length=10)
    edges: list[MaxCutEdge] = Field(min_length=1, max_length=45)

    @field_validator("nodes")
    @classmethod
    def node_labels_are_clean(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            label = value.strip()
            if not label:
                raise ValueError("Düğüm adları boş olamaz.")
            if any(character in label for character in "\r\n\t"):
                raise ValueError("Düğüm adları satır sonu veya sekme içeremez.")
            if len(label) > 80:
                raise ValueError("Düğüm adı en fazla 80 karakter olabilir.")
            cleaned.append(label)
        return cleaned

    @model_validator(mode="after")
    def graph_is_consistent(self) -> "MaxCutGraph":
        node_keys = [_maxcut_label_key(node) for node in self.nodes]
        if len(node_keys) != len(set(node_keys)):
            raise ValueError("Düğüm adları benzersiz olmalıdır.")

        known_nodes = set(node_keys)
        seen_edges: set[tuple[str, str]] = set()
        for edge in self.edges:
            source_key = _maxcut_label_key(edge.source)
            target_key = _maxcut_label_key(edge.target)
            if source_key not in known_nodes or target_key not in known_nodes:
                raise ValueError("Her kenarın iki ucu da tanımlı düğümlerden biri olmalıdır.")
            edge_key = tuple(sorted((source_key, target_key)))
            if edge_key in seen_edges:
                raise ValueError("Aynı iki düğüm arasında yinelenen kenar tanımlanamaz.")
            seen_edges.add(edge_key)
        return self


class MaxCutRequest(BaseModel):
    """Natural-language-ish, locally parsed Max-Cut request.

    ``problem`` deliberately stays text-only in the public API so that all
    graph inputs pass through the same strict ``Düğümler:/Kenarlar:`` parser.
    """

    problem: str = Field(min_length=12, max_length=2_000)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    annealing_iterations: int = Field(default=2_000, ge=100, le=100_000)
    quantum_layers: int = Field(default=2, ge=1, le=8)


class MaxCutQuboMetadata(BaseModel):
    """Transparent binary QUBO encoding for a Max-Cut request."""

    variables: list[str]
    upper_triangular_matrix: list[list[float]]
    objective: Literal["minimize_negative_cut_weight"] = "minimize_negative_cut_weight"
    encoding: str = "x_i=0 => Küme A, x_i=1 => Küme B"
    energy_formula: str = "E(x)=Σ_i Q_ii x_i + Σ_i<j Q_ij x_i x_j = -kesim_ağırlığı"
    constant_offset: float = 0.0


class MaxCutResult(BaseModel):
    solver: SolverName
    cut_weight: float
    partition_a: list[str]
    partition_b: list[str]
    cut_edges: list[MaxCutEdge]
    bitstring: str
    runtime_ms: float
    metadata: dict[str, float | int | str] = Field(default_factory=dict)


class MaxCutResponse(BaseModel):
    graph: MaxCutGraph
    qubo: MaxCutQuboMetadata
    results: list[MaxCutResult]
    best_solver: SolverName
    parser_source: str
    explanation: str
    warnings: list[str] = Field(default_factory=list)


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
