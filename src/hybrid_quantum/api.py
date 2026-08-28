from fastapi import FastAPI

from .models import OptimizationRequest, OptimizationResponse
from .service import optimize_routes

app = FastAPI(
    title="Hibrit Kuantum Optimizasyon Motoru",
    description="Doğal dil, klasik optimizasyon ve Microsoft Q# karşılaştırma motoru",
    version="0.2.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/optimize", response_model=OptimizationResponse)
def optimize(request: OptimizationRequest) -> OptimizationResponse:
    return optimize_routes(request)
