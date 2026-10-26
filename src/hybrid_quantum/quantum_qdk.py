from __future__ import annotations

import itertools
import hashlib
import importlib.metadata
import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np

from .models import City, RouteResult, SolverName
from .solvers import distance_matrix, route_cost


class QuantumRuntimeError(RuntimeError):
    """QDK kurulumu veya Azure Quantum yapılandırması kullanılamadığında oluşur."""


def _qsharp() -> Any:
    try:
        from qdk import qsharp
    except ImportError as exc:
        raise QuantumRuntimeError(
            'Microsoft QDK kurulu değil. `python -m pip install -e ".[quantum]"` çalıştırın.'
        ) from exc
    return qsharp


def _basis_phase(qs: str, state: int, qubits: int, angle: float) -> list[str]:
    zero_qubits = [index for index in range(qubits) if not (state >> index) & 1]
    lines = [f"X({qs}[{index}]);" for index in zero_qubits]
    if qubits == 1:
        lines.append(f"R1({angle:.12f}, {qs}[0]);")
    else:
        controls = ", ".join(f"{qs}[{index}]" for index in range(qubits - 1))
        lines.append(f"Controlled R1([{controls}], ({angle:.12f}, {qs}[{qubits - 1}]));")
    lines.extend(f"X({qs}[{index}]);" for index in reversed(zero_qubits))
    return lines


def _qsharp_source(
    costs: np.ndarray, qubits: int, gamma: float, beta: float, layers: int
) -> tuple[str, str]:
    operation = f"RouteQaoa_{uuid.uuid4().hex[:12]}"
    lines = [f"operation {operation}() : Result[] {{", f"use qs = Qubit[{qubits}];"]
    lines.extend(f"H(qs[{index}]);" for index in range(qubits))
    for _ in range(layers):
        for state, cost in enumerate(costs):
            lines.extend(_basis_phase("qs", state, qubits, -gamma * float(cost)))
        lines.extend(f"Rx({2 * beta:.12f}, qs[{index}]);" for index in range(qubits))
    measurements = ", ".join(f"MResetZ(qs[{index}])" for index in range(qubits))
    lines.extend([f"let results = [{measurements}];", "return results;", "}"])
    return operation, "\n".join(lines)


def _shot_index(shot: Sequence[Any]) -> int:
    index = 0
    for qubit, result in enumerate(shot):
        if str(result).lower().endswith("one") or str(result) == "1":
            index |= 1 << qubit
    return index


def _local_counts(operation: str, source: str, shots: int) -> Counter[int]:
    """QDK'yi temiz bir süreçte çalıştırarak Streamlit thread değişimlerinden ayır."""
    payload = json.dumps({"operation": operation, "source": source, "shots": shots})
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "hybrid_quantum.qdk_worker"],
            input=payload,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise QuantumRuntimeError("Kuantum devresi 120 saniye içinde tamamlanamadı.") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        message = detail[-1] if detail else "QDK çalışma süreci başlatılamadı."
        raise QuantumRuntimeError(f"Kuantum devresi çalıştırılamadı: {message}")
    try:
        data = json.loads(completed.stdout)
        return Counter({int(index): int(count) for index, count in data["counts"].items()})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise QuantumRuntimeError("Kuantum devresi geçerli ölçüm sonucu üretmedi.") from exc


def _azure_key_index(key: Any) -> int:
    if isinstance(key, (list, tuple)):
        return sum((1 << index) for index, value in enumerate(key) if int(value))
    tokens = re.findall(r"\b(?:0|1|Zero|One)\b", str(key), flags=re.IGNORECASE)
    bits = [1 if token.lower() in {"1", "one"} else 0 for token in tokens]
    return sum((1 << index) for index, value in enumerate(bits) if value)


def _azure_counts(
    qsharp: Any, operation: str, source: str, shots: int, target: str
) -> tuple[Counter[int], str]:
    resource_id = os.getenv("AZURE_QUANTUM_RESOURCE_ID")
    if not resource_id:
        raise QuantumRuntimeError(
            "Azure hedefi seçildi ancak AZURE_QUANTUM_RESOURCE_ID tanımlı değil."
        )
    try:
        from qdk.azure import Workspace
    except ImportError as exc:
        raise QuantumRuntimeError('Azure desteği için `qdk[azure]` kurulmalıdır.') from exc

    qsharp.init(target_profile=qsharp.TargetProfile.Base)
    qsharp.eval(source)
    program = qsharp.compile(f"{operation}()")
    workspace = Workspace(resource_id=resource_id)
    azure_target = workspace.get_targets(target)
    job = azure_target.submit(program, "HybridRouteQAOA", shots=shots)
    probabilities = job.get_results()
    counts: Counter[int] = Counter()
    for key, probability in probabilities.items():
        counts[_azure_key_index(key)] += round(float(probability) * shots)
    details = getattr(job, "details", None)
    return counts, str(getattr(details, "id", ""))


