from hybrid_quantum.models import City, OptimizationRequest, SolverName
from hybrid_quantum.natural_language import parse_route_problem
from hybrid_quantum.service import optimize_routes
from hybrid_quantum.solvers import distance_matrix, route_cost


def sample_cities() -> list[City]:
    return [
        City(name="A", x=0, y=0),
        City(name="B", x=1, y=0),
        City(name="C", x=1, y=1),
        City(name="D", x=0, y=1),
    ]


def test_route_cost_closes_the_tour() -> None:
    distances = distance_matrix(sample_cities())
    assert route_cost([0, 1, 2, 3], distances) == 4.0


def test_all_solvers_return_closed_valid_routes() -> None:
    response = optimize_routes(
        OptimizationRequest(cities=sample_cities(), annealing_iterations=500, quantum_layers=2)
    )
    assert len(response.results) == 3
    assert response.best_solver in set(SolverName)
    for result in response.results:
        assert result.route[0] == result.route[-1]
        assert set(result.route[:-1]) == {"A", "B", "C", "D"}
        assert result.distance >= 4.0


def test_quantum_result_is_reproducible() -> None:
    request = OptimizationRequest(cities=sample_cities(), seed=7, quantum_layers=2)
    first = optimize_routes(request)
    second = optimize_routes(request)
    first_quantum = next(r for r in first.results if r.solver == SolverName.QUANTUM_SIMULATOR)
    second_quantum = next(r for r in second.results if r.solver == SolverName.QUANTUM_SIMULATOR)
    assert first_quantum.route == second_quantum.route
    assert first_quantum.distance == second_quantum.distance
    assert first_quantum.metadata["state_space"] == 6
    assert float(first_quantum.metadata["peak_probability"]) > 0
    assert float(first_quantum.metadata["amplification_vs_uniform"]) > 0


def test_qdk_mode_degrades_gracefully_without_optional_runtime() -> None:
    request = OptimizationRequest(cities=sample_cities(), run_qdk=True, qdk_shots=64)
    response = optimize_routes(request)
    qdk_results = [result for result in response.results if result.solver == SolverName.QDK_QAOA]
    assert qdk_results or response.warnings
    if qdk_results:
        metadata = qdk_results[0].metadata
        assert metadata["backend"] == "qdk-local-sparse-simulator"
        assert metadata["qubits"] == 3
        assert metadata["gate_family"] == "H + Controlled-R1 + Rx + MResetZ"
        assert len(str(metadata["circuit_fingerprint"])) == 16
        assert metadata["feasible_routes"] == 6
        assert metadata["encoded_states"] == 8
        assert int(metadata["valid_shots"]) > 0


def test_turkish_natural_language_problem_is_parsed_in_mention_order() -> None:
    problem = parse_route_problem(
        "İstanbul'dan başlayıp Ankara, Elazığ ve İzmir için en kısa rotayı kuantumla karşılaştır."
    )
    assert [city.name for city in problem.cities] == ["İstanbul", "Ankara", "Elazığ", "İzmir"]
    assert problem.use_quantum is True
    assert problem.parser_source in {"Azure OpenAI", "Yerel şehir sözlüğü"}
