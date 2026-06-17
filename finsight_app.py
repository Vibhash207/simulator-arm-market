"""
FinSight MarketSim — AI- and Quantitative Model-Driven Multi-Layer
Semiconductor Market Risk Simulator for FP&A
Author : Vibhash | Senior Market Intelligence Analyst, Arm Ltd

TRUE zero-dependency build: every table, bar chart, and line chart is
rendered as raw HTML/CSS/SVG via st.markdown(). This app NEVER calls
st.dataframe(), st.bar_chart(), st.line_chart(), or st.table() — those
functions internally construct a pandas.DataFrame even when given a plain
dict/list, which breaks deployment when pandas/pyarrow wheels fail to
build on the target Python version. This app never imports pandas or
numpy anywhere.

MVP features implemented:
  1. Natural language prompt input (keyword-matched trigger parser)
  2. Market model selection (14 models: NAND, Server, AI Semi, etc.)
  3. Multi-model cascade chain simulation (BFS propagation engine)
  4. TAM, attach rate, royalty forecast output
  5. GPT-style auto-generated narrative summary (template-based)
  6. Exportable dashboard view (download as text report)

requirements.txt should contain ONLY: streamlit
Deploy: streamlit run finsight_app.py
"""

import streamlit as st
import random
import math
import re
from datetime import date
from collections import deque

