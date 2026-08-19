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

# --- Text size control — accessibility, helps older/low-vision users read labels/tables/charts UI ---
st.sidebar.markdown("## 🔤 Text Size")
font_choice = st.sidebar.select_slider(
    "Text size", options=["Normal", "Large", "Extra Large"], value="Normal", key="font_choice",
)
_font_px = {"Normal": 16, "Large": 20, "Extra Large": 24}[font_choice]
st.markdown(f"<style>html {{ font-size: {_font_px}px; }}</style>", unsafe_allow_html=True)
st.sidebar.divider()

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

from itertools import cycle
depot_colors = dict(zip(_all_depots_unfiltered, cycle([
    "#1f77b4", "black", "#2ca02c", "#d62728", "#9467bd", "#FF4C4C",
    "#e377c2", "#8c564b", "#bcbd22", "#17becf", "#ff7f0e", "#7f7f7f",
])))
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
all_types = sorted(df["Type"].unique())

defaults = {"start": d_min, "end": d_max, "depots": all_depots, "routes": all_routes,
            "shifts": all_shifts, "services": all_services, "types": all_types}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

st.sidebar.markdown("## 🔍 Filters")

# --- reset button placed FIRST, before any widget with these keys exists ---
if st.sidebar.button("↺ Reset all filters", use_container_width=True):
    for k, v in defaults.items():
        st.session_state[k] = v
    st.session_state["_prev_depots"] = defaults["depots"]

# --- pending actions from the Service picker's buttons that also touch `depots` —
# must be applied here, BEFORE the depots widget is instantiated below, or Streamlit
# raises "cannot be modified after widget is instantiated". ---
_pending = st.session_state.pop("_pending_service_action", None)
if _pending == "clear":
    st.session_state.services = []
    st.session_state.depots = []
    st.session_state["_prev_depots"] = []
elif _pending == "select_all":
    st.session_state.services = (
        sorted({s for d in st.session_state.depots for s in depot_service_map[d]})
        if st.session_state.depots else all_services
    )

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

# --- reusable "select all" multiselect block (used for Shift only) ---
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
types = picker("Type", all_types, "types")

# --- Service picker: same color-circle as its depot; emptying a depot's services drops that depot ---
def _on_service_change():
    new_services = set(st.session_state.services)
    remaining = [d for d in st.session_state.depots if any(s in new_services for s in depot_service_map[d])]
    st.session_state.depots = remaining
    st.session_state["_prev_depots"] = remaining

st.sidebar.caption("Service")
c1, c2 = st.sidebar.columns(2)
if c1.button("Select all", key="services_all", use_container_width=True):
    st.session_state["_pending_service_action"] = "select_all"
    st.rerun()
if c2.button("Clear", key="services_clear", use_container_width=True):
    st.session_state["_pending_service_action"] = "clear"
    st.rerun()
services = st.sidebar.multiselect(
    "Service", all_services, key="services", label_visibility="collapsed",
    format_func=lambda s: f"{depot_emoji.get(service_depot_map.get(s, [None])[0], '')} {s} "
                           f"({service_depot_map.get(s, ['?'])[0]})",
    on_change=_on_service_change,
)
st.sidebar.caption(f"{len(services)}/{len(all_services)} selected")

