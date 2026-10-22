from __future__ import annotations

from collections.abc import Sequence

from .llm import explain_results
from .models import OptimizationRequest, OptimizationResponse, RouteResult
from .quantum_qdk import QuantumRuntimeError, solve_qdk_qaoa
from .solvers import distance_matrix, solve_exact, solve_quantum_statevector, solve_simulated_annealing


def _select_cost_matrix(request: OptimizationRequest) -> tuple[Sequence[Sequence[float]] | None, str]:
    if request.precomputed_cost_matrix is not None:
        return request.precomputed_cost_matrix, request.cost_unit
    if request.optimization_metric == "duration" and request.road_duration_seconds is not None:
        return request.road_duration_seconds, "seconds"
    if request.optimization_metric == "distance" and request.road_distance_meters is not None:
        return request.road_distance_meters, "meters"
    return None, request.cost_unit


def _closed_route_total(
    route: list[str], city_indices: dict[str, int], matrix: Sequence[Sequence[float]]
) -> float:
    indices = [city_indices[name] for name in route]
    return sum(float(matrix[indices[index]][indices[index + 1]]) for index in range(len(indices) - 1))


def _attach_road_metrics(
    results: list[RouteResult], request: OptimizationRequest, cost_unit: str
) -> None:
    city_indices = {city.name: index for index, city in enumerate(request.cities)}
    for result in results:
        result.cost_unit = cost_unit
        result.metadata["cost_unit"] = cost_unit
        if request.road_distance_meters is not None:
            result.route_distance_meters = round(
                _closed_route_total(result.route, city_indices, request.road_distance_meters), 2
            )
        if request.road_duration_seconds is not None:
            result.route_duration_seconds = round(
                _closed_route_total(result.route, city_indices, request.road_duration_seconds), 2
            )


def optimize_routes(request: OptimizationRequest) -> OptimizationResponse:
    warnings: list[str] = []
    costs, cost_unit = _select_cost_matrix(request)
    shared_distances = distance_matrix(request.cities, costs)
    results = [
        solve_simulated_annealing(
            request.cities,
            seed=request.seed,
            iterations=request.annealing_iterations,
            distances=shared_distances,
        ),
        solve_quantum_statevector(
            request.cities,
            seed=request.seed,
            layers=request.quantum_layers,
            distances=shared_distances,
        ),
    ]
    # Exact factorial search is kept to a safe demo size.
    if len(request.cities) <= 9:
        results.insert(0, solve_exact(request.cities, distances=shared_distances))

    if request.run_qdk:
        try:
            results.append(
                solve_qdk_qaoa(
                    request.cities,
                    layers=min(request.quantum_layers, 4),
                    shots=request.qdk_shots,
                    target=request.azure_quantum_target,
                    distances=shared_distances,
                )
            )
        except QuantumRuntimeError as exc:
            warnings.append(str(exc))

    _attach_road_metrics(results, request, cost_unit)
    best = min(results, key=lambda item: item.distance)
    return OptimizationResponse(
        results=results,
        best_solver=best.solver,
        explanation=explain_results(results),
        warnings=warnings,
        cost_unit=cost_unit,
        optimization_metric=request.optimization_metric,
    )