st.set_page_config(
    page_title="FinSight MarketSim",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

ARM_BLUE   = "#0070C0"
ARM_GREEN  = "#1D9E75"
ARM_AMBER  = "#BA7517"
ARM_RED    = "#E24B4A"
ARM_PURPLE = "#7F77DD"
ARM_TEAL   = "#0F6E56"
ARM_GRAY   = "#888780"

st.markdown(f"""
<style>
  [data-testid="stMetricValue"] {{ font-size:1.8rem; font-weight:700; color:{ARM_BLUE}; }}
  [data-testid="stMetricDelta"] {{ font-size:0.82rem; }}
  .stTabs [data-baseweb="tab"]  {{ font-weight:600; font-size:0.9rem; }}
  .block-container               {{ padding-top:0.8rem; }}
  .fs-banner {{
    background:linear-gradient(90deg,{ARM_PURPLE},{ARM_BLUE});
    color:white; padding:0.5rem 1rem; border-radius:8px;
    font-size:0.78rem; margin-bottom:0.5rem;
  }}
  .htbl {{ width:100%; border-collapse:collapse; font-size:0.83rem; margin-bottom:0.8rem; }}
  .htbl th {{ text-align:left; padding:6px 10px; background:rgba(127,127,127,0.08);
              font-weight:600; border-bottom:1px solid rgba(127,127,127,0.25); }}
  .htbl td {{ padding:5px 10px; border-bottom:1px solid rgba(127,127,127,0.12); }}
  .htbl tr:hover td {{ background:rgba(127,127,127,0.05); }}
  .barwrap {{ display:flex; align-items:center; gap:8px; margin:4px 0; }}
  .barlbl  {{ width:190px; font-size:0.76rem; flex-shrink:0; text-align:right;
              white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .bartrack {{ flex:1; background:rgba(127,127,127,0.12); border-radius:4px;
               height:18px; position:relative; overflow:hidden; }}
  .barfill {{ height:100%; border-radius:4px; display:flex; align-items:center;
              padding-left:6px; box-sizing:border-box; }}
  .barval  {{ font-size:0.72rem; font-weight:600; color:white; white-space:nowrap; }}
  .cascade-node {{
    display:inline-flex; align-items:center; gap:6px; padding:6px 12px;
    border-radius:20px; font-size:0.78rem; font-weight:600; margin:3px;
  }}
  .narrative-box {{
    background:rgba(0,112,192,0.06); border-left:3px solid {ARM_BLUE};
    border-radius:6px; padding:14px 18px; font-size:0.92rem; line-height:1.65;
    margin:10px 0;
  }}
  .prompt-chip {{
    display:inline-block; padding:5px 12px; margin:3px; border-radius:16px;
    background:rgba(127,119,221,0.12); color:{ARM_PURPLE}; font-size:0.78rem;
    cursor:default; border:1px solid rgba(127,119,221,0.3);
  }}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# SYNTHETIC DATA — 14 market models, cascade graph, scenarios, NLP prompts
# (mirrors the Unified Simulation Matrix + Cross-Market Impact Matrix)
# ═══════════════════════════════════════════════════════════════════════════

MARKET_MODELS = {
    "MKT_001": {"name":"Overall Semiconductor Market", "category":"Macro",
                "driver":"Electronic unit production x Unit content x Device ASP",
                "tam_2025":620.0, "cagr":0.085, "attach_2025":0.42, "attach_cagr":0.015,
                "royalty_pct":1.15, "insight":"Align ARM's long-range royalty forecast with global semi trends"},
    "MKT_002": {"name":"AI Semiconductor Market", "category":"AI Compute",
                "driver":"Equipment units x Devices/unit x ASP",
                "tam_2025":95.0, "cagr":0.28, "attach_2025":0.38, "attach_cagr":0.045,
                "royalty_pct":1.85, "insight":"Target royalty growth in ML compute-heavy devices"},
    "MKT_003": {"name":"Foundry Services", "category":"Manufacturing",
                "driver":"Wafer demand + Tech node + Shipment x ASP",
                "tam_2025":130.0, "cagr":0.11, "attach_2025":0.0, "attach_cagr":0.0,
                "royalty_pct":0.0, "insight":"IP enablement timeline & fab strategy alignment"},
    "MKT_004": {"name":"Capital Spending", "category":"Macro",
                "driver":"Macro/foundry/memory capex",
                "tam_2025":190.0, "cagr":0.07, "attach_2025":0.0, "attach_cagr":0.0,
                "royalty_pct":0.0, "insight":"Region-based enablement & IP licensing focus"},
    "MKT_005": {"name":"DRAM Market", "category":"Memory",
                "driver":"Bit shipments x ASP",
                "tam_2025":80.0, "cagr":0.06, "attach_2025":0.05, "attach_cagr":0.02,
                "royalty_pct":0.15, "insight":"Memory-linked BoM modeling for server/AI/IP attach"},
    "MKT_006": {"name":"NAND Flash Market", "category":"Memory",
                "driver":"GB shipped x ASP x Capex",
                "tam_2025":45.0, "cagr":0.09, "attach_2025":0.22, "attach_cagr":0.025,
                "royalty_pct":0.45, "insight":"Inference build rate, hyperscaler deployment plans"},
    "MKT_007": {"name":"Automotive Semiconductor", "category":"End Market",
                "driver":"Vehicle units x Devices/vehicle x ASP",
                "tam_2025":72.0, "cagr":0.13, "attach_2025":0.55, "attach_cagr":0.035,
                "royalty_pct":1.65, "insight":"Royalty upside via automotive-grade ML SoCs"},
    "MKT_008": {"name":"Server Market", "category":"Data Center",
                "driver":"Units shipped x IT Budgets",
                "tam_2025":210.0, "cagr":0.14, "attach_2025":0.18, "attach_cagr":0.06,
                "royalty_pct":1.25, "insight":"Positioning of ARM-based CPUs and accelerators"},
    "MKT_009": {"name":"GenAI Model Market", "category":"AI Compute",
                "driver":"Foundation + Specialized models",
                "tam_2025":38.0, "cagr":0.42, "attach_2025":0.0, "attach_cagr":0.0,
                "royalty_pct":0.0, "insight":"Attach opportunity with specialized silicon"},
    "MKT_010": {"name":"Data Center / HCIS", "category":"Data Center",
                "driver":"Shipments + Vendor revenue",
                "tam_2025":95.0, "cagr":0.16, "attach_2025":0.20, "attach_cagr":0.05,
                "royalty_pct":1.05, "insight":"IP licensing route via near-edge inference shifts"},
    "MKT_011": {"name":"IoT Forecast", "category":"End Market",
                "driver":"Endpoint units x Electronics content",
                "tam_2025":95.0, "cagr":0.12, "attach_2025":0.71, "attach_cagr":0.02,
                "royalty_pct":0.65, "insight":"DSP/M-class chip licensing & attach forecasts"},
    "MKT_012": {"name":"Wearables Market", "category":"End Market",
                "driver":"Units x ASP x AI functionality",
                "tam_2025":18.0, "cagr":0.10, "attach_2025":0.88, "attach_cagr":0.015,
                "royalty_pct":0.55, "insight":"Target design wins for low-power ML inference"},
    "MKT_013": {"name":"Enterprise Machine Customers", "category":"End Market",
                "driver":"IoT endpoint count x Machine customer penetration",
                "tam_2025":22.0, "cagr":0.20, "attach_2025":0.48, "attach_cagr":0.04,
                "royalty_pct":0.95, "insight":"TAM for ARM SoCs in fully automated enterprise workflows"},
    "MKT_014": {"name":"PCs/Tablets/Mobile Phones", "category":"End Market",
                "driver":"ASP + Shipments + GenAI integration rate",
                "tam_2025":140.0, "cagr":0.04, "attach_2025":0.95, "attach_cagr":0.008,
                "royalty_pct":1.45, "insight":"Evaluate ARM licensing targets as GenAI reshapes devices"},
}

# Cross-Market Impact Matrix — (trigger, impacted, weight, lag_quarters, relationship)
# Cross-Market Impact Matrix — (trigger, impacted, weight, lag_quarters, sign, relationship)
# sign=+1: impact moves in the SAME direction as the trigger shock (e.g. macro
#          slowdown -> AI semi capex also falls)
# sign=-1: impact moves in the OPPOSITE direction (e.g. NAND/DRAM ASP FALLS ->
#          cheaper BoM -> server/SSD DEPLOYMENT VOLUME RISES). This correctly
#          captures price-vs-volume inverse relationships in the cascade graph,
#          matching the product spec's own scenario framing (NAND oversupply ->
#          cheaper SSDs -> MORE hyperscaler deployment, not less).
CASCADE_LINKS = [
    ("MKT_001","MKT_002", 0.65,1,+1,"Macro slowdown compresses AI semi capex"),
    ("MKT_001","MKT_014", 0.55,1,+1,"Macro slowdown compresses device shipments"),
    ("MKT_001","MKT_011", 0.40,2,+1,"Macro slowdown softens IoT endpoint growth"),
    ("MKT_003","MKT_002", 0.50,4,+1,"Node delay postpones AI chip availability"),
    ("MKT_003","MKT_008", 0.45,4,+1,"Node delay postpones server chip refresh"),
    ("MKT_003","MKT_007", 0.35,6,+1,"Node delay postpones automotive SoC programs"),
    ("MKT_003","MKT_014", 0.30,3,+1,"Node delay postpones premium phone SoCs"),
    ("MKT_004","MKT_003", 0.70,2,+1,"Capex shift drives foundry capacity build-out"),
    ("MKT_004","MKT_005", 0.55,2,+1,"Memory capex shift drives DRAM supply"),
    ("MKT_004","MKT_006", 0.55,2,+1,"Memory capex shift drives NAND supply"),
    ("MKT_005","MKT_008", 0.35,1,-1,"DRAM ASP falls -> lower BoM -> server refresh volume rises"),
    ("MKT_005","MKT_010", 0.25,1,-1,"DRAM ASP falls -> lower BoM -> data center deployment rises"),
    ("MKT_006","MKT_008", 0.30,1,-1,"NAND oversupply (ASP falls) -> cheaper SSDs -> hyperscaler server refresh accelerates"),
    ("MKT_006","MKT_010", 0.25,1,-1,"NAND ASP falls -> SSD deployment volume rises"),
    ("MKT_009","MKT_002", 0.75,1,+1,"GenAI model mix shift drives AI semi design wins"),
    ("MKT_009","MKT_008", 0.65,1,+1,"GenAI inference demand drives server upgrade cycle"),
    ("MKT_009","MKT_010", 0.50,2,+1,"GenAI deployment shifts data center mix"),
    ("MKT_009","MKT_014", 0.45,2,+1,"GenAI on-device shift drives smartphone AP redesign"),
    ("MKT_008","MKT_002", 0.40,1,+1,"Server refresh cycle pulls AI accelerator demand"),
    ("MKT_008","MKT_010", 0.45,1,+1,"Server demand shifts data center vendor revenue"),
    ("MKT_007","MKT_003", 0.40,4,+1,"Automotive SoC demand shifts foundry node allocation"),
    ("MKT_011","MKT_013", 0.60,2,+1,"IoT endpoint growth drives enterprise machine adoption"),
    ("MKT_011","MKT_012", 0.35,2,+1,"IoT growth correlates with wearables expansion"),
    ("MKT_013","MKT_011", 0.40,2,+1,"Enterprise automation drives additional IoT endpoints"),
    ("MKT_014","MKT_009", 0.30,2,+1,"Device GenAI integration drives specialized model demand"),
    ("MKT_012","MKT_011", 0.25,2,+1,"Wearables growth adds to IoT endpoint base"),
]

CASCADE_GRAPH = {}
for trig, imp, w, lag, sign, rel in CASCADE_LINKS:
    CASCADE_GRAPH.setdefault(trig, []).append((imp, w, lag, sign, rel))

# 12 sample multi-step scenarios (from product spec images 3-4)
SAMPLE_SCENARIOS = {
    "SCN_01": {"name":"NAND Oversupply + GenAI Acceleration", "trigger":"MKT_006", "shock":-30.0,
               "path":["Cheaper SSDs", "Hyperscalers accelerate server refresh",
                       "More GenAI inference capacity", "Increased demand for ML accelerators",
                       "ARM ML IP attach rate rises in inference chips"],
               "insight":"ARM could gain $60M in additional royalties across cloud providers over 3 years",
               "horizon":3},
    "SCN_02": {"name":"Foundry Delay + GenAI Model Specialization", "trigger":"MKT_003", "shock":-12.0,
               "path":["3nm capacity bottleneck", "OEMs pivot to 5nm/7nm SoCs",
                       "ARM IP still viable", "Growth of small GenAI models",
                       "ARM DSP and ML cores gain attach share"],
               "insight":"Sustains royalty streams even without bleeding-edge node access",
               "horizon":2},
    "SCN_03": {"name":"PC Refresh Cycle Driven by Windows 10 EOL", "trigger":"MKT_014", "shock":11.0,
               "path":["15M PCs replaced", "New hardware demand", "DRAM/NAND pricing stabilizes",
                       "OEMs explore ARM-based laptops for power efficiency",
                       "Attach rate of ARM CPU IP in notebooks rises"],
               "insight":"6-8% attach rate in refreshed segments can yield $30-50M in royalty uplift",
               "horizon":2},
    "SCN_04": {"name":"Robotaxi Adoption + Automotive SoC Spike", "trigger":"MKT_007", "shock":50.0,
               "path":["Robotaxis reach 50% of AVs by 2030", "More compute per car",
                       "High-end automotive SoCs", "Move to 5nm/3nm for ADAS chips",
                       "ARM safety IP and ML cores embedded in AV stack"],
               "insight":"Strategic push for ARM IP into auto SoCs = long-term high-ASP royalty tail",
               "horizon":5},
    "SCN_05": {"name":"Enterprise Machine Customers Replace Human Ops", "trigger":"MKT_013", "shock":70.0,
               "path":["70% of manufacturing bots auto-order parts by 2030",
                       "Spike in industrial IoT endpoints",
                       "ARM-based embedded controllers needed in field devices",
                       "Attach opportunity for M-class, DSP, TrustZone"],
               "insight":"Royalty TAM could double in industrial control IP over next 5 years",
               "horizon":5},
    "SCN_06": {"name":"On-Device GenAI Adoption in Smartphones", "trigger":"MKT_014", "shock":70.0,
               "path":["70% of smartphone SoCs include GenAI LLMs by 2027",
                       "Hardware requirements jump (ML cores, security modules)",
                       "ARM ML cores become baseline in premium & mid-tier phones"],
               "insight":"$100M+ attach TAM opportunity if capture rate exceeds 30%",
               "horizon":3},
    "SCN_07": {"name":"DRAM ASP Drop + Server Refresh Boom + ML Acceleration", "trigger":"MKT_005", "shock":-20.0,
               "path":["DRAM ASP falls 20% over 12 months", "Cloud providers refresh servers for GenAI workloads",
                       "ML inference chips ramp across data centers",
                       "ARM-based accelerators capture attach in inference-heavy use cases"],
               "insight":"Royalty acceleration follows hyperscaler build-up", "horizon":3},
    "SCN_08": {"name":"China Foundry Investment + Local Smartphone Growth", "trigger":"MKT_004", "shock":20.0,
               "path":["China increases foundry capex", "28nm capacity spikes",
                       "Domestic SoC design growth", "ARM IP used in many locally-designed AI-capable SoCs",
                       "Royalty growth from China-specific IP licensing programs"],
               "insight":"Geopolitically hedged royalty streams via local design wins", "horizon":4},
    "SCN_09": {"name":"Smart Factory IoT Explosion + Memory Cost Decline", "trigger":"MKT_011", "shock":12.0,
               "path":["12% CAGR in smart factory endpoints", "More devices per factory = more embedded compute",
                       "Lower BoM", "OEMs choose ARM over expensive alternatives",
                       "Attach for Cortex-M and TrustZone expands"],
               "insight":"ARM monetizes edge-scale growth via high-volume, low-cost IP", "horizon":4},
    "SCN_10": {"name":"Wearables Integrate GenAI Assistants", "trigger":"MKT_012", "shock":25.0,
               "path":["25% of smartwatches run GenAI LLMs by 2026",
                       "Need for real-time, on-device ML in ultra-low power form factor",
                       "ARM ML + DSP cores embedded in consumer wearables"],
               "insight":"New attach TAM for ultra-low power GenAI features", "horizon":3},
    "SCN_11": {"name":"Foundry Slowdown + Auto Segment Priority", "trigger":"MKT_003", "shock":-8.0,
               "path":["Foundries prioritize auto chips over consumer", "Consumer SoC launches delayed",
                       "Attach risk for ARM", "Auto segment gets faster access",
                       "Royalty pivot to automotive"],
               "insight":"Shift BU resources to automotive IP enablement", "horizon":2},
    "SCN_12": {"name":"Smartphone ASP Growth + AI Workload Shifts", "trigger":"MKT_014", "shock":10.0,
               "path":["Premium smartphone ASP rises 10%", "5% AI workload shift from cloud to edge",
                       "OEMs prioritize AI inference capability on-device",
                       "ARM ML cores capture premium tier design wins",
                       "Royalty per device increases disproportionately to unit growth"],
               "insight":"Royalty per device increases disproportionately to unit growth", "horizon":3},
}

# Stochastic volatility parameters per model (for Monte Carlo)
STOCHASTIC_PARAMS = {
    "MKT_001":12.0, "MKT_002":22.0, "MKT_003":18.0, "MKT_004":15.0, "MKT_005":28.0,
    "MKT_006":32.0, "MKT_007":14.0, "MKT_008":16.0, "MKT_009":30.0, "MKT_010":17.0,
    "MKT_011":11.0, "MKT_012":13.0, "MKT_013":19.0, "MKT_014":9.0,
}

# Natural language prompt -> trigger model keyword mapping
PROMPT_KEYWORDS = {
    "MKT_001": ["semiconductor market","overall semi","global semi","electronic unit"],
    "MKT_002": ["ai semiconductor","ai semi","ai chip","ml chip","inference chip","ai accelerator"],
    "MKT_003": ["foundry","fab","wafer","node","tsmc","3nm","5nm","7nm","capacity bottleneck"],
    "MKT_004": ["capital spending","capex","investment","china","sovereign"],
    "MKT_005": ["dram","memory price","memory market"],
    "MKT_006": ["nand","ssd","flash","nand pricing","nand crash","storage"],
    "MKT_007": ["automotive","auto semi","vehicle","robotaxi","ev","autonomous vehicle","adas"],
    "MKT_008": ["server","data center cpu","hyperscaler","server refresh"],
    "MKT_009": ["genai model","llm","foundation model","generative ai model"],
    "MKT_010": ["data center","hcis","edge ai"],
    "MKT_011": ["iot","internet of things","smart factory","industrial"],
    "MKT_012": ["wearable","smartwatch"],
    "MKT_013": ["enterprise machine","manufacturing bot","industrial robot","autonomous agent"],
    "MKT_014": ["smartphone","mobile phone","pc","tablet","laptop","windows 10","device"],
}

# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION ENGINE — BFS cascade propagation (pure Python, no numpy)
# ═══════════════════════════════════════════════════════════════════════════

def propagate_cascade(trigger_id, shock_pct, max_depth=4):
    """BFS through cascade graph. Returns dict: model_id -> impact detail."""
    results = {
        trigger_id: {
            "tam_delta_pct": shock_pct, "depth": 0, "lag_cumulative": 0,
            "path": [f"TRIGGER: {MARKET_MODELS[trigger_id]['name']} shocked {shock_pct:+.1f}%"],
        }
    }
    queue = deque([trigger_id])
    visited_depth = {trigger_id: 0}

    while queue:
        current = queue.popleft()
        current_depth = visited_depth[current]
        if current_depth >= max_depth:
            continue
        current_delta = results[current]["tam_delta_pct"]
        current_lag = results[current]["lag_cumulative"]

        for impacted_id, weight, lag, sign, relationship in CASCADE_GRAPH.get(current, []):
            lag_discount = max(0.5, 1 - (lag * 0.05))
            propagated_delta = current_delta * weight * lag_discount * sign

            if impacted_id not in results or abs(propagated_delta) > abs(results[impacted_id]["tam_delta_pct"]):
                new_path = results[current]["path"] + [
                    f"{MARKET_MODELS[impacted_id]['name']} ({relationship}): {propagated_delta:+.2f}%"
                ]
                results[impacted_id] = {
                    "tam_delta_pct": propagated_delta, "depth": current_depth + 1,
                    "lag_cumulative": current_lag + lag, "path": new_path,
                }
                if impacted_id not in visited_depth or visited_depth[impacted_id] > current_depth + 1:
                    visited_depth[impacted_id] = current_depth + 1
                    queue.append(impacted_id)
    return results

def get_latest_tam(model_id, horizon_years=5):
    """5-year forward TAM projection for a model."""
    m = MARKET_MODELS[model_id]
    return m["tam_2025"] * ((1 + m["cagr"]) ** horizon_years)

def calculate_royalty_impact(model_id, tam_delta_pct, horizon_years=5):
    """
    Converts TAM % delta into Arm royalty USD-million impact.

    Note on scale: this measures the royalty impact of the *delta* (the
    cascade-driven change), not Arm's full royalty TAM in that market. The
    attach-rate CAGR is capped at +1.5pp/year cumulative max to avoid runaway
    compounding over a 5-year horizon (e.g. Server's 6%/yr attach CAGR would
    otherwise compound to an unrealistic 48% attach rate by year 5). This
    keeps cascade-scenario outputs in the same order of magnitude as the
    product spec's own worked examples (e.g. NAND oversupply -> ~$60M).
    """
    m = MARKET_MODELS[model_id]
    base_tam_bn = get_latest_tam(model_id, horizon_years)
    attach_growth_capped = min(m["attach_cagr"] * horizon_years, 0.075)  # cap cumulative attach gain at 7.5pp
    attach_rate = min(0.65, m["attach_2025"] + attach_growth_capped)     # cap absolute attach rate at 65%
    royalty_pct = m["royalty_pct"]
    tam_delta_bn = base_tam_bn * (tam_delta_pct / 100)
    # Royalty impact = TAM delta x attach rate x royalty rate, scaled to USD millions
    royalty_delta_usd_m = tam_delta_bn * 1000 * attach_rate * (royalty_pct / 100)
    return round(royalty_delta_usd_m, 2)

def run_monte_carlo_scenario(trigger_id, base_shock, horizon_years, n_sims=2000):
    """MC simulation perturbing shock and cascade deltas. Pure Python — no numpy."""
    random.seed(hash((trigger_id, base_shock)) % (2**31))
    totals = []
    for _ in range(n_sims):
        shock_draw = random.gauss(base_shock, abs(base_shock) * 0.15 if base_shock != 0 else 1)
        cascade = propagate_cascade(trigger_id, shock_draw)
        total_royalty = 0.0
        for impacted_id, result in cascade.items():
            model_vol = STOCHASTIC_PARAMS.get(impacted_id, 15.0) / 100
            noisy_delta = result["tam_delta_pct"] * (1 + random.gauss(0, model_vol * 0.3))
            total_royalty += calculate_royalty_impact(impacted_id, noisy_delta, horizon_years)
        totals.append(total_royalty)
    return totals

def percentile(data, p):
    s = sorted(data)
    k = (len(s)-1) * p / 100
    lo, hi = int(k), min(int(k)+1, len(s)-1)
    return s[lo] + (s[hi]-s[lo]) * (k - lo)

def mc_stats(data):
    n = len(data)
    mean = sum(data)/n
    var = sum((x-mean)**2 for x in data)/n
    std = math.sqrt(var)
    return {"mean":mean, "median":percentile(data,50), "std":std,
            "p5":percentile(data,5), "p25":percentile(data,25),
            "p75":percentile(data,75), "p95":percentile(data,95),
            "min":min(data), "max":max(data)}

def parse_natural_language_prompt(prompt_text):
    """Keyword-match parser — finds the most likely trigger model + shock direction/magnitude."""
    text = prompt_text.lower()
    scores = {}
    for model_id, keywords in PROMPT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[model_id] = score
    if not scores:
        return None, None, None

    best_model = max(scores, key=scores.get)

    # Detect shock direction. Downside/upside words are weighted by *position*:
    # words appearing before the trigger keyword (describing the shock itself)
    # count double vs words appearing after it (often describing the downstream
    # outcome being asked about, e.g. "...crash affect GenAI royalty GROWTH").
    downside_words = ["crash","crashes","crashed","fall","falls","fell","falling",
                      "drop","drops","dropped","decline","declines","declining",
                      "slowdown","slows","bottleneck","delay","delayed","oversupply",
                      "decrease","decreases","cut","cuts","slump","plunge","plunges"]
    upside_words = ["boom","surge","surges","rise","rises","rising","risen",
                    "accelerate","accelerates","spike","spikes","increase","increases",
                    "adoption","ramp","ramps","expand","expands","reaches"]

    trigger_kw_pos = len(text)  # position of the matched trigger keyword in text
    for kw in PROMPT_KEYWORDS.get(best_model, []):
        idx = text.find(kw)
        if idx != -1:
            trigger_kw_pos = min(trigger_kw_pos, idx)

    direction = 0
    for w in downside_words:
        idx = text.find(w)
        if idx != -1:
            direction -= 2 if idx <= trigger_kw_pos + 30 else 1
    for w in upside_words:
        idx = text.find(w)
        if idx != -1:
            direction += 2 if idx <= trigger_kw_pos + 30 else 1
    direction = 1 if direction >= 0 else -1

    # Detect magnitude (look for percentage numbers)
    pct_match = re.search(r'(\d+)\s*%', text)
    magnitude = float(pct_match.group(1)) if pct_match else 20.0

    # Detect horizon
    horizon_match = re.search(r'(\d+)\s*[-\s]?year', text)
    horizon = int(horizon_match.group(1)) if horizon_match else 5

    return best_model, direction * magnitude, horizon

def generate_narrative_summary(trigger_id, shock_pct, cascade_results, mc_results, horizon_years):
    """Template-based GPT-style narrative — synthesizes the cascade path + insight."""
    trigger_name = MARKET_MODELS[trigger_id]["name"]
    direction_word = "decline" if shock_pct < 0 else "growth"
    n_touched = len(cascade_results) - 1  # exclude trigger itself

    sorted_impacts = sorted(
        [(mid, r) for mid, r in cascade_results.items() if mid != trigger_id],
        key=lambda x: abs(x[1]["tam_delta_pct"]), reverse=True
    )

    mc_s = mc_stats(mc_results) if mc_results else None
    total_mean = mc_s["mean"] if mc_s else sum(
        calculate_royalty_impact(mid, r["tam_delta_pct"], horizon_years)
        for mid, r in cascade_results.items()
    )

    direction_label = "downside risk" if total_mean < 0 else "an upside opportunity"
    direction_article = "a" if total_mean < 0 else ""

    article = "An" if str(abs(shock_pct))[0] in "18" else "A"
    summary_parts = [
        f"{article} {abs(shock_pct):.1f}% {direction_word} in the {trigger_name} triggers a measurable "
        f"cascade across {n_touched} downstream market{'s' if n_touched != 1 else ''} over a "
        f"{horizon_years}-year horizon."
    ]

    if sorted_impacts:
        top = sorted_impacts[0]
        top_name = MARKET_MODELS[top[0]]["name"]
        summary_parts.append(
            f"The largest secondary effect lands on {top_name}, "
            f"shifting its TAM by {top[1]['tam_delta_pct']:+.1f}% "
            f"with a propagation delay of approximately {top[1]['lag_cumulative']} "
            f"quarter{'s' if top[1]['lag_cumulative'] != 1 else ''}."
        )

    summary_parts.append(
        f"On a probability-weighted basis, this scenario represents {direction_article + ' ' if direction_article else ''}{direction_label} for Arm "
        f"royalty revenue of approximately ${abs(total_mean):,.1f}M"
        + (f" (90% confidence range: ${mc_s['p5']:,.1f}M to ${mc_s['p95']:,.1f}M)" if mc_s else "")
        + "."
    )

    if abs(total_mean) > 50:
        summary_parts.append(
            "Given the magnitude of this exposure, this scenario warrants inclusion in the "
            "quarterly FP&A risk register and scenario-weighted royalty forecast."
        )
    else:
        summary_parts.append(
            "The magnitude is moderate relative to Arm's total royalty base — monitor but "
            "does not currently require forecast revision."
        )

    return " ".join(summary_parts)

def fmt_m(v):
    return f"${v:,.1f}M" if abs(v) < 1000 else f"${v/1000:,.2f}B"
def fmt_bn(v):
    return f"${v:,.1f}B"

# ═══════════════════════════════════════════════════════════════════════════
# PURE-HTML RENDER HELPERS — no pandas, no numpy, no st.dataframe/st.bar_chart
# ═══════════════════════════════════════════════════════════════════════════

def html_table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body_rows = ""
    for r in rows:
        tds = "".join(f"<td>{c}</td>" for c in r)
        body_rows += f"<tr>{tds}</tr>"
    html = f'<table class="htbl"><thead><tr>{th}</tr></thead><tbody>{body_rows}</tbody></table>'
    st.markdown(html, unsafe_allow_html=True)

def html_bar_chart(labels_values, color=ARM_BLUE, fmt_func=None):
    if not labels_values:
        return
    fmt_func = fmt_func or (lambda v: f"{v:,.2f}")
    max_abs = max(abs(v) for _, v in labels_values) or 1
    rows_html = ""
    for label, val in labels_values:
        pct = min(100, abs(val) / max_abs * 100)
        bar_color = color if val >= 0 else ARM_RED
        rows_html += f"""
        <div class="barwrap">
          <div class="barlbl">{label}</div>
          <div class="bartrack">
            <div class="barfill" style="width:{pct:.1f}%; background:{bar_color};">
              <span class="barval">{fmt_func(val)}</span>
            </div>
          </div>
        </div>"""
    st.markdown(rows_html, unsafe_allow_html=True)

def html_line_chart(x_labels, y_vals, color=ARM_BLUE, height=220, y_label_fmt=None, fill=True):
    if not x_labels or not y_vals or len(x_labels) != len(y_vals):
        st.caption("No data to plot.")
        return
    y_label_fmt = y_label_fmt or (lambda v: f"{v:.1f}")
    w, h = 640, height
    pad_l, pad_r, pad_t, pad_b = 55, 16, 12, 24
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b

    y_min, y_max = min(y_vals), max(y_vals)
    if y_max == y_min: y_max = y_min + 1
    x_max = len(x_labels) - 1 if len(x_labels) > 1 else 1

    def sx(i): return pad_l + (i / max(x_max,1)) * plot_w
    def sy(v): return pad_t + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

    pts = [(sx(i), sy(v)) for i, v in enumerate(y_vals)]
    path_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area_d = ""
    if fill:
        area_d = (f"M {pts[0][0]:.1f},{pad_t+plot_h:.1f} "
                  + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                  + f" L {pts[-1][0]:.1f},{pad_t+plot_h:.1f} Z")

    grid_svg = ""
    for g in range(5):
        gy = pad_t + plot_h - (g/4) * plot_h
        gv = y_min + (g/4) * (y_max - y_min)
        grid_svg += (f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" '
                    f'stroke="rgba(127,127,127,0.15)" stroke-width="1"/>'
                    f'<text x="{pad_l-6}" y="{gy+3:.1f}" font-size="9" text-anchor="end" '
                    f'fill="currentColor" opacity="0.6">{y_label_fmt(gv)}</text>')

    x_label_svg = ""
    label_idxs = sorted(set([0, len(x_labels)//2, len(x_labels)-1]))
    for i in label_idxs:
        x_label_svg += (f'<text x="{sx(i):.1f}" y="{h-6}" font-size="9" text-anchor="middle" '
                        f'fill="currentColor" opacity="0.6">{x_labels[i]}</text>')

    fid = f"g{random.randint(0,999999)}"
    svg = f"""<svg viewBox="0 0 {w} {h}" style="width:100%; height:{h}px;">
      <defs><linearGradient id="{fid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="{color}" stop-opacity="0.30"/>
        <stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>
      </linearGradient></defs>
      {grid_svg}
      {f'<path d="{area_d}" fill="url(#{fid})" stroke="none"/>' if fill else ''}
      <path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.2"/>
      {x_label_svg}
    </svg>"""
    st.markdown(svg, unsafe_allow_html=True)

def html_multi_line_chart(x_labels, series_dict, height=240, y_label_fmt=None):
    """series_dict: {label: (values_list, color)}"""
    if not x_labels:
        st.caption("No data to plot.")
        return
    y_label_fmt = y_label_fmt or (lambda v: f"{v:.1f}")
    w, h = 640, height
    pad_l, pad_r, pad_t, pad_b = 55, 16, 12, 24
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b

    all_vals = [v for vals,_ in series_dict.values() for v in vals]
    y_min, y_max = min(all_vals), max(all_vals)
    if y_max == y_min: y_max = y_min + 1
    x_max = len(x_labels) - 1 if len(x_labels) > 1 else 1

    def sx(i): return pad_l + (i / max(x_max,1)) * plot_w
    def sy(v): return pad_t + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

    grid_svg = ""
    for g in range(5):
        gy = pad_t + plot_h - (g/4) * plot_h
        gv = y_min + (g/4) * (y_max - y_min)
        grid_svg += (f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" '
                    f'stroke="rgba(127,127,127,0.15)" stroke-width="1"/>'
                    f'<text x="{pad_l-6}" y="{gy+3:.1f}" font-size="9" text-anchor="end" '
                    f'fill="currentColor" opacity="0.6">{y_label_fmt(gv)}</text>')

    x_label_svg = ""
    label_idxs = sorted(set([0, len(x_labels)//2, len(x_labels)-1]))
    for i in label_idxs:
        x_label_svg += (f'<text x="{sx(i):.1f}" y="{h-6}" font-size="9" text-anchor="middle" '
                        f'fill="currentColor" opacity="0.6">{x_labels[i]}</text>')

    paths_svg = ""
    legend_html = ""
    for label, (vals, color) in series_dict.items():
        pts = [(sx(i), sy(v)) for i, v in enumerate(vals)]
        path_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        paths_svg += f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="2.2"/>'
        legend_html += (f'<span style="display:inline-flex;align-items:center;gap:4px;'
                        f'margin-right:14px;font-size:0.75rem;">'
                        f'<span style="width:9px;height:9px;border-radius:2px;background:{color};'
                        f'display:inline-block;"></span>{label}</span>')

    st.markdown(legend_html, unsafe_allow_html=True)
    svg = f"""<svg viewBox="0 0 {w} {h}" style="width:100%; height:{h}px;">
      {grid_svg}{paths_svg}{x_label_svg}
    </svg>"""
    st.markdown(svg, unsafe_allow_html=True)

def html_cascade_diagram(cascade_results, trigger_id):
    """Render the cascade chain as connected pill nodes grouped by depth."""
    by_depth = {}
    for mid, r in cascade_results.items():
        by_depth.setdefault(r["depth"], []).append((mid, r))

    html = '<div style="display:flex; flex-direction:column; gap:14px;">'
    for depth in sorted(by_depth.keys()):
        nodes = by_depth[depth]
        depth_label = "Trigger" if depth == 0 else f"Hop {depth}"
        html += f'<div><div style="font-size:0.7rem; color:var(--color-text-secondary,gray); margin-bottom:4px; text-transform:uppercase; letter-spacing:0.04em;">{depth_label}</div><div>'
        for mid, r in nodes:
            delta = r["tam_delta_pct"]
            color = ARM_RED if delta < 0 else ARM_GREEN
            bg = "rgba(226,75,74,0.12)" if delta < 0 else "rgba(29,158,117,0.12)"
            name = MARKET_MODELS[mid]["name"]
            html += (f'<span class="cascade-node" style="background:{bg}; color:{color};">'
                    f'{name} {delta:+.1f}%</span>')
        html += '</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f"<div style='font-size:1.4rem;font-weight:700;color:{ARM_BLUE}'>🧭 FinSight MarketSim</div>",
                unsafe_allow_html=True)
    st.markdown("<div style='font-size:0.72rem;color:gray;margin-bottom:0.8rem'>Multi-Layer Semiconductor Market Risk Simulator</div>",
                unsafe_allow_html=True)

    st.markdown("### Simulation Mode")
    mode = st.radio("Input method", ["Natural Language Prompt", "Manual Model Selection", "Pre-Built Scenario"],
                    label_visibility="collapsed")

    st.markdown("---")
    horizon_years = st.slider("Forecast horizon (years)", 1, 5, 5)
    n_mc_sims = st.select_slider("Monte Carlo iterations", options=[500,1000,2000,5000], value=2000)

    st.markdown("---")
    st.caption(f"Date: {date.today().strftime('%d %b %Y')} · 14 market models · 26 cascade links")
    st.caption("Synthetic demo data — production uses Databricks PySpark cascade engine on Delta Lake")

# ═══════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("# 🧭 FinSight MarketSim")
st.markdown("**AI- and Quantitative Model-Driven Multi-Layer Semiconductor Market Risk Simulator for FP&A**")
st.markdown(
    '<div class="fs-banner">📊 Public demo — synthetic data only · '
    'Zero pandas/numpy dependency — all visuals rendered in pure HTML/SVG · '
    '14 market models, 26 cascade relationships, 12 pre-built scenarios</div>',
    unsafe_allow_html=True
)

# ═══════════════════════════════════════════════════════════════════════════
# INPUT SECTION — determines trigger_id, shock_pct based on mode
# ═══════════════════════════════════════════════════════════════════════════
trigger_id, shock_pct, parsed_horizon = None, None, horizon_years
active_scenario_name = None

if mode == "Natural Language Prompt":
    st.markdown("### 💬 Natural Language Simulation Input")
    st.caption('Try: "How does a NAND pricing crash affect GenAI chip demand and Arm\'s royalty growth over 5 years?"')

    example_prompts = [
        "How does a NAND pricing crash affect GenAI chip demand and royalty growth over 5 years?",
        "What happens to Arm royalties if a 3nm foundry delay pushes GenAI chips to mature nodes?",
        "Simulate robotaxis reaching 50% of autonomous vehicles by 2030",
        "What is the impact of 70% of smartphone SoCs embedding GenAI LLMs by 2027?",
    ]
    chips_html = "".join(f'<span class="prompt-chip">{p[:55]}...</span>' for p in example_prompts[:2])
    st.markdown(chips_html, unsafe_allow_html=True)

    prompt_text = st.text_area(
        "Describe the market scenario you want to simulate",
        value="How does a NAND pricing crash affect GenAI chip demand and Arm's royalty growth over the next 5 years?",
        height=80, label_visibility="collapsed"
    )

    if st.button("🔮 Run Simulation from Prompt", type="primary"):
        st.session_state["nlp_triggered"] = True

    parsed_trigger, parsed_shock, parsed_h = parse_natural_language_prompt(prompt_text)
    if parsed_trigger:
        trigger_id, shock_pct = parsed_trigger, parsed_shock
        parsed_horizon = parsed_h if parsed_h else horizon_years
        st.success(
            f"Parsed: trigger = **{MARKET_MODELS[trigger_id]['name']}**, "
            f"shock = **{shock_pct:+.1f}%**, horizon = **{parsed_horizon} years**"
        )
    else:
        st.warning("Could not confidently parse a market trigger from this prompt — try mentioning a specific market (NAND, DRAM, foundry, server, automotive, etc.)")
        trigger_id, shock_pct = "MKT_006", -30.0

elif mode == "Manual Model Selection":
    st.markdown("### 🎛️ Manual Market Model Selection")
    c1, c2, c3 = st.columns(3)
    with c1:
        trigger_id = st.selectbox(
            "Trigger market model",
            list(MARKET_MODELS.keys()),
            format_func=lambda k: MARKET_MODELS[k]["name"],
            index=5  # default NAND
        )
    with c2:
        shock_direction = st.selectbox("Shock direction", ["Downside (decline)", "Upside (growth)"])
    with c3:
        shock_magnitude = st.slider("Shock magnitude (%)", 5, 80, 30)
    shock_pct = -shock_magnitude if "Downside" in shock_direction else shock_magnitude
    parsed_horizon = horizon_years

else:  # Pre-Built Scenario
    st.markdown("### 📋 Pre-Built Multi-Step Scenario")
    scenario_key = st.selectbox(
        "Select a scenario",
        list(SAMPLE_SCENARIOS.keys()),
        format_func=lambda k: SAMPLE_SCENARIOS[k]["name"]
    )
    scn = SAMPLE_SCENARIOS[scenario_key]
    trigger_id, shock_pct = scn["trigger"], scn["shock"]
    parsed_horizon = scn["horizon"]
    active_scenario_name = scn["name"]
    st.info(f"**Trigger:** {MARKET_MODELS[trigger_id]['name']} shocked {shock_pct:+.1f}% · "
            f"**Horizon:** {parsed_horizon} years")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# RUN SIMULATION
# ═══════════════════════════════════════════════════════════════════════════
cascade_results = propagate_cascade(trigger_id, shock_pct)
mc_results = run_monte_carlo_scenario(trigger_id, shock_pct, parsed_horizon, n_mc_sims)
mc_s = mc_stats(mc_results)
narrative = generate_narrative_summary(trigger_id, shock_pct, cascade_results, mc_results, parsed_horizon)

trigger_name = MARKET_MODELS[trigger_id]["name"]
st.markdown(f"## Simulation: {active_scenario_name or f'{trigger_name} shock'}")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 TAM, Attach & Royalty Forecast",
    "🔗 Cascade Chain Explorer",
    "🧠 GPT-Style Narrative Summary",
    "🎲 Monte Carlo Risk Analysis",
    "📚 All Market Models & Scenarios",
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1: TAM, ATTACH RATE, ROYALTY FORECAST OUTPUT
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("TAM, Attach Rate & Royalty Forecast Output")
    st.caption("MVP Feature: TAM, attach rate, royalty forecast output")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trigger Shock", f"{shock_pct:+.1f}%")
    c2.metric("Models Touched", f"{len(cascade_results)-1}")
    c3.metric("Max Cascade Depth", f"{max(r['depth'] for r in cascade_results.values())} hops")
    c4.metric("Mean Royalty Impact", fmt_m(mc_s["mean"]),
              delta="Upside" if mc_s["mean"] >= 0 else "Downside")

    st.markdown("---")
    st.markdown("#### Per-Model Impact Detail")
    detail_rows = []
    for mid, r in sorted(cascade_results.items(), key=lambda x: x[1]["depth"]):
        m = MARKET_MODELS[mid]
        base_tam = get_latest_tam(mid, parsed_horizon)
        attach = min(1.0, m["attach_2025"] + m["attach_cagr"] * parsed_horizon)
        royalty_impact = calculate_royalty_impact(mid, r["tam_delta_pct"], parsed_horizon)
        tier = "Trigger" if r["depth"]==0 else ("Direct" if r["depth"]==1 else f"Order-{r['depth']}")
        detail_rows.append([
            m["name"], tier, fmt_bn(base_tam), f"{attach*100:.1f}%",
            f"{m['royalty_pct']:.2f}%", f"{r['tam_delta_pct']:+.2f}%",
            fmt_m(royalty_impact), f"{r['lag_cumulative']}q"
        ])
    html_table(
        ["Market Model","Tier","TAM (Yr "+str(parsed_horizon)+")","Attach Rate","Royalty Rate",
         "TAM Δ%","Royalty Impact","Lag"],
        detail_rows
    )

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Royalty Impact by Model**")
        bar_data = [(MARKET_MODELS[mid]["name"], calculate_royalty_impact(mid, r["tam_delta_pct"], parsed_horizon))
                   for mid, r in cascade_results.items() if mid != trigger_id]
        bar_data.sort(key=lambda x: abs(x[1]), reverse=True)
        html_bar_chart(bar_data, color=ARM_PURPLE, fmt_func=fmt_m)

    with col_b:
        st.markdown("**TAM Trajectory — Trigger Model (5yr)**")
        years_lbl = [f"FY{2025+i}" for i in range(5)]
        base_path = [MARKET_MODELS[trigger_id]["tam_2025"] * ((1+MARKET_MODELS[trigger_id]["cagr"])**i) for i in range(5)]
        shocked_path = [v * (1 + shock_pct/100 if i >= 1 else 1) for i, v in enumerate(base_path)]
        html_multi_line_chart(
            years_lbl,
            {"Base forecast": (base_path, ARM_BLUE), "Post-shock": (shocked_path, ARM_RED)},
            y_label_fmt=lambda v: f"${v:.0f}B"
        )

# ════════════════════════════════════════════════════════════════════════════
# TAB 2: CASCADE CHAIN EXPLORER (Multi-model chain simulation)
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Multi-Model Cascade Chain Simulation")
    st.caption("MVP Feature: Multi-model chain simulation — visualizes the full propagation graph")

    html_cascade_diagram(cascade_results, trigger_id)

    st.markdown("---")
    st.markdown("#### Cascade Path Detail (full chain reasoning)")
    sorted_results = sorted(cascade_results.items(), key=lambda x: (x[1]["depth"], -abs(x[1]["tam_delta_pct"])))
    for mid, r in sorted_results:
        if mid == trigger_id:
            continue
        m = MARKET_MODELS[mid]
        with st.expander(f"{'🔴' if r['tam_delta_pct']<0 else '🟢'} {m['name']} — {r['tam_delta_pct']:+.2f}% (depth {r['depth']}, lag {r['lag_cumulative']}q)"):
            st.markdown(f"**Driver formula:** {m['driver']}")
            st.markdown(f"**Cascade path:**")
            for step in r["path"]:
                st.markdown(f"&nbsp;&nbsp;→ {step}")
            st.markdown(f"**Strategic insight:** {m['insight']}")
            royalty_impact = calculate_royalty_impact(mid, r["tam_delta_pct"], parsed_horizon)
            st.markdown(f"**Royalty impact:** {fmt_m(royalty_impact)}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 3: GPT-STYLE NARRATIVE SUMMARY
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Auto-Generated Executive Narrative")
    st.caption("MVP Feature: GPT summary — template-synthesized executive narrative from the cascade path and insight data")

    st.markdown(f'<div class="narrative-box">{narrative}</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Exportable Dashboard Report")

    report_lines = [
        "="*70,
        "FINSIGHT MARKETSIM — SIMULATION REPORT",
        "="*70,
        f"Generated: {date.today().strftime('%d %B %Y')}",
        f"Scenario: {active_scenario_name or f'{trigger_name} shock'}",
        f"Trigger: {trigger_name} | Shock: {shock_pct:+.1f}% | Horizon: {parsed_horizon} years",
        "",
        "EXECUTIVE SUMMARY",
        "-"*70,
        narrative,
        "",
        "ROYALTY IMPACT (Monte Carlo, N={:,} iterations)".format(n_mc_sims),
        "-"*70,
        f"Mean impact:    {fmt_m(mc_s['mean'])}",
        f"Median impact:  {fmt_m(mc_s['median'])}",
        f"P5 (downside):  {fmt_m(mc_s['p5'])}",
        f"P95 (upside):   {fmt_m(mc_s['p95'])}",
        f"Std deviation:  {fmt_m(mc_s['std'])}",
        "",
        "CASCADE CHAIN DETAIL",
        "-"*70,
    ]
    for mid, r in sorted_results:
        if mid == trigger_id: continue
        m = MARKET_MODELS[mid]
        royalty_impact = calculate_royalty_impact(mid, r["tam_delta_pct"], parsed_horizon)
        report_lines.append(f"  {m['name']}: {r['tam_delta_pct']:+.2f}% TAM | {fmt_m(royalty_impact)} royalty | depth {r['depth']}")
    report_lines += ["", "="*70, "Built with FinSight MarketSim | Vibhash, Arm Ltd", "="*70]

    report_text = "\n".join(report_lines)
    st.download_button(
        "📥 Download Dashboard Report (.txt)",
        data=report_text,
        file_name=f"finsight_report_{trigger_id}_{date.today().isoformat()}.txt",
        mime="text/plain"
    )
    with st.expander("Preview report"):
        st.text(report_text)

# ════════════════════════════════════════════════════════════════════════════
# TAB 4: MONTE CARLO RISK ANALYSIS
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Monte Carlo Risk Analysis — Quantified Uncertainty")
    st.caption(f"Quantify Uncertainty and Risk: {n_mc_sims:,} iterations perturbing shock magnitude and cascade deltas")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean Royalty Impact", fmt_m(mc_s["mean"]))
    c2.metric("Median", fmt_m(mc_s["median"]))
    c3.metric("Std Deviation", fmt_m(mc_s["std"]))
    c4.metric("90% CI Width", fmt_m(mc_s["p95"]-mc_s["p5"]))

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Royalty Impact Distribution (sorted draws)**")
        sorted_mc = sorted(mc_results)
        step = max(1, len(sorted_mc)//80)
        sampled = sorted_mc[::step]
        html_line_chart(list(range(len(sampled))), sampled, color=ARM_TEAL, height=240,
                        y_label_fmt=lambda v: f"${v:,.0f}M")
    with col_b:
        st.markdown("**Percentile Profile**")
        pct_data = [("P5", mc_s["p5"]), ("P25", mc_s["p25"]), ("Median", mc_s["median"]),
                    ("P75", mc_s["p75"]), ("P95", mc_s["p95"])]
        html_bar_chart(pct_data, color=ARM_AMBER, fmt_func=fmt_m)

    st.markdown("---")
    st.markdown("#### Value-at-Risk (VaR) & CVaR")
    p1 = percentile(mc_results, 1)
    p99 = percentile(mc_results, 99)
    cvar_losses = [v for v in mc_results if v <= p1]
    cvar = sum(cvar_losses)/len(cvar_losses) if cvar_losses else p1
    c1,c2,c3 = st.columns(3)
    c1.metric("P1 (VaR 99%)", fmt_m(p1), delta="Extreme downside")
    c2.metric("CVaR (expected shortfall)", fmt_m(cvar), delta="Avg of worst 1%")
    c3.metric("P99 (upside extreme)", fmt_m(p99))

    st.markdown("---")
    st.markdown("#### Stress Test — Magnitude Sensitivity")
    stress_rows = []
    for mult in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        test_shock = shock_pct * mult
        test_cascade = propagate_cascade(trigger_id, test_shock)
        test_total = sum(calculate_royalty_impact(mid, r["tam_delta_pct"], parsed_horizon)
                         for mid, r in test_cascade.items())
        stress_rows.append([f"×{mult:.2f}", f"{test_shock:+.1f}%", fmt_m(test_total)])
    html_table(["Shock Multiplier","Effective Shock","Total Royalty Impact"], stress_rows)

# ════════════════════════════════════════════════════════════════════════════
# TAB 5: ALL MARKET MODELS & SCENARIOS REFERENCE
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("Unified Simulation Matrix — All 14 Market Models")

    model_rows = []
    for mid, m in MARKET_MODELS.items():
        model_rows.append([
            m["name"], m["category"], m["driver"], fmt_bn(m["tam_2025"]),
            f"{m['cagr']*100:.1f}%", f"{m['attach_2025']*100:.0f}%", f"{m['royalty_pct']:.2f}%"
        ])
    html_table(
        ["Market Model","Category","Core Drivers","2025 TAM","CAGR","Attach Rate","Royalty Rate"],
        model_rows
    )

    st.markdown("---")
    st.markdown("#### Sample Multi-Step Simulation Scenarios (12 pre-built)")
    scen_rows = []
    for sid, s in SAMPLE_SCENARIOS.items():
        scen_rows.append([
            s["name"], MARKET_MODELS[s["trigger"]]["name"], f"{s['shock']:+.1f}%",
            f"{s['horizon']}yr", s["insight"][:80]+("..." if len(s["insight"])>80 else "")
        ])
    html_table(["Scenario","Trigger","Shock","Horizon","Insight"], scen_rows)

    st.markdown("---")
    st.markdown("#### Cross-Market Impact Matrix (26 cascade relationships)")
    link_rows = []
    for trig, imp, w, lag, rel in CASCADE_LINKS:
        link_rows.append([
            MARKET_MODELS[trig]["name"], MARKET_MODELS[imp]["name"],
            f"{w:.2f}", f"{lag}q", rel
        ])
    html_table(["Trigger Model","Impacted Model","Weight","Lag","Relationship"], link_rows)

# Footer
st.markdown("---")
st.caption(
    "FinSight MarketSim · AI- and Quantitative Model-Driven Multi-Layer Semiconductor Market Risk Simulator · "
    "Cascade engine: BFS graph propagation + Monte Carlo uncertainty quantification · "
    "Zero pandas/numpy dependency — all visuals rendered in pure HTML/SVG · "
    "Built by Vibhash — Senior Market Intelligence Analyst, Arm Ltd"
)
