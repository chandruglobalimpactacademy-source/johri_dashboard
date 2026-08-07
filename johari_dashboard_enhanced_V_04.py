import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(layout="wide", page_title="Route Performance Dashboard", page_icon="🚌")

# Full, working modebar for every chart: scroll-zoom, pan, box/lasso select, autoscale,
# reset axes, spike lines, draw/annotate tools, and a proper PNG export.
PLOTLY_CONFIG = {
    "displaylogo": False,
    "scrollZoom": True,
    "modeBarButtonsToAdd": [
        "drawline", "drawopenpath", "drawclosedpath", "drawcircle", "drawrect",
        "eraseshape", "toggleSpikelines",
    ],
    "toImageButtonOptions": {"format": "png", "filename": "chart", "scale": 2},
}

# ------------------------------------------------------------------
# LOAD
# ------------------------------------------------------------------
st.title("🚌 Route Performance Dashboard")
st.caption("Johari Window · Trends · Depot Comparison — built for quick daily review")

uploaded_file = st.file_uploader("Upload Excel or CSV File", type=["xlsx", "csv"])

if not uploaded_file:
    st.info("Upload the datewise operated & collection Excel/CSV to begin.")
    st.stop()

abstract_df = None
if uploaded_file.name.endswith("xlsx"):
    xls = pd.ExcelFile(uploaded_file)
    df = xls.parse(xls.sheet_names[0])
    if "Abstract" in xls.sheet_names:
        raw_abs = xls.parse("Abstract", header=None)
        header_rows = raw_abs.index[raw_abs[0].astype(str).str.strip() == "Date"]
        if len(header_rows):
            hi = header_rows[0]
            abstract_df = raw_abs.iloc[hi + 1:].copy()
            abstract_df.columns = raw_abs.iloc[hi].tolist()
            abstract_df = abstract_df.rename(columns={abstract_df.columns[0]: "Date"})
            abstract_df["Date"] = pd.to_datetime(abstract_df["Date"], errors="coerce")
            abstract_df = abstract_df.dropna(subset=["Date"])
else:
    df = pd.read_csv(uploaded_file)

df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)

# KM Efficiency: handle both "82%" strings and 0.82 fractions
eff = df["KM Efficency"].astype(str).str.replace("%", "", regex=False).astype(float)
df["KM Efficency"] = eff * 100 if eff.max() <= 1.5 else eff
df["EPBPD"] = df["Collection With Reimbursement"]

# ------------------------------------------------------------------
# SIDEBAR FILTERS — friendly panel
# ------------------------------------------------------------------
d_min, d_max = df["Date"].min().date(), df["Date"].max().date()
all_depots = sorted(df["Depot"].unique())
all_shifts = sorted(df["Shift"].unique())
all_services = sorted(df["Service"].unique())

defaults = {"start": d_min, "end": d_max, "depots": all_depots, "shifts": all_shifts, "services": all_services}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

st.sidebar.markdown("## 🔍 Filters")

# --- reset button placed FIRST, before any widget with these keys exists ---
if st.sidebar.button("↺ Reset all filters", use_container_width=True):
    for k, v in defaults.items():
        st.session_state[k] = v

st.sidebar.divider()

# --- quick date presets, built from the data's own span ---
st.sidebar.caption("Date range")

span_days = (d_max - d_min).days
week_starts = pd.date_range(d_min, d_max, freq="7D")
quick_options = ["Full range"]
week_bounds = {}
for i, ws in enumerate(week_starts, start=1):
    we = min(ws + pd.Timedelta(days=6), pd.Timestamp(d_max))
    label = f"Week {i} ({ws.date()} – {we.date()})"
    quick_options.append(label)
    week_bounds[label] = (ws.date(), we.date())
quick_options.append("Custom")

quick_pick = st.sidebar.selectbox("Quick pick", quick_options, label_visibility="collapsed")

if quick_pick == "Full range":
    st.session_state.start, st.session_state.end = d_min, d_max
