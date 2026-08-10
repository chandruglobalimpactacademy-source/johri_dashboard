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

# --- Tamil Nadu Government Public Holidays 2026 (official list) — edit/extend for other years. ---
HOLIDAYS = {
    "2026-01-01": "New Year's Day",
    "2026-01-15": "Pongal",
    "2026-01-16": "Thiruvalluvar Day",
    "2026-01-17": "Uzhavar Thirunal",
    "2026-01-26": "Republic Day",
    "2026-02-01": "Thai Poosam",
    "2026-03-19": "Telugu New Year's Day",
    "2026-03-21": "Ramzan (Idu'l Fitr)",
    "2026-03-31": "Mahaveer Jayanthi",
    "2026-04-01": "Annual Closing of Accounts",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Tamil New Year's Day / Dr. B.R. Ambedkar's Birthday",
    "2026-05-01": "May Day",
    "2026-05-28": "Bakrid (Idul Azha)",
    "2026-06-26": "Muharram (Yaom-E-Shahadath)",
    "2026-08-15": "Independence Day",
    "2026-08-26": "Milad-un-Nabi (Prophet's Birthday)",
    "2026-09-04": "Krishna Jayanthi",
    "2026-09-14": "Vinayagar Chathurthi",
    "2026-10-02": "Gandhi Jayanthi",
    "2026-10-19": "Ayutha Pooja",
    "2026-10-20": "Vijaya Dasami",
    "2026-11-08": "Deepavali",
    "2026-12-25": "Christmas",
}
holiday_dates = {pd.Timestamp(k): v for k, v in HOLIDAYS.items()}

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

# --- depot ↔ service relationships + a colored-circle marker per depot, built BEFORE filtering ---
CIRCLE_PALETTE = ["🔵", "🔴", "🟢", "🟡", "🟣", "🟠", "⚫", "🟤"]
_all_depots_unfiltered = sorted(df["Depot"].unique())
depot_emoji = {d: CIRCLE_PALETTE[i % len(CIRCLE_PALETTE)] for i, d in enumerate(_all_depots_unfiltered)}
depot_service_map = {d: sorted(df.loc[df["Depot"] == d, "Service"].unique()) for d in _all_depots_unfiltered}
service_depot_map = {}
for d, svcs in depot_service_map.items():
    for s in svcs:
        service_depot_map.setdefault(s, []).append(d)

# ------------------------------------------------------------------
# SIDEBAR FILTERS — friendly panel
# ------------------------------------------------------------------
d_min, d_max = df["Date"].min().date(), df["Date"].max().date()
all_depots = sorted(df["Depot"].unique())
all_routes = sorted(df["Route"].unique())
all_shifts = sorted(df["Shift"].unique())
all_services = sorted(df["Service"].unique())

defaults = {"start": d_min, "end": d_max, "depots": all_depots, "routes": all_routes,
            "shifts": all_shifts, "services": all_services}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

st.sidebar.markdown("## 🔍 Filters")

# --- reset button placed FIRST, before any widget with these keys exists ---
if st.sidebar.button("↺ Reset all filters", use_container_width=True):
    for k, v in defaults.items():
        st.session_state[k] = v
    st.session_state["_prev_depots"] = defaults["depots"]

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

# --- reusable "select all" multiselect block (used for Route/Shift) ---
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

st.session_state.setdefault("_prev_depots", st.session_state.depots)

# --- Depot picker: choosing a depot auto-adds its services; removing it auto-removes them ---
def _on_depot_change():
    new_depots = st.session_state.depots
    prev = st.session_state.get("_prev_depots", new_depots)
    added, removed = set(new_depots) - set(prev), set(prev) - set(new_depots)
    cur = set(st.session_state.services)
    for d in added:
        cur |= set(depot_service_map[d])
    for d in removed:
        cur -= set(depot_service_map[d])
    st.session_state.services = sorted(cur)
    st.session_state["_prev_depots"] = new_depots

st.sidebar.caption("Depot   " + "  ".join(f"{depot_emoji[d]} {d}" for d in all_depots))
c1, c2 = st.sidebar.columns(2)
if c1.button("Select all", key="depots_all", use_container_width=True):
    st.session_state.depots = all_depots
    st.session_state.services = sorted({s for d in all_depots for s in depot_service_map[d]})
    st.session_state["_prev_depots"] = all_depots
