"""Small, deterministic Max-Cut solvers for the hybrid optimization lab.

The public Max-Cut API accepts a deliberately constrained Turkish input
instead of free-form QUBO.  That keeps the graph and its QUBO representation
inspectable before the classical and quantum-inspired solvers run.
"""

from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .models import (
    MaxCutEdge,
    MaxCutGraph,
    MaxCutQuboMetadata,
    MaxCutRequest,
    MaxCutResponse,
    MaxCutResult,
    SolverName,
    _maxcut_label_key,
)


# The format is intentionally compact and documented by the UI/API rather
# than accepting arbitrary LLM-produced QUBO matrices.  A period can separate
# the two headings, and Turkish characters may be written with ASCII fallback.
_SECTIONS = re.compile(
    r"""^\s*
    d[üu][ğg][üu]mler\s*:\s*(?P<nodes>.*?)
    \s*(?:[.!?]\s*)?kenarlar\s*:\s*(?P<edges>.+?)\s*$
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)
_EDGE = re.compile(
    r"""\s*
    (?P<source>[^,;:\-–—\r\n]+?)\s*[-–—]\s*
    (?P<target>[^,;:\-–—\r\n]+?)\s*:\s*
    (?P<weight>(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)
    """,
    re.VERBOSE,
)
_NODE_SPLIT = re.compile(r"[,;\r\n]+")


@dataclass(frozen=True)
class ParsedMaxCutProblem:
    graph: MaxCutGraph
    parser_source: str = "Yerel Düğümler/Kenarlar ayrıştırıcısı"

    @property
    def summary(self) -> str:
        return (
            f"{len(self.graph.nodes)} düğüm, {len(self.graph.edges)} ağırlıklı kenar · "
            "hedef: maksimum kesim"
        )


def parse_maxcut_problem(text: str) -> ParsedMaxCutProblem:
    """Parse a small weighted graph from the documented local grammar.

    Accepted example::

        Düğümler: A, B, C. Kenarlar: A-B:3, A-C:1, B-C:2.

    A sentence after the final period is allowed so users can append a goal
    such as ``Maksimum kesimi klasik ve kuantumla karşılaştır.``  It is not
    used to build the graph.
    """

    if not text or not text.strip():
        raise ValueError("Önce Düğümler: ve Kenarlar: bölümlerini yazın.")

    sections = _SECTIONS.fullmatch(text)
    if sections is None:
        raise ValueError(
            "Biçim anlaşılmadı. Örnek: Düğümler: A, B, C. "
            "Kenarlar: A-B:3, A-C:1, B-C:2."
        )

    nodes = _parse_nodes(sections.group("nodes"))
    node_by_key = {_maxcut_label_key(node): node for node in nodes}
    if len(node_by_key) != len(nodes):
        raise ValueError("Düğüm adları benzersiz olmalıdır.")

    edges = _parse_edges(sections.group("edges"), node_by_key)
    try:
        graph = MaxCutGraph(nodes=nodes, edges=edges)
    except ValueError as exc:
        # Pydantic's validation text is useful, but prefixing it tells the UI
        # precisely which part of the natural-language-ish request failed.
        raise ValueError(f"Max-Cut grafı doğrulanamadı: {exc}") from exc
    return ParsedMaxCutProblem(graph=graph)


def _parse_nodes(section: str) -> list[str]:
    raw_nodes = [part.strip().rstrip(".") for part in _NODE_SPLIT.split(section) if part.strip()]
    if len(raw_nodes) < 2:
        raise ValueError("Düğümler bölümünde en az iki düğüm yazın.")
    if len(raw_nodes) > 10:
        raise ValueError("Kuantum esinli simülasyon en fazla 10 düğüm destekler.")

    nodes: list[str] = []
    for raw_node in raw_nodes:
        if any(character in raw_node for character in ":;,-–—"):
            raise ValueError(f"Geçersiz düğüm adı: {raw_node!r}")
        if not raw_node:
            raise ValueError("Düğüm adı boş olamaz.")
        nodes.append(raw_node)
    return nodes


def _parse_edges(section: str, node_by_key: dict[str, str]) -> list[MaxCutEdge]:
    """Consume every edge token, allowing a natural-language trailing sentence."""

    edges: list[MaxCutEdge] = []
    position = 0
    length = len(section)
    while position < length:
        match = _EDGE.match(section, position)
        if match is None:
            remainder = section[position:].strip()
            if not edges and remainder:
                raise ValueError(
                    "Kenarlar bölümünde A-B:3 biçiminde en az bir ağırlıklı kenar yazın."
                )
            if not remainder:
                break
            raise ValueError(f"Kenar tanımı anlaşılmadı: {remainder!r}")

        source_text = match.group("source").strip()
        target_text = match.group("target").strip()
        source = node_by_key.get(_maxcut_label_key(source_text))
        target = node_by_key.get(_maxcut_label_key(target_text))
        if source is None or target is None:
            raise ValueError(
                f"{source_text!r}-{target_text!r} kenarının iki ucu da Düğümler bölümünde olmalıdır."
            )
        if _maxcut_label_key(source) == _maxcut_label_key(target):
            raise ValueError("Max-Cut grafında bir kenar kendisine bağlanamaz.")
        try:
            weight = float(match.group("weight"))
        except ValueError as exc:  # Defensive: _EDGE only accepts numeric literals.
            raise ValueError("Kenar ağırlığı geçerli bir sayı olmalıdır.") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError("Kenar ağırlığı pozitif ve sonlu olmalıdır.")
        edges.append(MaxCutEdge(source=source, target=target, weight=weight))
        position = match.end()

        # Comma, semicolon and new line are unambiguous edge separators.
        separator = re.match(r"\s*[,;\r\n]+\s*", section[position:])
        if separator is not None:
            position += separator.end()
            if position >= length:
                raise ValueError("Son kenardan sonra yeni bir kenar bekleniyor.")
            continue

        # A full stop may either separate another edge or begin an optional
        # explanatory sentence after the final edge.
        period = re.match(r"\s*[.!?]\s*", section[position:])
        if period is not None:
            next_position = position + period.end()
            if next_position < length and _EDGE.match(section, next_position) is not None:
                position = next_position
                continue
            # Only prose is allowed after a terminating punctuation mark. It
            # deliberately has no effect on the graph or solver selection.
            break

        remainder = section[position:].strip()
        if remainder:
            raise ValueError(
                "Kenarları virgül, noktalı virgül veya yeni satırla ayırın; "
                "her kenar A-B:3 biçiminde olmalıdır."
            )
        break

    if not edges:
        raise ValueError("Kenarlar bölümünde en az bir kenar yazın.")
    return edges


def build_maxcut_qubo(graph: MaxCutGraph) -> np.ndarray:
    """Build the upper-triangular QUBO whose energy equals ``-cut_weight``.

    For every undirected edge ``(i, j, w)``, the max-cut contribution is
    ``w * (x_i + x_j - 2*x_i*x_j)``.  Negating it produces a minimization
    QUBO with ``Q_ii -= w``, ``Q_jj -= w`` and ``Q_ij += 2w`` for ``i < j``.
    """

    node_index = {_maxcut_label_key(node): index for index, node in enumerate(graph.nodes)}
    matrix = np.zeros((len(graph.nodes), len(graph.nodes)), dtype=float)
    for edge in graph.edges:
        source = node_index[_maxcut_label_key(edge.source)]
        target = node_index[_maxcut_label_key(edge.target)]
        low, high = sorted((source, target))
        matrix[low, low] -= edge.weight
        matrix[high, high] -= edge.weight
        matrix[low, high] += 2 * edge.weight
    return matrix


def qubo_energy(bits: Sequence[int] | np.ndarray, matrix: np.ndarray) -> float:
    """Evaluate the upper-triangular QUBO convention used by this module."""

    binary = np.asarray(bits, dtype=int)
    if binary.ndim != 1 or len(binary) != matrix.shape[0]:
        raise ValueError("Bit dizisi QUBO değişken sayısıyla aynı uzunlukta olmalıdır.")
    if not np.all((binary == 0) | (binary == 1)):
        raise ValueError("QUBO bitleri yalnızca 0 veya 1 olabilir.")
    diagonal = float(np.dot(np.diag(matrix), binary))
    interactions = 0.0
    for row in range(len(binary)):
        for column in range(row + 1, len(binary)):
            interactions += float(matrix[row, column] * binary[row] * binary[column])
    return diagonal + interactions


def cut_weight(graph: MaxCutGraph, bits: Sequence[int] | np.ndarray) -> float:
    """Return the total weight of edges crossing the represented partition."""

    binary = np.asarray(bits, dtype=int)
    if binary.ndim != 1 or len(binary) != len(graph.nodes):
        raise ValueError("Bit dizisi düğüm sayısıyla aynı uzunlukta olmalıdır.")
    if not np.all((binary == 0) | (binary == 1)):
        raise ValueError("Kesim bitleri yalnızca 0 veya 1 olabilir.")
    node_index = {_maxcut_label_key(node): index for index, node in enumerate(graph.nodes)}
    return float(
        sum(
            edge.weight
            for edge in graph.edges
            if binary[node_index[_maxcut_label_key(edge.source)]]
            != binary[node_index[_maxcut_label_key(edge.target)]]
        )
    )


def solve_maxcut(request: MaxCutRequest) -> MaxCutResponse:
    """Parse, encode and solve one small Max-Cut problem with three methods."""

    parsed = parse_maxcut_problem(request.problem)
    graph = parsed.graph
    matrix = build_maxcut_qubo(graph)
    results = [
        solve_maxcut_exact(graph, matrix),
        solve_maxcut_simulated_annealing(
            graph,
            matrix,
            seed=request.seed,
            iterations=request.annealing_iterations,
        ),
        solve_maxcut_quantum_inspired(
            graph,
            matrix,
            seed=request.seed,
            layers=request.quantum_layers,
        ),
    ]
    best = max(results, key=lambda result: result.cut_weight)
    return MaxCutResponse(
        graph=graph,
        qubo=_qubo_metadata(graph, matrix),
        results=results,
        best_solver=best.solver,
        parser_source=parsed.parser_source,
        explanation=(
            "Aynı ağırlıklı grafik, şeffaf QUBO modeline dönüştürüldü ve üç yöntemle "
            "karşılaştırıldı. Daha yüksek kesim ağırlığı daha iyi sonuçtur."
        ),
        warnings=[
            "Kuantum sonucu, gerçek kuantum donanımı değil; küçük grafikler için "
            "QAOA-esinli durum-vektörü simülasyonudur."
        ],
    )


def solve_maxcut_exact(graph: MaxCutGraph, matrix: np.ndarray | None = None) -> MaxCutResult:
    """Enumerate canonical bitstrings; bit zero stays in partition A."""

    started = time.perf_counter()
    qubo = matrix if matrix is not None else build_maxcut_qubo(graph)
    size = len(graph.nodes)
    best_bits: np.ndarray | None = None
    best_energy = math.inf
    for tail in range(1 << (size - 1)):
        bits = np.zeros(size, dtype=int)
        for index in range(1, size):
            bits[index] = (tail >> (index - 1)) & 1
        energy = qubo_energy(bits, qubo)
        if energy < best_energy:
            best_bits, best_energy = bits, energy
    assert best_bits is not None
    return _result(
        graph,
        best_bits,
        SolverName.EXACT,
        started,
        qubo,
        evaluated_states=1 << (size - 1),
        optimality="exact",
    )


def solve_maxcut_simulated_annealing(
    graph: MaxCutGraph,
    matrix: np.ndarray | None = None,
    *,
    seed: int,
    iterations: int,
) -> MaxCutResult:
    """A deterministic, single-bit-flip annealer over canonical partitions."""

    started = time.perf_counter()
    qubo = matrix if matrix is not None else build_maxcut_qubo(graph)
    rng = random.Random(seed)
    size = len(graph.nodes)
    current = np.array([0, *(rng.randrange(2) for _ in range(size - 1))], dtype=int)
    current_energy = qubo_energy(current, qubo)
    best = current.copy()
    best_energy = current_energy
    total_weight = sum(edge.weight for edge in graph.edges)
    temperature = max(total_weight, 1.0)
    cooling = (0.001 / temperature) ** (1 / max(iterations - 1, 1))
    accepted_moves = 0

    for _ in range(iterations):
        candidate = current.copy()
        candidate[rng.randrange(1, size)] ^= 1
        candidate_energy = qubo_energy(candidate, qubo)
        delta = candidate_energy - current_energy
        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-12)):
            current, current_energy = candidate, candidate_energy
            accepted_moves += 1
            if current_energy < best_energy:
                best, best_energy = current.copy(), current_energy
        temperature *= cooling

    return _result(
        graph,
        best,
        SolverName.SIMULATED_ANNEALING,
        started,
        qubo,
        iterations=iterations,
        accepted_moves=accepted_moves,
        seed=seed,
    )


def solve_maxcut_quantum_inspired(
    graph: MaxCutGraph,
    matrix: np.ndarray | None = None,
    *,
    seed: int,
    layers: int,
) -> MaxCutResult:
    """Run a compact QAOA-style state-vector experiment, not a hardware claim.

    The problem phase uses normalized QUBO energies.  The X-mixer is applied
    directly to a full state vector, which is practical only because the API
    caps graph size at ten vertices.
    """

    started = time.perf_counter()
    qubo = matrix if matrix is not None else build_maxcut_qubo(graph)
    size = len(graph.nodes)
    dimension = 1 << size
    indices = np.arange(dimension, dtype=np.int64)
    states = _all_bitstrings(size)
    energies = np.array([qubo_energy(bits, qubo) for bits in states], dtype=float)
    scale = max(float(np.std(energies)), 1e-9)
    normalized_energies = (energies - float(np.mean(energies))) / scale
    rng = np.random.default_rng(seed)

    best_expectation = math.inf
    best_probabilities: np.ndarray | None = None
    best_gamma = 0.0
    best_beta = 0.0
    parameter_trials = 12 + layers * 8
    for _ in range(parameter_trials):
        gamma = float(rng.uniform(0.05, math.pi))
        beta = float(rng.uniform(0.05, math.pi / 2))
        state = np.full(dimension, 1 / math.sqrt(dimension), dtype=complex)
        for layer in range(layers):
            state *= np.exp(-1j * gamma * (layer + 1) / layers * normalized_energies)
            state = _apply_x_mixer(state, beta * (layer + 1) / layers, size, indices)
        probabilities = np.abs(state) ** 2
        expectation = float(np.dot(probabilities, energies))
        if expectation < best_expectation:
            best_expectation = expectation
            best_probabilities = probabilities
            best_gamma, best_beta = gamma, beta

    assert best_probabilities is not None
    # Sampling preserves the "measured candidate" story while a seeded RNG
    # makes both the selected cut and every reported metric reproducible.
    shots = min(1_024, max(256, dimension * 4))
    samples = rng.choice(dimension, size=shots, p=best_probabilities)
    sampled_index = int(samples[np.argmin(energies[samples])])
    selected_bits = _canonical_bits(states[sampled_index])
    selected_index = _bits_to_index(selected_bits)
    peak_index = int(np.argmax(best_probabilities))
    peak_probability = float(best_probabilities[peak_index])
    selected_probability = float(best_probabilities[selected_index])
    nonzero_probabilities = best_probabilities[best_probabilities > 0]
    entropy = float(-np.sum(nonzero_probabilities * np.log2(nonzero_probabilities)))
    uniform_probability = 1.0 / dimension

    return _result(
        graph,
        selected_bits,
        SolverName.QUANTUM_SIMULATOR,
        started,
        qubo,
        layers=layers,
        state_space=dimension,
        parameter_trials=parameter_trials,
        gamma=round(best_gamma, 6),
        beta=round(best_beta, 6),
        expected_cut_weight=round(-best_expectation, 8),
        peak_probability=round(peak_probability, 8),
        selected_probability=round(selected_probability, 8),
        uniform_probability=round(uniform_probability, 8),
        amplification_vs_uniform=round(peak_probability / uniform_probability, 6),
        probability_entropy_bits=round(entropy, 6),
        simulator="qaoa-inspired-statevector",
    )


def _apply_x_mixer(
    state: np.ndarray, beta: float, size: int, indices: np.ndarray
) -> np.ndarray:
    mixed = state
    for qubit in range(size):
        before = mixed
        mixed = math.cos(beta) * before - 1j * math.sin(beta) * before[indices ^ (1 << qubit)]
    return mixed


def _all_bitstrings(size: int) -> np.ndarray:
    states = np.arange(1 << size, dtype=np.int64)
    return ((states[:, None] >> np.arange(size, dtype=np.int64)) & 1).astype(int)


def _canonical_bits(bits: Sequence[int] | np.ndarray) -> np.ndarray:
    binary = np.asarray(bits, dtype=int).copy()
    if binary[0] == 1:
        binary = 1 - binary
    return binary


def _bits_to_index(bits: Sequence[int] | np.ndarray) -> int:
    return int(sum(int(bit) << index for index, bit in enumerate(bits)))


def _result(
    graph: MaxCutGraph,
    bits: Sequence[int] | np.ndarray,
    solver: SolverName,
    started: float,
    matrix: np.ndarray,
    **metadata: float | int | str,
) -> MaxCutResult:
    binary = _canonical_bits(bits)
    node_index = {_maxcut_label_key(node): index for index, node in enumerate(graph.nodes)}
    partition_a = [node for index, node in enumerate(graph.nodes) if binary[index] == 0]
    partition_b = [node for index, node in enumerate(graph.nodes) if binary[index] == 1]
    crossing_edges = [
        edge
        for edge in graph.edges
        if binary[node_index[_maxcut_label_key(edge.source)]]
        != binary[node_index[_maxcut_label_key(edge.target)]]
    ]
    weight = float(sum(edge.weight for edge in crossing_edges))
    metadata_with_energy = {
        **metadata,
        "qubo_energy": round(qubo_energy(binary, matrix), 8),
        "crossing_edge_count": len(crossing_edges),
    }
    return MaxCutResult(
        solver=solver,
        cut_weight=round(weight, 8),
        partition_a=partition_a,
        partition_b=partition_b,
        cut_edges=crossing_edges,
        bitstring="".join(str(int(bit)) for bit in binary),
        runtime_ms=round((time.perf_counter() - started) * 1_000, 3),
        metadata=metadata_with_energy,
    )


def _qubo_metadata(graph: MaxCutGraph, matrix: np.ndarray) -> MaxCutQuboMetadata:
    return MaxCutQuboMetadata(
        variables=graph.nodes,
        upper_triangular_matrix=[
            [round(float(value), 8) for value in row] for row in matrix.tolist()
        ],
    )