# --- apply filters ---
df = df[
    (df["Date"] >= pd.to_datetime(start)) & (df["Date"] <= pd.to_datetime(end))
    & df["Depot"].isin(depots) & df["Route"].isin(routes) & df["Shift"].isin(shifts) & df["Service"].isin(services)
    & df["Type"].isin(types)
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

TAB_LABELS = ["🎯 Johari Window", "📈 Trends", "🏢 Depot Comparison", "📋 Data", "📆 Daily Abstract", "🔍 Observation"]
st.session_state.setdefault("active_tab", TAB_LABELS[0])
if "_redirect_to" in st.session_state:
    st.session_state["active_tab"] = st.session_state.pop("_redirect_to")

active_tab = st.radio("Section", TAB_LABELS, key="active_tab", horizontal=True, label_visibility="collapsed")
st.divider()

# ------------------------------------------------------------------
# TAB 1 — JOHARI WINDOW (cleaned up)
# ------------------------------------------------------------------
if active_tab == TAB_LABELS[0]:
    _avg_epbpd = pd.to_numeric(merged["EPBPD"], errors="coerce").mean()
    _period_label = f"{start.strftime('%B %Y')}" if start.strftime('%B %Y') == end.strftime('%B %Y') else f"{start} → {end}"
    _total_services = df["Service"].nunique()
    _total_depots = df["Depot"].nunique()
    _dep_svc_counts = df.groupby("Depot")["Service"].nunique().sort_index()
    _bus_days = merged["No of services operated per day"].sum()
    _avg_buses_per_day = merged["No of services operated per day"].mean()
    _sched_km_per_bus_day = total_sched_km / _bus_days if _bus_days else 0
    _avg_pax_per_bus_day = pd.to_numeric(
        merged["Total Passengers  per bus per day (Including women)"], errors="coerce"
    ).mean()

    st.markdown(f"## Johari Window of Services &nbsp;|&nbsp; {_period_label} &nbsp;|&nbsp; Route No: {route_val}")
    st.markdown(
        f"<span style='font-size:1.3rem'>"
        f"<b>Total No. of Services:</b> {_total_services} &nbsp;|&nbsp; <b>Total No. of Depots:</b> {_total_depots}"
        f"</span>", unsafe_allow_html=True,
    )
    st.markdown(
        "<span style='font-size:1.3rem'>" + " &nbsp;|&nbsp; ".join(
            f"<span style='white-space:nowrap'><b>{depot_emoji.get(d,'')} {d} – No. of Services:</b> {c}</span>"
            for d, c in _dep_svc_counts.items()
        ) + "</span>", unsafe_allow_html=True,
    )
    st.markdown(
        f"<span style='font-size:1.3rem'>"
        f"<b>Avg. EPBPD:</b> ₹{_avg_epbpd:,.0f} &nbsp;|&nbsp; <b>Avg. EPKM:</b> ₹{weighted_epkm:.2f} &nbsp;|&nbsp; "
        f"<b>Avg. No. of buses/day:</b> {_avg_buses_per_day:.1f} &nbsp;|&nbsp; "
        f"<b>Scheduled kms per bus/day:</b> {_sched_km_per_bus_day:,.1f} &nbsp;|&nbsp; "
        f"<b>Avg. KM efficiency:</b> {weighted_eff:.1f}% &nbsp;|&nbsp; "
        f"<b>Avg. Passengers carried/bus/day:</b> {_avg_pax_per_bus_day:,.1f}"
        f"</span>", unsafe_allow_html=True,
    )


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
        return f"<b>Government Holiday(s):</b> {'; '.join(hits)}<br>" if hits else ""
    extra["Holidays"] = df.groupby(["Service", "Depot"])["Date"].apply(holidays_for).values

    extra["DateRange"] = extra["MinDate"].dt.strftime("%d-%b-%Y") + " to " + extra["MaxDate"].dt.strftime("%d-%b-%Y")

    full_range = pd.date_range(start, end)
    def not_operated_for(g):
        by_date = g.groupby("Date")["Shift"].apply(set)
        entries = []
        for d in full_range:
            present = by_date.get(d, set())
            if "AS" in present:
                continue  # AS is a full-day shift — running it means nothing is missed
            missing = {"AM", "PM"} - present
            if missing:
                entries.append(f"{d.strftime('%d-%b')} ({', '.join(sorted(missing))})")
        if not entries:
            return "None — ran all shifts every day in range"
        chunks = ["; ".join(entries[i:i+3]) for i in range(0, len(entries), 3)]
        return "<br>".join(chunks)
    extra["NotOperated"] = df.groupby(["Service", "Depot"]).apply(not_operated_for).values

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

    all_depots_j = sorted(df["Depot"].unique())

    fig = go.Figure()

    # --- Depot color legend ---
    for depot, c in depot_colors.items():
        _svcs = sorted(df.loc[df["Depot"] == depot, "Service"].unique())
        if _svcs:
            _lines = [", ".join(_svcs[i:i+8]) for i in range(0, len(_svcs), 8)]
            _svc_str = "<br>" + "<br>".join(_lines)
        else:
            _svc_str = "<br>no services in current filter"
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(size=14, color=c, symbol="circle"),
            name=f"{depot}{_svc_str}", legendgroup="Depot",
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
                "Senior", "Trips", "DaysCovered", "DateRange", "NotOperated", "Holidays",
                "SchKM", "SchTrip", "TypeList", "ShiftList", "TripsPerDay", "Service",
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
                    "<b>Scheduled KM:</b> %{customdata[13]:,.1f} &nbsp; <b>Operated KM:</b> %{customdata[3]:,.1f}<br>"
                    "<b>Scheduled Trips:</b> %{customdata[14]:,.0f} &nbsp; <b>Operated Trips:</b> %{customdata[8]:,.0f}<br>"
                    "<b>Trips/day (avg):</b> %{customdata[17]:.1f}<br>"
                    "<b>Zero Value Tickets:</b> %{customdata[5]:,.0f} &nbsp; "
                    "<b>Ticket Passengers:</b> %{customdata[6]:,.0f} &nbsp; "
                    "<b>Senior Citizens:</b> %{customdata[7]:,.0f}<br>"
                    "<b>Date range:</b> %{customdata[10]}<br>"
                    "<b>Dates with a missed shift:</b> %{customdata[11]}<br>"
                    "%{customdata[12]}"
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
                    bgcolor="rgba(255,255,255,0.8)", bordercolor="black", borderwidth=1.5, itemsizing="constant",
                    x=1.02, y=0.97, xanchor="left", yanchor="top"),
        plot_bgcolor="white", paper_bgcolor="white",
        height=750, width=1150, margin=dict(r=200),
    )

    fig.add_annotation(
        xref="paper", yref="paper", x=1.15, y=1.0, xanchor="center", yanchor="bottom",
        text="<b>LEGEND</b>", showarrow=False,
        font=dict(size=18, family="Arial Black, Arial, sans-serif", color="black"),
    )

    johari_event = st.plotly_chart(
        fig, use_container_width=True, config=PLOTLY_CONFIG,
        on_select="rerun", selection_mode="points", key="johari_chart",
    )

    clicked_points = (johari_event or {}).get("selection", {}).get("points", [])
    if clicked_points:
        cd = clicked_points[0].get("customdata")
        if cd and len(cd) >= 19:
            st.session_state["trend_focus_service"] = cd[18]
            st.session_state["_force_trend_focus"] = True
            st.session_state["_redirect_to"] = TAB_LABELS[1]
            st.rerun()

