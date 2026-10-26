from __future__ import annotations

import pandas as pd
import streamlit as st

from hybrid_quantum.models import City, OptimizationRequest, RouteResult, SolverName
from hybrid_quantum.natural_language import CITY_CATALOG, parse_route_problem
from hybrid_quantum.service import optimize_routes


st.set_page_config(
    page_title="Quantum Route Lab",
    page_icon="⚛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

SOLVER_LABELS = {
    SolverName.EXACT: "Kesin kontrol yöntemi",
    SolverName.SIMULATED_ANNEALING: "Klasik hızlı yöntem",
    SolverName.QUANTUM_SIMULATOR: "Kuantum simülasyonu",
    SolverName.QDK_QAOA: "Microsoft Q# devresi",
}

SOLVER_FAMILIES = {
    SolverName.EXACT: "Klasik · tüm seçenekleri kontrol eder",
    SolverName.SIMULATED_ANNEALING: "Klasik · hızlı yaklaşık çözüm",
    SolverName.QUANTUM_SIMULATOR: "Kuantum modeli · bilgisayarda simülasyon",
    SolverName.QDK_QAOA: "Kuantum devresi · Microsoft QDK",
}

SOLVER_SHORT_LABELS = {
    SolverName.EXACT: "Kesin kontrol",
    SolverName.SIMULATED_ANNEALING: "Klasik hızlı",
    SolverName.QUANTUM_SIMULATOR: "Kuantum sim.",
    SolverName.QDK_QAOA: "Q# devresi",
}


def inject_design_system() -> None:
    st.markdown(
        """
        <style>
        :root {
            --qr-bg: #07101f;
            --qr-surface: rgba(12, 27, 52, .70);
            --qr-surface-strong: rgba(16, 34, 65, .92);
            --qr-border: rgba(137, 157, 255, .18);
            --qr-text: #f3f6ff;
            --qr-muted: #aebbd3;
            --qr-cyan: #66e6ff;
            --qr-violet: #8d78ff;
            --qr-green: #55e6a5;
            --qr-amber: #ffc66d;
        }
        .stApp {
            background:
                radial-gradient(circle at 82% 8%, rgba(104, 86, 255, .16), transparent 28rem),
                radial-gradient(circle at 12% 24%, rgba(0, 208, 255, .08), transparent 22rem),
                var(--qr-bg);
            color: var(--qr-text);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(8, 19, 38, .98), rgba(7, 16, 31, .96));
            border-right: 1px solid var(--qr-border);
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stDecoration"] { display: none; }
        .block-container { max-width: 1220px; padding-top: 2.1rem; padding-bottom: 4rem; }
        h1, h2, h3 { color: var(--qr-text); letter-spacing: -.025em; }
        p, label, [data-testid="stCaptionContainer"] { color: var(--qr-muted); }
        .quantum-hero {
            position: relative;
            overflow: hidden;
            padding: clamp(1.6rem, 4vw, 2.7rem);
            border: 1px solid rgba(137, 157, 255, .24);
            border-radius: 24px;
            background: linear-gradient(135deg, rgba(18, 37, 72, .94), rgba(12, 22, 44, .78));
            box-shadow: 0 24px 70px rgba(0, 0, 0, .25);
            margin-bottom: 1rem;
        }
        .quantum-hero::before {
            content: "";
            position: absolute;
            width: 18rem;
            height: 18rem;
            right: -5rem;
            top: -8rem;
            border: 1px solid rgba(102, 230, 255, .22);
            border-radius: 50%;
            box-shadow: 0 0 0 3rem rgba(141, 120, 255, .035), 0 0 0 6rem rgba(102, 230, 255, .025);
        }
        .quantum-hero::after {
            content: "ψ";
            position: absolute;
            right: 3rem;
            top: 50%;
            transform: translateY(-54%);
            color: rgba(133, 115, 255, .15);
            font: 700 10rem/1 Georgia, serif;
        }
        .quantum-eyebrow {
            color: var(--qr-cyan);
            font-size: .78rem;
            font-weight: 800;
            letter-spacing: .14em;
            text-transform: uppercase;
        }
        .quantum-hero h1 {
            position: relative;
            z-index: 1;
            max-width: 790px;
            margin: .55rem 0 .75rem;
            color: #f7f9ff;
            font-size: clamp(2.25rem, 5vw, 4rem);
            line-height: 1.02;
            letter-spacing: -.045em;
        }
        .quantum-hero p {
            position: relative;
            z-index: 1;
            max-width: 760px;
            margin: 0;
            color: var(--qr-muted);
            font-size: 1.03rem;
            line-height: 1.65;
        }
        .quantum-strip {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: .8rem;
            margin: 0 0 1.4rem;
        }
        .quantum-strip > div {
            padding: 1rem 1.1rem;
            border: 1px solid var(--qr-border);
            border-radius: 14px;
            background: var(--qr-surface);
            color: var(--qr-muted);
            font-size: .88rem;
        }
        .quantum-strip strong { display: block; color: var(--qr-text); margin-bottom: .25rem; }
        .section-kicker {
            color: var(--qr-cyan);
            font-weight: 800;
            font-size: .72rem;
            letter-spacing: .13em;
            text-transform: uppercase;
            margin-bottom: .35rem;
        }
        .section-title { margin: 0 0 .35rem; font-size: 1.65rem; }
        .section-copy { max-width: 760px; margin: 0 0 1.25rem; color: var(--qr-muted); line-height: 1.6; }
        .step-flow {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: .65rem;
            margin: 1rem 0 1.4rem;
        }
        .step-flow > div {
            min-height: 126px;
            padding: 1rem;
            border: 1px solid var(--qr-border);
            border-radius: 14px;
            background: var(--qr-surface);
        }
        .step-flow > div.quantum-step {
            border-color: rgba(141, 120, 255, .48);
            background: linear-gradient(145deg, rgba(76, 59, 163, .25), rgba(12, 27, 52, .72));
        }
        .step-no { color: var(--qr-cyan); font-size: .72rem; font-weight: 800; letter-spacing: .1em; }
        .step-flow strong { display: block; margin: .6rem 0 .3rem; color: var(--qr-text); font-size: .92rem; }
        .step-flow span:last-child { color: var(--qr-muted); font-size: .78rem; line-height: 1.45; }
        .comparison-box, .proof-box, .truth-box {
            padding: 1.1rem 1.2rem;
            border: 1px solid var(--qr-border);
            border-radius: 15px;
            background: var(--qr-surface);
            color: var(--qr-muted);
            line-height: 1.55;
        }
        .comparison-box strong, .proof-box strong, .truth-box strong { color: var(--qr-text); }
        .comparison-box.accent { border-left: 3px solid var(--qr-violet); }
        .proof-box.success { border-left: 3px solid var(--qr-green); }
        .proof-box.warn { border-left: 3px solid var(--qr-amber); }
        .quantum-level {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: .65rem;
            margin: .8rem 0 1.15rem;
        }
        .quantum-level > div {
            padding: .8rem .9rem;
            border: 1px solid var(--qr-border);
            border-radius: 12px;
            background: rgba(7, 16, 31, .55);
            color: #71819d;
            font-size: .78rem;
        }
        .quantum-level > div.active {
            color: var(--qr-text);
            border-color: rgba(102, 230, 255, .48);
            background: linear-gradient(135deg, rgba(21, 80, 110, .42), rgba(75, 58, 160, .28));
        }
        .quantum-level strong { display: block; color: inherit; margin-bottom: .2rem; }
        .architecture {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: .75rem;
            margin: 1rem 0;
        }
        .architecture > div {
            padding: 1.1rem;
            border-radius: 15px;
            border: 1px solid var(--qr-border);
            background: var(--qr-surface);
        }
        .architecture small { color: var(--qr-cyan); font-weight: 800; letter-spacing: .08em; }
        .architecture strong { display: block; color: var(--qr-text); margin: .45rem 0; }
        .architecture span { color: var(--qr-muted); font-size: .82rem; line-height: 1.45; }
        div[data-testid="stMetric"] {
            padding: .9rem 1rem;
            border: 1px solid var(--qr-border);
            border-radius: 14px;
            background: var(--qr-surface);
        }
        div[data-testid="stMetricLabel"] { color: var(--qr-muted); }
        div[data-testid="stMetricValue"] {
            color: var(--qr-text);
            font-size: clamp(1.35rem, 2.4vw, 2rem);
            white-space: normal;
            overflow-wrap: anywhere;
        }
        .stButton > button[kind="primary"] {
            min-height: 3rem;
            border: 0;
            border-radius: 12px;
            background: linear-gradient(90deg, #604ff1, #328edb);
            box-shadow: 0 10px 28px rgba(78, 92, 228, .24);
            font-weight: 750;
        }
        .stButton > button[kind="primary"]:hover { filter: brightness(1.08); }
        .stTabs [data-baseweb="tab-list"] { gap: .35rem; border-bottom: 1px solid var(--qr-border); }
        .stTabs [data-baseweb="tab"] { height: 3rem; color: var(--qr-muted); }
        .stTabs [aria-selected="true"] { color: var(--qr-text); }
        [data-testid="stDataFrame"], [data-testid="stDataEditor"] { border: 1px solid var(--qr-border); border-radius: 14px; overflow: hidden; }
        .sidebar-brand {
            padding: .8rem 0 1rem;
            border-bottom: 1px solid var(--qr-border);
            margin-bottom: 1rem;
        }
        .sidebar-brand strong { color: var(--qr-text); font-size: 1.05rem; }
        .sidebar-brand span { display: block; color: var(--qr-cyan); font-size: .7rem; letter-spacing: .12em; margin-top: .25rem; }
        .circuit-line {
            display: flex;
            align-items: center;
            gap: .45rem;
            flex-wrap: wrap;
            padding: 1rem 0 .25rem;
        }
        .gate {
            padding: .48rem .65rem;
            border: 1px solid rgba(141, 120, 255, .55);
            border-radius: 9px;
            color: var(--qr-text);
            background: rgba(86, 67, 184, .2);
            font: 700 .78rem/1 ui-monospace, SFMono-Regular, Menlo, monospace;
        }
        .wire { color: var(--qr-cyan); }
        @media (max-width: 900px) {
            .step-flow { grid-template-columns: 1fr 1fr; }
            .architecture { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 720px) {
            .quantum-hero { padding: 1.65rem 1.35rem; }
            .quantum-hero::after { display: none; }
            .quantum-strip, .step-flow, .architecture, .quantum-level { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    st.markdown(
        """
        <section class="quantum-hero">
            <div class="quantum-eyebrow">Klasik yöntem × Kuantum yöntemi</div>
            <h1>Rotaları karşılaştır, kuantumun farkını gör.</h1>
            <p>Şehirlerini gir ve tek düğmeye bas. Sistem aynı rota problemini klasik ve kuantum yöntemleriyle çözer; hangisinin daha kısa rota bulduğunu ve ne kadar sürdüğünü açıkça gösterir.</p>
        </section>
        <div class="quantum-strip">
            <div><strong>01 · Adil karşılaştırma</strong>Tüm yöntemler aynı şehirleri kullanır.</div>
            <div><strong>02 · Kolay sonuç</strong>Rota uzunluğu ve hesaplama süresi yan yana görünür.</div>
            <div><strong>03 · Kuantum kanıtı</strong>Kuantum devresinin gerçekten çalışıp çalışmadığı ayrıca gösterilir.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_heading(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="section-kicker">{kicker}</div>
        <h2 class="section-title">{title}</h2>
        <p class="section-copy">{copy}</p>
        """,
        unsafe_allow_html=True,
    )


def route_frame(result: RouteResult, cities: list[City]) -> pd.DataFrame:
    city_map = {city.name: city for city in cities}
    return pd.DataFrame(
        [
            {"İstasyon": name, "Sıra": order, "x": city_map[name].x, "y": city_map[name].y}
            for order, name in enumerate(result.route)
        ]
    )


def route_chart(result: RouteResult, cities: list[City]) -> None:
    frame = route_frame(result, cities)
    spec = {
        "height": 410,
        "layer": [
            {
                "mark": {"type": "line", "strokeWidth": 4, "color": "#66e6ff"},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative", "title": "X koordinatı"},
                    "y": {"field": "y", "type": "quantitative", "title": "Y koordinatı"},
                    "order": {"field": "Sıra", "type": "ordinal"},
                },
            },
            {
                "mark": {"type": "point", "filled": True, "size": 220, "color": "#8d78ff", "stroke": "#ffffff", "strokeWidth": 2},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative"},
                    "y": {"field": "y", "type": "quantitative"},
                    "tooltip": ["İstasyon", "Sıra", "x", "y"],
                },
            },
            {
                "mark": {"type": "text", "dy": -18, "fontSize": 13, "fontWeight": 700, "color": "#eef4ff"},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative"},
                    "y": {"field": "y", "type": "quantitative"},
                    "text": {"field": "İstasyon"},
                },
            },
        ],
        "config": {
            "background": "transparent",
            "view": {"stroke": None},
            "axis": {"labelColor": "#aebbd3", "titleColor": "#aebbd3", "gridColor": "#20314d", "domainColor": "#30415f"},
        },
    }
    st.vega_lite_chart(frame, spec, width="stretch")


def comparison_frame(results: list[RouteResult]) -> pd.DataFrame:
    exact = next((result for result in results if result.solver == SolverName.EXACT), None)
    reference = exact.distance if exact else min(result.distance for result in results)
    return pd.DataFrame(
        [
            {
                "Yöntem": SOLVER_LABELS[result.solver],
                "Nasıl çalışır?": SOLVER_FAMILIES[result.solver],
                "Rota uzunluğu": result.distance,
                "En iyi rotadan fark (%)": round((result.distance / reference - 1) * 100, 2),
                "Süre (saniye)": round(result.runtime_ms / 1_000, 4),
                "Rota": " → ".join(result.route),
            }
            for result in results
        ]
    )


def advantage_summary(results: list[RouteResult]) -> tuple[str, str]:
    quantum = next((result for result in results if result.solver == SolverName.QDK_QAOA), None)
    quantum = quantum or next(result for result in results if result.solver == SolverName.QUANTUM_SIMULATOR)
    classical = [result for result in results if result.solver in {SolverName.EXACT, SolverName.SIMULATED_ANNEALING}]
    best_classical = min(classical, key=lambda item: item.distance)
    quality_gap = (quantum.distance / best_classical.distance - 1) * 100
    runtime_ratio = quantum.runtime_ms / max(best_classical.runtime_ms, 0.001)
    if abs(quality_gap) < 0.01 and runtime_ratio < 1:
        status = "Kuantum yöntemi bu deneyde umut verici"
        detail = f"Kuantum yöntemi aynı uzunlukta rotayı buldu ve bu çalıştırmada {1 / runtime_ratio:.2f} kat daha hızlı ölçüldü. Kesin karar için daha fazla deney gerekir."
    elif abs(quality_gap) < 0.01:
        status = "Aynı uzunlukta rota bulundu"
        detail = f"Kuantum yöntemi en iyi klasik rotayla aynı uzunlukta bir rota buldu; fakat bu deneyde {runtime_ratio:.2f} kat daha uzun sürdü. Henüz hız avantajı yok."
    else:
        status = "Kuantum yöntemi bu deneyde öne geçmedi"
        detail = f"Kuantum rotası en iyi klasik rotadan %{quality_gap:.2f} daha uzun ve {runtime_ratio:.2f} kat daha uzun sürdü. Site sonucu saklamadan, olduğu gibi gösteriyor."
    return status, detail


def render_quantum_level(results: list[RouteResult]) -> None:
    qdk_result = next((result for result in results if result.solver == SolverName.QDK_QAOA), None)
    is_azure = bool(qdk_result and qdk_result.metadata.get("azure_job_id"))
    level = 3 if is_azure else 2 if qdk_result else 1
    labels = [
        ("1 · Kuantum modeli", "Olasılıklar bilgisayarda simüle edilir."),
        ("2 · Microsoft Q# devresi", "Gerçek kuantum kapıları ve ölçümler çalışır."),
        ("3 · Azure Quantum", "İş bir bulut kuantum hedefine gönderilir."),
    ]
    items = "".join(
        f'<div class="{"active" if index <= level else ""}"><strong>{title}</strong>{description}</div>'
        for index, (title, description) in enumerate(labels, start=1)
    )
    st.markdown(
        '<div class="section-kicker">Bu deney ne kadar kuantum?</div>'
        f'<div class="quantum-level">{items}</div>',
        unsafe_allow_html=True,
    )


def render_quantum_proof(results: list[RouteResult]) -> None:
    qdk_result = next((result for result in results if result.solver == SolverName.QDK_QAOA), None)
    simulated = next(result for result in results if result.solver == SolverName.QUANTUM_SIMULATOR)
    if not qdk_result:
        st.markdown(
            """
            <div class="proof-box warn"><strong>Bu sonuç kuantum simülasyonundan geldi.</strong><br>
            Kuantum hesabının matematiği normal bilgisayarda canlandırıldı. Microsoft Q# devresi çalışmadığı için bu sonuç gerçek kuantum donanımı anlamına gelmez.</div>
            """,
            unsafe_allow_html=True,
        )
        metadata = simulated.metadata
        top_columns = st.columns(2)
        bottom_columns = st.columns(2)
        top_columns[0].metric("Olası rota sayısı", metadata.get("state_space", "—"))
        top_columns[1].metric("Hesaplama turu", metadata.get("layers", "—"))
        bottom_columns[0].metric("En güçlü olasılık", f"%{float(metadata.get('peak_probability', 0)) * 100:.2f}")
        bottom_columns[1].metric("Rastgeleye göre", f"{metadata.get('amplification_vs_uniform', '—')}×")
        return

    metadata = qdk_result.metadata
    is_azure = str(metadata.get("backend", "")).startswith("azure-quantum:")
    proof_class = "success" if is_azure else "warn"
    execution_text = (
        "Hesap Azure Quantum'a gönderildi ve iş numarası alındı."
        if is_azure
        else "Microsoft Q# devresi çalıştı. Şimdilik gerçek kuantum cihazı yerine bilgisayardaki kuantum simülatörü kullanıldı."
    )
    st.markdown(
        f'<div class="proof-box {proof_class}"><strong>Kuantum çalıştırma sonucu:</strong> {execution_text}</div>',
        unsafe_allow_html=True,
    )
    top_columns = st.columns(3)
    bottom_columns = st.columns(2)
    top_columns[0].metric("Çalıştığı yer", "Azure Quantum" if is_azure else "Bu bilgisayar")
    top_columns[1].metric("Kuantum biti", metadata.get("qubits", "—"))
    top_columns[2].metric("Tekrar sayısı", metadata.get("shots_per_trial", "—"))
    bottom_columns[0].metric("Devre turu", metadata.get("layers", "—"))
    bottom_columns[1].metric("En sık sonuç", f"%{float(metadata.get('selected_probability', 0)) * 100:.1f}")
    with st.expander("Teknik kuantum kanıtını göster"):
        st.caption("Aşağıdaki kapılar ve kimlik, aynı kuantum devresinin tekrar doğrulanabilmesini sağlar.")
        st.markdown(
            """
            <div class="circuit-line" aria-label="Kuantum devre kapıları">
                <span class="gate">H</span><span class="wire">━━</span>
                <span class="gate">Controlled-R1</span><span class="wire">━━</span>
                <span class="gate">Rx</span><span class="wire">━━</span>
                <span class="gate">MResetZ</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.code(
            "Devre kimliği      : " + str(metadata.get("circuit_fingerprint", "—")) + "\n"
            "Microsoft QDK      : " + str(metadata.get("qdk_version", "—")) + "\n"
            "Geçerli rota sayısı: " + str(metadata.get("feasible_routes", "—")) + "\n"
            "Kodlanan durumlar  : " + str(metadata.get("encoded_states", "—")) + "\n"
            "En sık ölçümler    : " + str(metadata.get("top_measurements", "—")),
            language="text",
        )
    if metadata.get("azure_job_id"):
        st.success(f"Azure Quantum iş kimliği: {metadata['azure_job_id']}")


def render_results(response: object, cities: list[City], fallback_notice: str = "") -> None:
    results = response.results
    best = min(results, key=lambda item: item.distance)
    qdk_result = next((result for result in results if result.solver == SolverName.QDK_QAOA), None)
    status, status_detail = advantage_summary(results)
    st.success("✓ Hesaplama tamamlandı. Sonuçlar hazır.")
    if fallback_notice:
        st.warning(fallback_notice)
    section_heading(
        "Sonuç",
        f"{len(results)} yöntem karşılaştırıldı",
        "Önce en kısa rotaya bakın. Ardından isterseniz süre karşılaştırmasını ve kuantum ayrıntısını inceleyin.",
    )
    top_summary = st.columns(2)
    bottom_summary = st.columns(2)
    top_summary[0].metric("En kısa mesafe", f"{best.distance:.3f}")
    top_summary[1].metric("En iyi yöntem", SOLVER_SHORT_LABELS[best.solver])
    bottom_summary[0].metric("Yöntem sayısı", len(results))
    bottom_summary[1].metric("Kuantum türü", "Q# devresi" if qdk_result else "Simülasyon")
    st.caption(
        f"Kısa özet: {SOLVER_LABELS[best.solver]} {best.distance:.3f} uzunluğunda en iyi rotayı buldu."
    )
    render_quantum_level(results)
    for warning in response.warnings:
        st.warning(warning)
    result_tab, route_tab, proof_tab = st.tabs(["Basit karşılaştırma", "En iyi rota", "Kuantum ayrıntısı"])
    with result_tab:
        frame = comparison_frame(results)
        st.dataframe(
            frame,
            width="stretch",
            hide_index=True,
            column_config={
                "Rota uzunluğu": st.column_config.NumberColumn(format="%.4f"),
                "En iyi rotadan fark (%)": st.column_config.NumberColumn(format="%.2f%%"),
                "Süre (saniye)": st.column_config.NumberColumn(format="%.4f"),
            },
        )
        left, right = st.columns(2)
        with left:
            st.caption("Rota uzunluğu · küçük sayı daha iyi")
            st.bar_chart(frame.set_index("Yöntem")[["Rota uzunluğu"]], color="#66e6ff", height=270)
        with right:
            st.caption("Hesaplama süresi · küçük sayı daha iyi")
            st.bar_chart(frame.set_index("Yöntem")[["Süre (saniye)"]], color="#8d78ff", height=270)
        st.markdown(
            f'<div class="comparison-box accent"><strong>{status}</strong><br>{status_detail}</div>',
            unsafe_allow_html=True,
        )
    with route_tab:
        st.caption(f"{SOLVER_LABELS[best.solver]} · {' → '.join(best.route)}")
        route_chart(best, cities)
    with proof_tab:
        render_quantum_proof(results)
    with st.expander("Geliştiriciler için teknik veriler"):
        for result in results:
            st.markdown(f"**{SOLVER_LABELS[result.solver]}**")
            st.json(result.metadata)


def execute_experiment(
    cities: list[City],
    *,
    requested_qdk: bool,
    iterations: int,
    layers: int,
    seed: int,
    qdk_shots: int,
    azure_target: str,
) -> tuple[object, str]:
    qdk_fallback = requested_qdk and len(cities) > 5
    fallback_notice = (
        f"{len(cities)} şehir seçildi. Microsoft Q# devresi en fazla 5 şehirle çalıştığı için "
        "bu deney kuantum simülasyonuyla tamamlandı. Q# devresini görmek için 5 şehir kullanın."
        if qdk_fallback
        else ""
    )
    request = OptimizationRequest(
        cities=cities,
        seed=int(seed),
        annealing_iterations=iterations,
        quantum_layers=layers,
        run_qdk=requested_qdk and not qdk_fallback,
        qdk_shots=qdk_shots,
        azure_quantum_target=azure_target.strip() or None,
    )
    with st.status("Rotalar hesaplanıyor...", expanded=True) as progress:
        progress.write("Aynı şehirler klasik ve kuantum yöntemlerine hazırlanıyor.")
        response = optimize_routes(request)
        progress.update(label="Hesaplama tamamlandı", state="complete", expanded=False)
    st.toast("Sonuçlar hazır", icon="✅")
    return response, fallback_notice


inject_design_system()
hero()

if st.session_state.get("app_state_version") != "natural-language-v3":
    for state_key in (
        "latest_response",
        "latest_cities",
        "latest_fallback_notice",
        "nl_response",
        "nl_cities",
        "nl_fallback_notice",
        "nl_summary",
        "nl_parser_source",
    ):
        st.session_state.pop(state_key, None)
    st.session_state["app_state_version"] = "natural-language-v3"

default_cities = pd.DataFrame(
    [
        {"name": "İstanbul", "x": 0.0, "y": 4.0},
        {"name": "Ankara", "x": 4.0, "y": 3.0},
        {"name": "İzmir", "x": 1.0, "y": 0.0},
        {"name": "Antalya", "x": 4.0, "y": 0.0},
        {"name": "Bursa", "x": 1.0, "y": 3.0},
    ]
)

with st.sidebar:
    st.markdown(
        '<div class="sidebar-brand"><strong>⚛ Quantum Route Lab</strong><span>HYBRID OPTIMIZATION ENGINE</span></div>',
        unsafe_allow_html=True,
    )
    st.subheader("Nasıl çalışsın?")
    run_qdk = st.checkbox(
        "Kuantum devresini de çalıştır", value=True,
        help="5 veya daha az şehirde Microsoft'un kuantum devresi de karşılaştırmaya eklenir.",
    )
    st.caption("5 veya daha az şehir seçildiğinde Microsoft Q# devresi otomatik olarak eklenir.")
    with st.expander("Gelişmiş ayarlar · isteğe bağlı"):
        iterations = st.slider(
            "Klasik aramanın deneme sayısı", 500, 20_000, 4_000, 500,
            help="Sayı büyüdükçe klasik yöntem daha fazla rota dener.",
        )
        layers = st.slider(
            "Kuantum hesabının tekrar turu", 1, 4, 1,
            help="Kuantum işlemlerinin kaç tur tekrarlandığını belirler.",
        )
        seed = st.number_input(
            "Aynı sonucu yeniden üretme numarası", value=42, step=1,
            help="Aynı numara, rastlantısal yöntemin aynı şekilde tekrar edilmesini sağlar.",
        )
        qdk_shots = st.slider(
            "Kuantum ölçüm tekrarı", 64, 1024, 64, 64, disabled=not run_qdk,
            help="Kuantum devresinin kaç kez ölçüleceğini belirler.",
        )
    with st.expander("Azure bulutunda çalıştır · isteğe bağlı"):
        azure_target = st.text_input(
            "Azure Quantum hedef adı", value="", disabled=not run_qdk,
            placeholder="Boş bırakırsanız bu bilgisayarda çalışır",
            help="Azure Quantum hesabı bağlandıysa hedef adı buraya yazılır.",
        )
        st.caption("Bu alanı bilmiyorsanız boş bırakın.")
    st.info("Başlamak için şehirleri kontrol edin ve sağdaki büyük düğmeye basın.")

experiment_tab, language_tab, quantum_tab, architecture_tab = st.tabs(
    ["Haritayla dene", "Yazarak çöz", "Kuantum nasıl çalışır?", "Proje nasıl çalışır?"]
)

with experiment_tab:
    section_heading(
        "Rota deneyi",
        "Şehirleri kontrol et ve karşılaştırmayı başlat",
        "Sadece şehir isimlerini değiştirebilirsiniz. Sağ-sol ve aşağı-yukarı sayıları şehirlerin örnek haritadaki yerini gösterir.",
    )
    edited = st.data_editor(
        default_cities,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Şehir / istasyon", required=True),
            "x": st.column_config.NumberColumn("Haritada sağ-sol", format="%.2f", required=True),
            "y": st.column_config.NumberColumn("Haritada aşağı-yukarı", format="%.2f", required=True),
        },
        key="route_city_editor_simple",
    )
    st.caption("İpucu: Tam kuantum devresini görmek için en fazla 5 şehir kullanın. Daha fazla şehirde kuantum simülasyonu yine çalışır.")
    if st.button("Rotaları karşılaştır", type="primary", width="stretch"):
        try:
            cities = [City(**row) for row in edited.to_dict(orient="records")]
            response, fallback_notice = execute_experiment(
                cities,
                requested_qdk=run_qdk,
                iterations=iterations,
                layers=layers,
                seed=int(seed),
                qdk_shots=qdk_shots,
                azure_target=azure_target,
            )
            st.session_state["latest_response"] = response
            st.session_state["latest_cities"] = cities
            st.session_state["latest_fallback_notice"] = fallback_notice
        except Exception as exc:
            st.error(f"Hesaplama tamamlanamadı: {exc}")
    if "latest_response" in st.session_state:
        render_results(
            st.session_state["latest_response"],
            st.session_state["latest_cities"],
            st.session_state.get("latest_fallback_notice", ""),
        )
    else:
        st.markdown(
            """
            <div class="truth-box"><strong>Her şey hazır.</strong><br>
            “Rotaları karşılaştır” düğmesine bastığınızda en kısa rota, yöntemlerin süresi ve kuantumun çalışıp çalışmadığı hemen burada görünecek.</div>
            """,
            unsafe_allow_html=True,
        )

with language_tab:
    section_heading(
        "Doğal dille optimizasyon",
        "Problemi normal bir cümleyle anlat",
        "Şehirleri ve kuantum isteğini cümlenden çıkarır; ardından aynı klasik–kuantum karşılaştırmasını otomatik başlatır.",
    )
    natural_text = st.text_area(
        "Çözmek istediğin problem",
        value=(
            "İstanbul'dan başlayıp Ankara, İzmir, Antalya ve Bursa'yı ziyaret eden "
            "en kısa turu bul. Klasik yöntemlerle kuantum yöntemini karşılaştır."
        ),
        height=120,
        help="Şimdilik şehir seçimi, en kısa kapalı tur ve kuantum karşılaştırması anlaşılır.",
        key="natural_route_problem",
    )
    supported_names = ", ".join(city[0] for city in CITY_CATALOG.values())
    st.caption("Kullanılabilen laboratuvar şehirleri: " + supported_names)
    st.info(
        "Azure OpenAI bağlıysa cümleyi yapay zekâ yapılandırır. Bağlı değilse uygulama aynı özelliği yerel şehir sözlüğüyle çalıştırır."
    )
    if st.button("Cümleyi anla ve çöz", type="primary", width="stretch"):
        try:
            parsed_problem = parse_route_problem(natural_text)
            response, fallback_notice = execute_experiment(
                parsed_problem.cities,
                requested_qdk=parsed_problem.use_quantum or run_qdk,
                iterations=iterations,
                layers=layers,
                seed=int(seed),
                qdk_shots=qdk_shots,
                azure_target=azure_target,
            )
            st.session_state["nl_response"] = response
            st.session_state["nl_cities"] = parsed_problem.cities
            st.session_state["nl_fallback_notice"] = fallback_notice
            st.session_state["nl_summary"] = parsed_problem.summary
            st.session_state["nl_parser_source"] = parsed_problem.parser_source
        except Exception as exc:
            st.error(f"Cümle çözülemedi: {exc}")
    if "nl_response" in st.session_state:
        st.success(
            "Anladığım problem: "
            + st.session_state["nl_summary"]
            + " · yorumlayan: "
            + st.session_state["nl_parser_source"]
        )
        render_results(
            st.session_state["nl_response"],
            st.session_state["nl_cities"],
            st.session_state.get("nl_fallback_notice", ""),
        )
    else:
        st.markdown(
            """
            <div class="truth-box"><strong>Örnek hazır.</strong><br>
            Cümleyi değiştirebilir veya doğrudan “Cümleyi anla ve çöz” düğmesine basabilirsin.</div>
            """,
            unsafe_allow_html=True,
        )

with quantum_tab:
    section_heading(
        "Basit anlatım",
        "Kuantum bu projede ne yapıyor?",
        "Normal yöntem rotaları tek tek veya küçük değişikliklerle arar. Kuantum yöntemi ise rota seçeneklerini olasılıklara çevirip iyi rotaların daha sık seçilmesini sağlamaya çalışır.",
    )
    st.markdown(
        """
        <div class="step-flow">
            <div><span class="step-no">01</span><strong>Şehirleri hazırla</strong><span>Şehirler arasındaki uzaklıklar hesaplanır.</span></div>
            <div class="quantum-step"><span class="step-no">02</span><strong>Rotaları sayılara çevir</strong><span>Her olası rota kuantum devresinde bir sayı ile temsil edilir.</span></div>
            <div class="quantum-step"><span class="step-no">03</span><strong>Kısa rotaları işaretle</strong><span>Devre, kısa ve uzun rotalara farklı işaretler verir.</span></div>
            <div class="quantum-step"><span class="step-no">04</span><strong>İyi rotaların şansını artır</strong><span>Kısa rotaların ölçümde daha sık çıkması hedeflenir.</span></div>
            <div><span class="step-no">05</span><strong>Sonucu karşılaştır</strong><span>Çıkan rota klasik yöntemlerle yan yana gösterilir.</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    classical_column, quantum_column = st.columns(2)
    with classical_column:
        st.markdown(
            '<div class="comparison-box"><strong>Normal bilgisayar ne yapıyor?</strong><br>Rotaları tek tek kontrol eder veya mevcut rotada küçük değişiklikler deneyerek daha kısa bir yol arar.</div>',
            unsafe_allow_html=True,
        )
    with quantum_column:
        st.markdown(
            '<div class="comparison-box accent"><strong>Kuantum yöntemi neyi farklı yapıyor?</strong><br>Rotaları olasılıklar halinde işler. Kuantum biti denilen “qubit”ler ve özel işlemler, iyi rotaların seçilme şansını değiştirmeye çalışır.</div>',
            unsafe_allow_html=True,
        )
    st.warning(
        "Önemli: Kuantum devresinin çalışması, otomatik olarak daha hızlı olduğu anlamına gelmez. "
        "Bu site tam olarak bunu ölçer ve sonucu dürüstçe gösterir."
    )
    st.subheader("İnsanlar bu projeyi neden kullanır?")
    use_columns = st.columns(3)
    use_columns[0].markdown("**Öğrenmek**\n\nKuantum kapıları ile gerçek bir optimizasyon problemi arasındaki bağı görür.")
    use_columns[1].markdown("**Kıyaslamak**\n\nKlasik ve kuantum yöntemleri aynı koşullarda ölçer; pazarlama yerine veri üretir.")
    use_columns[2].markdown("**Hazırlanmak**\n\nBugünün simülatöründen yarının Azure Quantum donanımına geçebilen iş akışı kurar.")

with architecture_tab:
    section_heading(
        "Projenin içi",
        "Site sonucu nasıl oluşturuyor?",
        "Kullanıcının cümlesi çözülebilir bir probleme dönüşür; klasik ve kuantum motorları aynı veride yarışır; sonuç kanıtlarıyla açıklanır.",
    )
    st.markdown(
        """
        <div class="architecture">
            <div><small>01 · KULLANICI</small><strong>Cümle veya tablo</strong><span>Problem normal cümleyle anlatılır ya da şehirler doğrudan girilir.</span></div>
            <div><small>02 · AZURE OPENAI</small><strong>Problem yapılandırma</strong><span>Şehirleri, hedefi ve kuantum isteğini çözülebilir veriye dönüştürür.</span></div>
            <div><small>03 · HİBRİT MOTOR</small><strong>Klasik + Microsoft Q#</strong><span>Aynı problem klasik yöntemler ve kuantum devresiyle çalıştırılır.</span></div>
            <div><small>04 · KANITLI SONUÇ</small><strong>Rota, süre ve kuantum seviyesi</strong><span>Sonuçlar yan yana gösterilir; kuantum avantajı varsa ölçülür.</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="proof-box success"><strong>Projeyi diğer rota sitelerinden ayıran nokta:</strong><br>
        Amaç yalnızca A noktasından B noktasına yol çizmek değildir. Kullanıcı problemi doğal dille verir; sistem aynı optimizasyon problemini klasik ve kuantum yöntemlerle çözüp kuantumun etkisini ölçülebilir hale getirir.</div>
        """,
        unsafe_allow_html=True,
    )
