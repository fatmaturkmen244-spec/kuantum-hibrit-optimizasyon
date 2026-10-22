import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from quantum_solver import QuantumOptimizationEngine
from llm_orchestrator import LLMOrchestrator

# Load initial environment variables
load_dotenv()

app = FastAPI(title="Kuantum Hibrit Optimizasyon Motoru API", version="1.0.0")

# Initialize engines
quantum_engine = QuantumOptimizationEngine()
llm_orchestrator = LLMOrchestrator()

# Pydantic Schemas for Requests
class ConfigUpdateRequest(BaseModel):
    azure_openai_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: Optional[str] = None
    azure_openai_version: Optional[str] = None
    azure_quantum_resource_id: Optional[str] = None
    azure_quantum_location: Optional[str] = None

class FormulateRequest(BaseModel):
    problem: str = Field(..., example="5 şehirli Gezgin Satıcı Problemi için en kısa yol rotası")
    num_variables: int = Field(..., ge=2, le=14, example=5) # Restrict local Qiskit/sim simulation to max 14 qubits for stability

class SolveRequest(BaseModel):
    matrix: List[List[float]]
    method: str = Field(..., example="QAOA") # QAOA, Simulated Annealing, Azure Quantum
    p_steps: Optional[int] = Field(1, ge=1, le=5)
    iterations: Optional[int] = Field(30, ge=5, le=100)

class ExplainRequest(BaseModel):
    problem: str
    variables: List[str]
    matrix: List[List[float]]
    best_state: str
    best_energy: float
    method: str

# API Endpoints

@app.get("/api/status")
def get_status():
    """Checks connection statuses of AI and Quantum backends."""
    # Reload configurations in orchestrator dynamically in case .env changed
    global llm_orchestrator
    llm_orchestrator = LLMOrchestrator()
    
    openai_ok, openai_msg = llm_orchestrator.test_connection()
    
    # Check Azure Quantum library availability and if resource id is present
    quantum_id = os.environ.get("AZURE_QUANTUM_RESOURCE_ID", "")
    quantum_configured = bool(quantum_id and "your-subscription-id" not in quantum_id)
    
    from quantum_solver import HAS_QISKIT, HAS_AER, HAS_AZURE_QUANTUM
    
    return {
        "azure_openai": {
            "configured": llm_orchestrator.is_configured,
            "status_ok": openai_ok,
            "message": openai_msg,
            "deployment": llm_orchestrator.deployment_name
        },
        "azure_quantum": {
            "configured": quantum_configured,
            "library_installed": HAS_AZURE_QUANTUM,
            "message": "Bağlantı kurulmaya hazır." if quantum_configured else "Azure Quantum Workspace bilgileri eksik."
        },
        "local_simulators": {
            "qiskit_installed": HAS_QISKIT,
            "qiskit_aer_installed": HAS_AER,
            "numpy_fallback_active": True
        }
    }

def _local_config_is_explicitly_enabled(request: Request) -> bool:
    """Never accept cloud credentials from a public browser deployment."""
    local_hosts = {"127.0.0.1", "::1", "localhost"}
    client_host = request.client.host if request.client else ""
    return (
        os.getenv("ENABLE_LOCAL_CONFIG", "false").casefold() == "true"
        and client_host in local_hosts
    )


