import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="Route Performance Dashboard", page_icon="🚌")

# ------------------------------------------------------------------
# LOAD
# ------------------------------------------------------------------
st.title("🚌 Route Performance Dashboard")
st.caption("Johari Window · Trends · Depot Comparison — built for quick daily review")

uploaded_file = st.file_uploader("Upload Excel or CSV File", type=["xlsx", "csv"])

if not uploaded_file:
    st.info("Upload the datewise operated & collection Excel/CSV to begin.")
    st.stop()

df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith("xlsx") else pd.read_csv(uploaded_file)
df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)

# KM Efficiency: handle both "82%" strings and 0.82 fractions
eff = df["KM Efficency"].astype(str).str.replace("%", "", regex=False).astype(float)
df["KM Efficency"] = eff * 100 if eff.max() <= 1.5 else eff
df["EPBPD"] = df["Collection With Reimbursement"]

# ------------------------------------------------------------------
# SIDEBAR FILTERS
# ------------------------------------------------------------------
st.sidebar.header("Filters")

d_min, d_max = df["Date"].min(), df["Date"].max()
date_range = st.sidebar.date_input("Date range", (d_min, d_max), min_value=d_min, max_value=d_max)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    df = df[(df["Date"] >= start) & (df["Date"] <= end)]

depots = st.sidebar.multiselect("Depot", sorted(df["Depot"].unique()), default=sorted(df["Depot"].unique()))
shifts = st.sidebar.multiselect("Shift", sorted(df["Shift"].unique()), default=sorted(df["Shift"].unique()))
services = st.sidebar.multiselect("Service", sorted(df["Service"].unique()), default=sorted(df["Service"].unique()))

df = df[df["Depot"].isin(depots) & df["Shift"].isin(shifts) & df["Service"].isin(services)]

if df.empty:
    st.warning("No data for the selected filters.")
    st.stop()

# ------------------------------------------------------------------
# KPI STRIP
# ------------------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Collection (₹)", f"{df['Collection With Reimbursement'].sum():,.0f}")
k2.metric("Avg EPKM (₹/km)", f"{df['EPKM'].mean():.2f}")
k3.metric("Avg KM Efficiency", f"{df['KM Efficency'].mean():.1f}%")
k4.metric("Total Passengers", f"{df['Total Passengers'].sum():,.0f}")
k5.metric("Trips Operated", f"{df['Operated Trip'].sum():,.0f}")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["🎯 Johari Window", "📈 Trends", "🏢 Depot Comparison", "📋 Data"])

