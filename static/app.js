// Application State
let appState = {
    variables: [],
    matrix: [],
    problemText: "",
    solverMethod: "QAOA",
    bestState: "",
    bestEnergy: null,
    status: {},
    formulated: false
};

// Chart instances
let convergenceChart = null;
let probabilityChart = null;

// Predefined templates data
const problemTemplates = {
    maxcut: {
        description: "5 düğümlü (0, 1, 2, 3, 4) bir sosyal ağ grafiğinde maksimum kesim (Max-Cut) kümelemesini bul.\nKenarlar: (0,1), (0,2), (1,2), (1,3), (2,4), (3,4).\nAmaç, kesilen kenar sayısını maksimize edecek şekilde düğümleri iki ayrı gruba (0 ve 1) ayırmak.",
        variables: 5
    },
    tsp: {
        description: "3 şehirli (A, B, C) bir Gezgin Satıcı Problemi (TSP).\nŞehirler arası mesafeler: A-B = 10, B-C = 15, A-C = 20.\nAmaç, her şehri tam olarak bir kez ziyaret edip başlangıç noktasına dönen en kısa tur rotasını belirlemek.\n(İpucu: x_{c,t} değişkeni c şehrinin t. sırada ziyaret edilmesini temsil eder, toplam 3x3=9 değişken kullanılır).",
        variables: 9
    },
    knapsack: {
        description: "4 adet eşya için Kısıtlı Sırt Çantası Problemi.\nEşyaların Değerleri: E1 = 10 TL, E2 = 20 TL, E3 = 15 TL, E4 = 25 TL.\nAğırlıklar: E1 = 2 kg, E2 = 3 kg, E3 = 4 kg, E4 = 5 kg.\nÇantanın maksimum taşıma kapasitesi = 7 kg.\nToplam değeri maksimize ederken kapasite kısıtını aşmayan en verimli eşya kombinasyonunu (seç/seçme) belirle.",
        variables: 4
    },
    portfolio: {
        description: "4 varlıklı finansal portföy seçimi optimizasyonu.\nBeklenen getiriler: V1=%12, V2=%15, V3=%10, V4=%18.\nRisk seviyeleri (Kovaryans ilişkili): V1=%4, V2=%9, V3=%2, V4=%12.\nAmaç, riski minimize ederken getiriyi maksimize eden optimal ikili varlık sepetini belirlemektir.",
        variables: 4
    },
    custom: {
        description: "",
        variables: 5
    }
};

// DOM Elements
const elements = {
    cfgOpenaiKey: document.getElementById('cfg-openai-key'),
    cfgOpenaiEndpoint: document.getElementById('cfg-openai-endpoint'),
    cfgOpenaiDeployment: document.getElementById('cfg-openai-deployment'),
    cfgQuantumId: document.getElementById('cfg-quantum-id'),
    cfgQuantumLocation: document.getElementById('cfg-quantum-location'),
    btnSaveConfig: document.getElementById('btn-save-config'),
    
    problemTemplate: document.getElementById('problem-template'),
    problemDesc: document.getElementById('problem-desc'),
    variableSlider: document.getElementById('variable-slider'),
    variableVal: document.getElementById('variable-val'),
    btnFormulate: document.getElementById('btn-formulate'),
    
    quboExplanation: document.getElementById('qubo-explanation'),
    matrixGridContainer: document.getElementById('matrix-grid-container'),
    
    solverMethod: document.getElementById('solver-method'),
    qaoaParametersBox: document.getElementById('qaoa-parameters-box'),
    qaoaP: document.getElementById('qaoa-p'),
    qaoaIter: document.getElementById('qaoa-iter'),
    btnSolve: document.getElementById('btn-solve'),
    
    tabBtnCircuit: document.getElementById('tab-btn-circuit'),
    circuitCodeBlock: document.getElementById('circuit-code-block'),
    aiReportContent: document.getElementById('ai-report-content'),
    
    resultSummaryBox: document.getElementById('result-summary-box'),
    sumBestState: document.getElementById('sum-best-state'),
    sumBestEnergy: document.getElementById('sum-best-energy'),
    sumTime: document.getElementById('sum-time'),
    
    loadingSpinner: document.getElementById('loading-spinner'),
    loadingText: document.getElementById('loading-text')
};

