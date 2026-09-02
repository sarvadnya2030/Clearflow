#!/usr/bin/env python3
"""
ClearFlow Observability Dashboard v2.0
Live command center: 8 services · Elasticsearch · Prometheus · MCP · Docker
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

st.set_page_config(
    page_title="ClearFlow Command Center",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Inject dark theme CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background-color: #0d1117; color: #e6edf3; }
  section[data-testid="stSidebar"] { background-color: #161b22; }
  div[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 700; }
  div[data-testid="stMetricLabel"] { font-size: 0.75rem; color: #8b949e; }
  .service-chip {
    display: inline-block; padding: 6px 14px; border-radius: 20px;
    font-size: 0.8rem; font-weight: 600; margin: 4px;
  }
  .chip-up   { background: #0d3b27; color: #3fb950; border: 1px solid #3fb950; }
  .chip-down { background: #3b0d0d; color: #f85149; border: 1px solid #f85149; }
  .alert-high   { background: #3b1f0d; border-left: 3px solid #f0883e; padding: 8px 12px; border-radius: 4px; margin: 4px 0; }
  .alert-medium { background: #2d2208; border-left: 3px solid #d29922; padding: 8px 12px; border-radius: 4px; margin: 4px 0; }
  .kpi-box {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 18px 16px; text-align: center;
  }
  .kpi-num   { font-size: 2rem; font-weight: 700; color: #58a6ff; }
  .kpi-label { font-size: 0.75rem; color: #8b949e; margin-top: 4px; }
  .kpi-sub   { font-size: 0.7rem; color: #3fb950; margin-top: 2px; }
  div[data-testid="stDataFrameResizable"] { background: #161b22 !important; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ─────────────────────────────────────────────────────────────────
ES   = "http://localhost:9200"
MCP  = "http://localhost:8087"
PROM = "http://localhost:9090"

SERVICES = {
    "gateway":               8080,
    "fraud-scoring":         8081,
    "validation-enrichment": 8082,
    "aml-compliance":        8083,
    "routing-execution":     8084,
    "settlement":            8085,
    "audit":                 8086,
    "mcp-readonly-gateway":  8087,
}

SERVICE_EMOJI = {
    "gateway":               "🚪",
    "fraud-scoring":         "🔍",
    "validation-enrichment": "✅",
    "aml-compliance":        "🛡️",
    "routing-execution":     "🔀",
    "settlement":            "💰",
    "audit":                 "📋",
    "mcp-readonly-gateway":  "🤖",
}

ISO2_TO_ISO3 = {
    "US":"USA","GB":"GBR","DE":"DEU","FR":"FRA","NL":"NLD","CH":"CHE","SG":"SGP",
    "JP":"JPN","AU":"AUS","CA":"CAN","CN":"CHN","RU":"RUS","IR":"IRN","KP":"PRK",
    "BR":"BRA","IN":"IND","ZA":"ZAF","MX":"MEX","AR":"ARG","AE":"ARE","SA":"SAU",
    "TR":"TUR","KR":"KOR","ID":"IDN","PL":"POL","IT":"ITA","ES":"ESP","SE":"SWE",
    "NO":"NOR","DK":"DNK","BE":"BEL","AT":"AUT","PT":"PRT","IE":"IRL","HK":"HKG",
    "NG":"NGA","KE":"KEN","EG":"EGY","PK":"PAK","BD":"BGD","TH":"THA","MY":"MYS",
    "VN":"VNM","PH":"PHL","NZ":"NZL","UA":"UKR","RO":"ROU","CZ":"CZE","HU":"HUN",
    "GR":"GRC","FI":"FIN","SK":"SVK","HR":"HRV","BG":"BGR","LT":"LTU","LV":"LVA",
}

PIPELINE_STAGES = [
    "Gateway", "Fraud Scoring", "Validation", "AML Compliance",
    "Routing", "Settlement", "Audit",
]

# ─── Data helpers ──────────────────────────────────────────────────────────────

def _es(index, body, timeout=5):
    try:
        r = requests.post(f"{ES}/{index}/_search", json=body,
                          headers={"Content-Type":"application/json"}, timeout=timeout)
        return r.json() if r.ok else {}
    except Exception:
        return {}

def _prom(q, timeout=5):
    try:
        r = requests.get(f"{PROM}/api/v1/query", params={"query": q}, timeout=timeout)
        d = r.json()
        return d["data"]["result"] if d.get("status") == "success" else []
    except Exception:
        return []

def _prom_val(q, default=0.0):
    res = _prom(q)
    if res:
        try:
            return float(res[0]["value"][1])
        except Exception:
            pass
    return default

def _prom_range(q, minutes=30, step="30s", timeout=10):
    end   = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    try:
        r = requests.get(f"{PROM}/api/v1/query_range", timeout=timeout, params={
            "query": q, "start": start.timestamp(),
            "end": end.timestamp(), "step": step,
        })
        d = r.json()
        return d["data"]["result"] if d.get("status") == "success" else []
    except Exception:
        return []

def _mcp(path, timeout=5):
    try:
        r = requests.get(f"{MCP}{path}", timeout=timeout)
        return r.json() if r.ok else {}
    except Exception:
        return {}

# ─── Cached data functions ─────────────────────────────────────────────────────

@st.cache_data(ttl=8)
def svc_health():
    out = {}
    for name, port in SERVICES.items():
        try:
            r = requests.get(f"http://localhost:{port}/actuator/health", timeout=2)
            d = r.json()
            out[name] = {"status": d.get("status","UNKNOWN"), "port": port, "up": r.ok}
        except Exception:
            out[name] = {"status": "DOWN", "port": port, "up": False}
    return out

@st.cache_data(ttl=15)
def prom_counters():
    queries = {
        "initiated":   "sum(clearflow_payments_total)",
        "fraud_scored":"sum(clearflow_fraud_scored_total)",
        "val_accepted":"sum(clearflow_validation_accepted_total)",
        "val_rejected":"sum(clearflow_validation_rejected_total)",
        "aml_clear":   "sum(clearflow_aml_clear_total)",
        "aml_hit":     "sum(clearflow_aml_hit_total)",
        "routed":      "sum(clearflow_routing_routed_total)",
        "route_fail":  "sum(clearflow_routing_failed_total)",
        "settled":     "sum(clearflow_settlements_total)",
        "audit_fail":  "sum(clearflow_audit_save_failures_total)",
        "inflight":    "clearflow_gateway_inflight",
    }
    return {k: _prom_val(q) for k, q in queries.items()}

@st.cache_data(ttl=20)
def es_summary():
    body = {
        "size": 0,
        "query": {"range": {"@timestamp": {"gte": "now-1h"}}},
        "aggs": {
            "by_service": {"terms": {"field": "service.keyword", "size": 20}},
            "by_level":   {"terms": {"field": "level.keyword", "size": 10}},
            "per_minute": {"date_histogram": {"field": "@timestamp",
                                               "calendar_interval": "1m",
                                               "min_doc_count": 0,
                                               "extended_bounds": {"min": "now-60m", "max": "now"}}},
        }
    }
    r = _es("clearflow-*", body)
    aggs = r.get("aggregations", {})
    return {
        "total":       r.get("hits", {}).get("total", {}).get("value", 0),
        "by_service":  {b["key"]: b["doc_count"] for b in aggs.get("by_service",{}).get("buckets",[])},
        "by_level":    {b["key"]: b["doc_count"] for b in aggs.get("by_level",{}).get("buckets",[])},
        "per_minute":  [{"t": b["key_as_string"], "n": b["doc_count"]}
                        for b in aggs.get("per_minute",{}).get("buckets",[])],
    }

@st.cache_data(ttl=20)
def fraud_geo():
    body = {
        "size": 0,
        "query": {
            "bool": {"should": [
                {"terms": {"riskBand.keyword": ["CRITICAL","HIGH"]}},
                {"term":  {"level.keyword": "ERROR"}},
            ], "minimum_should_match": 1}
        },
        "aggs": {
            "debtor_country":  {"terms": {"field": "debtorCountry.keyword",  "size": 60}},
            "creditor_country":{"terms": {"field": "creditorCountry.keyword", "size": 60}},
            "risk_band":       {"terms": {"field": "riskBand.keyword",        "size": 10}},
            "over_time":       {"date_histogram": {"field": "@timestamp",
                                                    "calendar_interval": "5m",
                                                    "min_doc_count": 1}},
        }
    }
    r = _es("clearflow-*", body)
    aggs = r.get("aggregations", {})
    return {
        "by_debtor":   {b["key"]: b["doc_count"] for b in aggs.get("debtor_country",{}).get("buckets",[])},
        "by_creditor": {b["key"]: b["doc_count"] for b in aggs.get("creditor_country",{}).get("buckets",[])},
        "by_risk":     {b["key"]: b["doc_count"] for b in aggs.get("risk_band",{}).get("buckets",[])},
        "over_time":   [{"t": b["key_as_string"], "n": b["doc_count"]}
                        for b in aggs.get("over_time",{}).get("buckets",[])],
    }

@st.cache_data(ttl=10)
def recent_payments(n=50):
    body = {
        "size": n,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {"exists": {"field": "paymentId"}},
        "_source": ["@timestamp","service","level","paymentId","correlationId",
                    "debtorCountry","creditorCountry","amount","currency","riskBand",
                    "fraudScore","rail","durationMs","message"],
    }
    r = _es("clearflow-*", body)
    return [h["_source"] for h in r.get("hits",{}).get("hits",[])]

@st.cache_data(ttl=10)
def recent_alerts(n=30):
    body = {
        "size": n,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {
            "bool": {"should": [
                {"term": {"level.keyword": "ERROR"}},
                {"term": {"alert_level.keyword": "HIGH"}},
            ], "minimum_should_match": 1}
        },
        "_source": ["@timestamp","service","level","paymentId","message","alert_level"],
    }
    r = _es("clearflow-*", body)
    return [h["_source"] for h in r.get("hits",{}).get("hits",[])]

@st.cache_data(ttl=10)
def security_events(n=50):
    body = {
        "size": n,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "_source": ["@timestamp","service","level","paymentId","message",
                    "siem_severity","eventType","riskBand","screeningResult","matchScore"],
    }
    r = _es("clearflow-security-*", body)
    return [h["_source"] for h in r.get("hits",{}).get("hits",[])]

@st.cache_data(ttl=15)
def latency_data():
    services = {
        "gateway":   "http://localhost:8080/actuator/prometheus",
        "fraud":     "http://localhost:8081/actuator/prometheus",
        "validation":"http://localhost:8082/actuator/prometheus",
        "aml":       "http://localhost:8083/actuator/prometheus",
        "routing":   "http://localhost:8084/actuator/prometheus",
        "settlement":"http://localhost:8085/actuator/prometheus",
        "audit":     "http://localhost:8086/actuator/prometheus",
    }
    rows = []
    for svc, url in services.items():
        try:
            r = requests.get(url, timeout=3)
            if r.ok:
                for line in r.text.splitlines():
                    if line.startswith("http_server_requests_seconds_max{") or \
                       "http_server_requests_seconds_count{" in line:
                        rows.append({"service": svc, "raw": line})
        except Exception:
            pass
    return rows

@st.cache_data(ttl=30)
def es_index_stats():
    try:
        r = requests.get(f"{ES}/clearflow-*/_stats/docs,store", timeout=5)
        if r.ok:
            indices = r.json().get("indices", {})
            rows = []
            for idx, data in sorted(indices.items()):
                docs  = data["primaries"]["docs"]["count"]
                size  = data["primaries"]["store"]["size_in_bytes"]
                rows.append({"Index": idx, "Docs": f"{docs:,}",
                             "Size": f"{size/1024/1024:.1f} MB"})
            return rows
    except Exception:
        pass
    return []

@st.cache_data(ttl=30)
def kafka_topics():
    try:
        r = subprocess.run(
            ["docker", "compose", "-f",
             "/home/admin-/Desktop/EDI6/clearflow/infrastructure/docker-compose.yml",
             "exec", "-T", "kafka", "kafka-topics",
             "--bootstrap-server", "kafka:9092", "--list"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            return [t.strip() for t in r.stdout.strip().split("\n") if t.strip()]
    except Exception:
        pass
    return []

@st.cache_data(ttl=20)
def docker_containers():
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            capture_output=True, text=True, timeout=5
        )
        rows = []
        for line in r.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                name   = parts[0]
                status = parts[1]
                image  = parts[2] if len(parts) > 2 else ""
                up = "Up" in status
                rows.append({"name": name, "status": status, "image": image, "up": up})
        return rows
    except Exception:
        return []

@st.cache_data(ttl=15)
def mcp_overview():
    return _mcp("/mcp/metrics/overview")

@st.cache_data(ttl=15)
def mcp_rails():
    return _mcp("/mcp/metrics/rails")

@st.cache_data(ttl=15)
def mcp_fraud():
    return _mcp("/mcp/metrics/fraud")

@st.cache_data(ttl=60)
def get_forecast():
    return _mcp("/mcp/forecast/settlement?horizonHours=24")

@st.cache_data(ttl=30)
def get_uetr_anomalies(window: int):
    return _mcp(f"/mcp/anomalies/uetr?windowMinutes={window}")

# ─── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💳 ClearFlow")
    st.markdown("**ISO 20022 Intelligence**")
    st.divider()

    page = st.radio("", [
        "🎯  Command Center",
        "🌊  Payment Flow",
        "🔍  Fraud & AML",
        "⚡  Performance",
        "🚨  Security Events",
        "🏗️  Infrastructure",
        "🔮  Forecast",
        "📡  Live Boards",
        "🤖  AI Assistant",
    ], label_visibility="collapsed")

    st.divider()
    auto_refresh = st.toggle("Auto-refresh (30s)", value=False)
    if st.button("⟳  Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}")

# Auto-refresh via JS injection
if auto_refresh:
    st.components.v1.html(
        '<script>setTimeout(() => window.parent.location.reload(), 30000);</script>',
        height=0
    )

# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 1 — COMMAND CENTER
# ─────────────────────────────────────────────────────────────────────────────
if "Command Center" in page:
    st.title("🎯 ClearFlow Command Center")

    health   = svc_health()
    counters = prom_counters()
    summary  = es_summary()

    # ── Service health chips ──────────────────────────────────────────────────
    chips = ""
    for name, info in health.items():
        cls  = "chip-up" if info["up"] else "chip-down"
        icon = "●" if info["up"] else "✗"
        label = SERVICE_EMOJI.get(name, "") + " " + name.replace("-", " ").title()
        chips += f'<span class="service-chip {cls}">{icon} {label}</span>'
    st.markdown(chips, unsafe_allow_html=True)

    up_count = sum(1 for i in health.values() if i["up"])
    if up_count == len(SERVICES):
        st.success(f"All {len(SERVICES)} services UP", icon="✅")
    elif up_count == 0:
        st.error("All services DOWN — run `bash start_live_traffic.sh`", icon="🔴")
    else:
        st.warning(f"{up_count}/{len(SERVICES)} services UP", icon="⚠️")

    st.divider()

    # ── KPI row ───────────────────────────────────────────────────────────────
    total     = int(counters.get("initiated", 0))
    settled   = int(counters.get("settled", 0))
    aml_hit   = int(counters.get("aml_hit", 0))
    route_fail= int(counters.get("route_fail", 0))
    inflight  = int(counters.get("inflight", 0))
    settle_rt = f"{settled/total*100:.1f}%" if total > 0 else "—"

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Payments",   f"{total:,}",     "all time")
    k2.metric("Settlement Rate",  settle_rt,         f"{settled:,} settled")
    k3.metric("AML Hits",         f"{aml_hit:,}",   "🚨 blocked" if aml_hit else "✓ none")
    k4.metric("Routing Failures", f"{route_fail:,}", "⚠️ check" if route_fail else "✓ ok")
    k5.metric("In-Flight Now",    f"{inflight:,}",   "live")

    st.divider()

    col_left, col_right = st.columns([3, 2])

    with col_left:
        # ── Sankey ────────────────────────────────────────────────────────────
        st.subheader("Payment Pipeline Flow")
        initiated  = max(total, 1)
        fraud_sc   = int(counters.get("fraud_scored", 0))
        val_ok     = int(counters.get("val_accepted", 0))
        val_rej    = int(counters.get("val_rejected", 0))
        aml_ok     = int(counters.get("aml_clear", 0))
        routed     = int(counters.get("routed", 0))

        have_prom = initiated > 1
        if not have_prom:
            # Demo values so graph always renders
            initiated=1000; fraud_sc=1000; val_ok=950; val_rej=50
            aml_ok=900; aml_hit=50; routed=880; route_fail=20; settled=860
        else:
            aml_hit = int(counters.get("aml_hit", 0))
            route_fail = int(counters.get("route_fail", 0))

        labels = ["Gateway","Fraud","Validated","❌ Rejected","AML Clear",
                  "🚨 AML Hit","Routing","⚠️ Route Fail","Settled"]
        colors = ["#58a6ff","#3fb950","#3fb950","#f85149",
                  "#3fb950","#f0883e","#3fb950","#f0883e","#3fb950"]
        link_colors = [
            "rgba(88,166,255,0.3)","rgba(63,185,80,0.3)","rgba(63,185,80,0.3)",
            "rgba(248,81,73,0.3)","rgba(63,185,80,0.3)","rgba(240,136,62,0.3)",
            "rgba(63,185,80,0.3)","rgba(240,136,62,0.3)"
        ]
        fig_sankey = go.Figure(go.Sankey(
            arrangement="snap",
            node=dict(label=labels, color=colors, pad=18, thickness=24,
                      line=dict(color="rgba(0,0,0,0)", width=0)),
            link=dict(
                source=[0,1,2,2,3,3,4,4],
                target=[1,2,3,7,4,5,6,7],  # note: index 7=route_fail here, shifted
                value =[fraud_sc, val_ok+val_rej, val_ok, val_rej,
                        aml_ok, aml_hit, routed, route_fail],
                color=link_colors,
            )
        ))
        # Fix label indices: 0=Gateway,1=Fraud,2=Validated,3=❌Rejected,
        #                    4=AML Clear,5=🚨AML Hit,6=Routing,7=⚠️Route Fail,8=Settled
        fig_sankey = go.Figure(go.Sankey(
            arrangement="snap",
            node=dict(
                label=["Gateway","Fraud","Validated","❌ Rejected",
                       "AML Clear","🚨 AML Hit","Routing","⚠️ Route Fail","Settled"],
                color=["#58a6ff","#3fb950","#3fb950","#f85149",
                       "#3fb950","#f0883e","#3fb950","#f0883e","#3fb950"],
                pad=18, thickness=24,
            ),
            link=dict(
                source=[0,1,2,2,3,3,6,6],
                target=[1,2,3,3,4,5,8,7],
                value =[fraud_sc, val_ok+val_rej, val_ok, val_rej,
                        aml_ok, aml_hit, settled, route_fail],
                color=["rgba(88,166,255,0.3)","rgba(63,185,80,0.3)","rgba(63,185,80,0.3)",
                       "rgba(248,81,73,0.3)","rgba(63,185,80,0.3)","rgba(240,136,62,0.3)",
                       "rgba(63,185,80,0.3)","rgba(240,136,62,0.3)"],
            )
        ))
        fig_sankey.update_layout(
            height=340,
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3", size=13),
            margin=dict(t=10, b=10, l=10, r=10),
        )
        st.plotly_chart(fig_sankey, use_container_width=True)
        if not have_prom:
            st.caption("⚠️ No Prometheus data — showing demo values. Start services and send payments.")

    with col_right:
        # ── Stage completion table ─────────────────────────────────────────────
        st.subheader("Stage Completion")
        base = max(total, 1)
        stage_rows = [
            ("🚪 Gateway",     total,    100.0),
            ("🔍 Fraud",       fraud_sc, fraud_sc/base*100  if total else 0),
            ("✅ Validated",   val_ok,   val_ok/base*100    if total else 0),
            ("🛡️ AML Clear",  aml_ok,   aml_ok/base*100    if total else 0),
            ("🔀 Routed",      routed,   routed/base*100    if total else 0),
            ("💰 Settled",     settled,  settled/base*100   if total else 0),
        ]
        df_stages = pd.DataFrame(stage_rows, columns=["Stage","Count","Rate%"])
        df_stages["Rate%"] = df_stages["Rate%"].map(lambda x: f"{x:.1f}%")
        if total:
            df_stages["Count"] = df_stages["Count"].map(lambda x: f"{x:,}")
        st.dataframe(df_stages, use_container_width=True, hide_index=True,
                     column_config={"Rate%": st.column_config.TextColumn(width="small")})

        st.divider()
        # ── Rejection breakdown ────────────────────────────────────────────────
        st.subheader("Rejections")
        rej_data = [("AML Hit", aml_hit), ("Route Fail", route_fail),
                    ("Validation", val_rej), ("Audit Errors", int(counters.get("audit_fail",0)))]
        rej_data = [(k, v) for k, v in rej_data if v > 0]
        if rej_data:
            df_rej = pd.DataFrame(rej_data, columns=["Reason","Count"])
            fig_rej = px.pie(df_rej, values="Count", names="Reason",
                             color_discrete_sequence=["#f85149","#f0883e","#d29922","#58a6ff"],
                             hole=0.45)
            fig_rej.update_layout(height=220, showlegend=True,
                                   paper_bgcolor="rgba(0,0,0,0)",
                                   font=dict(color="#e6edf3"),
                                   margin=dict(t=0,b=0,l=0,r=0))
            st.plotly_chart(fig_rej, use_container_width=True)
        else:
            st.info("No rejection data yet")

    st.divider()

    # ── Log throughput ────────────────────────────────────────────────────────
    st.subheader("Log Throughput — Last 60 Minutes")
    pts = summary.get("per_minute", [])
    if pts:
        df_tp = pd.DataFrame(pts)
        df_tp["t"] = pd.to_datetime(df_tp["t"])
        fig_tp = px.area(df_tp, x="t", y="n",
                         color_discrete_sequence=["#58a6ff"],
                         labels={"n": "events/min", "t": ""})
        fig_tp.update_layout(height=180, showlegend=False,
                              paper_bgcolor="rgba(0,0,0,0)",
                              plot_bgcolor="rgba(0,0,0,0)",
                              margin=dict(t=10,b=10,l=10,r=10),
                              xaxis=dict(showgrid=False),
                              yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
        fig_tp.update_traces(fillcolor="rgba(88,166,255,0.15)", line_width=2)
        st.plotly_chart(fig_tp, use_container_width=True)
    else:
        st.info("No log throughput data — services must be running with Logstash pipeline active")

    # ── Recent alerts ─────────────────────────────────────────────────────────
    st.subheader("Recent Alerts")
    alerts = recent_alerts(15)
    if alerts:
        for a in alerts[:8]:
            svc  = a.get("service", a.get("SERVICE_NAME", "unknown"))
            msg  = a.get("message","")[:140]
            ts   = a.get("@timestamp","")[:19].replace("T"," ")
            lvl  = a.get("level","")
            cls  = "alert-high" if lvl == "ERROR" else "alert-medium"
            pid  = a.get("paymentId","")
            pid_str = f" | pid:{pid}" if pid else ""
            st.markdown(
                f'<div class="{cls}"><b>{svc}</b> <span style="color:#8b949e;font-size:0.75rem">{ts}{pid_str}</span><br>{msg}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.success("✓ No errors in the last hour")


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 2 — PAYMENT FLOW
# ─────────────────────────────────────────────────────────────────────────────
elif "Payment Flow" in page:
    st.title("🌊 Live Payment Flow")

    tab_live, tab_trace = st.tabs(["📊 Live Funnel", "🔎 Trace a Payment"])

    with tab_live:
        counters = prom_counters()
        total = int(counters.get("initiated", 0))

        st.subheader("Pipeline Stage Volume")
        stages = [
            ("Gateway Accepted",   total),
            ("Fraud Scored",       int(counters.get("fraud_scored",0))),
            ("Validation Passed",  int(counters.get("val_accepted",0))),
            ("AML Cleared",        int(counters.get("aml_clear",0))),
            ("Successfully Routed",int(counters.get("routed",0))),
            ("Settled",            int(counters.get("settled",0))),
        ]
        df_funnel = pd.DataFrame(stages, columns=["Stage","Count"])
        if total > 0:
            df_funnel["Pass Rate"] = (df_funnel["Count"]/total*100).map(lambda x: f"{x:.1f}%")
        else:
            df_funnel["Pass Rate"] = "—"

        fig_funnel = go.Figure(go.Funnel(
            y=df_funnel["Stage"],
            x=df_funnel["Count"],
            textposition="inside",
            textinfo="value+percent initial",
            marker=dict(color=["#58a6ff","#3fb950","#3fb950","#3fb950","#3fb950","#a371f7"]),
            connector=dict(line=dict(color="rgba(255,255,255,0.1)", width=1)),
        ))
        fig_funnel.update_layout(
            height=380, paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(t=10,b=10,l=140,r=10),
        )
        st.plotly_chart(fig_funnel, use_container_width=True)

        st.divider()
        st.subheader("Recent Payment Activity")
        pmts = recent_payments(30)
        if pmts:
            df_pmts = pd.DataFrame(pmts)
            cols_want = ["@timestamp","paymentId","service","level","amount","currency",
                         "debtorCountry","creditorCountry","riskBand","rail"]
            cols_have = [c for c in cols_want if c in df_pmts.columns]
            df_pmts = df_pmts[cols_have].rename(columns={
                "@timestamp":"Time","paymentId":"Payment ID","service":"Service",
                "level":"Level","debtorCountry":"From","creditorCountry":"To"
            })
            if "Time" in df_pmts.columns:
                df_pmts["Time"] = pd.to_datetime(df_pmts["Time"]).dt.strftime("%H:%M:%S")
            st.dataframe(df_pmts, use_container_width=True, hide_index=True,
                         height=400)
        else:
            st.info("No recent payment logs found in Elasticsearch")

    with tab_trace:
        st.subheader("Trace Individual Payment Journey")
        payment_id = st.text_input("Payment ID", placeholder="e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6")

        if payment_id:
            with st.spinner("Fetching timeline from MCP gateway..."):
                timeline = _mcp(f"/mcp/payments/{payment_id}/timeline")
                risk     = _mcp(f"/mcp/payments/{payment_id}/risk")
                compliance = _mcp(f"/mcp/payments/{payment_id}/compliance")

            col_tl, col_rf = st.columns([2,1])

            with col_tl:
                st.markdown("#### Timeline")
                if timeline and isinstance(timeline, dict):
                    events = timeline.get("events", timeline.get("stages", []))
                    if events:
                        for ev in events:
                            ts  = ev.get("timestamp","")[:19].replace("T"," ")
                            svc = ev.get("service","")
                            msg = ev.get("message","")[:120]
                            lvl = ev.get("level","INFO")
                            icon = "✅" if lvl in ("INFO","DEBUG") else "❌"
                            st.markdown(
                                f'<div class="alert-medium"><b>{icon} {svc}</b> <span style="color:#8b949e">{ts}</span><br>{msg}</div>',
                                unsafe_allow_html=True
                            )
                    else:
                        st.json(timeline)
                elif timeline:
                    st.json(timeline)
                else:
                    # Fallback: query ES directly
                    body = {
                        "size": 20,
                        "sort": [{"@timestamp": {"order": "asc"}}],
                        "query": {"term": {"paymentId.keyword": payment_id}},
                        "_source": ["@timestamp","service","level","message","riskBand","rail","durationMs"],
                    }
                    r = _es("clearflow-*", body)
                    hits = [h["_source"] for h in r.get("hits",{}).get("hits",[])]
                    if hits:
                        for h in hits:
                            ts  = h.get("@timestamp","")[:19].replace("T","")
                            svc = h.get("service","?")
                            msg = h.get("message","")[:100]
                            lvl = h.get("level","INFO")
                            icon = "✅" if lvl not in ("ERROR","WARN") else "⚠️"
                            st.markdown(
                                f'<div class="alert-medium">{icon} <b>{svc}</b> <span style="color:#8b949e">{ts}</span><br>{msg}</div>',
                                unsafe_allow_html=True
                            )
                    else:
                        st.warning(f"No logs found for payment ID `{payment_id}`")

            with col_rf:
                st.markdown("#### Fraud Risk")
                if risk and isinstance(risk, dict):
                    fraud_events = risk.get("fraudEvents", [])
                    if fraud_events:
                        fe = fraud_events[0]
                        score = fe.get("fraudScore", "?")
                        band  = fe.get("riskBand", "?")
                        color = "#f85149" if band in ("CRITICAL","HIGH") else "#3fb950"
                        st.markdown(
                            f'<div class="kpi-box"><div class="kpi-num" style="color:{color}">{score}</div>'
                            f'<div class="kpi-label">Fraud Score</div>'
                            f'<div class="kpi-sub">{band}</div></div>',
                            unsafe_allow_html=True
                        )
                    elif risk.get("fraudCacheEntry"):
                        st.code(risk["fraudCacheEntry"])
                    else:
                        st.info("No fraud data")
                else:
                    st.info("MCP not available — check JWT config")

                st.markdown("#### AML Compliance")
                if compliance and isinstance(compliance, dict):
                    aml_events = compliance.get("amlEvents", [])
                    if aml_events:
                        ae = aml_events[0]
                        result = ae.get("screeningResult","?")
                        match  = ae.get("matchScore","?")
                        hit    = ae.get("listHit","?")
                        color  = "#f85149" if result == "HIT" else "#3fb950"
                        st.markdown(
                            f'<div class="kpi-box"><div class="kpi-num" style="color:{color}">{result}</div>'
                            f'<div class="kpi-label">AML Result</div>'
                            f'<div class="kpi-sub">match:{match} | hit:{hit}</div></div>',
                            unsafe_allow_html=True
                        )
                    else:
                        st.info("No AML data")
                else:
                    st.info("MCP not available")
        else:
            # Show recent payment IDs to pick from
            st.markdown("**Recent payment IDs you can trace:**")
            pmts = recent_payments(20)
            if pmts:
                ids = list({p.get("paymentId") for p in pmts if p.get("paymentId")})[:10]
                for pid in ids:
                    st.code(pid, language=None)
            else:
                st.info("Send payments first: `python3 live_payment_sender.py`")


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 3 — FRAUD & AML
# ─────────────────────────────────────────────────────────────────────────────
elif "Fraud" in page:
    st.title("🔍 Fraud & AML Intelligence")

    geo     = fraud_geo()
    counters = prom_counters()

    # ── Top row KPIs ──────────────────────────────────────────────────────────
    aml_hit  = int(counters.get("aml_hit",  0))
    aml_ok   = int(counters.get("aml_clear",0))
    total    = int(counters.get("initiated",0))
    aml_rate = aml_hit / (aml_hit + aml_ok) * 100 if (aml_hit + aml_ok) > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("AML Hits",       f"{aml_hit:,}",   "blocked")
    k2.metric("AML Hit Rate",   f"{aml_rate:.2f}%","of screened")
    k3.metric("High-Risk Logs", f"{sum(geo['by_risk'].values()):,}", "CRITICAL+HIGH")
    k4.metric("Countries Seen", f"{len(geo['by_debtor']):,}",       "unique debtors")

    st.divider()

    # ── Choropleth — Fraud origin by debtor country ───────────────────────────
    st.subheader("Fraud Origin Heatmap — Debtor Country")
    debtor_raw = geo.get("by_debtor", {})

    if debtor_raw:
        map_data = []
        for code2, cnt in debtor_raw.items():
            code3 = ISO2_TO_ISO3.get(code2.upper())
            if code3:
                map_data.append({"iso3": code3, "country": code2, "count": cnt})
        if map_data:
            df_map = pd.DataFrame(map_data)
            fig_map = px.choropleth(
                df_map, locations="iso3", color="count",
                hover_name="country", hover_data={"iso3": False},
                color_continuous_scale=[[0,"#0d3b27"],[0.3,"#1a7a3a"],[0.6,"#d29922"],[1.0,"#f85149"]],
                labels={"count": "High-Risk Events"},
                projection="natural earth",
            )
            fig_map.update_layout(
                height=400, paper_bgcolor="#0d1117",
                geo=dict(bgcolor="#0d1117", showland=True, landcolor="#21262d",
                         showocean=True, oceancolor="#0d1117",
                         showcoastlines=True, coastlinecolor="#30363d",
                         showframe=False),
                coloraxis_colorbar=dict(tickfont=dict(color="#e6edf3"),
                                        titlefont=dict(color="#e6edf3")),
                margin=dict(t=10,b=10,l=0,r=0),
            )
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("Country codes not mappable — check if debtorCountry MDC field is populated")
    else:
        st.info("No fraud geo data yet — process payments with debtor/creditor countries set")

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        # ── Risk band distribution ─────────────────────────────────────────────
        st.subheader("Risk Band Distribution")
        risk_data = geo.get("by_risk", {})
        mcp_fraud_data = mcp_fraud()
        if mcp_fraud_data and isinstance(mcp_fraud_data, dict):
            # Prefer MCP histogram if available
            hist = mcp_fraud_data.get("histogram", mcp_fraud_data.get("riskBands", {}))
            if hist:
                risk_data = hist

        if risk_data:
            df_risk = pd.DataFrame([
                {"Risk Band": k, "Count": v} for k, v in
                sorted(risk_data.items(), key=lambda x: ["LOW","MEDIUM","HIGH","CRITICAL"].index(x[0])
                       if x[0] in ["LOW","MEDIUM","HIGH","CRITICAL"] else 99)
            ])
            band_colors = {"CRITICAL":"#f85149","HIGH":"#f0883e","MEDIUM":"#d29922","LOW":"#3fb950"}
            df_risk["Color"] = df_risk["Risk Band"].map(lambda x: band_colors.get(x,"#58a6ff"))
            fig_risk = px.bar(df_risk, y="Risk Band", x="Count", orientation="h",
                               color="Risk Band",
                               color_discrete_map=band_colors)
            fig_risk.update_layout(
                height=280, showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6edf3"),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                margin=dict(t=10,b=10,l=10,r=10),
            )
            st.plotly_chart(fig_risk, use_container_width=True)
        else:
            st.info("No risk band data available")

        # ── Top risky countries ────────────────────────────────────────────────
        st.subheader("Top High-Risk Origination Countries")
        if debtor_raw:
            top = sorted(debtor_raw.items(), key=lambda x: x[1], reverse=True)[:10]
            df_top = pd.DataFrame(top, columns=["Country","Events"])
            st.dataframe(df_top, use_container_width=True, hide_index=True)
        else:
            st.info("No country data yet")

    with col_right:
        # ── AML timeline ──────────────────────────────────────────────────────
        st.subheader("Fraud/AML Events Over Time")
        over_time = geo.get("over_time", [])
        if over_time:
            df_ot = pd.DataFrame(over_time)
            df_ot["t"] = pd.to_datetime(df_ot["t"])
            fig_ot = px.line(df_ot, x="t", y="n",
                              color_discrete_sequence=["#f0883e"],
                              labels={"n":"High-risk events","t":""})
            fig_ot.update_layout(
                height=220, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6edf3"), showlegend=False,
                xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                margin=dict(t=10,b=10,l=10,r=10),
            )
            fig_ot.update_traces(line_width=2, fill="tozeroy",
                                  fillcolor="rgba(240,136,62,0.1)")
            st.plotly_chart(fig_ot, use_container_width=True)
        else:
            st.info("No event timeline data")

        # ── Payment rail distribution ─────────────────────────────────────────
        st.subheader("Payment Rail Distribution")
        rails_data = mcp_rails()
        if rails_data and isinstance(rails_data, dict):
            items = rails_data.get("railCounts", rails_data.get("distribution", {}))
            if items:
                df_rails = pd.DataFrame(
                    [{"Rail": k, "Count": v} for k, v in items.items()]
                ).sort_values("Count", ascending=False)
                fig_rails = px.pie(df_rails, values="Count", names="Rail",
                                    color_discrete_sequence=px.colors.qualitative.Bold,
                                    hole=0.4)
                fig_rails.update_layout(
                    height=300, paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e6edf3"),
                    margin=dict(t=0,b=0,l=0,r=0),
                    legend=dict(font=dict(size=11)),
                )
                st.plotly_chart(fig_rails, use_container_width=True)
            else:
                st.info("Rail data available but empty")
        else:
            # Fallback: query ES for rail field
            body = {
                "size": 0,
                "query": {"exists": {"field": "rail"}},
                "aggs": {"by_rail": {"terms": {"field": "rail.keyword", "size": 20}}}
            }
            r = _es("clearflow-*", body)
            buckets = r.get("aggregations",{}).get("by_rail",{}).get("buckets",[])
            if buckets:
                df_rails = pd.DataFrame([{"Rail": b["key"], "Count": b["doc_count"]} for b in buckets])
                fig_rails = px.pie(df_rails, values="Count", names="Rail",
                                    color_discrete_sequence=px.colors.qualitative.Bold, hole=0.4)
                fig_rails.update_layout(
                    height=300, paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e6edf3"),
                    margin=dict(t=0,b=0,l=0,r=0),
                )
                st.plotly_chart(fig_rails, use_container_width=True)
            else:
                st.info("No rail data — MCP not reachable and no ES data")


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 4 — PERFORMANCE
# ─────────────────────────────────────────────────────────────────────────────
elif "Performance" in page:
    st.title("⚡ Performance Telemetry")

    # ── Prometheus throughput over time ───────────────────────────────────────
    st.subheader("Payment Throughput — rate(30m)")
    series = _prom_range("rate(clearflow_payments_total[5m])", minutes=60, step="60s")
    if series:
        vals = series[0]["values"]
        df_thr = pd.DataFrame(vals, columns=["ts","rate"])
        df_thr["ts"] = pd.to_datetime(df_thr["ts"], unit="s")
        df_thr["rate"] = df_thr["rate"].astype(float)
        fig_thr = px.line(df_thr, x="ts", y="rate",
                           labels={"rate":"payments/sec","ts":""},
                           color_discrete_sequence=["#3fb950"])
        fig_thr.update_layout(
            height=220, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"), showlegend=False,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            margin=dict(t=10,b=10,l=10,r=10),
        )
        fig_thr.update_traces(fill="tozeroy", fillcolor="rgba(63,185,80,0.1)", line_width=2)
        st.plotly_chart(fig_thr, use_container_width=True)
    else:
        st.info("Prometheus not reachable or no data yet")

    st.divider()

    # ── HTTP latency from Spring Boot Actuator ────────────────────────────────
    st.subheader("HTTP Request Latency (from /actuator/prometheus)")
    lat_raw = latency_data()

    max_latency = {}
    for row in lat_raw:
        svc = row["service"]
        line = row["raw"]
        # Parse "http_server_requests_seconds_max{...} 0.123"
        if "seconds_max{" in line and "}" in line:
            try:
                val = float(line.split("}")[-1].strip())
                if svc not in max_latency or val > max_latency[svc]:
                    max_latency[svc] = val
            except Exception:
                pass

    if max_latency:
        df_lat = pd.DataFrame([
            {"Service": k, "Max Latency (ms)": round(v*1000, 1)}
            for k, v in sorted(max_latency.items())
        ])
        fig_lat = px.bar(df_lat, x="Service", y="Max Latency (ms)",
                          color="Max Latency (ms)",
                          color_continuous_scale=[[0,"#3fb950"],[0.5,"#d29922"],[1.0,"#f85149"]],
                          text="Max Latency (ms)")
        fig_lat.update_layout(
            height=320, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"), showlegend=False, coloraxis_showscale=False,
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            margin=dict(t=10,b=10,l=10,r=10),
        )
        fig_lat.update_traces(textfont_size=12, textposition="outside")
        st.plotly_chart(fig_lat, use_container_width=True)
    else:
        st.info("No latency data — ensure services are running (8080-8087 must be UP)")

    st.divider()

    # ── Service error rates ────────────────────────────────────────────────────
    st.subheader("Log Error Rate by Service (Last Hour)")
    summary = es_summary()
    by_svc = summary.get("by_service", {})
    total_logs = summary.get("total", 0)

    # Also get error counts per service
    err_body = {
        "size": 0,
        "query": {"bool": {"filter": [
            {"range": {"@timestamp": {"gte": "now-1h"}}},
            {"term": {"level.keyword": "ERROR"}}
        ]}},
        "aggs": {"by_svc": {"terms": {"field": "service.keyword", "size": 20}}}
    }
    err_r = _es("clearflow-*", err_body)
    err_by_svc = {b["key"]: b["doc_count"]
                  for b in err_r.get("aggregations",{}).get("by_svc",{}).get("buckets",[])}

    if by_svc:
        err_rows = []
        for svc, total_svc in by_svc.items():
            errors = err_by_svc.get(svc, 0)
            rate = errors / total_svc * 100 if total_svc > 0 else 0
            err_rows.append({
                "Service": svc,
                "Total Logs": f"{total_svc:,}",
                "Errors": errors,
                "Error Rate": f"{rate:.2f}%",
            })
        df_err = pd.DataFrame(err_rows).sort_values("Errors", ascending=False)
        st.dataframe(df_err, use_container_width=True, hide_index=True)
    else:
        st.info("No log data in the last hour")

    st.divider()

    # ── In-flight gauge ────────────────────────────────────────────────────────
    col_g1, col_g2, col_g3 = st.columns(3)

    with col_g1:
        st.subheader("In-Flight Payments")
        inflight = _prom_val("clearflow_gateway_inflight")
        fig_if = go.Figure(go.Indicator(
            mode="gauge+number",
            value=inflight,
            gauge=dict(
                axis=dict(range=[0, 1000], tickfont=dict(color="#8b949e")),
                bar=dict(color="#58a6ff"),
                bgcolor="rgba(0,0,0,0)",
                steps=[
                    dict(range=[0,500],   color="#0d3b27"),
                    dict(range=[500,800], color="#3b2a0d"),
                    dict(range=[800,1000],color="#3b0d0d"),
                ],
                threshold=dict(line=dict(color="#f85149",width=3), thickness=0.75, value=1000)
            ),
            number=dict(font=dict(color="#e6edf3")),
        ))
        fig_if.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(t=10,b=10,l=10,r=10),
        )
        st.plotly_chart(fig_if, use_container_width=True)

    with col_g2:
        st.subheader("Settlement Rate")
        total  = int(_prom_val("sum(clearflow_payments_total)"))
        settled = int(_prom_val("sum(clearflow_settlements_total)"))
        rate = settled/total*100 if total > 0 else 0
        fig_sr = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=rate,
            number=dict(suffix="%", font=dict(color="#e6edf3")),
            delta=dict(reference=95, valueformat=".1f"),
            gauge=dict(
                axis=dict(range=[0,100], tickfont=dict(color="#8b949e")),
                bar=dict(color="#3fb950"),
                bgcolor="rgba(0,0,0,0)",
                steps=[
                    dict(range=[0,80],   color="#3b0d0d"),
                    dict(range=[80,95],  color="#3b2a0d"),
                    dict(range=[95,100], color="#0d3b27"),
                ],
                threshold=dict(line=dict(color="#3fb950",width=3), thickness=0.75, value=95)
            ),
        ))
        fig_sr.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(t=10,b=10,l=10,r=10),
        )
        st.plotly_chart(fig_sr, use_container_width=True)

    with col_g3:
        st.subheader("AML Hit Rate")
        aml_hit = int(_prom_val("sum(clearflow_aml_hit_total)"))
        aml_ok  = int(_prom_val("sum(clearflow_aml_clear_total)"))
        aml_total = aml_hit + aml_ok
        aml_rate = aml_hit / aml_total * 100 if aml_total > 0 else 0
        fig_aml = go.Figure(go.Indicator(
            mode="gauge+number",
            value=aml_rate,
            number=dict(suffix="%", font=dict(color="#e6edf3")),
            gauge=dict(
                axis=dict(range=[0, 20], tickfont=dict(color="#8b949e")),
                bar=dict(color="#f0883e"),
                bgcolor="rgba(0,0,0,0)",
                steps=[
                    dict(range=[0,5],   color="#0d3b27"),
                    dict(range=[5,10],  color="#3b2a0d"),
                    dict(range=[10,20], color="#3b0d0d"),
                ],
            ),
        ))
        fig_aml.update_layout(
            height=230, paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6edf3"),
            margin=dict(t=10,b=10,l=10,r=10),
        )
        st.plotly_chart(fig_aml, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 5 — SECURITY EVENTS
# ─────────────────────────────────────────────────────────────────────────────
elif "Security" in page:
    st.title("🚨 Security Events — SIEM Feed")

    events = security_events(100)
    if not events:
        events = recent_alerts(50)

    if events:
        df_sec = pd.DataFrame(events)

        # ── Severity distribution ──────────────────────────────────────────────
        col_d, col_t = st.columns([1, 3])

        with col_d:
            st.subheader("Severity")
            sev_col = "siem_severity" if "siem_severity" in df_sec.columns else "level"
            if sev_col in df_sec.columns:
                sev_counts = df_sec[sev_col].value_counts().reset_index()
                sev_counts.columns = ["Severity","Count"]
                sev_map = {"CRITICAL":"#f85149","HIGH":"#f0883e","ERROR":"#f85149",
                           "WARN":"#d29922","WARNING":"#d29922","INFO":"#3fb950"}
                fig_sev = px.pie(sev_counts, values="Count", names="Severity",
                                  color="Severity",
                                  color_discrete_map=sev_map,
                                  hole=0.5)
                fig_sev.update_layout(
                    height=240, paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e6edf3"), showlegend=True,
                    margin=dict(t=0,b=0,l=0,r=0),
                )
                st.plotly_chart(fig_sev, use_container_width=True)

        with col_t:
            st.subheader("Events Timeline")
            if "@timestamp" in df_sec.columns:
                df_sec["ts"] = pd.to_datetime(df_sec["@timestamp"], errors="coerce")
                df_sec_valid = df_sec.dropna(subset=["ts"])
                if not df_sec_valid.empty:
                    df_sec_valid = df_sec_valid.set_index("ts").sort_index()
                    event_series = df_sec_valid.resample("5min").size().reset_index()
                    event_series.columns = ["Time","Count"]
                    fig_ev = px.bar(event_series, x="Time", y="Count",
                                     color_discrete_sequence=["#f0883e"])
                    fig_ev.update_layout(
                        height=240, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#e6edf3"), showlegend=False,
                        xaxis=dict(showgrid=False),
                        yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                        margin=dict(t=0,b=0,l=10,r=10),
                    )
                    st.plotly_chart(fig_ev, use_container_width=True)

        st.divider()

        # ── Event type breakdown ───────────────────────────────────────────────
        if "eventType" in df_sec.columns:
            st.subheader("Event Types")
            ev_counts = df_sec["eventType"].dropna().value_counts().head(10).reset_index()
            ev_counts.columns = ["Event Type","Count"]
            fig_et = px.bar(ev_counts, x="Count", y="Event Type", orientation="h",
                             color_discrete_sequence=["#58a6ff"])
            fig_et.update_layout(
                height=280, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6edf3"),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(showgrid=False),
                margin=dict(t=10,b=10,l=10,r=10),
            )
            st.plotly_chart(fig_et, use_container_width=True)
            st.divider()

        # ── Full feed ─────────────────────────────────────────────────────────
        st.subheader("Live Feed")
        display_cols = [c for c in ["@timestamp","service","level","eventType","paymentId",
                                     "siem_severity","message","riskBand"] if c in df_sec.columns]
        df_display = df_sec[display_cols].rename(columns={
            "@timestamp": "Time", "service": "Service",
            "level": "Level", "eventType": "Event", "paymentId": "Payment ID",
            "siem_severity": "Severity", "riskBand": "Risk",
        })
        if "Time" in df_display.columns:
            df_display["Time"] = pd.to_datetime(df_display["Time"]).dt.strftime("%m-%d %H:%M:%S")
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=500)
    else:
        st.success("✓ No security events found in clearflow-security-* index")
        st.info("""
        **To see security events:**
        1. Ensure services are running
        2. Send payments with AML-blocked IBANs (IR/KP/RU debtors)
        3. Logstash security pipeline ingests from Kafka topics:
           - `clearflow.aml.sanctions.hit`
           - `clearflow.payment.blocked`
           - `clearflow.compliance.alerts`
        """)


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 6 — INFRASTRUCTURE
# ─────────────────────────────────────────────────────────────────────────────
elif "Infrastructure" in page:
    st.title("🏗️ Infrastructure Health")

    # ── Docker containers ─────────────────────────────────────────────────────
    st.subheader("Docker Containers")
    containers = docker_containers()
    if containers:
        df_docker = pd.DataFrame(containers)
        df_docker["Status Icon"] = df_docker["up"].map(lambda x: "🟢" if x else "🔴")
        df_docker = df_docker.rename(columns={"name":"Container","status":"Status","image":"Image"})
        display = df_docker[["Status Icon","Container","Status","Image"]]

        # Split clearflow infra vs external
        infra_kw = ["kafka","zookeeper","redis","mongo","cassandra","elasticsearch",
                    "kibana","logstash","activemq","prometheus","grafana","vault","camunda"]
        df_infra = display[display["Container"].str.lower().apply(
            lambda n: any(k in n for k in infra_kw))]
        df_other = display[~display["Container"].str.lower().apply(
            lambda n: any(k in n for k in infra_kw))]

        if not df_infra.empty:
            st.markdown("**Core Infrastructure**")
            st.dataframe(df_infra, use_container_width=True, hide_index=True)
        if not df_other.empty:
            st.markdown("**Other Containers**")
            st.dataframe(df_other, use_container_width=True, hide_index=True)

        up_cnt  = df_docker["up"].sum()
        all_cnt = len(df_docker)
        if up_cnt == all_cnt:
            st.success(f"All {all_cnt} containers running")
        else:
            st.warning(f"{up_cnt}/{all_cnt} containers running")
    else:
        st.warning("Could not query Docker — ensure Docker is running")

    st.divider()

    # ── Elasticsearch indices ─────────────────────────────────────────────────
    st.subheader("Elasticsearch Indices")
    idx_stats = es_index_stats()
    if idx_stats:
        df_idx = pd.DataFrame(idx_stats)
        st.dataframe(df_idx, use_container_width=True, hide_index=True)

        # Total docs
        total_docs = sum(
            int(r["Docs"].replace(",","")) for r in idx_stats
            if r.get("Docs","").replace(",","").isdigit()
        )
        st.metric("Total Indexed Documents", f"{total_docs:,}")
    else:
        try:
            r = requests.get(f"{ES}/_cluster/health", timeout=3)
            if r.ok:
                h = r.json()
                col1, col2, col3 = st.columns(3)
                col1.metric("Cluster Status",  h.get("status","?").upper())
                col2.metric("Active Shards",   h.get("active_shards","?"))
                col3.metric("Data Nodes",      h.get("number_of_data_nodes","?"))
            else:
                st.warning("Elasticsearch returned non-200")
        except Exception:
            st.error("Elasticsearch not reachable (localhost:9200)")

    st.divider()

    # ── Kafka topics ──────────────────────────────────────────────────────────
    st.subheader("Kafka Topics")
    topics = kafka_topics()
    if topics:
        clearflow_topics = [t for t in topics if "clearflow" in t.lower()]
        other_topics = [t for t in topics if "clearflow" not in t.lower()]
        st.markdown(f"**ClearFlow topics ({len(clearflow_topics)}):**")
        cols = st.columns(3)
        for i, t in enumerate(sorted(clearflow_topics)):
            cols[i % 3].markdown(f"• `{t}`")
        if other_topics:
            with st.expander(f"Other topics ({len(other_topics)})"):
                st.text("\n".join(other_topics))
    else:
        st.info("Cannot query Kafka topics — Docker compose must be running")

    st.divider()

    # ── Prometheus targets ─────────────────────────────────────────────────────
    st.subheader("Prometheus Scrape Targets")
    try:
        r = requests.get(f"{PROM}/api/v1/targets", timeout=5)
        if r.ok:
            targets = r.json().get("data",{}).get("activeTargets",[])
            if targets:
                df_tgt = pd.DataFrame([{
                    "Job":    t.get("labels",{}).get("job","?"),
                    "Instance": t.get("labels",{}).get("instance","?"),
                    "Health": "🟢 UP" if t.get("health")=="up" else "🔴 DOWN",
                    "Last Scrape": t.get("lastScrapeDuration","?"),
                } for t in targets])
                st.dataframe(df_tgt, use_container_width=True, hide_index=True)
            else:
                st.info("No active targets")
    except Exception:
        st.info("Prometheus not reachable (localhost:9090)")

    st.divider()

    # ── Quick-start reference ─────────────────────────────────────────────────
    with st.expander("📋 Quick Start Commands"):
        st.code("""# Start everything
