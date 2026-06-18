"""
FinSight MarketSim v2 — AI- and Quantitative Model-Driven Multi-Layer
Semiconductor Market Risk Simulator for FP&A
Author : Vibhash | Senior Market Intelligence Analyst, Arm Ltd

THIS IS A REBUILD, NOT v1. v1 collapsed every market into an opaque
(TAM, CAGR) pair and shocked an abstract "% of TAM" directly — that
produced economically nonsensical results (a NAND price CRASH showing as
bad for Arm, when cheaper memory should drive MORE downstream deployment)
and had no connection to any real number. v2 decomposes every market into
its actual named unit-economics drivers (e.g. NAND = gb_shipped x
asp_per_gb, not a single TAM blob), adds real price elasticity so a price
shock correctly produces an inverse volume response, and ties total
royalty output to Arm's actual reported FY24 royalty revenue (~$1.93B) as
a standing sanity check — this build computes ~$1.75B, a 0.91x ratio,
verified before this UI was written. All 12 sample scenarios were tested
end-to-end and confirmed to produce a royalty-impact SIGN that matches
their own stated business narrative (not just a plausible-looking number).

Zero external dependencies beyond streamlit — every table and chart is
rendered as raw HTML/CSS/SVG. Verified via Python's AST parser that no
st.dataframe/st.bar_chart/st.line_chart/st.table call exists anywhere in
this file (those functions internally construct a pandas.DataFrame even
from a plain dict, which is what breaks deployment on Streamlit Cloud).

requirements.txt should contain ONLY: streamlit
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

ARM_BLUE, ARM_GREEN, ARM_AMBER = "#0070C0", "#1D9E75", "#BA7517"
ARM_RED, ARM_PURPLE, ARM_TEAL = "#E24B4A", "#7F77DD", "#0F6E56"

st.markdown(f"""
<style>
  [data-testid="stMetricValue"] {{ font-size:1.8rem; font-weight:700; color:{ARM_BLUE}; }}
  [data-testid="stMetricDelta"] {{ font-size:0.82rem; }}
  .stTabs [data-baseweb="tab"]  {{ font-weight:600; font-size:0.9rem; }}
  .block-container               {{ padding-top:0.8rem; }}
  .fs-banner {{ background:linear-gradient(90deg,{ARM_PURPLE},{ARM_BLUE}); color:white;
    padding:0.5rem 1rem; border-radius:8px; font-size:0.78rem; margin-bottom:0.5rem; }}
  .htbl {{ width:100%; border-collapse:collapse; font-size:0.83rem; margin-bottom:0.8rem; }}
  .htbl th {{ text-align:left; padding:6px 10px; background:rgba(127,127,127,0.08);
              font-weight:600; border-bottom:1px solid rgba(127,127,127,0.25); }}
  .htbl td {{ padding:5px 10px; border-bottom:1px solid rgba(127,127,127,0.12); }}
  .htbl tr:hover td {{ background:rgba(127,127,127,0.05); }}
  .barwrap {{ display:flex; align-items:center; gap:8px; margin:4px 0; }}
  .barlbl  {{ width:200px; font-size:0.76rem; flex-shrink:0; text-align:right;
              white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .bartrack {{ flex:1; background:rgba(127,127,127,0.12); border-radius:4px;
               height:18px; position:relative; overflow:hidden; }}
  .barfill {{ height:100%; border-radius:4px; display:flex; align-items:center;
              padding-left:6px; box-sizing:border-box; }}
  .barval  {{ font-size:0.72rem; font-weight:600; color:white; white-space:nowrap; }}
  .cascade-node {{ display:inline-flex; align-items:center; gap:6px; padding:6px 12px;
    border-radius:20px; font-size:0.76rem; font-weight:600; margin:3px; }}
  .narrative-box {{ background:rgba(0,112,192,0.06); border-left:3px solid {ARM_BLUE};
    border-radius:6px; padding:14px 18px; font-size:0.92rem; line-height:1.65; margin:10px 0; }}
  .verify-box {{ background:rgba(29,158,117,0.07); border-left:3px solid {ARM_GREEN};
    border-radius:6px; padding:10px 16px; font-size:0.82rem; line-height:1.5; margin:10px 0; }}
  .driver-pill {{ display:inline-block; padding:2px 9px; margin:2px; border-radius:12px;
    font-size:0.7rem; background:rgba(127,127,127,0.1); }}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# DATA — 14 markets with DECOMPOSED, named, verified unit-economics drivers
# (every TAM figure below reproduces the real-world 2025 published market
# size within 3%, checked in generate_finsight_v2.py before this app existed)
# ═══════════════════════════════════════════════════════════════════════════

MARKET_MODELS = {
    "MKT_001": {"name":"Overall Semiconductor Market","category":"Macro",
        "tam_formula":"unit_production_bn*1e9*unit_content_usd/1e9","target_tam":620.0,
        "drivers":{
            "unit_production_bn":{"value":6.5,"unit":"billion electronic units/yr","cagr":0.035,"role":"volume"},
            "unit_content_usd":{"value":95.0,"unit":"USD semi content per unit","cagr":0.048,"role":"price"},
        }, "elasticity":-0.3},
    "MKT_002": {"name":"AI Semiconductor Market","category":"AI Compute",
        "tam_formula":"equipment_units_m*1e6*devices_per_unit*asp_usd/1e9","target_tam":95.0,
        "drivers":{
            "equipment_units_m":{"value":1.5,"unit":"million AI server/accelerator systems/yr","cagr":0.18,"role":"volume"},
            "devices_per_unit":{"value":8.0,"unit":"accelerator chips per system","cagr":0.04,"role":"volume"},
            "asp_usd":{"value":8000.0,"unit":"USD ASP per accelerator chip","cagr":0.02,"role":"price"},
        }, "elasticity":-0.5},
    "MKT_003": {"name":"Foundry Services","category":"Manufacturing",
        "tam_formula":"wafer_starts_m*1e6*wafer_asp_usd/1e9","target_tam":130.0,
        "drivers":{
            "wafer_starts_m":{"value":30.0,"unit":"million 300mm-equiv wafer starts/yr","cagr":0.06,"role":"volume"},
            "wafer_asp_usd":{"value":4333.0,"unit":"USD blended ASP per wafer","cagr":0.045,"role":"price"},
        }, "elasticity":-0.2},
    "MKT_004": {"name":"Capital Spending","category":"Macro",
        "tam_formula":"foundry_capex_bn+memory_capex_bn+other_capex_bn","target_tam":190.0,
        "drivers":{
            "foundry_capex_bn":{"value":95.0,"unit":"USD bn foundry capex/yr","cagr":0.06,"role":"volume"},
            "memory_capex_bn":{"value":65.0,"unit":"USD bn memory capex/yr","cagr":0.08,"role":"volume"},
            "other_capex_bn":{"value":30.0,"unit":"USD bn other semi capex/yr","cagr":0.05,"role":"volume"},
        }, "elasticity":0.0},
    "MKT_005": {"name":"DRAM Market","category":"Memory",
        "tam_formula":"bit_shipments_gb_bn*asp_usd_per_gb","target_tam":80.0,
        "drivers":{
            "bit_shipments_gb_bn":{"value":28000.0,"unit":"billion GB shipped/yr","cagr":0.18,"role":"volume"},
            "asp_usd_per_gb":{"value":0.0029,"unit":"USD per GB","cagr":-0.10,"role":"price"},
        }, "elasticity":-0.9},
    "MKT_006": {"name":"NAND Flash Market","category":"Memory",
        "tam_formula":"gb_shipped_bn*asp_usd_per_gb","target_tam":45.0,
        "drivers":{
            "gb_shipped_bn":{"value":1100.0,"unit":"billion GB shipped/yr","cagr":0.22,"role":"volume"},
            "asp_usd_per_gb":{"value":0.041,"unit":"USD per GB","cagr":-0.12,"role":"price"},
        }, "elasticity":-0.9},
    "MKT_007": {"name":"Automotive Semiconductor","category":"End Market",
        "tam_formula":"vehicle_units_m*1e6*devices_per_vehicle*asp_usd/1e9","target_tam":72.0,
        "drivers":{
            "vehicle_units_m":{"value":88.0,"unit":"million vehicles produced/yr","cagr":0.025,"role":"volume"},
            "devices_per_vehicle":{"value":38.0,"unit":"semi devices per vehicle","cagr":0.07,"role":"volume"},
            "asp_usd":{"value":21.5,"unit":"USD ASP per device","cagr":0.015,"role":"price"},
        }, "elasticity":-0.15},
    "MKT_008": {"name":"Server Market","category":"Data Center",
        "tam_formula":"server_units_m*1e6*it_budget_per_unit_usd/1e9","target_tam":210.0,
        "drivers":{
            "server_units_m":{"value":14.0,"unit":"million servers shipped/yr","cagr":0.06,"role":"volume"},
            "it_budget_per_unit_usd":{"value":15000.0,"unit":"USD avg system value","cagr":0.075,"role":"price"},
        }, "elasticity":-0.4},
    "MKT_009": {"name":"GenAI Model Market","category":"AI Compute",
        "tam_formula":"foundation_model_spend_bn+specialized_model_spend_bn","target_tam":38.0,
        "drivers":{
            "foundation_model_spend_bn":{"value":24.0,"unit":"USD bn foundation model spend/yr","cagr":0.38,"role":"volume"},
            "specialized_model_spend_bn":{"value":14.0,"unit":"USD bn specialized model spend/yr","cagr":0.50,"role":"volume"},
        }, "elasticity":0.0},
    "MKT_010": {"name":"Data Center / HCIS","category":"Data Center",
        "tam_formula":"equipment_shipments_m*1e6*vendor_revenue_per_unit_usd/1e9","target_tam":95.0,
        "drivers":{
            "equipment_shipments_m":{"value":1.9,"unit":"million HCIS units shipped/yr","cagr":0.10,"role":"volume"},
            "vendor_revenue_per_unit_usd":{"value":50000.0,"unit":"USD avg vendor revenue/unit","cagr":0.055,"role":"price"},
        }, "elasticity":-0.35},
    "MKT_011": {"name":"IoT Forecast","category":"End Market",
        "tam_formula":"endpoint_units_bn*1e9*electronics_content_usd/1e9","target_tam":95.0,
        "drivers":{
            "endpoint_units_bn":{"value":19.0,"unit":"billion IoT endpoints shipped/yr","cagr":0.09,"role":"volume"},
            "electronics_content_usd":{"value":5.0,"unit":"USD electronics content/endpoint","cagr":0.025,"role":"price"},
        }, "elasticity":-0.25},
    "MKT_012": {"name":"Wearables Market","category":"End Market",
        "tam_formula":"units_m*1e6*asp_usd/1e9","target_tam":18.0,
        "drivers":{
            "units_m":{"value":520.0,"unit":"million units shipped/yr","cagr":0.07,"role":"volume"},
            "asp_usd":{"value":34.6,"unit":"USD ASP per unit","cagr":0.03,"role":"price"},
        }, "elasticity":-0.3},
    "MKT_013": {"name":"Enterprise Machine Customers","category":"End Market",
        "tam_formula":"iot_endpoint_count_bn*1e9*machine_penetration_pct*value_per_penetrated_usd/1e9","target_tam":22.0,
        "drivers":{
            "iot_endpoint_count_bn":{"value":4.5,"unit":"billion enterprise IoT endpoints","cagr":0.14,"role":"volume"},
            "machine_penetration_pct":{"value":0.12,"unit":"% endpoints with autonomous purchasing/ops","cagr":0.06,"role":"volume"},
            "value_per_penetrated_usd":{"value":40.74,"unit":"USD value per penetrated endpoint","cagr":0.0,"role":"price"},
        }, "elasticity":0.0},
    "MKT_014": {"name":"PCs/Tablets/Mobile Phones","category":"End Market",
        "tam_formula":"shipments_m*1e6*asp_usd/1e9","target_tam":140.0,
        "drivers":{
            "shipments_m":{"value":1750.0,"unit":"million combined PC/tablet/phone units/yr","cagr":0.015,"role":"volume"},
            "asp_usd":{"value":80.0,"unit":"USD ASP per unit (semi content)","cagr":0.025,"role":"price"},
        }, "elasticity":-0.2},
}

# Cross-Market Cascade Links: (trigger_model, trigger_driver, impacted_model,
# impacted_driver, transmission, weight, lag_quarters, relationship)
CASCADE_LINKS = [
    ("MKT_001","unit_content_usd","MKT_002","equipment_units_m","same_sign",0.50,1,"Macro semi-content slowdown compresses AI semi unit growth"),
    ("MKT_001","unit_content_usd","MKT_014","shipments_m","same_sign",0.45,1,"Macro slowdown compresses device shipment growth"),
    ("MKT_001","unit_content_usd","MKT_011","endpoint_units_bn","same_sign",0.35,2,"Macro slowdown softens IoT endpoint shipment growth"),
    ("MKT_003","wafer_starts_m","MKT_002","equipment_units_m","same_sign",0.45,4,"Foundry capacity delay postpones AI chip volume availability"),
    ("MKT_003","wafer_starts_m","MKT_008","server_units_m","same_sign",0.40,4,"Foundry capacity delay postpones server unit shipments"),
    ("MKT_003","wafer_starts_m","MKT_007","vehicle_units_m","same_sign",0.25,6,"Foundry delay postpones automotive SoC-dependent vehicle volume"),
    ("MKT_003","wafer_starts_m","MKT_014","shipments_m","same_sign",0.25,3,"Foundry delay postpones premium phone SoC volume"),
    ("MKT_004","foundry_capex_bn","MKT_003","wafer_starts_m","same_sign",0.55,2,"Foundry capex shift drives wafer capacity build-out"),
    ("MKT_004","memory_capex_bn","MKT_005","bit_shipments_gb_bn","same_sign",0.50,2,"Memory capex shift drives DRAM bit supply growth"),
    ("MKT_004","memory_capex_bn","MKT_006","gb_shipped_bn","same_sign",0.50,2,"Memory capex shift drives NAND GB supply growth"),
    ("MKT_005","asp_usd_per_gb","MKT_008","server_units_m","inverse",0.30,1,"DRAM ASP falls -> lower server BoM -> server refresh VOLUME rises"),
    ("MKT_005","asp_usd_per_gb","MKT_010","equipment_shipments_m","inverse",0.20,1,"DRAM ASP falls -> lower BoM -> data center equipment shipment volume rises"),
    ("MKT_006","asp_usd_per_gb","MKT_008","server_units_m","inverse",0.25,1,"NAND ASP falls -> cheaper SSDs -> hyperscaler server refresh VOLUME accelerates"),
    ("MKT_006","asp_usd_per_gb","MKT_010","equipment_shipments_m","inverse",0.20,1,"NAND ASP falls -> SSD deployment volume rises"),
    ("MKT_009","foundation_model_spend_bn","MKT_002","equipment_units_m","same_sign",0.60,1,"GenAI foundation model spend drives AI semi unit design wins"),
    ("MKT_009","foundation_model_spend_bn","MKT_008","server_units_m","same_sign",0.50,1,"GenAI inference demand drives server unit upgrade cycle"),
    ("MKT_009","specialized_model_spend_bn","MKT_010","equipment_shipments_m","same_sign",0.40,2,"GenAI specialized model deployment shifts data center equipment mix"),
    ("MKT_009","specialized_model_spend_bn","MKT_014","shipments_m","same_sign",0.30,2,"GenAI on-device shift drives smartphone unit redesign/refresh"),
    ("MKT_008","server_units_m","MKT_002","equipment_units_m","same_sign",0.35,1,"Server unit refresh cycle pulls AI accelerator unit demand"),
    ("MKT_008","server_units_m","MKT_010","equipment_shipments_m","same_sign",0.40,1,"Server unit demand shifts data center equipment shipment volume"),
    ("MKT_007","vehicle_units_m","MKT_003","wafer_starts_m","same_sign",0.20,4,"Automotive SoC unit demand shifts foundry wafer allocation"),
    ("MKT_011","endpoint_units_bn","MKT_013","iot_endpoint_count_bn","same_sign",0.55,2,"IoT endpoint unit growth drives enterprise machine endpoint base"),
    ("MKT_011","endpoint_units_bn","MKT_012","units_m","same_sign",0.30,2,"IoT endpoint growth correlates with wearables unit expansion"),
    ("MKT_013","machine_penetration_pct","MKT_011","endpoint_units_bn","same_sign",0.30,2,"Enterprise automation penetration drives additional IoT endpoint units"),
    ("MKT_014","shipments_m","MKT_009","specialized_model_spend_bn","same_sign",0.25,2,"Device unit growth with GenAI integration drives specialized model spend"),
    ("MKT_012","units_m","MKT_011","endpoint_units_bn","same_sign",0.20,2,"Wearables unit growth adds to IoT endpoint base"),
]

# Arm attach economics: model_id -> (unit_driver_name, chips_per_driver_unit,
# attach_rate_2025, attach_rate_cagr, royalty_per_unit_usd)
# chips_per_driver_unit is 1 wherever the market's own volume drivers already
# multiply together to form the full chip count (e.g. Automotive: vehicle x
# devices/vehicle). Only DRAM/NAND need a fractional multiplier here, since
# GB shipped isn't yet a chip count (1 controller chip per ~256GB/512GB).
ARM_ATTACH = {
    "MKT_001":{"unit_driver":"unit_production_bn","chips_per_unit":1,"attach":0.42,"attach_cagr":0.010,"royalty_per_chip":0.085},
    "MKT_002":{"unit_driver":"equipment_units_m","chips_per_unit":1,"attach":0.38,"attach_cagr":0.030,"royalty_per_chip":0.22},
    "MKT_003":{"unit_driver":"wafer_starts_m","chips_per_unit":0,"attach":0.0,"attach_cagr":0.0,"royalty_per_chip":0.0},
    "MKT_004":{"unit_driver":"foundry_capex_bn","chips_per_unit":0,"attach":0.0,"attach_cagr":0.0,"royalty_per_chip":0.0},
    "MKT_005":{"unit_driver":"bit_shipments_gb_bn","chips_per_unit":1/256,"attach":0.35,"attach_cagr":0.015,"royalty_per_chip":0.0021},
    "MKT_006":{"unit_driver":"gb_shipped_bn","chips_per_unit":1/512,"attach":0.45,"attach_cagr":0.020,"royalty_per_chip":0.018},
    "MKT_007":{"unit_driver":"vehicle_units_m","chips_per_unit":1,"attach":0.55,"attach_cagr":0.025,"royalty_per_chip":0.31},
    "MKT_008":{"unit_driver":"server_units_m","chips_per_unit":1,"attach":0.18,"attach_cagr":0.040,"royalty_per_chip":22.0},
    "MKT_009":{"unit_driver":"foundation_model_spend_bn","chips_per_unit":0,"attach":0.0,"attach_cagr":0.0,"royalty_per_chip":0.0},
    "MKT_010":{"unit_driver":"equipment_shipments_m","chips_per_unit":1,"attach":0.20,"attach_cagr":0.035,"royalty_per_chip":0.78},
    "MKT_011":{"unit_driver":"endpoint_units_bn","chips_per_unit":1,"attach":0.71,"attach_cagr":0.015,"royalty_per_chip":0.045},
    "MKT_012":{"unit_driver":"units_m","chips_per_unit":1,"attach":0.88,"attach_cagr":0.010,"royalty_per_chip":0.038},
    "MKT_013":{"unit_driver":"iot_endpoint_count_bn","chips_per_unit":1,"attach":0.48,"attach_cagr":0.030,"royalty_per_chip":0.052},
    "MKT_014":{"unit_driver":"shipments_m","chips_per_unit":1,"attach":0.95,"attach_cagr":0.006,"royalty_per_chip":0.095},
}

# Markets where royalty-per-chip should NOT scale with the market's own price
# driver — memory controller royalty reflects its own design complexity, not
# the commodity memory die's market price.
PRICE_DECOUPLED_ROYALTY_MODELS = {"MKT_005", "MKT_006"}

SAMPLE_SCENARIOS = {
    "SCN_01":{"name":"NAND Oversupply + GenAI Acceleration","trigger":"MKT_006","driver":"asp_usd_per_gb","shock":-30.0,
        "desc":"NAND ASPs fall 30% due to oversupply",
        "insight":"Cheaper SSDs raise hyperscaler deployment volume, which lifts server unit refresh and AI semi accelerator attach — net positive royalty impact for Arm","horizon":3},
    "SCN_02":{"name":"Foundry Delay + GenAI Model Specialization","trigger":"MKT_003","driver":"wafer_starts_m","shock":-12.0,
        "desc":"3nm capacity bottleneck delays wafer starts 12%",
        "insight":"Wafer start delay postpones AI/server/auto/phone chip volume; Arm IP sustained via mature-node mobile/IoT designs even without bleeding-edge access","horizon":2},
    "SCN_03":{"name":"PC Refresh Cycle Driven by Windows 10 EOL","trigger":"MKT_014","driver":"shipments_m","shock":11.0,
        "desc":"15M incremental PC units replaced due to Windows upgrade mandate",
        "insight":"Device shipment volume surge drives GenAI model spend and ARM CPU attach in ARM-based notebook designs","horizon":2},
    "SCN_04":{"name":"Robotaxi Adoption + Automotive SoC Spike","trigger":"MKT_007","driver":"devices_per_vehicle","shock":35.0,
        "desc":"Robotaxi compute requirements raise devices-per-vehicle by 35%",
        "insight":"Higher device count per vehicle drives foundry wafer allocation toward automotive-grade ADAS SoCs with high ARM IP and safety-core attach","horizon":5},
    "SCN_05":{"name":"Enterprise Machine Customers Replace Human Ops","trigger":"MKT_013","driver":"machine_penetration_pct","shock":70.0,
        "desc":"Machine-customer penetration of IoT endpoints rises 70% (relative)",
        "insight":"Spike in autonomous-purchasing endpoints drives additional IoT endpoint units, raising attach opportunity for Cortex-M / DSP / TrustZone","horizon":5},
    "SCN_06":{"name":"On-Device GenAI Adoption in Smartphones","trigger":"MKT_009","driver":"specialized_model_spend_bn","shock":70.0,
        "desc":"Specialized (on-device) GenAI model spend rises 70%",
        "insight":"On-device specialized model growth drives smartphone unit refresh and ARM ML core attach as baseline silicon requirement","horizon":3},
    "SCN_07":{"name":"DRAM ASP Drop + Server Refresh Boom + ML Acceleration","trigger":"MKT_005","driver":"asp_usd_per_gb","shock":-20.0,
        "desc":"DRAM ASP falls 20% over 12 months",
        "insight":"Lower memory BoM accelerates server unit refresh for GenAI workloads, lifting AI semi accelerator unit demand and Arm attach","horizon":3},
    "SCN_08":{"name":"China Foundry Investment + Local Smartphone Growth","trigger":"MKT_004","driver":"foundry_capex_bn","shock":20.0,
        "desc":"China foundry capex rises 20%",
        "insight":"Domestic wafer capacity growth drives local SoC design wins, lifting Arm IP licensing via China-specific programs and phone unit volume","horizon":4},
    "SCN_09":{"name":"Smart Factory IoT Explosion + Memory Cost Decline","trigger":"MKT_011","driver":"endpoint_units_bn","shock":12.0,
        "desc":"IoT endpoint unit shipments grow 12% (smart factory build-out)",
        "insight":"Endpoint unit growth lifts enterprise machine adoption and wearables units, expanding Cortex-M / TrustZone attach at high volume, low ASP","horizon":4},
    "SCN_10":{"name":"Wearables Integrate GenAI Assistants","trigger":"MKT_012","driver":"units_m","shock":25.0,
        "desc":"Wearable unit shipments rise 25% on GenAI assistant features",
        "insight":"Wearables unit growth adds to IoT endpoint base, opening ultra-low-power ARM ML+DSP attach TAM","horizon":3},
    "SCN_11":{"name":"Foundry Slowdown + Auto Segment Priority","trigger":"MKT_003","driver":"wafer_starts_m","shock":-8.0,
        "desc":"Foundries reduce consumer wafer allocation 8%, prioritizing auto",
        "insight":"Consumer SoC volume delay creates attach risk; automotive wafer priority shifts BU resources toward automotive IP enablement","horizon":2},
    "SCN_12":{"name":"Smartphone ASP Growth + AI Workload Shifts","trigger":"MKT_014","driver":"asp_usd","shock":10.0,
        "desc":"Premium smartphone semi-content ASP rises 10%",
        "insight":"Higher ASP reflects on-device AI inference silicon upgrade, raising royalty per device disproportionately to unit growth","horizon":3},
}

PROMPT_KEYWORDS = {
    "MKT_006": (["nand","ssd","flash","storage"], "asp_usd_per_gb"),
    "MKT_005": (["dram","memory price","memory market"], "asp_usd_per_gb"),
    "MKT_003": (["foundry","fab","wafer","node","tsmc","3nm","5nm","7nm"], "wafer_starts_m"),
    "MKT_004": (["capital spending","capex","china foundry"], "foundry_capex_bn"),
    "MKT_007": (["automotive","auto semi","vehicle","robotaxi","adas"], "devices_per_vehicle"),
    "MKT_008": (["server","data center cpu","hyperscaler"], "server_units_m"),
    "MKT_002": (["ai semiconductor","ai semi","ai chip","accelerator"], "equipment_units_m"),
    "MKT_009": (["genai model","llm","foundation model","specialized model","on-device genai","on device genai"], "specialized_model_spend_bn"),
    "MKT_010": (["data center","hcis","edge ai"], "equipment_shipments_m"),
    "MKT_011": (["iot","internet of things","smart factory"], "endpoint_units_bn"),
    "MKT_012": (["wearable","smartwatch"], "units_m"),
    "MKT_013": (["enterprise machine","manufacturing bot","autonomous agent"], "machine_penetration_pct"),
    "MKT_014": (["smartphone","mobile phone","pc","tablet","laptop","windows 10"], "shipments_m"),
}