if c2.button("Clear", key="depots_clear", use_container_width=True):
    st.session_state.depots = []
    st.session_state.services = []
    st.session_state["_prev_depots"] = []
depots = st.sidebar.multiselect(
    "Depot", all_depots, key="depots", label_visibility="collapsed",
    format_func=lambda d: f"{depot_emoji[d]} {d}", on_change=_on_depot_change,
)
st.sidebar.caption(f"{len(depots)}/{len(all_depots)} selected")
st.sidebar.divider()

routes = picker("Route", all_routes, "routes")
shifts = picker("Shift", all_shifts, "shifts")

# --- Service picker: same color-circle as its depot; emptying a depot's services drops that depot ---
def _on_service_change():
    new_services = set(st.session_state.services)
    remaining = [d for d in st.session_state.depots if any(s in new_services for s in depot_service_map[d])]
    st.session_state.depots = remaining
    st.session_state["_prev_depots"] = remaining

st.sidebar.caption("Service")
c1, c2 = st.sidebar.columns(2)
if c1.button("Select all", key="services_all", use_container_width=True):
    st.session_state.services = (
        sorted({s for d in st.session_state.depots for s in depot_service_map[d]})
        if st.session_state.depots else all_services
    )
if c2.button("Clear", key="services_clear", use_container_width=True):
    st.session_state.services = []
    st.session_state.depots = []
    st.session_state["_prev_depots"] = []
services = st.sidebar.multiselect(
    "Service", all_services, key="services", label_visibility="collapsed",
    format_func=lambda s: f"{depot_emoji.get(service_depot_map.get(s, [None])[0], '')} {s}",
    on_change=_on_service_change,
)
st.sidebar.caption(f"{len(services)}/{len(all_services)} selected")