@app.post("/api/config")
def update_config(req: ConfigUpdateRequest, request: Request):
    """Development-only local configuration helper; disabled in public deployments."""
    if not _local_config_is_explicitly_enabled(request):
        raise HTTPException(
            status_code=403,
            detail=(
                "Bu geliştirme endpoint'i kapalıdır. Gizli anahtarları public API'ye göndermeyin; "
                "sunucu ortam değişkenleri veya Key Vault kullanın."
            ),
        )
    try:
        env_lines = []
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        config_dict = {
            "AZURE_OPENAI_API_KEY": req.azure_openai_key,
            "AZURE_OPENAI_ENDPOINT": req.azure_openai_endpoint,
            "AZURE_OPENAI_DEPLOYMENT_NAME": req.azure_openai_deployment,
            "AZURE_OPENAI_API_VERSION": req.azure_openai_version,
            "AZURE_QUANTUM_RESOURCE_ID": req.azure_quantum_resource_id,
            "AZURE_QUANTUM_LOCATION": req.azure_quantum_location,
        }

        # Update environment in active process memory
        for k, v in config_dict.items():
            if v is not None:
                os.environ[k] = v

        # Write updates to .env file
        updated_keys = set()
        new_env_lines = []
        
        for line in env_lines:
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                new_env_lines.append(line)
                continue
            
            parts = stripped.split("=", 1)
            key = parts[0].strip()
            if key in config_dict and config_dict[key] is not None:
                new_env_lines.append(f"{key}={config_dict[key]}\n")
                updated_keys.add(key)
            else:
                new_env_lines.append(line)

        # Append new configurations that were not in the file before
        for key, val in config_dict.items():
            if val is not None and key not in updated_keys:
                new_env_lines.append(f"{key}={val}\n")

        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(new_env_lines)
            
        # Re-initialize LLM Orchestrator
        global llm_orchestrator
        llm_orchestrator = LLMOrchestrator()

        return {"success": True, "message": "Konfigürasyon güncellendi ve .env dosyasına kaydedildi."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Konfigürasyon yazılırken hata oluştu: {str(e)}")

@app.post("/api/formulate")
def formulate_problem(req: FormulateRequest):
    """Asks AI to translate the problem description to a QUBO matrix."""
    result = llm_orchestrator.formulate_problem(req.problem, req.num_variables)
    if not result.get("success"):
        # If there's an error and no fallback, raise exception
        if "matrix" not in result:
            raise HTTPException(status_code=500, detail=result.get("error", "QUBO formülasyonu başarısız."))
    return result

@app.post("/api/solve")
def solve_problem(req: SolveRequest):
    """Executes the selected solver (QAOA, SA, Azure Quantum) on the QUBO matrix."""
    n = len(req.matrix)
    if n < 2 or n > 14:
        raise HTTPException(status_code=400, detail="Değişken sayısı 2 ile 14 arasında olmalıdır.")

    if req.method == "QAOA":
        # Check if Qiskit is used or NumPy simulator is called
        result = quantum_engine.solve_qaoa_qiskit(req.matrix, p=req.p_steps, iterations=req.iterations)
    elif req.method == "SA":
        result = quantum_engine.solve_simulated_annealing(req.matrix, num_steps=200)
    elif req.method == "AQ":
        res_id = os.environ.get("AZURE_QUANTUM_RESOURCE_ID", "")
        loc = os.environ.get("AZURE_QUANTUM_LOCATION", "eastus")
        result = quantum_engine.solve_azure_quantum(req.matrix, resource_id=res_id, location=loc)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Azure Quantum çözümü başarısız."))
    else:
        raise HTTPException(status_code=400, detail="Geçersiz çözücü yöntemi belirtildi.")
        
    return result

@app.post("/api/explain")
def explain_results(req: ExplainRequest):
    """Asks AI to explain the optimization results in plain language."""
    explanation = llm_orchestrator.explain_results(
        problem_description=req.problem,
        variables=req.variables,
        qubo_matrix=req.matrix,
        best_state=req.best_state,
        best_energy=req.best_energy,
        method=req.method
    )
    return {"explanation": explanation}

# Serve static web frontend
if os.path.exists("./static"):
    app.mount("/", StaticFiles(directory="./static", html=True), name="static")
else:
    @app.get("/")
    def root_fallback():
        return {"message": "Statik arayüz klasörü bulunamadı. Lütfen /static dizinini oluşturun."}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Hibrit Kuantum Optimizasyon Motoru http://{host}:{port} adresinde başlıyor...")
    uvicorn.run("main:app", host=host, port=port, reload=True)