// Initialize App
window.addEventListener('DOMContentLoaded', () => {
    // Initialize icons
    lucide.createIcons();
    
    // Fetch initial status and populate configs
    checkServerStatus();
    
    // Set initial template
    handleTemplateChange();
    
    // Register event listeners
    registerEventListeners();
    
    // Initialize charts placeholder
    setupEmptyCharts();
});

// Event Listeners Registration
function registerEventListeners() {
    // Config Saving
    elements.btnSaveConfig.addEventListener('click', saveConfiguration);
    
    // Template & Slider Change
    elements.problemTemplate.addEventListener('change', handleTemplateChange);
    elements.variableSlider.addEventListener('input', (e) => {
        elements.variableVal.textContent = e.target.value;
    });
    
    // Solver Change (Show/Hide QAOA params)
    elements.solverMethod.addEventListener('change', (e) => {
        appState.solverMethod = e.target.value;
        if (e.target.value === 'QAOA') {
            elements.qaoaParametersBox.style.display = 'block';
            elements.tabBtnCircuit.style.opacity = '1';
            elements.tabBtnCircuit.style.pointerEvents = 'auto';
        } else {
            elements.qaoaParametersBox.style.display = 'none';
            elements.tabBtnCircuit.style.opacity = '0.5';
            elements.tabBtnCircuit.style.pointerEvents = 'none';
            // Switch tab if current was circuit
            const activeTab = document.querySelector('.tab-btn.active');
            if (activeTab && activeTab.getAttribute('data-tab') === 'tab-circuit') {
                switchTab('tab-chart');
            }
        }
    });
    
    // Formulate Button
    elements.btnFormulate.addEventListener('click', formulateProblem);
    
    // Solve Button
    elements.btnSolve.addEventListener('click', solveProblem);
    
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const tabId = btn.getAttribute('data-tab');
            switchTab(tabId);
        });
    });
}

// Show/Hide Loading Overlay
function showLoading(show, text = "Lütfen bekleyin...") {
    elements.loadingText.textContent = text;
    elements.loadingSpinner.style.display = show ? 'flex' : 'none';
}

// Server Status Check
async function checkServerStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        appState.status = status;
        
        // Update header badges
        updateStatusBadge('status-openai', status.azure_openai.status_ok, status.azure_openai.status_ok ? "Bağlı" : "Bağlantı Hatası");
        updateStatusBadge('status-quantum', status.azure_quantum.configured, status.azure_quantum.configured ? "Yapılandırıldı" : "Yapılandırılmadı");
        
        // Pre-fill config form inputs if backend has them
        if (status.azure_openai.deployment) {
            elements.cfgOpenaiDeployment.value = status.azure_openai.deployment;
        }
    } catch (error) {
        console.error("Status check failed:", error);
        updateStatusBadge('status-openai', false, "Sunucu Çevrimdışı");
        updateStatusBadge('status-quantum', false, "Sunucu Çevrimdışı");
    }
}

function updateStatusBadge(badgeId, isOk, text) {
    const badge = document.getElementById(badgeId);
    if (!badge) return;
    
    const textEl = badge.querySelector('.status-text');
    textEl.textContent = text;
    
    if (isOk) {
        badge.classList.remove('disconnected');
        badge.classList.add('connected');
    } else {
        badge.classList.remove('connected');
        badge.classList.add('disconnected');
    }
}