# ------------------------------------------------------------------
# TAB 2 — TRENDS OVER TIME
# ------------------------------------------------------------------
elif active_tab == TAB_LABELS[1]:
    st.subheader("Daily Trend")

    focus_service = st.session_state.get("trend_focus_service")
    force_now = st.session_state.pop("_force_trend_focus", False)

    if focus_service:
        bc1, bc2 = st.columns([4, 1])
        bc1.info(f"Showing only Service **'{focus_service}'** (selected from the Johari Window). "
                 "Use the box below to add other services back, or clear it and pick 'Select all'.")
        if bc2.button("← Back to Johari Window"):
            st.session_state["_redirect_to"] = TAB_LABELS[0]
            st.rerun()

    if force_now:
        st.session_state["group_by_radio"] = "Service"
    group_by = st.radio("Break down by", ["Depot", "Service", "None"], horizontal=True, key="group_by_radio")

    scope_df = df
    if group_by == "Service":
        service_options_here = sorted(df["Service"].unique())
        if force_now and focus_service in service_options_here:
            st.session_state["trend_services_multiselect"] = [focus_service]
        chosen_services = st.multiselect(
            "Services to show (others are hidden — add them back here)",
            service_options_here, default=service_options_here, key="trend_services_multiselect",
            format_func=lambda s: f"{depot_emoji.get(service_depot_map.get(s, [None])[0], '')} {s} "
                                   f"({service_depot_map.get(s, ['?'])[0]})",
        )
        scope_df = df[df["Service"].isin(chosen_services)]
        if scope_df.empty:
            st.warning("No services selected — pick at least one above.")
            st.stop()

    metric_options = [
        "Combined EPKM + EPBPD", "Collection Total", "Total Passengers", "EPKM", "KM Efficency", "EPBPD",
        "Zero Value Ticket", "Ticket Passenger", "Senior Citizens", "Operated KM",
        "No of services operated per day", "number of trips operated per day",
        "Total Passengers per bus per day",
    ]
    metric = st.selectbox("Metric", metric_options)

    if metric == "Combined EPKM + EPBPD":
        _t2_period_label = f"{start.strftime('%B %Y')}" if start.strftime('%B %Y') == end.strftime('%B %Y') else f"{start} → {end}"
        st.markdown(f"## Daily Revenue Parameter – {_t2_period_label}")

        _scope_pairs = sorted(
            scope_df[["Service", "Depot"]].drop_duplicates().itertuples(index=False, name=None)
        )
        _badges = "".join(
            f'<span style="background:{depot_colors.get(dep, "#888")};color:white;padding:3px 10px;'
            f'border-radius:12px;margin:3px 4px 3px 0;display:inline-block;font-size:13px;">'
            f'{depot_emoji.get(dep, "")} {svc} ({dep})</span>'
            for svc, dep in _scope_pairs
        )
        st.markdown(f"<div style='margin:0 0 4px 0;line-height:1.6;'>{_badges}</div>", unsafe_allow_html=True)

        if group_by != "Service":
            st.caption("Tip: switch 'Break down by' to Service to scope this to one bus/service — "
                       "otherwise all currently filtered services are combined together below.")

        # --- shift-status box, right under Metric — commented out, uncomment to re-enable ---
        # _scope_shifts_early = set(scope_df["Shift"].unique())
        # _shift_by_date = scope_df.groupby("Date")["Shift"].apply(lambda s: sorted(s.unique()))
        # def _status_for(d):
        #     present = _shift_by_date.get(d, [])
        #     if not present:
        #         return "Not run (no shifts operated)"
        #     missing = sorted(_scope_shifts_early - set(present))
        #     txt = "Running: " + ", ".join(present)
        #     txt += (" — Not running: " + ", ".join(missing)) if missing else " — (all shifts running)"
        #     return txt
        # box_date = st.session_state.get("trend_box_date")
        # box_dt = pd.to_datetime(box_date, errors="coerce") if box_date else None
        # if box_dt is None or box_dt not in _shift_by_date.index:
        #     box_dt = sorted(_shift_by_date.index)[0]
        #     box_date = box_dt.strftime("%Y-%m-%d")
        # box_status = _status_for(box_dt)
        # st.info(f"**Shift status — {box_date}:** {box_status}")

        join_unique = lambda s: ", ".join(sorted(s.astype(str).unique()))

        daily_c = scope_df.groupby("Date").agg(
            Collection=("Collection With Reimbursement", "sum"),
            OpKM=("Operated KM", "sum"),
            Services=("Service", "nunique"),
            Pax=("Total Passengers", "sum"),
            SchKM=("Scheduled KM", "sum"),
            SchTrip=("Scheduled Trip", "sum"),
            Trips=("Operated Trip", "sum"),
            ZeroTicket=("Zero Value Ticket", "sum"),
            TicketPax=("Ticket Passenger", "sum"),
            Senior=("Senior Citizens", "sum"),
            TypeList=("Type", join_unique),
            ShiftList=("Shift", join_unique),
        ).reset_index()
        daily_c["EPBPD"] = daily_c["Collection"] / daily_c["Services"]
        daily_c["EPKM"] = daily_c["Collection"] / daily_c["OpKM"]

        if group_by != "Service":
            # whole-route view — safe to use the SAME authoritative EPBPD/EPKM as KPI strip &
            # Daily Abstract tab (Abstract sheet if present); doesn't apply once scoped to specific
            # service(s), since Abstract-sheet figures are route totals, not per-service.
            auth = merged[["Date", "EPBPD", "EPKM"]].rename(columns={"EPBPD": "EPBPD_auth", "EPKM": "EPKM_auth"})
            daily_c = daily_c.merge(auth, on="Date", how="left")
            daily_c["EPBPD"] = pd.to_numeric(daily_c["EPBPD_auth"], errors="coerce").fillna(daily_c["EPBPD"])
            daily_c["EPKM"] = pd.to_numeric(daily_c["EPKM_auth"], errors="coerce").fillna(daily_c["EPKM"])
        daily_c["Weekday"] = daily_c["Date"].dt.day_name()
        daily_c["HolidayFlag"] = daily_c["Date"].map(lambda d: holiday_dates.get(d, "No"))

        # --- per-shift breakdown, same concept as the single-metric trend view — scoped to same services ---
        shift_stats_c = scope_df.groupby(["Date", "Shift"]).agg(
            Collection=("Collection With Reimbursement", "sum"),
            Pax=("Total Passengers", "sum"),
            SchKM=("Scheduled KM", "sum"),
            OpKM=("Operated KM", "sum"),
            SchTrip=("Scheduled Trip", "sum"),
            Trips=("Operated Trip", "sum"),
            ZeroTicket=("Zero Value Ticket", "sum"),
            TicketPax=("Ticket Passenger", "sum"),
            Senior=("Senior Citizens", "sum"),
        ).reset_index()

        def _shift_block(g):
            blocks = []
            for r in g.sort_values("Shift").itertuples():
                km_eff = (r.OpKM / r.SchKM * 100) if r.SchKM else 0
                avg_pax = (r.Pax / r.Trips) if r.Trips else 0
                blocks.append(
                    f"<b>— {r.Shift} shift —</b><br>"
                    f"Collection: ₹{r.Collection:,.0f} &nbsp; Passengers: {r.Pax:,.0f}<br>"
                    f"Scheduled KM: {r.SchKM:,.1f} &nbsp; Operated KM: {r.OpKM:,.1f} &nbsp; KM Efficiency: {km_eff:.1f}%<br>"
                    f"Scheduled Trips: {r.SchTrip:,.0f} &nbsp; Operated Trips: {r.Trips:,.0f} &nbsp; Avg Passengers/Trip: {avg_pax:,.1f}<br>"
                    f"Zero Value Tickets: {r.ZeroTicket:,.0f} &nbsp; Ticket Passengers: {r.TicketPax:,.0f} "
                    f"&nbsp; Senior Citizens: {r.Senior:,.0f}"
                )
            return "<br><br>".join(blocks)

        shift_block_c = shift_stats_c.groupby("Date").apply(_shift_block).reset_index(name="ShiftBreakdown")
        daily_c = daily_c.merge(shift_block_c, on="Date", how="left")

        # --- per-date shift status: AS is a full-day shift on its own; AM+PM together also
        # cover the full day. Only report a real gap, never "not running: AS" when AM+PM ran. ---
        def _shift_status(g):
            present = set(g["Shift"].unique())
            if not present:
                return "Not run (no shifts operated)"
            txt = "Running: " + ", ".join(sorted(present))
            if "AS" in present:
                return txt + " — (full day covered)"
            missing = {"AM", "PM"} - present
            txt += (" — Not running: " + ", ".join(sorted(missing))) if missing else " — (all shifts running)"
            return txt
        shift_status_c = shift_stats_c.groupby("Date").apply(_shift_status).reset_index(name="ShiftStatus")
        daily_c = daily_c.merge(shift_status_c, on="Date", how="left")
        daily_c["ShiftStatus"] = daily_c["ShiftStatus"].fillna("Not run (no shifts operated)")

        def _missed_shift(row):
            present = set(str(row["ShiftList"]).split(", ")) if row["ShiftList"] else set()
            if "AS" in present:
                return "None"
            missing = {"AM", "PM"} - present
            return ", ".join(sorted(missing)) if missing else "None"

        daily_c["MissedShift"] = daily_c.apply(_missed_shift, axis=1)
        daily_c["OverallKmEff"] = daily_c.apply(lambda r: (r["OpKM"] / r["SchKM"] * 100) if r["SchKM"] else 0, axis=1)
        daily_c["OverallAvgPax"] = daily_c.apply(lambda r: (r["Pax"] / r["Trips"]) if r["Trips"] else 0, axis=1)

        custom_cols_c = [
            "TypeList", "Weekday", "HolidayFlag", "Collection", "Pax", "SchKM", "OpKM",
            "SchTrip", "Trips", "ZeroTicket", "TicketPax", "Senior", "ShiftBreakdown", "MissedShift",
            "ShiftStatus", "OverallKmEff", "OverallAvgPax",
        ]
        custom_data_c = daily_c[custom_cols_c].values

        combined_block = (
            "<b>Type:</b> %{customdata[0]}<br>"
            "<b>Date:</b> %{x|%d-%b-%Y} (%{customdata[1]}) &nbsp; <b>Holiday:</b> %{customdata[2]}<br>"
            "<b>Shift status:</b> %{customdata[14]}<br><br>"
            "<b>— Combined (all shifts) —</b><br>"
            "Collection: ₹%{customdata[3]:,.0f} &nbsp; Passengers: %{customdata[4]:,.0f}<br>"
            "Scheduled KM: %{customdata[5]:,.1f} &nbsp; Operated KM: %{customdata[6]:,.1f} &nbsp; KM Efficiency: %{customdata[15]:.1f}%<br>"
            "Scheduled Trips: %{customdata[7]:,.0f} &nbsp; Operated Trips: %{customdata[8]:,.0f} &nbsp; Avg Passengers/Trip: %{customdata[16]:,.1f}<br>"
            "Zero Value Tickets: %{customdata[9]:,.0f} &nbsp; Ticket Passengers: %{customdata[10]:,.0f} "
            "&nbsp; Senior Citizens: %{customdata[11]:,.0f}<br><br>"
            "%{customdata[12]}<br><br>"
            "<b>Missed shift(s):</b> %{customdata[13]}"
            "<extra></extra>"
        )

        figc = go.Figure()

        _d0, _d1 = daily_c["Date"].min(), daily_c["Date"].max()
        _range_start = _d0 - pd.Timedelta(days=_d0.weekday())          # Monday of first week
        _range_end = _d1 - pd.Timedelta(days=_d1.weekday()) + pd.Timedelta(days=7)  # Monday after last week
        _week_starts = pd.date_range(_range_start, _range_end, freq="7D")
        for i in range(len(_week_starts) - 1):
            ws = _week_starts[i]
            we = ws + pd.Timedelta(days=6, hours=12)   # ends mid-way between Sunday and next Monday
            figc.add_vrect(
                x0=ws, x1=we,
                fillcolor="#EAF0FB" if i % 2 else "#FBF3E7",
                opacity=1, line_width=0, layer="below",
            )

        sunday_mask = daily_c["Weekday"] == "Sunday"
        holiday_mask = (daily_c["HolidayFlag"] != "No") & ~sunday_mask
        epbpd_colors = ["red" if s else ("darkorange" if h else "#1E90FF")
                        for s, h in zip(sunday_mask, holiday_mask)]
        epkm_colors = ["red" if s else ("darkorange" if h else "black")
                       for s, h in zip(sunday_mask, holiday_mask)]
        marker_sizes = [11 if (s or h) else 8 for s, h in zip(sunday_mask, holiday_mask)]
        figc.add_trace(go.Scatter(
            x=daily_c["Date"], y=daily_c["EPBPD"], name="EPBPD (₹/bus/day)",
            mode="lines+markers", line=dict(color="blue"), yaxis="y1",
            marker=dict(color=epbpd_colors, size=marker_sizes, opacity=1, line=dict(width=0)),
            customdata=custom_data_c,
            hovertemplate="<b>EPBPD:</b> %{y:,.0f} ₹/bus/day<br><br>" + combined_block,
        ))
        figc.add_trace(go.Scatter(
            x=daily_c["Date"], y=daily_c["EPKM"], name="EPKM (₹/km)",
            mode="lines+markers", line=dict(color="black"), yaxis="y2",
            marker=dict(color=epkm_colors, size=marker_sizes, opacity=1, line=dict(width=0)),
            customdata=custom_data_c,
            hovertemplate="<b>EPKM:</b> %{y:,.2f} ₹/km<br><br>" + combined_block,
        ))

        # --- Two avg-EPBPD reference lines: this selection vs ALL services (route overall), for comparison ---
        avg_epbpd_val = daily_c["EPBPD"].mean()
        scope_collection = scope_df["Collection With Reimbursement"].sum()
        scope_op_km = scope_df["Operated KM"].sum()
        scope_sch_km = scope_df["Scheduled KM"].sum()
        scope_epkm = scope_collection / scope_op_km if scope_op_km else 0
        scope_eff = (scope_op_km / scope_sch_km * 100) if scope_sch_km else 0
        n_pts = len(daily_c)
        figc.add_trace(go.Scatter(
            x=daily_c["Date"], y=[avg_epbpd_val] * n_pts,
            mode="lines", name="Avg EPBPD (this selection)", yaxis="y1",
            line=dict(color="green", dash="dash", width=2),
            hovertemplate=(
                "<b>Avg EPBPD — this selection</b><br>"
                f"₹{avg_epbpd_val:,.0f} /bus/day<br>"
                f"Avg EPKM: ₹{scope_epkm:.2f}/km"
                "<extra></extra>"
            ),
        ))

        overall_avg_epbpd = pd.to_numeric(merged["EPBPD"], errors="coerce").mean()
        overall_avg_epkm = pd.to_numeric(merged["EPKM"], errors="coerce").mean()
        figc.add_trace(go.Scatter(
            x=daily_c["Date"], y=[overall_avg_epbpd] * n_pts,
            mode="lines", name="Avg EPBPD (all services)", yaxis="y1",
            line=dict(color="purple", dash="dot", width=2),
            hovertemplate=(
                "<b>Avg EPBPD — all services (route overall)</b><br>"
                f"₹{overall_avg_epbpd:,.0f} /bus/day<br>"
                f"Route: {route_val}<br>"
                f"Avg EPKM: ₹{overall_avg_epkm:.2f}/km"
                "<extra></extra>"
            ),
        ))

        figc.update_traces(selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)))

        _wd_abbrev = {"Sunday": "S", "Monday": "M", "Tuesday": "TU", "Wednesday": "W",
                      "Thursday": "TH", "Friday": "F", "Saturday": "SA"}
        _tickvals = daily_c["Date"]
        _ticktext = [
            f"{d.strftime('%d')}<br><span style='color:darkred'>{_wd_abbrev[w]}</span>" if w == "Sunday"
            else f"{d.strftime('%d')}<br>{_wd_abbrev[w]}"
            for d, w in zip(daily_c["Date"], daily_c["Weekday"])
        ]

        figc.update_layout(
            height=520, plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(title="Date", tickmode="array", tickvals=_tickvals, ticktext=_ticktext, tickangle=0),
            yaxis=dict(title=dict(text="EPBPD (₹/bus/day)", font=dict(color="blue")), tickfont=dict(color="blue")),
            yaxis2=dict(title=dict(text="EPKM (₹/km)", font=dict(color="black")), tickfont=dict(color="black"),
                        overlaying="y", side="right"),
            legend=dict(orientation="h", y=-0.25),
            margin=dict(b=100),
        )
        st.plotly_chart(figc, use_container_width=True, config=PLOTLY_CONFIG)
        # --- click-to-update-box handler — commented out along with the box above, uncomment together ---
        # trend_event = st.plotly_chart(
        #     figc, use_container_width=True, config=PLOTLY_CONFIG,
        #     on_select="rerun", selection_mode="points", key="trend_combined_chart",
        # )
        # clicked_c = (trend_event or {}).get("selection", {}).get("points", [])
        # if clicked_c:
        #     cd = clicked_c[0].get("customdata")
        #     if cd and len(cd) >= 15:
        #         st.session_state["trend_box_date"] = clicked_c[0].get("x")
        #         st.session_state["trend_box_status"] = cd[14]

        st.caption("Combined view aggregates the currently scoped selection by day "
                   "(use 'Break down by → Service' above to scope to one bus/service). "
                   "🔴 red marker = Sunday · 🟠 orange marker = Govt holiday. Green dashed = this selection's avg EPBPD, "
                   "purple dotted = all-services route avg EPBPD — compare the two to see above/below average.")
    else:
        group_cols = ["Date"] if group_by == "None" else ["Date", group_by]

        base = scope_df.groupby(group_cols).agg(
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
            "Collection Total": base["Collection"],
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
        base["Weekday"] = base["Date"].dt.day_name()
        base["HolidayFlag"] = base["Date"].map(lambda d: holiday_dates.get(d, "No"))

        if group_by in ("Service", "Depot"):
            join_unique = lambda s: ", ".join(sorted(s.astype(str).unique()))
            other_dim = "Depot" if group_by == "Service" else "Service"
            detail = scope_df.groupby(group_cols).agg(
                TypeList=("Type", join_unique),
                ShiftList=("Shift", join_unique),
                OtherList=(other_dim, join_unique),
                SchTrip=("Scheduled Trip", "sum"),
            ).reset_index()
            base = base.merge(detail, on=group_cols)

            # --- per-shift breakdown: AM/PM/AS each fully separated, own block, all fields ---
            shift_stats = scope_df.groupby(group_cols + ["Shift"]).agg(
                Collection=("Collection With Reimbursement", "sum"),
                Pax=("Total Passengers", "sum"),
                SchKM=("Scheduled KM", "sum"),
                OpKM=("Operated KM", "sum"),
                SchTrip=("Scheduled Trip", "sum"),
                Trips=("Operated Trip", "sum"),
                ZeroTicket=("Zero Value Ticket", "sum"),
                TicketPax=("Ticket Passenger", "sum"),
                Senior=("Senior Citizens", "sum"),
            ).reset_index()

            def _shift_block(g):
                blocks = []
                for r in g.sort_values("Shift").itertuples():
                    km_eff = (r.OpKM / r.SchKM * 100) if r.SchKM else 0
                    avg_pax = (r.Pax / r.Trips) if r.Trips else 0
                    blocks.append(
                        f"<b>— {r.Shift} shift —</b><br>"
                        f"Collection: ₹{r.Collection:,.0f} &nbsp; Passengers: {r.Pax:,.0f}<br>"
                        f"Scheduled KM: {r.SchKM:,.1f} &nbsp; Operated KM: {r.OpKM:,.1f} &nbsp; KM Efficiency: {km_eff:.1f}%<br>"
                        f"Scheduled Trips: {r.SchTrip:,.0f} &nbsp; Operated Trips: {r.Trips:,.0f} &nbsp; Avg Passengers/Trip: {avg_pax:,.1f}<br>"
                        f"Zero Value Tickets: {r.ZeroTicket:,.0f} &nbsp; Ticket Passengers: {r.TicketPax:,.0f} "
                        f"&nbsp; Senior Citizens: {r.Senior:,.0f}"
                    )
                return "<br><br>".join(blocks)

            shift_block = shift_stats.groupby(group_cols).apply(_shift_block).reset_index(name="ShiftBreakdown")
            base = base.merge(shift_block, on=group_cols, how="left")

            def _missed_shift(row):
                present = set(str(row["ShiftList"]).split(", ")) if row["ShiftList"] else set()
                if "AS" in present:
                    return "None"
                missing = {"AM", "PM"} - present
                return ", ".join(sorted(missing)) if missing else "None"

            base["MissedShift"] = base.apply(_missed_shift, axis=1)
            base["OverallKmEff"] = base.apply(lambda r: (r["OpKM"] / r["SchKM"] * 100) if r["SchKM"] else 0, axis=1)
            base["OverallAvgPax"] = base.apply(lambda r: (r["Pax"] / r["Trips"]) if r["Trips"] else 0, axis=1)

            custom_cols = [
                "OtherList", "TypeList", "Weekday", "HolidayFlag",
                "ShiftBreakdown", "MissedShift",
                "Collection", "Pax", "SchKM", "OpKM", "SchTrip", "Trips",
                "ZeroTicket", "TicketPax", "Senior", "OverallKmEff", "OverallAvgPax",
            ]
            other_label = "Depot" if group_by == "Service" else "Service"

            if group_by == "Service":
                base["Legend"] = base["Service"].map(
                    lambda s: f"{s} ({depot_emoji.get(service_depot_map.get(s, [None])[0], '')} "
                              f"{service_depot_map.get(s, ['?'])[0]})"
                )
                legend_col = "Legend"
                color_map = {
                    row["Legend"]: depot_colors.get(service_depot_map.get(row["Service"], [None])[0], "#1f77b4")
                    for _, row in base[["Legend", "Service"]].drop_duplicates().iterrows()
                }
            else:
                legend_col = group_by
                color_map = depot_colors

            if group_by == "None":
                fig2 = px.line(base, x="Date", y="value", markers=True, custom_data=custom_cols)
            else:
                fig2 = px.line(base, x="Date", y="value", color=legend_col, markers=True,
                                custom_data=custom_cols, color_discrete_map=color_map)

            name_line = (
                f"<b>{group_by}:</b> %{{fullData.name}}<br>" if group_by == "Service"
                else f"<b>{group_by}:</b> %{{fullData.name}}  ({other_label}: %{{customdata[0]}})<br>"
            )
            fig2.update_traces(hovertemplate=(
                name_line +
                "<b>Date:</b> %{x|%d-%b-%Y} (%{customdata[2]}) &nbsp; <b>Holiday:</b> %{customdata[3]}<br>"
                "<b>Type:</b> %{customdata[1]}<br><br>"
                "<b>— Combined (all shifts) —</b><br>"
                "Collection: ₹%{customdata[6]:,.0f} &nbsp; Passengers: %{customdata[7]:,.0f}<br>"
                "Scheduled KM: %{customdata[8]:,.1f} &nbsp; Operated KM: %{customdata[9]:,.1f} &nbsp; KM Efficiency: %{customdata[15]:.1f}%<br>"
                "Scheduled Trips: %{customdata[10]:,.0f} &nbsp; Operated Trips: %{customdata[11]:,.0f} &nbsp; Avg Passengers/Trip: %{customdata[16]:,.1f}<br>"
                "Zero Value Tickets: %{customdata[12]:,.0f} &nbsp; Ticket Passengers: %{customdata[13]:,.0f} "
                "&nbsp; Senior Citizens: %{customdata[14]:,.0f}<br><br>"
                "%{customdata[4]}<br><br>"
                "<b>Missed shift(s):</b> %{customdata[5]}"
                "<extra></extra>"
            ))
        else:
            fig2 = px.line(base, x="Date", y="value", markers=True, custom_data=["Weekday", "HolidayFlag"])
            fig2.update_traces(hovertemplate=(
                "<b>Date:</b> %{x|%d-%b-%Y} (%{customdata[0]}) &nbsp; <b>Holiday:</b> %{customdata[1]}<br>"
                f"<b>{metric}:</b> %{{y:,.2f}}<extra></extra>"
            ))

        # --- color individual markers: red = govt holiday or Sunday, else the trace's own (depot) color ---
        holiday_idx = 3 if group_by in ("Service", "Depot") else 1
        weekday_idx = 2 if group_by in ("Service", "Depot") else 0
        for trace in fig2.data:
            if trace.customdata is None:
                continue
            base_color = trace.line.color or "#1f77b4"
            colors, sizes = [], []
            for cd in trace.customdata:
                if cd[holiday_idx] != "No":
                    colors.append("red"); sizes.append(11)
                elif cd[weekday_idx] == "Sunday":
                    colors.append("red"); sizes.append(9)
                else:
                    colors.append(base_color); sizes.append(6)
            trace.update(marker=dict(color=colors, size=sizes, line=dict(width=1, color="DarkSlateGrey")))

        fig2.update_layout(height=500, plot_bgcolor="white", paper_bgcolor="white", yaxis_title=metric)
        st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption("🔴 marker = Tamil Nadu Govt holiday or Sunday · normal color = regular weekday.")
        if metric in ("EPKM", "KM Efficency", "EPBPD", "Total Passengers per bus per day"):
            st.caption("Rate metrics are computed from summed numerator/denominator per period, not averaged row %s.")

# ------------------------------------------------------------------
# TAB 3 — DEPOT COMPARISON
# ------------------------------------------------------------------
elif active_tab == TAB_LABELS[2]:
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
elif active_tab == TAB_LABELS[3]:
    st.subheader("Filtered Data")
    st.dataframe(df, use_container_width=True, height=500)
    st.download_button("Download filtered CSV", df.to_csv(index=False).encode(), "filtered_data.csv", "text/csv")

# ------------------------------------------------------------------
# TAB 5 — DAILY ABSTRACT
# ------------------------------------------------------------------
elif active_tab == TAB_LABELS[4]:
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

# ------------------------------------------------------------------
# KPI STRIP — front page only (Johari Window tab), not shown under other tabs
# ------------------------------------------------------------------
if active_tab == TAB_LABELS[0]:
    st.divider()
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

# ------------------------------------------------------------------
# TAB 6 — OBSERVATION: cross-depot comparison, best performer per metric
# ------------------------------------------------------------------
elif active_tab == TAB_LABELS[5]:
    st.subheader("Observation — Depot-wise Comparison")

    _obs_daily = df.groupby(["Depot", "Date"]).agg(
        Collection=("Collection With Reimbursement", "sum"),
        Pax=("Total Passengers", "sum"),
        OpKM=("Operated KM", "sum"),
        SchKM=("Scheduled KM", "sum"),
        Services=("Service", "nunique"),
        Trips=("Operated Trip", "sum"),
        SchTrip=("Scheduled Trip", "sum"),
        ZeroTicket=("Zero Value Ticket", "sum"),
        TicketPax=("Ticket Passenger", "sum"),
        Senior=("Senior Citizens", "sum"),
    ).reset_index()
    _obs_daily["EPBPD"] = _obs_daily["Collection"] / _obs_daily["Services"].replace(0, pd.NA)
    _obs_daily["PaxPerBus"] = _obs_daily["Pax"] / _obs_daily["Services"].replace(0, pd.NA)

    _obs_tot = _obs_daily.groupby("Depot").agg(
        Collection=("Collection", "sum"), Pax=("Pax", "sum"), OpKM=("OpKM", "sum"), SchKM=("SchKM", "sum"),
        Trips=("Trips", "sum"), SchTrip=("SchTrip", "sum"), ZeroTicket=("ZeroTicket", "sum"),
        TicketPax=("TicketPax", "sum"), Senior=("Senior", "sum"),
    ).reset_index()
    _obs_tot["EPKM"] = _obs_tot["Collection"] / _obs_tot["OpKM"].replace(0, pd.NA)
    _obs_tot["Efficiency"] = _obs_tot["OpKM"] / _obs_tot["SchKM"].replace(0, pd.NA) * 100
    _obs_avg = _obs_daily.groupby("Depot").agg(
        EPBPD=("EPBPD", "mean"), PaxPerBus=("PaxPerBus", "mean"),
        Services=("Services", "mean"), TripsPerDay=("Trips", "mean"),
    ).reset_index()
    obs = _obs_tot.merge(_obs_avg, on="Depot")

    # metric_name -> (column, higher_is_better, display format)
    _obs_metrics = {
        "EPKM (₹/km)": ("EPKM", True, "₹{:.2f}"),
        "EPBPD (₹/bus/day)": ("EPBPD", True, "₹{:,.0f}"),
        "KM Efficiency (%)": ("Efficiency", True, "{:.1f}%"),
        "Passengers/bus/day": ("PaxPerBus", True, "{:,.1f}"),
        "Total Collection (₹)": ("Collection", True, "₹{:,.0f}"),
        "Total Passengers": ("Pax", True, "{:,.0f}"),
        "Services operated/day": ("Services", True, "{:.1f}"),
        "Trips operated/day": ("TripsPerDay", True, "{:.1f}"),
        "Zero Value Tickets (total)": ("ZeroTicket", True, "{:,.0f}"),
        "Senior Citizens (total)": ("Senior", True, "{:,.0f}"),
    }

    st.markdown("##### 🏆 Best performing depot — by category")
    _cards = st.columns(3)
    for i, (label, (col, higher_better, fmt)) in enumerate(_obs_metrics.items()):
        row = obs.loc[obs[col].idxmax()] if higher_better else obs.loc[obs[col].idxmin()]
        with _cards[i % 3]:
            st.markdown(
                f"<div style='background:#F5F9FF;border:1px solid #D8E4F5;border-radius:10px;"
                f"padding:12px 14px;margin-bottom:10px;'>"
                f"<div style='font-size:0.85rem;color:#555;'>{label}</div>"
                f"<div style='font-size:1.4rem;font-weight:700;color:{depot_colors.get(row['Depot'], '#1f77b4')};'>"
                f"{depot_emoji.get(row['Depot'], '')} {row['Depot']}</div>"
                f"<div style='font-size:1rem;color:#222;'>{fmt.format(row[col])}</div>"
                f"</div>", unsafe_allow_html=True,
            )

    st.divider()
    st.markdown("##### Full comparison table")
    _tbl = obs[["Depot", "EPKM", "EPBPD", "Efficiency", "PaxPerBus", "Collection", "Pax",
                "Services", "TripsPerDay", "ZeroTicket", "Senior"]].copy()
    _tbl.columns = ["Depot", "EPKM (₹/km)", "Avg EPBPD (₹/bus/day)", "KM Efficiency (%)",
                    "Avg Pax/bus/day", "Total Collection (₹)", "Total Passengers",
                    "Avg Services/day", "Avg Trips/day", "Zero Value Tickets", "Senior Citizens"]
    def _green_scale(s):
        s_num = pd.to_numeric(s, errors="coerce")
        lo, hi = s_num.min(), s_num.max()
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            return ["" for _ in s]
        styles = []
        for v in s_num:
            if pd.isna(v):
                styles.append("")
                continue
            frac = (v - lo) / (hi - lo)
            g = int(230 - frac * 90)   # 230 (pale) -> 140 (deeper green) as value increases
            styles.append(f"background-color: rgb({g},235,{g})")
        return styles

    _styled = _tbl.style.format({
        "EPKM (₹/km)": "₹{:.2f}", "Avg EPBPD (₹/bus/day)": "₹{:,.0f}", "KM Efficiency (%)": "{:.1f}%",
        "Avg Pax/bus/day": "{:,.1f}", "Total Collection (₹)": "₹{:,.0f}", "Total Passengers": "{:,.0f}",
        "Avg Services/day": "{:.1f}", "Avg Trips/day": "{:.1f}",
        "Zero Value Tickets": "{:,.0f}", "Senior Citizens": "{:,.0f}",
    }).apply(_green_scale, subset=[
        "EPKM (₹/km)", "Avg EPBPD (₹/bus/day)", "KM Efficiency (%)", "Avg Pax/bus/day",
    ])
    st.dataframe(_styled, use_container_width=True)

    st.divider()
    st.markdown("##### Side-by-side charts")
    g1, g2 = st.columns(2)
    for (metric_col, title), holder in zip(
        [("EPKM", "EPKM by Depot"), ("EPBPD", "Avg EPBPD by Depot"),
         ("Efficiency", "KM Efficiency by Depot"), ("PaxPerBus", "Avg Passengers/bus/day by Depot")],
        [g1, g2, g1, g2],
    ):
        _f = px.bar(obs, x="Depot", y=metric_col, color="Depot", title=title,
                    text_auto=".2f" if metric_col in ("EPKM",) else ".1f")
        _f.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white")
        holder.plotly_chart(_f, use_container_width=True, config=PLOTLY_CONFIG)

    st.caption("EPKM, EPBPD and KM Efficiency use totals-based math. 'Best' picks the highest value per category.")