# ------------------------------------------------------------------
# TAB 1 — JOHARI WINDOW (cleaned up)
# ------------------------------------------------------------------
with tab1:
    st.subheader("Average EPKM vs EPBPD per Service")
    st.caption("Bubble size = passenger load · Color = KM efficiency band · Split at the median of each axis")

    agg_df = df.groupby(["Service", "Depot"]).agg(
        EPKM=("EPKM", "mean"),
        EPBPD=("EPBPD", "mean"),
        Total_Passengers=("Total Passengers", "mean"),
        KM_Eff=("KM Efficency", "mean"),
    ).reset_index()

    def eff_band(v):
        if v < 85: return "< 85% (Poor)"
        if v < 95: return "85–95% (Fair)"
        if v < 99: return "95–99% (Good)"
        return "≥ 99% (Excellent)"

    agg_df["Efficiency Band"] = agg_df["KM_Eff"].apply(eff_band)

    x_mid = agg_df["EPBPD"].median()
    y_mid = agg_df["EPKM"].median()

    color_map = {
        "< 85% (Poor)": "#d62728",
        "85–95% (Fair)": "#1f77b4",
        "95–99% (Good)": "#2ca02c",
        "≥ 99% (Excellent)": "#ff7f0e",
    }

    fig = px.scatter(
        agg_df, x="EPBPD", y="EPKM",
        color="Efficiency Band", color_discrete_map=color_map,
        size="Total_Passengers", size_max=45,
        symbol="Depot", text="Service",
        hover_data={"Service": True, "Depot": True, "EPKM": ":.2f", "EPBPD": ":.0f",
                     "Total_Passengers": ":.0f", "KM_Eff": ":.1f", "Efficiency Band": False},
    )
    fig.update_traces(textposition="middle center", textfont=dict(size=11, color="white", family="Arial Black"))

    fig.add_vline(x=x_mid, line_dash="dash", line_color="gray",
                   annotation_text=f"median EPBPD {x_mid:,.0f}", annotation_position="top")
    fig.add_hline(y=y_mid, line_dash="dash", line_color="gray",
                   annotation_text=f"median EPKM {y_mid:,.1f}", annotation_position="right")

    fig.add_annotation(x=agg_df["EPBPD"].max(), y=agg_df["EPKM"].max(), text="⭐ Stars: high EPKM, high EPBPD",
                        showarrow=False, font=dict(size=11, color="gray"), xanchor="right", yanchor="top")

    fig.update_layout(
        height=650, plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0),
        xaxis_title="Average EPBPD (₹/bus/day)", yaxis_title="Average EPKM (₹/km)",
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("What do the four quadrants mean?"):
        c1, c2 = st.columns(2)
        c1.markdown("**Top-Right — Stars** \nHigh revenue-per-km AND high collection-per-day. Best performers.")
        c1.markdown("**Bottom-Right — Cash cows** \nHigh collection but lower EPKM — long/high-volume routes.")
        c2.markdown("**Top-Left — Efficient niches** \nHigh EPKM but lower daily collection — short profitable hops.")
        c2.markdown("**Bottom-Left — Needs attention** \nBelow median on both. Candidates for review.")

# ------------------------------------------------------------------
# TAB 2 — TRENDS OVER TIME
# ------------------------------------------------------------------
with tab2:
    st.subheader("Daily Trend")
    metric = st.selectbox("Metric", ["Collection With Reimbursement", "EPKM", "KM Efficency", "Total Passengers"])
    group_by = st.radio("Break down by", ["Depot", "Service", "None"], horizontal=True)

    if group_by == "None":
        trend = df.groupby("Date")[metric].mean().reset_index()
        fig2 = px.line(trend, x="Date", y=metric, markers=True)
    else:
        trend = df.groupby(["Date", group_by])[metric].mean().reset_index()
        fig2 = px.line(trend, x="Date", y=metric, color=group_by, markers=True)

    fig2.update_layout(height=500, plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig2, use_container_width=True)

# ------------------------------------------------------------------
# TAB 3 — DEPOT COMPARISON
# ------------------------------------------------------------------
with tab3:
    st.subheader("Depot Comparison")
    c1, c2 = st.columns(2)

    dep_avg = df.groupby("Depot").agg(EPKM=("EPKM", "mean"), Efficiency=("KM Efficency", "mean"),
                                       Collection=("Collection With Reimbursement", "sum")).reset_index()
    fig3 = px.bar(dep_avg, x="Depot", y="EPKM", color="Depot", title="Avg EPKM by Depot", text_auto=".2f")
    fig3.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white")
    c1.plotly_chart(fig3, use_container_width=True)

    fig4 = px.box(df, x="Depot", y="KM Efficency", color="Depot", title="KM Efficiency Spread by Depot")
    fig4.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white")
    c2.plotly_chart(fig4, use_container_width=True)

    fig5 = px.bar(dep_avg, x="Depot", y="Collection", color="Depot", title="Total Collection by Depot", text_auto=",.0f")
    fig5.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig5, use_container_width=True)

# ------------------------------------------------------------------
# TAB 4 — RAW DATA
# ------------------------------------------------------------------
with tab4:
    st.subheader("Filtered Data")
    st.dataframe(df, use_container_width=True, height=500)
    st.download_button("Download filtered CSV", df.to_csv(index=False).encode(), "filtered_data.csv", "text/csv")