// Save Configuration
async function saveConfiguration() {
    showLoading(true, "Konfigürasyon güncelleniyor ve test ediliyor...");
    
    const payload = {
        azure_openai_key: elements.cfgOpenaiKey.value || null,
        azure_openai_endpoint: elements.cfgOpenaiEndpoint.value || null,
        azure_openai_deployment: elements.cfgOpenaiDeployment.value || null,
        azure_quantum_resource_id: elements.cfgQuantumId.value || null,
        azure_quantum_location: elements.cfgQuantumLocation.value || null
    };
    
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        if (data.success) {
            // Re-check status
            await checkServerStatus();
            alert("Konfigürasyon başarıyla kaydedildi!");
        } else {
            alert("Hata: " + data.message);
        }
    } catch (error) {
        alert("Bağlantı hatası oluştu.");
    } finally {
        showLoading(false);
    }
}

// Template Selection Handler
function handleTemplateChange() {
    const templateName = elements.problemTemplate.value;
    const template = problemTemplates[templateName];
    
    if (template) {
        elements.problemDesc.value = template.description;
        if (templateName !== 'custom') {
            elements.variableSlider.value = template.variables;
            elements.variableVal.textContent = template.variables;
            elements.variableSlider.disabled = true; // Lock slider for presets
        } else {
            elements.variableSlider.disabled = false;
        }
    }
}

// Switch Results Tabs
function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.getAttribute('data-tab') === tabId) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    document.querySelectorAll('.tab-panel').forEach(panel => {
        if (panel.id === tabId) {
            panel.classList.add('active');
        } else {
            panel.classList.remove('active');
        }
    });
}

// Formulation (AI Parsing)
async function formulateProblem() {
    const problem = elements.problemDesc.value.trim();
    const numVars = parseInt(elements.variableSlider.value);
    
    if (!problem) {
        alert("Lütfen bir problem açıklaması yazın.");
        return;
    }
    
    showLoading(true, "Azure OpenAI problemi analiz ediyor ve QUBO matrisini formüle ediyor...");
    
    try {
        const response = await fetch('/api/formulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ problem: problem, num_variables: numVars })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Formülasyon başarısız.");
        }
        
        const data = await response.json();
        
        // Save to state
        appState.variables = data.variables;
        appState.matrix = data.matrix;
        appState.problemText = problem;
        appState.formulated = true;
        
        // Update UI
        elements.quboExplanation.innerHTML = `<h4>Yapay Zeka Formülasyon Analizi</h4><p>${data.explanation}</p>`;
        if (data.is_mock) {
            elements.quboExplanation.innerHTML += `<div style="color:var(--danger); margin-top:8px; font-size:0.75rem;">⚠️ Yerel simülasyon modu devrede (Azure OpenAI anahtarı eksik).</div>`;
        }
        
        renderMatrixGrid(data.matrix, data.variables);
        elements.btnSolve.disabled = false;
        
        // Automatically switch to first tab and scroll to QUBO card
        document.getElementById('col-qubo').scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        alert("Hata oluştu: " + error.message);
    } finally {
        showLoading(false);
    }
}

// Render QUBO matrix as interactive inputs
function renderMatrixGrid(matrix, variables) {
    const n = matrix.length;
    elements.matrixGridContainer.innerHTML = '';
    
    const grid = document.createElement('div');
    grid.className = 'matrix-grid';
    grid.style.gridTemplateColumns = `repeat(${n}, auto)`;
    
    for (let i = 0; i < n; i++) {
        for (let j = 0; j < n; j++) {
            const cell = document.createElement('input');
            cell.type = 'text';
            cell.className = 'matrix-cell';
            
            // Format labels for mouse hover
            let title = `Q[${i}][${j}]`;
            if (i === j) {
                cell.classList.add('diagonal');
                title += ` (Linear term: ${variables[i]})`;
            } else if (i < j) {
                title += ` (Quadratic term: ${variables[i]} & ${variables[j]})`;
            } else {
                cell.classList.add('zero-cell');
                cell.disabled = true; // Lower triangular elements are locked to 0
            }
            
            cell.title = title;
            cell.value = matrix[i][j].toFixed(2);
            
            // Allow manual matrix tuning
            if (i <= j) {
                cell.addEventListener('change', (e) => {
                    const val = parseFloat(e.target.value);
                    if (!isNaN(val)) {
                        appState.matrix[i][j] = val;
                        e.target.value = val.toFixed(2);
                    } else {
                        e.target.value = appState.matrix[i][j].toFixed(2);
                    }
                });
            }
            
            grid.appendChild(cell);
        }
    }
    
    elements.matrixGridContainer.appendChild(grid);
}

