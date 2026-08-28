from __future__ import annotations

from .llm import explain_results
from .models import OptimizationRequest, OptimizationResponse
from .quantum_qdk import QuantumRuntimeError, solve_qdk_qaoa
from .solvers import solve_exact, solve_quantum_statevector, solve_simulated_annealing


def optimize_routes(request: OptimizationRequest) -> OptimizationResponse:
    warnings: list[str] = []
    results = [
        solve_simulated_annealing(
            request.cities, seed=request.seed, iterations=request.annealing_iterations
        ),
        solve_quantum_statevector(
            request.cities, seed=request.seed, layers=request.quantum_layers
        ),
    ]
    # Exact factorial search is kept to a safe demo size.
    if len(request.cities) <= 9:
        results.insert(0, solve_exact(request.cities))

    if request.run_qdk:
        try:
            results.append(
                solve_qdk_qaoa(
                    request.cities,
                    layers=min(request.quantum_layers, 4),
                    shots=request.qdk_shots,
                    target=request.azure_quantum_target,
                )
            )
        except QuantumRuntimeError as exc:
            warnings.append(str(exc))

    best = min(results, key=lambda item: item.distance)
    return OptimizationResponse(
        results=results,
        best_solver=best.solver,
        explanation=explain_results(results),
        warnings=warnings,
    )
