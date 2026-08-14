import os
import json
import re
from typing import Dict, List, Any, Tuple
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LLMOrchestrator:
    def __init__(self):
        self.api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        self.endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4")
        self.api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        
        self.is_configured = bool(self.api_key and self.endpoint and "your_azure" not in self.api_key)
        
        self.client = None
        if self.is_configured:
            try:
                self.client = AzureOpenAI(
                    api_key=self.api_key,
                    api_version=self.api_version,
                    azure_endpoint=self.endpoint
                )
            except Exception as e:
                print(f"Error initializing Azure OpenAI client: {e}")
                self.client = None
                self.is_configured = False

    def test_connection(self) -> Tuple[bool, str]:
        """Tests if the Azure OpenAI service is reachable with current credentials."""
        if not self.is_configured or not self.client:
            return False, "Azure OpenAI kimlik bilgileri eksik veya hatalı yapılandırılmış (.env dosyasını kontrol edin)."
        
        try:
            # Simple prompt to test connection
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5
            )
            return True, "Bağlantı Başarılı!"
        except Exception as e:
            return False, f"Bağlantı hatası: {str(e)}"

    def formulate_problem(self, problem_description: str, num_variables: int) -> Dict[str, Any]:
        """
        Sends natural language optimization problem to GPT and retrieves the QUBO formulation.
        """
        if not self.is_configured or not self.client:
            # Fallback mock formulation for demonstration if API is not configured
            return self._mock_formulation(problem_description, num_variables)

        system_prompt = f"""You are an expert Quantum Computing and Optimization AI.
Your task is to take a natural language optimization problem and translate it into a QUBO (Quadratic Unconstrained Binary Optimization) mathematical model.

The user will provide the problem and specify that it has {num_variables} binary variables.

You must return a single JSON object containing EXACTLY these keys:
1. "variables": A list of {num_variables} strings describing what each binary variable x_i represents (index 0 to {num_variables-1}).
2. "matrix": An upper-triangular matrix of size {num_variables}x{num_variables} represented as a list of lists of floats.
   - The diagonal elements matrix[i][i] are the linear coefficients (Q_ii).
   - The off-diagonal elements matrix[i][j] (where i < j) are the quadratic coupling coefficients (Q_ij).
   - Since it's upper-triangular, matrix[i][j] MUST be 0.0 for i > j.
   - The energy formulation is E(x) = sum_i Q_ii x_i + sum_(i<j) Q_ij x_i x_j.
   - IMPORTANT: We want to MINIMIZE the energy E(x). Adjust signs accordingly (e.g. if the user wants to maximize value, you must minimize -value).
3. "explanation": A brief Turkish explanation explaining the mapping, objective function, and constraints penalties.

Few-Shot Example:
Problem: "3 nodes triangle graph Max-Cut"
Variables count: 3
Output JSON:
{{
  "variables": ["Node 0 set selection (0 or 1)", "Node 1 set selection (0 or 1)", "Node 2 set selection (0 or 1)"],
  "matrix": [
    [-2.0, 2.0, 2.0],
    [0.0, -2.0, 2.0],
    [0.0, 0.0, -2.0]
  ],
  "explanation": "Max-Cut problem aims to put connected nodes in different sets. For each edge (i,j), we minimize -x_i - x_j + 2*x_i*x_j. Summing for triangle: E(x) = -2*x_0 - 2*x_1 - 2*x_2 + 2*x_0*x_1 + 2*x_1*x_2 + 2*x_2*x_0."
}}

Do NOT wrap the output in markdown code blocks like ```json ... ```. Output raw JSON string only. If you do use markdown, the system will strip it, but it is preferred to output raw JSON directly. Ensure the matrix has exactly dimensions {num_variables}x{num_variables}.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Problem: {problem_description}\nVariables count: {num_variables}"}
                ],
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_response(content, num_variables)
            
        except Exception as e:
            print(f"Error in LLM formulate_problem: {e}")
            return {
                "success": False,
                "error": f"Azure OpenAI çağrısı başarısız oldu: {str(e)}",
                "fallback": True,
                **self._mock_formulation(problem_description, num_variables)
            }

    def explain_results(self, problem_description: str, variables: List[str], 
                        qubo_matrix: List[List[float]], best_state: str, 
                        best_energy: float, method: str) -> str:
        """
        Asks GPT to explain the optimization results in plain Turkish.
        """
        if not self.is_configured or not self.client:
            return self._mock_explanation(problem_description, variables, best_state, best_energy, method)

        system_prompt = """You are a Quantum Optimization Consultant explaining results to a student/internship supervisor.
Translate the binary solution state (e.g. '101') back into the context of the original problem using the descriptions of the variables.
Explain the meaning of the energy value (lower is better, indicating optimal satisfaction of constraints).
Keep the tone professional, encouraging, and clear. Write in Turkish."""

        user_content = f"""