elif quick_pick == "Custom":
    pass  # leaves whatever is already in session_state, editable below
else:
    st.session_state.start, st.session_state.end = week_bounds[quick_pick]

if quick_pick == "Custom":
    picked = st.sidebar.date_input(
        "Custom range", (st.session_state.start, st.session_state.end), min_value=d_min, max_value=d_max,
    )
    if isinstance(picked, tuple) and len(picked) == 2:
        start, end = picked
        st.session_state.start, st.session_state.end = start, end
    else:
        # user has only picked one end so far — keep previous valid range until they finish
        start, end = st.session_state.start, st.session_state.end
        st.sidebar.caption("Pick the end date to apply the custom range.")
else:
    start, end = st.session_state.start, st.session_state.end
    st.sidebar.caption(f"📅 {start} → {end}")

st.sidebar.divider()

# --- reusable "select all" multiselect block ---
def picker(label, options, state_key):
    st.sidebar.caption(label)
    c1, c2 = st.sidebar.columns(2)
    if c1.button("Select all", key=f"{state_key}_all", use_container_width=True):
        st.session_state[state_key] = options
    if c2.button("Clear", key=f"{state_key}_clear", use_container_width=True):
        st.session_state[state_key] = []
    selection = st.sidebar.multiselect(label, options, key=state_key, label_visibility="collapsed")
    st.sidebar.caption(f"{len(selection)}/{len(options)} selected")
    st.sidebar.divider()
    return selection

depots = picker("Depot", all_depots, "depots")
shifts = picker("Shift", all_shifts, "shifts")
services = picker("Service", all_services, "services")

# --- apply filters ---
df = df[
    (df["Date"] >= pd.to_datetime(start)) & (df["Date"] <= pd.to_datetime(end))
    & df["Depot"].isin(depots) & df["Shift"].isin(shifts) & df["Service"].isin(services)
]

st.sidebar.metric("Rows matching filters", f"{len(df):,}")

if df.empty:
    st.warning("No data for the selected filters — try Reset all filters.")
    st.stop()

# ------------------------------------------------------------------
# DAILY AGGREGATE (shared by KPI grid + Daily Abstract tab)
# ------------------------------------------------------------------
daily_extra = df.groupby("Date").agg(
    **{
        "Route": ("Route", "first"),
        "No of services operated per day": ("Service", "nunique"),
        "number of trips operated per day": ("Operated Trip", "sum"),
        "Operated KM": ("Operated KM", "sum"),
        "Zero Value Ticket": ("Zero Value Ticket", "sum"),
        "Ticket Passenger": ("Ticket Passenger", "sum"),
        "Senior Citizens": ("Senior Citizens", "sum"),
        "Total Passengers  per day (Including women)": ("Total Passengers", "sum"),
    }
).reset_index()

if abstract_df is not None:
    core_cols = [c for c in ["Date", "EPBPD", "EPKM", "Kilometric efficiency for the day",
                              "Total Passengers  per bus per day (Including women)"] if c in abstract_df.columns]
    merged = pd.merge(abstract_df[core_cols], daily_extra, on="Date", how="right")
else:
    coll = df.groupby("Date")["Collection With Reimbursement"].sum()
    opkm = df.groupby("Date")["Operated KM"].sum()
    schkm = df.groupby("Date")["Scheduled KM"].sum()
    daily_extra["EPKM"] = (coll / opkm).round(2).values
    daily_extra["Kilometric efficiency for the day"] = (opkm / schkm).round(3).values
    daily_extra["EPBPD"] = (coll / daily_extra["No of services operated per day"].values).round(0).values
    daily_extra["Total Passengers  per bus per day (Including women)"] = (
        df.groupby("Date")["Total Passengers"].sum() / daily_extra["No of services operated per day"].values
    ).round(1).values
    merged = daily_extra