// Solve Problem
async function solveProblem() {
    if (!appState.formulated) return;
    
    const method = elements.solverMethod.value;
    const pSteps = parseInt(elements.qaoaP.value);
    const iterations = parseInt(elements.qaoaIter.value);
    
    showLoading(true, `${method === 'QAOA' ? 'Kuantum Simülatörü' : 'Optimizasyon Motoru'} çalıştırılıyor. Lütfen bekleyin...`);
    
    const startTime = performance.now();
    
    try {
        const response = await fetch('/api/solve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                matrix: appState.matrix,
                method: method,
                p_steps: pSteps,
                iterations: iterations
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Çözüm işlemi başarısız.");
        }
        
        const data = await response.json();
        const endTime = performance.now();
        const elapsedTime = ((endTime - startTime) / 1000).toFixed(2);
        
        appState.bestState = data.best_state;
        appState.bestEnergy = data.best_energy;
        
        // Show summary box
        elements.resultSummaryBox.style.display = 'flex';
        elements.sumBestState.textContent = data.best_state;
        elements.sumBestEnergy.textContent = data.best_energy.toFixed(3);
        elements.sumTime.textContent = `${elapsedTime} sn`;
        
        // Render convergence and probability charts
        updateCharts(data, method);
        
        // Render circuit if QAOA
        if (method === 'QAOA' && data.circuit_text) {
            elements.circuitCodeBlock.textContent = data.circuit_text;
        } else {
            elements.circuitCodeBlock.textContent = "Kuantum devresi çizelgesi bulunmamaktadır (Yalnızca QAOA çözücüsünde oluşturulur).";
        }
        
        // Automatically request AI result explanation
        await requestResultExplanation(data, method);
        
        // Scroll to results panel
        document.getElementById('col-results').scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        alert("Çözüm hatası: " + error.message);
    } finally {
        showLoading(false);
    }
}

// Request AI explanation
async function requestResultExplanation(solveData, method) {
    elements.aiReportContent.innerHTML = `<p class="text-muted">Azure OpenAI çözümü analiz ediyor ve Türkçe rapor hazırlıyor...</p>`;
    
    // Switch to GPT explanation tab to show real-time progress
    switchTab('tab-explanation');
    
    const payload = {
        problem: appState.problemText,
        variables: appState.variables,
        matrix: appState.matrix,
        best_state: solveData.best_state,
        best_energy: solveData.best_energy,
        method: solveData.method
    };
    
    try {
        const response = await fetch('/api/explain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        // Render response as simple HTML structure since markdown has headers and lists
        const formattedReport = formatMarkdownToHTML(data.explanation);
        elements.aiReportContent.innerHTML = formattedReport;
    } catch (error) {
        elements.aiReportContent.innerHTML = `<p style="color:var(--danger)">Azure OpenAI raporlama motoruna bağlanılamadı. Ham sonuçlar:</p>
        <pre>En İyi Durum: ${solveData.best_state}\nEnerji: ${solveData.best_energy}</pre>`;
    }
}

// Simple helper to parse basic markdown format (headers, bold, lists) to HTML
function formatMarkdownToHTML(markdown) {
    let html = markdown
        .replace(/### (.*)/g, '<h4>$1</h4>')
        .replace(/## (.*)/g, '<h3>$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/^- (.*)/gm, '<li>$1</li>');
        
    // Wrap adjacent list items in <ul>
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    return html;
}

// Visualization Charts Helpers
function setupEmptyCharts() {
    const ctxConv = document.getElementById('convergence-chart').getContext('2d');
    const ctxProb = document.getElementById('probability-chart').getContext('2d');
    
    Chart.defaults.color = '#9aa0b1';
    Chart.defaults.font.family = 'Outfit';
    
    convergenceChart = new Chart(ctxConv, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: 'Optimizasyon Yakınsama Grafiği', color: '#f0f2f5' }
            },
            scales: {
                x: { grid: { color: 'rgba(255, 255, 255, 0.05)' } },
                y: { grid: { color: 'rgba(255, 255, 255, 0.05)' } }
            }
        }
    });
    
    probabilityChart = new Chart(ctxProb, {
        type: 'bar',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: 'Kuantum Durum Olasılık Dağılımı', color: '#f0f2f5' }
            },
            scales: {
                x: { grid: { color: 'rgba(255, 255, 255, 0.05)' } },
                y: { min: 0, max: 1, grid: { color: 'rgba(255, 255, 255, 0.05)' } }
            }
        }
    });
}

