import re
from pathlib import Path

from hybrid_quantum.models import City, OptimizationRequest, SolverName
from hybrid_quantum.natural_language import CITY_CATALOG, parse_route_problem
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


def test_published_gps_catalog_matches_the_backend_catalog() -> None:
    source = (Path(__file__).parents[1] / "docs" / "app.js").read_text(encoding="utf-8")
    entries = re.findall(
        r'^\s*(\w+): \{ lat: ([0-9.]+), lon: ([0-9.]+), name: "([^"]+)"',
        source,
        flags=re.MULTILINE,
    )
    published = {
        key: (name, float(longitude), float(latitude))
        for key, latitude, longitude, name in entries
    }

    assert set(published) == set(CITY_CATALOG)
    assert published == CITY_CATALOG
    assert all(35 <= latitude <= 42 and 26 <= longitude <= 42 for _, longitude, latitude in published.values())


def test_all_solvers_use_the_same_directed_road_cost_matrix() -> None:
    road_distances = [
        [0, 7, 2, 9],
        [8, 0, 4, 1],
        [3, 6, 0, 5],
        [2, 8, 7, 0],
    ]
    road_durations = [
        [0, 70, 20, 90],
        [80, 0, 40, 10],
        [30, 60, 0, 50],
        [20, 80, 70, 0],
    ]
    response = optimize_routes(
        OptimizationRequest(
            cities=sample_cities(),
            annealing_iterations=500,
            quantum_layers=2,
            precomputed_cost_matrix=road_distances,
            cost_unit="meters",
            road_distance_meters=road_distances,
            road_duration_seconds=road_durations,
        )
    )
    city_index = {city.name: index for index, city in enumerate(sample_cities())}
    assert response.cost_unit == "meters"
    for result in response.results:
        indices = [city_index[name] for name in result.route]
        expected_distance = sum(
            road_distances[indices[index]][indices[index + 1]]
            for index in range(len(indices) - 1)
        )
        expected_duration = sum(
            road_durations[indices[index]][indices[index + 1]]
            for index in range(len(indices) - 1)
        )
        assert result.distance == expected_distance
        assert result.route_distance_meters == expected_distance
        assert result.route_duration_seconds == expected_duration
        assert result.cost_unit == "meters"