merged = merged[(merged["Date"] >= pd.to_datetime(start)) & (merged["Date"] <= pd.to_datetime(end))].sort_values("Date")

# ------------------------------------------------------------------
# KPI STRIP — totals-based, matches the Abstract sheet's own methodology
# (EPKM and efficiency are ratios of sums, not averages of daily %s)
# ------------------------------------------------------------------
total_collection = df["Collection With Reimbursement"].sum()
total_op_km = df["Operated KM"].sum()
total_sched_km = df["Scheduled KM"].sum()
weighted_epkm = total_collection / total_op_km if total_op_km else 0
weighted_eff = (total_op_km / total_sched_km * 100) if total_sched_km else 0

eff_col = merged["Kilometric efficiency for the day"]
eff_col = pd.to_numeric(eff_col, errors="coerce")
eff_pct = eff_col * 100 if eff_col.max() <= 1.5 else eff_col

route_val = ", ".join(str(r) for r in sorted(df["Route"].unique()))

st.markdown("#### Overview — selected period")
r1 = st.columns(4)
r1[0].metric("Route", route_val)
r1[1].metric("Total Collection (₹)", f"{total_collection:,.0f}")
r1[2].metric("Total Passengers", f"{df['Total Passengers'].sum():,.0f}")
r1[3].metric("Trips Operated (total)", f"{df['Operated Trip'].sum():,.0f}")

r2 = st.columns(4)
r2[0].metric("EPKM (₹/km)", f"{weighted_epkm:.2f}")
r2[1].metric("KM Efficiency", f"{weighted_eff:.1f}%")
r2[2].metric("Avg EPBPD (₹/bus/day)", f"{pd.to_numeric(merged['EPBPD'], errors='coerce').mean():,.0f}")
r2[3].metric("Avg Kilometric Efficiency/day", f"{eff_pct.mean():.1f}%")

r3 = st.columns(4)
r3[0].metric("Avg services operated/day", f"{merged['No of services operated per day'].mean():.1f}")
r3[1].metric("Avg trips operated/day", f"{merged['number of trips operated per day'].mean():.1f}")
r3[2].metric("Operated KM (total)", f"{merged['Operated KM'].sum():,.0f}")
r3[3].metric("Avg passengers/bus/day", f"{pd.to_numeric(merged['Total Passengers  per bus per day (Including women)'], errors='coerce').mean():,.1f}")

r4 = st.columns(4)
r4[0].metric("Zero Value Ticket (total)", f"{merged['Zero Value Ticket'].sum():,.0f}")
r4[1].metric("Ticket Passenger (total)", f"{merged['Ticket Passenger'].sum():,.0f}")
r4[2].metric("Senior Citizens (total)", f"{merged['Senior Citizens'].sum():,.0f}")
r4[3].metric("Total Passengers/day (avg)", f"{merged['Total Passengers  per day (Including women)'].mean():,.0f}")

