from __future__ import annotations

import itertools

import pytest
from fastapi.testclient import TestClient

from hybrid_quantum.api import app
from hybrid_quantum.maxcut import (
    build_maxcut_qubo,
    cut_weight,
    parse_maxcut_problem,
    qubo_energy,
    solve_maxcut,
)
from hybrid_quantum.models import MaxCutRequest, SolverName


TRIANGLE = (
    "Düğümler: A, B, C. "
    "Kenarlar: A-B:1, A-C:1, B-C:1. "
    "Maksimum kesimi klasik ve kuantumla karşılaştır."
)


def test_local_parser_builds_a_canonical_graph() -> None:
    parsed = parse_maxcut_problem(
        "Dugumler: Ankara, Izmir, Bursa. "
        "Kenarlar: ankara-izmir:2.5; Izmir-BURSA:1; Bursa-Ankara:3."
    )
    assert parsed.graph.nodes == ["Ankara", "Izmir", "Bursa"]
    assert [(edge.source, edge.target, edge.weight) for edge in parsed.graph.edges] == [
        ("Ankara", "Izmir", 2.5),
        ("Izmir", "Bursa", 1.0),
        ("Bursa", "Ankara", 3.0),
    ]
    assert parsed.parser_source == "Yerel Düğümler/Kenarlar ayrıştırıcısı"


@pytest.mark.parametrize(
    "problem, error",
    [
        ("Düğümler: A, B. Kenarlar: A-A:1", "kendisine"),
        ("Düğümler: A, B. Kenarlar: A-C:1", "Düğümler bölümünde"),
        ("Düğümler: A, B. Kenarlar: A-B:-1", "Kenarlar bölümünde"),
        ("Düğümler: A, B. Kenarlar: A-B:1, B-A:2", "yinelenen"),
    ],
)
def test_local_parser_rejects_invalid_graphs(problem: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_maxcut_problem(problem)


def test_qubo_energy_is_negative_cut_weight_for_every_bitstring() -> None:
    graph = parse_maxcut_problem(
        "Düğümler: A, B, C. Kenarlar: A-B:2.5, A-C:1, B-C:4.25"
    ).graph
    matrix = build_maxcut_qubo(graph)

    for bits in itertools.product((0, 1), repeat=len(graph.nodes)):
        assert qubo_energy(bits, matrix) == pytest.approx(-cut_weight(graph, bits))


def test_exact_solver_finds_triangle_max_cut_and_exposes_qubo_metadata() -> None:
    response = solve_maxcut(MaxCutRequest(problem=TRIANGLE, seed=7, annealing_iterations=300))
    exact = next(result for result in response.results if result.solver == SolverName.EXACT)

    assert exact.cut_weight == 2.0
    assert len(exact.partition_a) + len(exact.partition_b) == 3
    assert exact.partition_a[0] == "A"
    assert exact.metadata["qubo_energy"] == -2.0
    assert response.qubo.variables == ["A", "B", "C"]
    assert response.qubo.upper_triangular_matrix == [
        [-2.0, 2.0, 2.0],
        [0.0, -2.0, 2.0],
        [0.0, 0.0, -2.0],
    ]


def test_annealing_and_quantum_inspired_results_are_seeded_and_reproducible() -> None:
    request = MaxCutRequest(problem=TRIANGLE, seed=19, annealing_iterations=400, quantum_layers=2)
    first = solve_maxcut(request)
    second = solve_maxcut(request)
    first_by_solver = {result.solver: result for result in first.results}
    second_by_solver = {result.solver: result for result in second.results}

    assert set(first_by_solver) == {
        SolverName.EXACT,
        SolverName.SIMULATED_ANNEALING,
        SolverName.QUANTUM_SIMULATOR,
    }
    for solver in first_by_solver:
        assert first_by_solver[solver].bitstring == second_by_solver[solver].bitstring
        assert first_by_solver[solver].cut_weight == second_by_solver[solver].cut_weight
    quantum = first_by_solver[SolverName.QUANTUM_SIMULATOR]
    assert quantum.metadata["simulator"] == "qaoa-inspired-statevector"
    assert float(quantum.metadata["peak_probability"]) > 0


def test_maxcut_endpoint_uses_the_same_local_parser_and_returns_validation_errors() -> None:
    client = TestClient(app)
    success = client.post("/maxcut/solve", json={"problem": TRIANGLE, "seed": 5})
    assert success.status_code == 200
    body = success.json()
    assert body["best_solver"] == "exact"
    assert body["qubo"]["objective"] == "minimize_negative_cut_weight"
    assert len(body["results"]) == 3

    invalid = client.post("/maxcut/solve", json={"problem": "Düğümler: A, B. Kenarlar: A-A:1"})
    assert invalid.status_code == 422
    assert "kendisine" in invalid.json()["detail"]

