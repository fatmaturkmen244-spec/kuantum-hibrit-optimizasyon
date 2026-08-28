from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SolverName(str, Enum):
    EXACT = "exact"
    SIMULATED_ANNEALING = "simulated_annealing"
    QUANTUM_SIMULATOR = "quantum_simulator"
    QDK_QAOA = "qdk_qaoa"


class City(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    x: float
    y: float


class OptimizationRequest(BaseModel):
    cities: list[City] = Field(min_length=3, max_length=10)
    seed: int = 42
    annealing_iterations: int = Field(default=4_000, ge=100, le=100_000)
    quantum_layers: int = Field(default=3, ge=1, le=8)
    run_qdk: bool = False
    qdk_shots: int = Field(default=256, ge=64, le=4096)
    azure_quantum_target: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def city_names_are_unique(self) -> "OptimizationRequest":
        names = [city.name.casefold() for city in self.cities]
        if len(names) != len(set(names)):
            raise ValueError("Şehir/istasyon adları benzersiz olmalıdır.")
        return self


class RouteResult(BaseModel):
    solver: SolverName
    route: list[str]
    distance: float
    runtime_ms: float
    metadata: dict[str, float | int | str] = Field(default_factory=dict)


class OptimizationResponse(BaseModel):
    results: list[RouteResult]
    best_solver: SolverName
    explanation: str
    warnings: list[str] = Field(default_factory=list)