st.caption("Route/EPKM/Efficiency/EPBPD use totals-based math (same approach as your workbook's Abstract sheet). "
           "Per-day figures are averaged across the selected date range; ticket-category totals are summed.")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🎯 Johari Window", "📈 Trends", "🏢 Depot Comparison", "📋 Data", "📆 Daily Abstract"]
)

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
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

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
    metric_options = [
        "Collection With Reimbursement", "Total Passengers", "EPKM", "KM Efficency", "EPBPD",
        "Zero Value Ticket", "Ticket Passenger", "Senior Citizens", "Operated KM",
        "No of services operated per day", "number of trips operated per day",
        "Total Passengers per bus per day",
    ]
    metric = st.selectbox("Metric", metric_options)
    group_by = st.radio("Break down by", ["Depot", "Service", "None"], horizontal=True)
    group_cols = ["Date"] if group_by == "None" else ["Date", group_by]

    base = df.groupby(group_cols).agg(
        Collection=("Collection With Reimbursement", "sum"),
        Pax=("Total Passengers", "sum"),
        OpKM=("Operated KM", "sum"),
        SchKM=("Scheduled KM", "sum"),
        ZeroTicket=("Zero Value Ticket", "sum"),
        TicketPax=("Ticket Passenger", "sum"),
        Senior=("Senior Citizens", "sum"),
        Services=("Service", "nunique"),
        Trips=("Operated Trip", "sum"),
    ).reset_index()

    metric_map = {
        "Collection With Reimbursement": base["Collection"],
        "Total Passengers": base["Pax"],
        "EPKM": base["Collection"] / base["OpKM"],
        "KM Efficency": base["OpKM"] / base["SchKM"] * 100,
        "EPBPD": base["Collection"] / base["Services"],
        "Zero Value Ticket": base["ZeroTicket"],
        "Ticket Passenger": base["TicketPax"],
        "Senior Citizens": base["Senior"],
        "Operated KM": base["OpKM"],
        "No of services operated per day": base["Services"],
        "number of trips operated per day": base["Trips"],
        "Total Passengers per bus per day": base["Pax"] / base["Services"],
    }
    base["value"] = metric_map[metric]

    if group_by == "None":
        fig2 = px.line(base, x="Date", y="value", markers=True)
    else:
        fig2 = px.line(base, x="Date", y="value", color=group_by, markers=True)

    fig2.update_layout(height=500, plot_bgcolor="white", paper_bgcolor="white", yaxis_title=metric)
    st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG)
    if metric in ("EPKM", "KM Efficency", "EPBPD", "Total Passengers per bus per day"):
        st.caption("Rate metrics are computed from summed numerator/denominator per period, not averaged row %s.")