# --- apply filters ---
df = df[
    (df["Date"] >= pd.to_datetime(start)) & (df["Date"] <= pd.to_datetime(end))
    & df["Depot"].isin(depots) & df["Route"].isin(routes) & df["Shift"].isin(shifts) & df["Service"].isin(services)
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
    st.subheader("Johari Window of Services – Avg EPKM vs EPBPD")

    # --- Tamil Nadu Govt 2026 holiday list — see HOLIDAYS near the top of the file to edit/extend ---
    st.caption("Hover a point for the full breakdown. Holiday flags use the official Tamil Nadu Government "
               "2026 public holiday list (edit `HOLIDAYS` near the top of the code to add other years).")

    agg_df = df.groupby(["Service", "Depot"]).agg({
        "EPKM": "mean",
        "EPBPD": "mean",
        "Total Passengers": "mean",
        "KM Efficency": "mean",
    }).reset_index()

    # --- full metric breakdown + weekday/holiday info per Service+Depot, for the hover card ---
    extra = df.groupby(["Service", "Depot"]).agg(
        Collection=("Collection With Reimbursement", "sum"),
        Pax=("Total Passengers", "sum"),
        OpKM=("Operated KM", "sum"),
        SchKM=("Scheduled KM", "sum"),
        SchTrip=("Scheduled Trip", "sum"),
        ZeroTicket=("Zero Value Ticket", "sum"),
        TicketPax=("Ticket Passenger", "sum"),
        Senior=("Senior Citizens", "sum"),
        Trips=("Operated Trip", "sum"),
        DaysCovered=("Date", "nunique"),
        MinDate=("Date", "min"),
        MaxDate=("Date", "max"),
    ).reset_index()
    extra["EffPct"] = extra["OpKM"] / extra["SchKM"] * 100
    extra["TripsPerDay"] = extra["Trips"] / extra["DaysCovered"]

    join_unique = lambda s: ", ".join(sorted(s.astype(str).unique()))
    extra["TypeList"] = df.groupby(["Service", "Depot"])["Type"].apply(join_unique).values
    extra["ShiftList"] = df.groupby(["Service", "Depot"])["Shift"].apply(join_unique).values

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    def weekdays_for(group):
        names = set(group.dt.day_name())
        return ", ".join(sorted(names, key=weekday_order.index))
    extra["Weekdays"] = df.groupby(["Service", "Depot"])["Date"].apply(weekdays_for).values

    def holidays_for(group):
        hits = [f"{d.strftime('%d-%b')} ({holiday_dates[d]})" for d in group.unique() if d in holiday_dates]
        return "; ".join(hits) if hits else "None in range"
    extra["Holidays"] = df.groupby(["Service", "Depot"])["Date"].apply(holidays_for).values

    extra["DateRange"] = extra["MinDate"].dt.strftime("%d-%b-%Y") + " to " + extra["MaxDate"].dt.strftime("%d-%b-%Y")

    agg_df = agg_df.merge(extra, on=["Service", "Depot"])

    def get_dynamic_shape(p):
        if p < 500:
            return "circle"
        elif p < 800:
            return "square"
        elif p < 1100:
            return "diamond"
        elif p < 1400:
            return "triangle-up"
        elif p < 1500:
            return "cross"
        else:
            return "star"

    def get_color(km_eff):
        try:
            km_eff = float(km_eff)
            if km_eff < 85:
                return "red"
            elif km_eff < 95:
                return "blue"
            elif km_eff < 99:
                return "green"
            else:
                return "orange"
        except Exception:
            return "gray"

    from itertools import cycle
    all_depots_j = sorted(df["Depot"].unique())
    depot_colors = dict(zip(all_depots_j, cycle([
        "#1f77b4", "black", "#2ca02c", "#d62728", "#9467bd", "#FF4C4C",
        "#e377c2", "#8c564b", "#bcbd22", "#17becf", "#ff7f0e", "#7f7f7f",
    ])))

    fig = go.Figure()

    # --- Depot color legend ---
    for depot, c in depot_colors.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=14, color=c, symbol="circle"),
            name=f"{depot} (Depot Color)", legendgroup="Depot",
        ))

    agg_df["Shape"] = agg_df["Total Passengers"].apply(get_dynamic_shape)
    agg_df["Color"] = agg_df["KM Efficency"].apply(get_color)
    agg_df["DepotColor"] = agg_df["Depot"].map(depot_colors)

    epbpd_threshold = (agg_df["EPBPD"].min() + agg_df["EPBPD"].max()) / 2
    epkm_threshold = 80

    x_min = agg_df["EPBPD"].min() - 1000
    x_max = agg_df["EPBPD"].max() + 1000
    y_min = agg_df["EPKM"].min() - 10
    y_max = agg_df["EPKM"].max() + 10

    # --- Passenger-load shape legend ---
    shape_legend_map = {
        "circle": "< 500 Passengers",
        "square": "500–800 Passengers",
        "diamond": "800–1100 Passengers",
        "triangle-up": "1100–1400 Passengers",
        "cross": "1400–1500 Passengers",
        "star": "≥ 1500 Passengers",
    }
    for shape_symbol, label in shape_legend_map.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=14, symbol=shape_symbol, color="black"),
            name=label, legendgroup="Shape",
        ))

    # --- KM Efficiency color legend ---
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                             marker=dict(size=14, color="red"), name="< 85% KM Efficiency", legendgroup="Color"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                             marker=dict(size=14, color="blue"), name="85%–95% KM Efficiency", legendgroup="Color"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                             marker=dict(size=14, color="green"), name="96%–99% KM Efficiency", legendgroup="Color"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers",
                             marker=dict(size=14, color="orange"), name="100% KM Efficiency", legendgroup="Color"))

    # --- Quadrant background colors ---
    fig.add_shape(type="rect", x0=x_min, x1=epbpd_threshold, y0=y_min, y1=epkm_threshold,
                  fillcolor="rgba(255, 0, 0, 0.1)", line=dict(width=0))
    fig.add_shape(type="rect", x0=epbpd_threshold, x1=x_max, y0=epkm_threshold, y1=y_max,
                  fillcolor="rgba(0, 255, 0, 0.1)", line=dict(width=0))
    fig.add_shape(type="rect", x0=x_min, x1=epbpd_threshold, y0=epkm_threshold, y1=y_max,
                  fillcolor="rgba(255, 255, 0, 0.1)", line=dict(width=0))
    fig.add_shape(type="rect", x0=epbpd_threshold, x1=x_max, y0=y_min, y1=epkm_threshold,
                  fillcolor="rgba(173, 216, 230, 0.1)", line=dict(width=0))

    # --- Real data plot ---
    for shape in agg_df["Shape"].unique():
        for color in agg_df["Color"].unique():
            sub_df = agg_df[(agg_df["Shape"] == shape) & (agg_df["Color"] == color)]
            if sub_df.empty:
                continue
            customdata = sub_df[[
                "Depot", "Collection", "Pax", "OpKM", "EffPct", "ZeroTicket", "TicketPax",
                "Senior", "Trips", "DaysCovered", "DateRange", "Weekdays", "Holidays",
                "SchKM", "SchTrip", "TypeList", "ShiftList", "TripsPerDay",
            ]].values
            fig.add_trace(go.Scatter(
                x=sub_df["EPBPD"], y=sub_df["EPKM"],
                mode="markers+text",
                marker=dict(size=16, symbol=shape, color=color, line=dict(width=1.5, color="DarkSlateGrey")),
                text=sub_df["Service"], texttemplate="%{text}", textposition="top center",
                textfont=dict(color=sub_df["DepotColor"], family="Arial Black, Arial, sans-serif", size=18),
                customdata=customdata,
                hovertemplate=(
                    "<b>Service:</b> %{text}  (Depot: %{customdata[0]})<br>"
                    "<b>Type:</b> %{customdata[15]} &nbsp; <b>Shift:</b> %{customdata[16]}<br>"
                    "<b>Avg EPKM:</b> %{y:.2f} ₹/km &nbsp; <b>Avg EPBPD:</b> %{x:,.0f} ₹/day<br>"
                    "<b>KM Efficiency:</b> %{customdata[4]:.1f}%<br>"
                    "<b>Total Collection:</b> ₹%{customdata[1]:,.0f}<br>"
                    "<b>Total Passengers:</b> %{customdata[2]:,.0f}<br>"
                    "<b>Scheduled KM:</b> %{customdata[13]:,.1f} &nbsp; <b>Operated KM:</b> %{customdata[3]:,.1f}<br>"
                    "<b>Scheduled Trips:</b> %{customdata[14]:,.0f} &nbsp; <b>Operated Trips:</b> %{customdata[8]:,.0f}<br>"
                    "<b>Trips/day (avg):</b> %{customdata[17]:.1f}<br>"
                    "<b>Zero Value Tickets:</b> %{customdata[5]:,.0f} &nbsp; "
                    "<b>Ticket Passengers:</b> %{customdata[6]:,.0f} &nbsp; "
                    "<b>Senior Citizens:</b> %{customdata[7]:,.0f}<br>"
                    "<b>Days covered:</b> %{customdata[9]}<br>"
                    "<b>Date range:</b> %{customdata[10]}<br>"
                    "<b>Weekdays operated:</b> %{customdata[11]}<br>"
                    "<b>Holidays in range:</b> %{customdata[12]}"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

    # --- Quadrant lines ---
    fig.add_shape(type="line", x0=epbpd_threshold, x1=epbpd_threshold, y0=y_min, y1=y_max,
                  line=dict(dash="dash", color="green", width=2))
    fig.add_shape(type="line", x0=x_min, x1=x_max, y0=epkm_threshold, y1=epkm_threshold,
                  line=dict(dash="dash", color="green", width=2))
    fig.add_annotation(x=epbpd_threshold, y=y_max, text=f"{epbpd_threshold:.0f}",
                        showarrow=True, arrowhead=2, ax=40, ay=-40)
    fig.add_annotation(x=x_max, y=epkm_threshold, text=f"{epkm_threshold}",
                        showarrow=True, arrowhead=2, ax=-60, ay=30)

    fig.update_layout(
        title=dict(text="Johari Window – Average EPKM vs EPBPD per Service",
                   font=dict(size=22, family="Arial Black, Arial, sans-serif", color="black")),
        xaxis=dict(title=dict(text="Average EPBPD (₹/bus/day)", font=dict(size=18, family="Arial", color="black")),
                   tickfont=dict(size=15, family="Arial", color="black"),
                   showline=True, linecolor="black", linewidth=2, range=[x_min, x_max], tickformat=",d"),
        yaxis=dict(title=dict(text="Average EPKM (₹/km)", font=dict(size=18, family="Arial", color="black")),
                   tickfont=dict(size=15, family="Arial", color="black"),
                   showline=True, linecolor="black", linewidth=2, range=[y_min, y_max], tickformat=",d"),
        legend=dict(font=dict(size=16, family="Arial Black, Arial, sans-serif", color="black"),
                    bgcolor="rgba(255,255,255,0.8)", bordercolor="black", borderwidth=1.5, itemsizing="constant"),
        legend_title_text=None,
        plot_bgcolor="white", paper_bgcolor="white",
        height=750, width=1150, margin=dict(r=200),
    )

    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

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

    if group_by in ("Service", "Depot"):
        join_unique = lambda s: ", ".join(sorted(s.astype(str).unique()))
        other_dim = "Depot" if group_by == "Service" else "Service"
        detail = df.groupby(group_cols).agg(
            TypeList=("Type", join_unique),
            ShiftList=("Shift", join_unique),
            OtherList=(other_dim, join_unique),
            SchTrip=("Scheduled Trip", "sum"),
        ).reset_index()
        base = base.merge(detail, on=group_cols)
        base["Weekday"] = base["Date"].dt.day_name()
        base["HolidayFlag"] = base["Date"].map(lambda d: holiday_dates.get(d, "No"))

        custom_cols = [
            "OtherList", "TypeList", "ShiftList", "Weekday", "HolidayFlag",
            "Collection", "Pax", "SchKM", "OpKM", "SchTrip", "Trips",
            "ZeroTicket", "TicketPax", "Senior",
        ]
        other_label = "Depot" if group_by == "Service" else "Service"

        if group_by == "Service":
            base["Legend"] = base["Service"].map(
                lambda s: f"{s} ({depot_emoji.get(service_depot_map.get(s, [None])[0], '')} "
                          f"{service_depot_map.get(s, ['?'])[0]})"
            )
            legend_col = "Legend"
        else:
            legend_col = group_by

        if group_by == "None":
            fig2 = px.line(base, x="Date", y="value", markers=True, custom_data=custom_cols)
        else:
            fig2 = px.line(base, x="Date", y="value", color=legend_col, markers=True, custom_data=custom_cols)

        name_line = (
            f"<b>{group_by}:</b> %{{fullData.name}}<br>" if group_by == "Service"
            else f"<b>{group_by}:</b> %{{fullData.name}}  ({other_label}: %{{customdata[0]}})<br>"
        )
        fig2.update_traces(hovertemplate=(
            name_line +
            "<b>Date:</b> %{x|%d-%b-%Y} (%{customdata[3]}) &nbsp; <b>Holiday:</b> %{customdata[4]}<br>"
            "<b>Type:</b> %{customdata[1]} &nbsp; <b>Shift:</b> %{customdata[2]}<br>"
            f"<b>{metric}:</b> %{{y:,.2f}}<br>"
            "<b>Collection:</b> ₹%{customdata[5]:,.0f} &nbsp; <b>Passengers:</b> %{customdata[6]:,.0f}<br>"
            "<b>Scheduled KM:</b> %{customdata[7]:,.1f} &nbsp; <b>Operated KM:</b> %{customdata[8]:,.1f}<br>"
            "<b>Scheduled Trips:</b> %{customdata[9]:,.0f} &nbsp; <b>Operated Trips:</b> %{customdata[10]:,.0f}<br>"
            "<b>Zero Value Tickets:</b> %{customdata[11]:,.0f} &nbsp; "
            "<b>Ticket Passengers:</b> %{customdata[12]:,.0f} &nbsp; "
            "<b>Senior Citizens:</b> %{customdata[13]:,.0f}"
            "<extra></extra>"
        ))
    else:
        fig2 = px.line(base, x="Date", y="value", markers=True)

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
