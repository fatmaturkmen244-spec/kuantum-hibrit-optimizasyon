from __future__ import annotations

import itertools
import math
import random
import time
from collections.abc import Sequence

import numpy as np

from .models import City, RouteResult, SolverName


def distance_matrix(cities: Sequence[City]) -> np.ndarray:
    points = np.array([(city.x, city.y) for city in cities], dtype=float)
    delta = points[:, None, :] - points[None, :, :]
    return np.sqrt(np.sum(delta * delta, axis=2))


def route_cost(route: Sequence[int], distances: np.ndarray) -> float:
    return float(sum(distances[route[i], route[(i + 1) % len(route)]] for i in range(len(route))))


def _result(
    solver: SolverName,
    route: Sequence[int],
    cities: Sequence[City],
    cost: float,
    started: float,
    **metadata: float | int | str,
) -> RouteResult:
    closed_route = [cities[index].name for index in route] + [cities[route[0]].name]
    return RouteResult(
        solver=solver,
        route=closed_route,
        distance=round(cost, 4),
        runtime_ms=round((time.perf_counter() - started) * 1_000, 3),
        metadata=metadata,
    )


def solve_exact(cities: Sequence[City]) -> RouteResult:
    """Brute-force benchmark; the first city is fixed to remove rotations."""
    started = time.perf_counter()
    distances = distance_matrix(cities)
    best_route: tuple[int, ...] | None = None
    best_cost = math.inf
    for tail in itertools.permutations(range(1, len(cities))):
        route = (0, *tail)
        cost = route_cost(route, distances)
        if cost < best_cost:
            best_route, best_cost = route, cost
    assert best_route is not None
    return _result(
        SolverName.EXACT,
        best_route,
        cities,
        best_cost,
        started,
        evaluated_routes=math.factorial(len(cities) - 1),
    )


def solve_simulated_annealing(
    cities: Sequence[City], *, seed: int, iterations: int
) -> RouteResult:
    started = time.perf_counter()
    rng = random.Random(seed)
    distances = distance_matrix(cities)
    current = list(range(len(cities)))
    rng.shuffle(current)
    current_cost = route_cost(current, distances)
    best, best_cost = current.copy(), current_cost

    temperature = max(float(np.max(distances)), 1.0)
    cooling = (0.001 / temperature) ** (1 / max(iterations - 1, 1))
    accepted = 0
    for _ in range(iterations):
        i, j = sorted(rng.sample(range(1, len(cities)), 2))
        candidate = current.copy()
        candidate[i : j + 1] = reversed(candidate[i : j + 1])
        candidate_cost = route_cost(candidate, distances)
        delta = candidate_cost - current_cost
        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-12)):
            current, current_cost = candidate, candidate_cost
            accepted += 1
            if current_cost < best_cost:
                best, best_cost = current.copy(), current_cost
        temperature *= cooling

    return _result(
        SolverName.SIMULATED_ANNEALING,
        best,
        cities,
        best_cost,
        started,
        iterations=iterations,
        accepted_moves=accepted,
    )


def solve_quantum_statevector(
    cities: Sequence[City], *, seed: int, layers: int
) -> RouteResult:
    """QAOA-style simulator over the feasible-tour state space.

    This educational simulator applies a cost phase and a global diffusion mixer.
    It is intentionally dependency-light and is not represented as hardware QAOA.
    """
    started = time.perf_counter()
    rng = np.random.default_rng(seed)
    distances = distance_matrix(cities)
    tours = np.array([(0, *tail) for tail in itertools.permutations(range(1, len(cities)))])
    costs = np.array([route_cost(route, distances) for route in tours])
    scale = max(float(np.std(costs)), 1e-9)
    normalized = (costs - float(np.min(costs))) / scale
    dimension = len(tours)

    best_expectation = math.inf
    best_probabilities: np.ndarray | None = None
    best_gamma = 0.0
    best_beta = 0.0
    # Lightweight variational parameter search, deterministic for a given seed.
    parameter_trials = 12 + layers * 8
    for _ in range(parameter_trials):
        gamma = float(rng.uniform(0.05, math.pi))
        beta = float(rng.uniform(0.05, math.pi / 2))
        state = np.full(dimension, 1 / math.sqrt(dimension), dtype=complex)
        for layer in range(layers):
            state *= np.exp(-1j * gamma * (layer + 1) / layers * normalized)
            # exp(-i*beta*|s><s|) diffusion mixer in the feasible subspace.
            state += (np.exp(-1j * beta) - 1) * np.mean(state)
            state /= np.linalg.norm(state)
        probabilities = np.abs(state) ** 2
        expectation = float(np.dot(probabilities, costs))
        if expectation < best_expectation:
            best_expectation = expectation
            best_probabilities = probabilities
            best_gamma, best_beta = gamma, beta

    assert best_probabilities is not None
    sampled = rng.choice(dimension, size=min(512, dimension * 4), p=best_probabilities)
    best_index = int(sampled[np.argmin(costs[sampled])])
    peak_index = int(np.argmax(best_probabilities))
    peak_probability = float(best_probabilities[peak_index])
    uniform_probability = 1.0 / dimension
    nonzero = best_probabilities[best_probabilities > 0]
    probability_entropy = float(-np.sum(nonzero * np.log2(nonzero)))
    return _result(
        SolverName.QUANTUM_SIMULATOR,
        tours[best_index],
        cities,
        float(costs[best_index]),
        started,
        layers=layers,
        state_space=dimension,
        gamma=round(best_gamma, 4),
        beta=round(best_beta, 4),
        expected_distance=round(best_expectation, 4),
        peak_probability=round(peak_probability, 6),
        uniform_probability=round(uniform_probability, 6),
        amplification_vs_uniform=round(peak_probability / uniform_probability, 3),
        probability_entropy_bits=round(probability_entropy, 4),
        most_likely_route=" → ".join(cities[index].name for index in tours[peak_index]),
        simulator="feasible-subspace-statevector",
    )