def solve_qdk_qaoa(
    cities: Sequence[City],
    *,
    layers: int,
    shots: int,
    target: str | None = None,
    distances: Sequence[Sequence[float]] | np.ndarray | None = None,
) -> RouteResult:
    """Kapı düzeyi QAOA devresini QDK simülatöründe veya Azure Quantum'da çalıştırır."""
    if len(cities) > 5:
        raise QuantumRuntimeError(
            "QDK çalışması en fazla 5 istasyonla sınırlandırıldı; qubit/devre maliyeti hızla büyür."
        )

    started = time.perf_counter()
    qsharp = _qsharp() if target else None
    distances = distance_matrix(cities, distances)
    tours = [(0, *tail) for tail in itertools.permutations(range(1, len(cities)))]
    tour_costs = np.array([route_cost(route, distances) for route in tours], dtype=float)
    qubits = max(1, math.ceil(math.log2(len(tours))))
    state_count = 2**qubits
    normalized = (tour_costs - tour_costs.min()) / max(float(np.ptp(tour_costs)), 1e-9)
    encoded_costs = np.full(state_count, float(normalized.max() + 2.0), dtype=float)
    encoded_costs[: len(tours)] = normalized

    # Arayüz çalışmasını hızlı ve öngörülebilir tutmak için tek devre parametresi çalıştırılır.
    # Daha kapsamlı parametre taraması ayrı benchmark akışında yapılmalıdır.
    candidates = [(0.8, 0.55)]
    best_expected = math.inf
    best_valid_counts: Counter[int] = Counter()
    best_parameters = candidates[0]
    azure_job_id = ""
    best_source = ""

    for gamma, beta in candidates:
        operation, source = _qsharp_source(encoded_costs, qubits, gamma, beta, layers)
        if target:
            assert qsharp is not None
            counts, azure_job_id = _azure_counts(qsharp, operation, source, shots, target)
        else:
            counts = _local_counts(operation, source, shots)
        valid_counts = Counter({index: count for index, count in counts.items() if index < len(tours)})
        valid_shots = sum(valid_counts.values())
        if not valid_shots:
            continue
        expected = sum(float(tour_costs[index]) * count for index, count in valid_counts.items()) / valid_shots
        if expected < best_expected:
            best_expected = expected
            best_valid_counts = valid_counts
            best_parameters = (gamma, beta)
            best_source = source

    if not best_valid_counts:
        raise QuantumRuntimeError("QDK çalıştırması geçerli bir rota ölçemedi.")

    best_index = max(best_valid_counts, key=best_valid_counts.get)
    route = tours[best_index]
    valid_shots = sum(best_valid_counts.values())
    top_measurements = ", ".join(
        f"{index:0{qubits}b}:{count}"
        for index, count in best_valid_counts.most_common(5)
    )
    backend_name = f"azure-quantum:{target}" if target else "qdk-local-sparse-simulator"
    circuit_fingerprint = hashlib.sha256(best_source.encode("utf-8")).hexdigest()[:16]
    try:
        qdk_version = importlib.metadata.version("qdk")
    except importlib.metadata.PackageNotFoundError:
        qdk_version = "unknown"
    return RouteResult(
        solver=SolverName.QDK_QAOA,
        route=[cities[index].name for index in route] + [cities[route[0]].name],
        distance=round(float(tour_costs[best_index]), 4),
        runtime_ms=round((time.perf_counter() - started) * 1_000, 3),
        metadata={
            "backend": backend_name,
            "qubits": qubits,
            "layers": layers,
            "shots_per_trial": shots,
            "parameter_trials": len(candidates),
            "gamma": best_parameters[0],
            "beta": best_parameters[1],
            "expected_distance": round(best_expected, 4),
            "feasible_routes": len(tours),
            "encoded_states": state_count,
            "valid_shots": valid_shots,
            "selected_probability": round(best_valid_counts[best_index] / valid_shots, 6),
            "top_measurements": top_measurements,
            "azure_job_id": azure_job_id,
            "circuit_model": "qsharp-binary-tour-cost-phase-qaoa",
            "circuit_fingerprint": circuit_fingerprint,
            "gate_family": "H + Controlled-R1 + Rx + MResetZ",
            "qdk_version": qdk_version,
            "execution_kind": "azure-hardware-or-provider" if target else "local-quantum-simulator",
        },
    )