Original Problem: {problem_description}
Variables representation: {json.dumps(variables, ensure_ascii=False)}
QUBO Matrix: {json.dumps(qubo_matrix)}
Selected Solver Method: {method}

Optimization Results:
- Best State found: '{best_state}'
- Best Energy level: {best_energy}

Please explain:
1. What does the state '{best_state}' mean in terms of the variables? Which items/cities/nodes are selected/assigned?
2. Why is this state the optimal solution (how does it minimize the cost or satisfy constraints)?
3. A brief summary of how the quantum or quantum-inspired method ({method}) succeeded in solving this.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Azure OpenAI rapor üretme hatası: {str(e)}\n\nKuantum Motoru Sonucu:\nEn İyi Durum: {best_state}\nEn Düşük Enerji: {best_energy}\nÇözücü: {method}"

    def _parse_json_response(self, content: str, n: int) -> Dict[str, Any]:
        """Cleans and parses JSON output from LLM, ensuring matrix dimension check."""
        try:
            # Strip markdown formatting if any
            clean_content = content
            if "```" in content:
                # Find content between ```json and ``` or ``` and ```
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if match:
                    clean_content = match.group(1)
            
            data = json.loads(clean_content)
            
            # Validation checks
            if "matrix" not in data or "variables" not in data:
                raise ValueError("JSON misses 'matrix' or 'variables' fields.")
                
            matrix = data["matrix"]
            if len(matrix) != n:
                raise ValueError(f"Matrix height ({len(matrix)}) does not match expected {n}.")
            for row in matrix:
                if len(row) != n:
                    raise ValueError(f"Matrix row width does not match expected {n}.")
                    
            data["success"] = True
            return data
        except Exception as e:
            print(f"JSON parsing error: {e}. Raw content was: {content}")
            return {
                "success": False,
                "error": f"JSON ayrıştırma hatası: {str(e)}. Lütfen tekrar deneyin.",
                "raw_content": content
            }

    def _mock_formulation(self, problem_description: str, n: int) -> Dict[str, Any]:
        """Mock formulation generator when API key is missing or calls fail."""
        variables = [f"Karar Değişkeni x_{i} (Seçim {i})" for i in range(n)]
        
        # Create a simple Max-Cut style upper triangular matrix as fallback
        # Let's put some negative linear weights on diagonal and positive coupling on off-diagonal
        matrix = [[0.0 for _ in range(n)] for _ in range(n)]
        for i in range(n):
            matrix[i][i] = -2.0
            for j in range(i + 1, n):
                matrix[i][j] = 2.0
                
        explanation = (
            "Not: Azure OpenAI bağlantısı aktif değil. Bu nedenle sistem otomatik olarak varsayılan bir "
            "Max-Cut/Ising optimizasyon modeli üretti. Diagonal terimler (-2.0) seçim yapmayı teşvik ederken, "
            "off-diagonal terimler (2.0) değişkenlerin aynı anda 1 olmasını engeller (penaltı)."
        )
        
        return {
            "success": True,
            "variables": variables,
            "matrix": matrix,
            "explanation": explanation,
            "is_mock": True
        }

    def _mock_explanation(self, problem_description: str, variables: List[str], 
                          best_state: str, best_energy: float, method: str) -> str:
        """Mock result explanation generator when API key is missing."""
        explanation = f"""### 🌟 Optimizasyon Sonuç Analiz Raporu (Simülasyon Modu)

**[UYARI]** Azure OpenAI API bağlantısı kurulmadığı için bu rapor yerel şablon motoru tarafından üretilmiştir.

#### 1. Elde Edilen Çözümün Anlamı:
Bulunan en iyi kuantum durumu: **'{best_state}'**
Değişken bazlı açılımı:
"""
        for i, char in enumerate(best_state):
            desc = variables[i] if i < len(variables) else f"Değişken x_{i}"
            status = "🟢 AKTİF / SEÇİLDİ (1)" if char == '1' else "🔴 PASİF / SEÇİLMEDİ (0)"
            explanation += f"- **{desc}**: {status}\n"
            
        explanation += f"""
#### 2. Enerji Seviyesi Değerlendirmesi:
- **Minimum Enerji Seviyesi**: `{best_energy}`
- Elde edilen negatif enerji değeri, optimizasyon motorunun kısıtları ihlal etmeden amaç fonksiyonunu minimize ettiğini gösterir. Bu durum, QUBO matrisindeki penaltıların ve hedeflerin dengelendiği en uyumlu noktadır.

#### 3. Çözücü Yöntemi ({method}):
- Kullandığınız **{method}** algoritması, olası {2**len(best_state)} farklı durum kombinasyonunu tarayarak en düşük enerji seviyesine sahip olan bu kombinasyonu başarıyla bulmuştur. QAOA simülasyonu, parametrik kuantum kapılarını (rotasyonları) optimize ederek bu duruma ait olasılık genliğini tepe noktasına ulaştırmıştır.
"""
        return explanation