function updateCharts(solverData, method) {
    // 1. Update Convergence/History Chart
    if (solverData.history && solverData.history.length > 0) {
        const labels = solverData.history.map(h => 
            method === 'QAOA' ? `Iter ${h.iteration}` : `Step ${h.step}`
        );
        const energies = solverData.history.map(h => 
            method === 'QAOA' ? h.expected_energy : h.energy
        );
        
        convergenceChart.data.labels = labels;
        convergenceChart.data.datasets = [{
            label: method === 'QAOA' ? 'Beklenen Kuantum Enerjisi' : 'Klasik Sıcaklık Enerjisi',
            data: energies,
            borderColor: method === 'QAOA' ? '#bd00ff' : '#00f2fe',
            backgroundColor: method === 'QAOA' ? 'rgba(189, 0, 255, 0.1)' : 'rgba(0, 242, 254, 0.1)',
            fill: true,
            tension: 0.2
        }];
        
        // If simulated annealing, we can also plot the best energy found
        if (method === 'SA') {
            const bestEnergies = solverData.history.map(h => h.best_energy);
            convergenceChart.data.datasets.push({
                label: 'En İyi Enerji (Tarihsel)',
                data: bestEnergies,
                borderColor: '#00ff87',
                borderDash: [5, 5],
                fill: false
            });
        }
        
        convergenceChart.update();
    } else {
        // Clear history graph if solver didn't provide history (e.g. Azure Quantum direct output)
        convergenceChart.data.labels = ['Bulut Sonucu'];
        convergenceChart.data.datasets = [{
            label: 'Enerji Seviyesi',
            data: [solverData.best_energy],
            borderColor: '#00ff87',
            backgroundColor: 'rgba(0, 255, 135, 0.2)',
            fill: true
        }];
        convergenceChart.update();
    }
    
    // 2. Update State Probabilities Chart
    if (method === 'QAOA' && solverData.state_probabilities && solverData.state_probabilities.length > 0) {
        // Take top 8 states for cleaner rendering
        const topStates = solverData.state_probabilities.slice(0, 8);
        
        probabilityChart.data.labels = topStates.map(s => s.bitstring);
        probabilityChart.data.datasets = [{
            label: 'Ölçüm Olasılığı',
            data: topStates.map(s => s.probability),
            backgroundColor: topStates.map((s, idx) => 
                idx === 0 ? 'rgba(0, 255, 135, 0.7)' : 'rgba(0, 242, 254, 0.4)'
            ),
            borderColor: topStates.map((s, idx) => 
                idx === 0 ? '#00ff87' : '#00f2fe'
            ),
            borderWidth: 1
        }];
        probabilityChart.update();
        elements.probabilityChartCanvas = document.getElementById('probability-chart');
        elements.probabilityChartCanvas.style.display = 'block';
    } else {
        // Hide or clear probability chart for Simulated Annealing/Azure Quantum since they output 1 single state
        probabilityChart.data.labels = [solverData.best_state];
        probabilityChart.data.datasets = [{
            label: 'Bulunan Tekil Çözüm Olasılığı',
            data: [1.0],
            backgroundColor: 'rgba(0, 255, 135, 0.7)',
            borderColor: '#00ff87',
            borderWidth: 1
        }];
        probabilityChart.update();
    }
}
