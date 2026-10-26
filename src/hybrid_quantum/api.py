from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .maxcut import solve_maxcut
from .maps import (
    AzureMapsClient,
    AzureMapsConfigurationError,
    AzureMapsError,
    AzureMapsRateLimitError,
    AzureMapsUpstreamError,
)
from .models import (
    City,
    GeocodeRequest,
    GeocodeResponse,
    MaxCutRequest,
    MaxCutResponse,
    OptimizationRequest,
    OptimizationResponse,
    RoadOptimizationRequest,
    RouteMatrixRequest,
    RouteMatrixResponse,
)
from .service import optimize_routes

app = FastAPI(
    title="Hibrit Kuantum Optimizasyon Motoru",
    description="Doğal dil, klasik optimizasyon ve Microsoft Q# karşılaştırma motoru",
    version="0.2.0",
)


def _allowed_origins() -> list[str]:
    defaults = {
        "https://fatmaturkmen244-spec.github.io",
        "http://127.0.0.1:8501",
        "http://localhost:8501",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }
    configured = os.getenv("CORS_ALLOW_ORIGINS", "")
    defaults.update(origin.strip() for origin in configured.split(",") if origin.strip())
    return sorted(defaults)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)


class _MapsRequestLimiter:
    """Small in-process throttle for the public route proxy; deploy a gateway for scale."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.calls: dict[str, deque[float]] = defaultdict(deque)

    def enforce(self, request: Request) -> None:
        client_id = request.client.host if request.client else "unknown"
        now = time.monotonic()
        history = self.calls[client_id]
        while history and now - history[0] >= self.window_seconds:
            history.popleft()
        if len(history) >= self.limit:
            raise HTTPException(
                status_code=429,
                detail="Konum isteği sınırına ulaşıldı. Bir dakika sonra tekrar deneyin.",
            )
        history.append(now)


_maps_limiter = _MapsRequestLimiter(
    limit=max(1, int(os.getenv("MAPS_RATE_LIMIT_PER_MINUTE", "30")))
)


def _maps_client(request: Request) -> AzureMapsClient:
    _maps_limiter.enforce(request)
    try:
        return AzureMapsClient()
    except AzureMapsConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _raise_maps_error(exc: AzureMapsError) -> None:
    if isinstance(exc, AzureMapsRateLimitError):
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if isinstance(exc, AzureMapsUpstreamError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=503, detail="Konum hizmeti şu anda kullanılamıyor.") from exc


@app.get("/health")
def health() -> dict[str, str]:
    try:
        AzureMapsClient()
        maps_status = "configured"
    except AzureMapsConfigurationError:
        maps_status = "not_configured"
    return {"status": "ok", "azure_maps": maps_status}


@app.post("/optimize", response_model=OptimizationResponse)
def optimize(request: OptimizationRequest) -> OptimizationResponse:
    return optimize_routes(request)


@app.post("/maxcut/solve", response_model=MaxCutResponse)
def optimize_maxcut(request: MaxCutRequest) -> MaxCutResponse:
    """Solve a locally parsed, small weighted Max-Cut problem.

    No Azure credential or free-form QUBO is accepted on this endpoint; the
    graph must pass the shared ``Düğümler:/Kenarlar:`` validation first.
    """

    try:
        return solve_maxcut(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/maps/geocode", response_model=GeocodeResponse)
async def geocode_location(body: GeocodeRequest, request: Request) -> GeocodeResponse:
    """Resolve an address server-side; the Maps credential never reaches the browser."""
    client = _maps_client(request)
    try:
        return await client.geocode(body.query, top=body.top)
    except AzureMapsError as exc:
        _raise_maps_error(exc)


@app.post("/maps/route-matrix", response_model=RouteMatrixResponse)
async def route_matrix(body: RouteMatrixRequest, request: Request) -> RouteMatrixResponse:
    """Return a real, directed road-distance/time matrix for a small route request."""
    client = _maps_client(request)
    try:
        return await client.route_matrix(body.locations, traffic=body.traffic)
    except AzureMapsError as exc:
        _raise_maps_error(exc)


@app.post("/maps/optimize", response_model=OptimizationResponse)
async def optimize_road_route(
    body: RoadOptimizationRequest, request: Request
) -> OptimizationResponse:
    """Fetch one road matrix then run every solver against that exact same matrix."""
    client = _maps_client(request)
    try:
        routing = await client.route_matrix(body.locations, traffic=body.traffic)
    except AzureMapsError as exc:
        _raise_maps_error(exc)

    uses_duration = body.optimization_metric == "duration"
    response = optimize_routes(
        OptimizationRequest(
            cities=[City(name=location.name, location=location.point) for location in body.locations],
            seed=body.seed,
            annealing_iterations=body.annealing_iterations,
            quantum_layers=body.quantum_layers,
            run_qdk=body.run_qdk,
            qdk_shots=body.qdk_shots,
            azure_quantum_target=body.azure_quantum_target,
            precomputed_cost_matrix=(
                routing.duration_seconds if uses_duration else routing.distance_meters
            ),
            cost_unit="seconds" if uses_duration else "meters",
            road_distance_meters=routing.distance_meters,
            road_duration_seconds=routing.duration_seconds,
            optimization_metric=body.optimization_metric,
        )
    )
    response.routing = routing
    return response