cd /home/admin-/Desktop/EDI6/clearflow
bash start_live_traffic.sh

# Smoke test (15 payments)
python3 live_payment_sender.py

# Load test (100K payments)
python3 batch_100k.py

# Stop
bash stop_live_traffic.sh

# This dashboard
streamlit run observability_dashboard.py --server.port 8501
""", language="bash")


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 7 — FORECAST
# ─────────────────────────────────────────────────────────────────────────────
elif "Forecast" in page:
    st.title("🔮 Settlement Forecast & Anomaly Detection")

    tab_forecast, tab_anomalies = st.tabs(["📈 Settlement Forecast", "🚨 UETR Anomalies"])

    with tab_forecast:
        forecast_data = get_forecast()
        forecasts = forecast_data.get("forecasts", []) if isinstance(forecast_data, dict) else []

        if forecasts:
            df_fc = pd.DataFrame(forecasts)
            hours = df_fc.get("hour", df_fc.iloc[:, 0]).tolist() if "hour" in df_fc.columns else df_fc.iloc[:, 0].tolist()
            predicted = df_fc["predicted"].tolist() if "predicted" in df_fc.columns else []
            upper95   = df_fc["upper95"].tolist()   if "upper95"   in df_fc.columns else []
            lower95   = df_fc["lower95"].tolist()   if "lower95"   in df_fc.columns else []

            fig_fc = go.Figure()

            if upper95:
                fig_fc.add_trace(go.Scatter(
                    x=hours, y=upper95,
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor="rgba(88,166,255,0.15)",
                    name="95% CI Upper",
                    showlegend=False,
                ))
            if lower95:
                fig_fc.add_trace(go.Scatter(
                    x=hours, y=lower95,
                    mode="lines",
                    line=dict(width=0),
                    fill="tozeroy",
                    fillcolor="rgba(88,166,255,0.08)",
                    name="95% CI Lower",
                    showlegend=False,
                ))
            if predicted:
                fig_fc.add_trace(go.Scatter(
                    x=hours, y=predicted,
                    mode="lines",
                    line=dict(color="#58a6ff", width=2),
                    name="Predicted",
                ))

            fig_fc.update_layout(
                title="Hourly Settlement Volume Forecast — Next 24h",
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e6edf3"),
                xaxis=dict(showgrid=False, title="Hour"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="Predicted Count"),
                margin=dict(t=40, b=20, l=20, r=20),
            )
            st.plotly_chart(fig_fc, use_container_width=True)

            col_m1, col_m2 = st.columns(2)
            confidence = forecast_data.get("confidenceScore", forecast_data.get("confidence"))
            method     = forecast_data.get("method", "")
            if confidence is not None:
                col_m1.metric("Confidence Score", f"{confidence:.2f}" if isinstance(confidence, float) else str(confidence))
            if method:
                col_m2.caption(f"Method: {method}")
        else:
            st.info("Start services and process payments to generate forecast")

    with tab_anomalies:
        window_minutes = st.slider("Window (minutes)", 15, 120, 60, 15)
        anomaly_data   = get_uetr_anomalies(window_minutes)
        anomalies      = anomaly_data.get("anomalies", []) if isinstance(anomaly_data, dict) else []

        if anomalies:
            total_anom  = anomaly_data.get("totalAnomalies", len(anomalies))
            scanned     = anomaly_data.get("scannedCount", anomaly_data.get("totalScanned", "—"))
            window_start = anomaly_data.get("windowStart", "—")

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Anomalies",  str(total_anom))
            m2.metric("Scanned Count",    str(scanned))
            m3.metric("Window Start",     str(window_start)[:19].replace("T", " "))

            df_anom = pd.DataFrame(anomalies)
            # Normalise column names — tolerate camelCase or snake_case
            col_map = {}
            for src, dst in [("debtorRef","debtorRef"),("count","count"),
                              ("zScore","zScore"),("z_score","zScore"),
                              ("severity","severity"),("detectedAt","detectedAt"),
                              ("detected_at","detectedAt")]:
                if src in df_anom.columns:
                    col_map[src] = dst
            df_anom = df_anom.rename(columns=col_map)
            display_cols = [c for c in ["debtorRef","count","zScore","severity","detectedAt"]
                            if c in df_anom.columns]
            df_anom_disp = df_anom[display_cols].copy() if display_cols else df_anom.copy()

            severity_color = {"HIGH": "#f85149", "MEDIUM": "#f0883e", "LOW": "#d29922"}

            if "zScore" in df_anom_disp.columns and "debtorRef" in df_anom_disp.columns:
                df_top = df_anom_disp.dropna(subset=["zScore"]).copy()
                df_top["zScore"] = pd.to_numeric(df_top["zScore"], errors="coerce")
                df_top = df_top.nlargest(15, "zScore")
                df_top["color"] = df_top.get("severity", pd.Series(dtype=str)).map(
                    lambda s: severity_color.get(str(s).upper(), "#58a6ff")
                )
                fig_anom = px.bar(
                    df_top, x="zScore", y="debtorRef",
                    orientation="h",
                    color="severity" if "severity" in df_top.columns else None,
                    color_discrete_map=severity_color,
                    labels={"zScore": "Z-Score", "debtorRef": "Debtor Ref"},
                    title="Top 15 UETR Anomalies by Z-Score",
                )
                fig_anom.update_layout(
                    height=400,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#e6edf3"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    yaxis=dict(showgrid=False),
                    margin=dict(t=40, b=10, l=10, r=10),
                )
                st.plotly_chart(fig_anom, use_container_width=True)

            st.dataframe(df_anom_disp, use_container_width=True, hide_index=True)
        else:
            st.success("No UETR velocity anomalies detected")


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 8 — LIVE BOARDS
# ─────────────────────────────────────────────────────────────────────────────
elif "Live Boards" in page:
    st.title("📡 Live Grafana Boards")

    st.markdown(
        "Grafana is provisioned with 5 dashboards. "
        "Open Grafana at [http://localhost:3000](http://localhost:3000)"
    )
    st.divider()

    dashboard_links = [
        ("Command Center",       "http://localhost:3000/d/clearflow-cmd"),
        ("SLO & Error Budget",   "http://localhost:3000/d/clearflow-slo"),
        ("Fraud Intelligence",   "http://localhost:3000/d/clearflow-fraud"),
        ("Infrastructure",       "http://localhost:3000/d/clearflow-infra"),
    ]

    link_html = ""
    for title, url in dashboard_links:
        link_html += (
            f'<a href="{url}" target="_blank" style="text-decoration:none">'
            f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;'
            f'padding:14px 18px;margin:6px 0;color:#58a6ff;font-weight:600;font-size:0.95rem;">'
            f'&#128279; {title} &nbsp;<span style="color:#8b949e;font-size:0.8rem">{url}</span>'
            f'</div></a>'
        )
    st.markdown(link_html, unsafe_allow_html=True)

    st.divider()
    st.subheader("Command Center — Embedded")
    st.components.v1.iframe(
        "http://localhost:3000/d/clearflow-cmd?orgId=1&kiosk=tv&refresh=10s&theme=dark",
        height=600,
        scrolling=True,
    )
    st.caption(
        "If iframe shows login screen: set Grafana anonymous auth or "
        "log in at http://localhost:3000 (admin/admin)"
    )

    st.divider()
    st.subheader("Distributed Tracing — Jaeger")
    st.markdown(
        "Jaeger UI is available at "
        "[http://localhost:16686](http://localhost:16686). "
        "Use it to search for traces by `paymentId` or `correlationId` "
        "across all 8 microservices."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  PAGE 9 — AI ASSISTANT
# ─────────────────────────────────────────────────────────────────────────────
elif "AI Assistant" in page:
    st.title("🤖 ClearFlow AI Assistant")

    st.markdown(
        "Ask questions about payments, fraud scores, AML results, and system health. "
        "Powered by the MCP gateway LLM."
    )

    payment_id = st.text_input("Payment ID (optional — for payment-specific queries)")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # ── Quick-start example prompts ───────────────────────────────────────────
    st.markdown("**Example prompts:**")
    ex_col1, ex_col2, ex_col3, ex_col4 = st.columns(4)
    example_prompts = [
        "What is the current fraud risk level?",
        "Are there any AML concerns right now?",
        "What is the settlement success rate?",
        "Explain the payment pipeline stages",
    ]
    for col, prompt in zip([ex_col1, ex_col2, ex_col3, ex_col4], example_prompts):
        if col.button(prompt, use_container_width=True):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.spinner("Thinking..."):
                payload = {
                    "question": prompt,
                    "history":  st.session_state.chat_history[-5:],
                }
                if payment_id:
                    payload["paymentId"] = payment_id
                try:
                    resp = requests.post(
                        f"{MCP}/mcp/chat",
                        json=payload,
                        timeout=30,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.ok:
                        answer = resp.json().get("answer", resp.json().get("response", str(resp.json())))
                    else:
                        answer = f"MCP returned HTTP {resp.status_code}. Check that services are running."
                except Exception as exc:
                    answer = None
                    mcp_error = str(exc)
            if answer is not None:
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
            else:
                st.warning(
                    f"Could not reach MCP gateway: {mcp_error}. "
                    "Start services with `bash start_live_traffic.sh` and ensure "
                    "mcp-readonly-gateway is UP on port 8087."
                )
            st.rerun()

    st.divider()

    # ── Chat history display ──────────────────────────────────────────────────
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input ────────────────────────────────────────────────────────────
    user_message = st.chat_input("Ask about payments, fraud, routing...")
    if user_message:
        st.session_state.chat_history.append({"role": "user", "content": user_message})
        with st.chat_message("user"):
            st.markdown(user_message)

        with st.spinner("Thinking..."):
            payload = {
                "question": user_message,
                "history":  st.session_state.chat_history[-5:],
            }
            if payment_id:
                payload["paymentId"] = payment_id
            try:
                resp = requests.post(
                    f"{MCP}/mcp/chat",
                    json=payload,
                    timeout=30,
                    headers={"Content-Type": "application/json"},
                )
                if resp.ok:
                    answer = resp.json().get("answer", resp.json().get("response", str(resp.json())))
                else:
                    answer = f"MCP returned HTTP {resp.status_code}. Check that services are running."
            except Exception as exc:
                answer = None
                mcp_error = str(exc)

        if answer is not None:
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            with st.chat_message("assistant"):
                st.markdown(answer)
        else:
            st.warning(
                f"Could not reach MCP gateway: {mcp_error}. "
                "Start services with `bash start_live_traffic.sh` and ensure "
                "mcp-readonly-gateway is UP on port 8087."
            )


# ─── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    '<div style="text-align:center; color:#8b949e; font-size:0.7rem">'
    'ClearFlow ISO 20022 · 8 microservices · 17 Kafka topics · ELK + Prometheus + MCP'
    '</div>',
    unsafe_allow_html=True
)