# ------------------------------------------------------------------
# TAB 3 — DEPOT COMPARISON
# ------------------------------------------------------------------
with tab3:
    st.subheader("Depot Comparison")
    c1, c2 = st.columns(2)

    dep_totals = df.groupby("Depot").agg(
        Collection=("Collection With Reimbursement", "sum"),
        OpKM=("Operated KM", "sum"),
        SchKM=("Scheduled KM", "sum"),
    ).reset_index()
    dep_totals["EPKM"] = dep_totals["Collection"] / dep_totals["OpKM"]
    dep_totals["Efficiency"] = dep_totals["OpKM"] / dep_totals["SchKM"] * 100

    fig3 = px.bar(dep_totals, x="Depot", y="EPKM", color="Depot", title="EPKM by Depot (Collection ÷ Operated KM)", text_auto=".2f")
    fig3.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white")
    c1.plotly_chart(fig3, use_container_width=True, config=PLOTLY_CONFIG)

    # day-level weighted efficiency per depot, for a meaningful min–max range
    daily_depot = df.groupby(["Depot", "Date"]).agg(OpKM=("Operated KM", "sum"), SchKM=("Scheduled KM", "sum")).reset_index()
    daily_depot["Eff"] = daily_depot["OpKM"] / daily_depot["SchKM"] * 100
    dep_range = daily_depot.groupby("Depot")["Eff"].agg(min="min", max="max").reset_index()
    dep_stats = dep_totals[["Depot", "Efficiency"]].merge(dep_range, on="Depot")

    fig4 = go.Figure()
    fig4.add_trace(go.Bar(
        x=dep_stats["Depot"], y=dep_stats["Efficiency"],
        error_y=dict(type="data", symmetric=False,
                     array=dep_stats["max"] - dep_stats["Efficiency"],
                     arrayminus=dep_stats["Efficiency"] - dep_stats["min"],
                     color="gray", thickness=1.5, width=5),
        marker_color="#1f77b4",
        text=dep_stats["Efficiency"].round(1).astype(str) + "%",
        textposition="outside",
    ))
    fig4.add_hline(y=85, line_dash="dot", line_color="red", annotation_text="85% min target")
    fig4.update_layout(
        title="KM Efficiency by Depot (Operated KM ÷ Scheduled KM) — with day-to-day range",
        yaxis_title="KM Efficiency (%)", xaxis_title="Depot",
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    c2.plotly_chart(fig4, use_container_width=True, config=PLOTLY_CONFIG)
    c2.caption("Bar = totals-based efficiency for the depot. Whiskers = lowest/highest single day observed.")

    fig5 = px.bar(dep_totals, x="Depot", y="Collection", color="Depot", title="Total Collection by Depot", text_auto=",.0f")
    fig5.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig5, use_container_width=True, config=PLOTLY_CONFIG)

    st.divider()
    st.markdown("##### Compare another category by depot")

    daily_dep = df.groupby(["Depot", "Date"]).agg(
        Collection=("Collection With Reimbursement", "sum"),
        Pax=("Total Passengers", "sum"),
        OpKM=("Operated KM", "sum"),
        ZeroTicket=("Zero Value Ticket", "sum"),
        TicketPax=("Ticket Passenger", "sum"),
        Senior=("Senior Citizens", "sum"),
        Services=("Service", "nunique"),
        Trips=("Operated Trip", "sum"),
    ).reset_index()
    daily_dep["EPBPD"] = daily_dep["Collection"] / daily_dep["Services"]
    daily_dep["PaxPerBus"] = daily_dep["Pax"] / daily_dep["Services"]

    extra_metric_map = {
        "Total Passengers (total)": ("Pax", "sum"),
        "Total Passengers per day (avg)": ("Pax", "mean"),
        "Zero Value Ticket (total)": ("ZeroTicket", "sum"),
        "Ticket Passenger (total)": ("TicketPax", "sum"),
        "Senior Citizens (total)": ("Senior", "sum"),
        "Operated KM (total)": ("OpKM", "sum"),
        "Avg EPBPD (₹/bus/day)": ("EPBPD", "mean"),
        "Avg services operated/day": ("Services", "mean"),
        "Avg trips operated/day": ("Trips", "mean"),
        "Avg passengers/bus/day": ("PaxPerBus", "mean"),
    }
    selected_extra = st.selectbox("Metric", list(extra_metric_map.keys()))
    col, agg_fn = extra_metric_map[selected_extra]
    dep_extra = daily_dep.groupby("Depot")[col].agg(agg_fn).reset_index(name="value")

    fig6 = px.bar(dep_extra, x="Depot", y="value", color="Depot", title=f"{selected_extra} by Depot",
                  text_auto=",.1f" if agg_fn == "mean" else ",.0f")
    fig6.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white", yaxis_title=selected_extra)
    st.plotly_chart(fig6, use_container_width=True, config=PLOTLY_CONFIG)

# ------------------------------------------------------------------
# TAB 4 — RAW DATA
# ------------------------------------------------------------------
with tab4:
    st.subheader("Filtered Data")
    st.dataframe(df, use_container_width=True, height=500)
    st.download_button("Download filtered CSV", df.to_csv(index=False).encode(), "filtered_data.csv", "text/csv")

# ------------------------------------------------------------------
# TAB 5 — DAILY ABSTRACT
# ------------------------------------------------------------------
with tab5:
    st.subheader("Daily Abstract")
    if abstract_df is not None:
        st.caption("EPBPD, EPKM and Kilometric efficiency are the **official values from your workbook's Abstract sheet** "
                    "— not affected by the Depot/Shift/Service filters (they're already route-level totals).")
    else:
        st.warning("No 'Abstract' sheet found in this file — showing EPBPD/EPKM/efficiency computed directly "
                   "from the Master File instead (approximate for EPBPD, since its exact bus-count basis isn't in the row data).")

    merged_display = merged.copy()
    merged_display["Date"] = merged_display["Date"].dt.strftime("%d-%m-%Y")

    st.dataframe(merged_display, use_container_width=True, height=520)
    st.download_button("Download daily abstract CSV", merged.to_csv(index=False).encode(),
                        "daily_abstract.csv", "text/csv")