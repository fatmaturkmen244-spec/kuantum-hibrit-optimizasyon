# Kuantum Hibrit Yol Optimizasyon Motoru 🔬⚛️

Kuantum bilişim ve yapay zeka tekniklerini birleştiren hibrit bir optimizasyon motoru. QUBO problemlerini QAOA, Simulated Annealing ve Azure Quantum kullanarak çözer.

## 🚀 Özellikler

- **QAOA** (Quantum Approximate Optimization Algorithm) — Qiskit ile lokal simülasyon
- **Simulated Annealing** — Klasik optimizasyon algoritması
- **Azure Quantum** — Bulut tabanlı gerçek kuantum işlemcisi desteği
- **Azure OpenAI** entegrasyonu — Problemi QUBO matrisine dönüştürme ve sonuçları açıklama
- **FastAPI** tabanlı REST API
- Modern web arayüzü

## 🛠️ Kurulum

```bash
# Depoyu klonlayın
git clone https://github.com/fatmaturkmen244-spec/kuantum-hibrit-optimizasyon.git
cd kuantum-hibrit-optimizasyon

# Sanal ortam oluşturun
python -m venv venv
venv\Scripts\activate  # Windows

# Bağımlılıkları yükleyin
pip install -r requirements.txt

# .env dosyasını oluşturun
cp .env.example .env
# .env dosyasını kendi API anahtarlarınızla düzenleyin
```

## ⚙️ Konfigürasyon

`.env` dosyasında aşağıdaki değişkenleri ayarlayın:

```env
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=your_endpoint
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_QUANTUM_RESOURCE_ID=your_resource_id
AZURE_QUANTUM_LOCATION=eastus
```

## ▶️ Çalıştırma

```bash
python run.py
# veya
python main.py
```

API `http://127.0.0.1:8000` adresinde çalışır.

## 📡 API Endpoints

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/api/status` | GET | Bağlantı durumlarını kontrol eder |
| `/api/config` | POST | API anahtarlarını günceller |
| `/api/formulate` | POST | Problemi QUBO matrisine dönüştürür |
| `/api/solve` | POST | Seçilen yöntemle optimizasyon çalıştırır |
| `/api/explain` | POST | Sonuçları AI ile açıklar |

## 📦 Teknolojiler

- **Python** + **FastAPI** + **Uvicorn**
- **Qiskit** + **Qiskit Aer**
- **Azure Quantum**
- **Azure OpenAI**
- **NumPy** + **SciPy**

## 📄 Lisans

MIT
