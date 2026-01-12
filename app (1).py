import time
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# =========================================================
# CONFIG
# =========================================================
SERVER = "https://drns-1.onrender.com"
REFRESH_SEC = 2

st.set_page_config(page_title="UAV Dashboard", layout="wide")

# =========================================================
# STYLE (SAFE, NO CUT)
# =========================================================
st.markdown("""
<style>
.block-container {
    padding-top: 1.2rem;
    padding-bottom: 0.5rem;
}
h2 {
    margin-top: 0;
    margin-bottom: 0.6rem;
}
.stAlert { display: none; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# TITLE
# =========================================================
st.markdown(
    "<h2>UAV Real-Time Monitoring & Collision Avoidance Dashboard</h2>",
    unsafe_allow_html=True
)

# =========================================================
# FETCH DATA
# =========================================================
@st.cache_data(ttl=2)
def fetch_data():
    before = requests.get(SERVER + "/uavs?process=false", timeout=20).json()
    after  = requests.get(SERVER + "/uavs?process=true",  timeout=20).json()
    return before, after

try:
    data_before, data_after = fetch_data()
except Exception as e:
    st.error(f"Server connection failed: {e}")
    st.stop()

# =========================================================
# TO DATAFRAME
# =========================================================
def to_df(data):
    rows = []
    for u in data["uavs"]:
        rows.append({
            "UAV_ID": u["uav_id"],
            "X": u["x"],              # longitude
            "Y": u["y"],              # latitude
            "Status": u["status"],
            "dmin": u["min_distance_km"],
            "PredX": u["predicted"]["x"] if u.get("predicted") else np.nan,
            "PredY": u["predicted"]["y"] if u.get("predicted") else np.nan
        })
    return pd.DataFrame(rows)

dfB = to_df(data_before)
dfA = to_df(data_after)

# =========================================================
# COLLISION ALERT
# =========================================================
collision_df = dfA[dfA["Status"] == "collision"]
collision_count = len(collision_df)

if collision_count > 0:
    st.error(f"🚨 COLLISION ALERT: {collision_count} UAV(s) detected!")
else:
    st.success("✅ No collisions detected")

# =========================================================
# ===== TOP ROW : 4 MAIN PLOTS =====
# =========================================================
colors = {
    "safe": "blue",
    "outer_near": "gold",
    "inner_near": "orange",
    "collision": "red"
}

fig_top = make_subplots(
    rows=1, cols=4,
    subplot_titles=[
        "BEFORE – Raw Positions",
        "Prediction",
        "AFTER – Avoidance",
        "Status Distribution"
    ]
)

# BEFORE
for s in colors:
    d = dfB[dfB["Status"] == s]
    fig_top.add_trace(
        go.Scatter(
            x=d["X"], y=d["Y"],
            mode="markers",
            marker=dict(size=8, symbol="circle-open", color=colors[s]),
            name=f"BEFORE {s}"
        ),
        row=1, col=1
    )

# PREDICTION
valid = dfB["PredX"].notna()
fig_top.add_trace(go.Scatter(
    x=dfB[valid]["X"], y=dfB[valid]["Y"],
    mode="markers",
    marker=dict(size=7, symbol="circle-open", color="black"),
    name="Before"
), row=1, col=2)

fig_top.add_trace(go.Scatter(
    x=dfB[valid]["PredX"], y=dfB[valid]["PredY"],
    mode="markers",
    marker=dict(size=8, symbol="circle-open", color="magenta"),
    name="Predicted"
), row=1, col=2)

# AFTER
for s in colors:
    d = dfA[dfA["Status"] == s]
    fig_top.add_trace(
        go.Scatter(
            x=d["X"], y=d["Y"],
            mode="markers",
            marker=dict(size=8, symbol="circle-open", color=colors[s]),
            name=f"AFTER {s}"
        ),
        row=1, col=3
    )

# STATUS DISTRIBUTION
labels = list(colors.keys())
fig_top.add_trace(go.Bar(
    x=labels,
    y=[sum(dfB["Status"] == s) for s in labels],
    name="Before"
), row=1, col=4)

fig_top.add_trace(go.Bar(
    x=labels,
    y=[sum(dfA["Status"] == s) for s in labels],
    name="After"
), row=1, col=4)

fig_top.update_layout(
    height=360,
    barmode="group",
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", y=-0.28)
)

st.plotly_chart(fig_top, use_container_width=True)

# =========================================================
# ===== SECOND ROW : 3 ANALYSIS PLOTS =====
# =========================================================
dmin_before = dfB["dmin"].values
dmin_after  = dfA["dmin"].values
delta_dmin  = dmin_after - dmin_before

pred_move = np.sqrt(
    (dfB["PredX"] - dfB["X"])**2 +
    (dfB["PredY"] - dfB["Y"])**2
)

# Predicted displacement (Line + Markers)
fig1 = go.Figure()
fig1.add_trace(go.Scatter(
    y=pred_move,
    mode="lines+markers",
    line=dict(width=2, color="blue"),
    marker=dict(size=7, symbol="circle-open")
))
fig1.update_layout(
    title="Predicted Displacement",
    xaxis_title="UAV Index",
    yaxis_title="Predicted Displacement (km)",
    height=260
)

# Delta dmin
fig2 = go.Figure()
fig2.add_trace(go.Bar(y=delta_dmin))
fig2.update_layout(
    title="Δ dmin",
    xaxis_title="UAV Index",
    yaxis_title="Δ Minimum Distance (km)",
    height=260
)

# dmin before vs after
fig3 = go.Figure()
fig3.add_trace(go.Scatter(y=dmin_before, mode="lines+markers", name="Before"))
fig3.add_trace(go.Scatter(y=dmin_after,  mode="lines+markers", name="After"))
fig3.update_layout(
    title="dmin Before vs After",
    xaxis_title="UAV Index",
    yaxis_title="Minimum Distance (km)",
    height=260
)

c1, c2, c3 = st.columns(3)
with c1: st.plotly_chart(fig1, use_container_width=True)
with c2: st.plotly_chart(fig2, use_container_width=True)
with c3: st.plotly_chart(fig3, use_container_width=True)

# =========================================================
# UAV MAP
# =========================================================
st.subheader("🗺️ UAV Geographical Map")

map_fig = go.Figure()

for s, col in colors.items():
    d = dfA[dfA["Status"] == s]
    map_fig.add_trace(go.Scattermapbox(
        lat=d["Y"],
        lon=d["X"],
        mode="markers",
        marker=dict(size=11, color=col),
        name=s
    ))

map_fig.update_layout(
    mapbox=dict(
        style="open-street-map",
        center=dict(lat=dfA["Y"].mean(), lon=dfA["X"].mean()),
        zoom=11
    ),
    height=420,
    margin=dict(l=0, r=0, t=30, b=0)
)

st.plotly_chart(map_fig, use_container_width=True)

# =========================================================
# TABLES
# =========================================================
st.subheader("RAW UAV DATA")

t1, t2 = st.columns(2)
with t1:
    st.markdown("**BEFORE**")
    st.dataframe(dfB, use_container_width=True, height=320)

with t2:
    st.markdown("**AFTER**")
    st.dataframe(dfA, use_container_width=True, height=320)

# =========================================================
# AUTO REFRESH
# =========================================================
time.sleep(REFRESH_SEC)
st.rerun()
