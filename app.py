import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
from neo4j import GraphDatabase

st.set_page_config(page_title="Banking Fraud Intelligence", page_icon="🏦", layout="wide", initial_sidebar_state="expanded")

COLORS = {"Low": "#10B981", "Medium": "#F59E0B", "High": "#EF4444", "Unknown": "#94A3B8"}
PALETTE = ["#38BDF8", "#A78BFA", "#34D399", "#FBBF24", "#FB7185", "#22D3EE", "#F472B6", "#C4B5FD"]
ALERT_COLUMNS = ["alert_id", "alert_type", "severity", "primary_account", "related_accounts", "evidence"]

st.markdown("""<style>
.stApp {background-color:#0B1120;color:#F8FAFC}
.block-container {padding-top:1.8rem;padding-bottom:2rem;max-width:1550px}
[data-testid="stMetric"] {background:#111827;border:1px solid #263349;padding:18px;border-radius:12px}
[data-testid="stMetricLabel"] {color:#94A3B8}
[data-testid="stMetricValue"] {color:#F8FAFC}
[data-testid="stSidebar"] {background:#111827}
h1,h2,h3 {color:#F8FAFC}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def get_driver():
    driver = GraphDatabase.driver(
        st.secrets["NEO4J_URI"],
        auth=(st.secrets["NEO4J_USERNAME"], st.secrets["NEO4J_PASSWORD"]),
    )
    driver.verify_connectivity()
    return driver


@st.cache_data(ttl=300, show_spinner=False)
def run_query(query):
    # Let Aura select its default database.
    with get_driver().session() as session:
        return session.run(query).data()


@st.cache_data(ttl=300, show_spinner=False)
def load_accounts():
    return pd.DataFrame(run_query("""
        MATCH (a:Account)
        RETURN a.account_id AS account_id,
               coalesce(a.community_id,-1) AS community_id,
               coalesce(a.pagerank,0.0) AS pagerank,
               coalesce(a.enhanced_risk_score,a.risk_score,0) AS risk_score,
               coalesce(a.enhanced_risk_level,a.risk_level,'Unknown') AS risk_level
        ORDER BY account_id
    """))


@st.cache_data(ttl=300, show_spinner=False)
def load_transactions():
    return pd.DataFrame(run_query("""
        MATCH (source:Account)-[:INITIATED]->(t:Transaction)-[:SENT_TO]->(target:Account)
        RETURN source.account_id AS source, target.account_id AS target,
               t.transaction_id AS transaction_id, t.amount AS amount,
               toString(t.timestamp) AS timestamp
        ORDER BY transaction_id
    """))


@st.cache_data(ttl=300, show_spinner=False)
def load_account_context():
    return pd.DataFrame(run_query("""
        MATCH (c:Customer)-[:OWNS]->(a:Account)
        OPTIONAL MATCH (c)-[:USES]->(d:Device)
        WITH c,a,collect(DISTINCT d.device_id) AS devices
        OPTIONAL MATCH (c)-[:REGISTERED_AT]->(addr:Address)
        RETURN a.account_id AS account_id, c.customer_id AS customer_id,
               devices, collect(DISTINCT addr.address_id) AS addresses
        ORDER BY account_id
    """))


@st.cache_data(ttl=300, show_spinner=False)
def load_fraud_alerts():
    """Read-only, rule-based alerts. Each shared-device/address account receives an alert."""
    query = """
    CALL {
        MATCH (a1:Account)-[:INITIATED]->(t:Transaction)-[:SENT_TO]->(a2:Account)
        WHERE t.amount >= 50000
        RETURN 'HV-' + toString(t.transaction_id) AS alert_id,
               'HIGH_VALUE_TRANSFER' AS alert_type,
               'High' AS severity,
               a1.account_id AS primary_account,
               toString(a2.account_id) AS related_accounts,
               'Transaction ' + toString(t.transaction_id) +
               ': INR ' + toString(t.amount) AS evidence
        UNION ALL
        MATCH (c:Customer)-[:USES]->(d:Device)
        WITH d, collect(DISTINCT c) AS customers
        WHERE size(customers) >= 3
        UNWIND customers AS c
        MATCH (c)-[:OWNS]->(a:Account)
        RETURN 'DEV-' + toString(d.device_id) + '-' + toString(a.account_id) AS alert_id,
               'SHARED_DEVICE' AS alert_type,
               'Medium' AS severity,
               a.account_id AS primary_account,
               toString(d.device_id) AS related_accounts,
               'Device used by ' + toString(size(customers)) + ' customers' AS evidence
        UNION ALL
        MATCH (c:Customer)-[:REGISTERED_AT]->(addr:Address)
        WITH addr, collect(DISTINCT c) AS customers
        WHERE size(customers) >= 3
        UNWIND customers AS c
        MATCH (c)-[:OWNS]->(a:Account)
        RETURN 'ADDR-' + toString(addr.address_id) + '-' + toString(a.account_id) AS alert_id,
               'SHARED_ADDRESS' AS alert_type,
               'Medium' AS severity,
               a.account_id AS primary_account,
               toString(addr.address_id) AS related_accounts,
               'Address registered to ' + toString(size(customers)) + ' customers' AS evidence
        UNION ALL
        MATCH (a1:Account)-[:TRANSFERRED_TO]->(a2:Account)
              -[:TRANSFERRED_TO]->(a3:Account)
              -[:TRANSFERRED_TO]->(a1)
        WHERE a1 <> a2 AND a2 <> a3 AND a1 <> a3
          AND toString(a1.account_id) < toString(a2.account_id)
          AND toString(a1.account_id) < toString(a3.account_id)
        RETURN 'CYCLE-' + toString(a1.account_id) + '-' +
               toString(a2.account_id) + '-' + toString(a3.account_id) AS alert_id,
               'CIRCULAR_TRANSFER' AS alert_type,
               'High' AS severity,
               a1.account_id AS primary_account,
               toString(a2.account_id) + ', ' + toString(a3.account_id) AS related_accounts,
               'Three-account directed transfer cycle (timing not assessed)' AS evidence
    }
    RETURN DISTINCT alert_id, alert_type, severity, primary_account, related_accounts, evidence
    ORDER BY CASE severity WHEN 'High' THEN 0 ELSE 1 END, alert_type, primary_account
    """
    return pd.DataFrame(run_query(query), columns=ALERT_COLUMNS)


def theme(fig, height=410):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#111827", plot_bgcolor="#111827",
        font=dict(color="#E2E8F0"), height=height,
        margin=dict(l=25, r=25, t=45, b=35), legend_title_text=""
    )
    return fig


def create_network_figure(account_frame, transaction_frame):
    graph = nx.DiGraph()
    for row in account_frame.itertuples(index=False):
        graph.add_node(
            row.account_id, community=row.community_id, risk=row.risk_level,
            score=float(row.risk_score), pagerank=float(row.pagerank)
        )
    if not transaction_frame.empty:
        edges = transaction_frame.groupby(["source", "target"], as_index=False).agg(
            amount=("amount", "sum"), count=("transaction_id", "count")
        )
        for row in edges.itertuples(index=False):
            if row.source in graph and row.target in graph:
                graph.add_edge(row.source, row.target, amount=float(row.amount), count=int(row.count))
    fig = go.Figure()
    if not graph.nodes:
        return theme(fig, 650)
    positions = nx.spring_layout(graph.to_undirected(), seed=42, iterations=250)
    for source, target, data in graph.edges(data=True):
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1], mode="lines",
            line=dict(color="rgba(148,163,184,0.42)", width=2),
            hoverinfo="skip", showlegend=False
        ))
        fig.add_trace(go.Scatter(
            x=[(x0+x1)/2], y=[(y0+y1)/2], mode="markers",
            marker=dict(size=16, color="rgba(148,163,184,0.01)"),
            hovertemplate=(f"<b>{source} → {target}</b><br>Transfer value: ₹{data['amount']:,.0f}"
                           f"<br>Transactions: {data['count']}<extra></extra>"),
            showlegend=False
        ))
        fig.add_annotation(
            x=x0+0.79*(x1-x0), y=y0+0.79*(y1-y0),
            ax=x0+0.65*(x1-x0), ay=y0+0.65*(y1-y0),
            xref="x", yref="y", axref="x", ayref="y", showarrow=True,
            arrowhead=3, arrowsize=1.1, arrowwidth=1.7, arrowcolor="#94A3B8"
        )
    communities = sorted({graph.nodes[n]["community"] for n in graph}, key=str)
    for index, community in enumerate(communities):
        members = [n for n in graph if graph.nodes[n]["community"] == community]
        fig.add_trace(go.Scatter(
            x=[positions[n][0] for n in members],
            y=[positions[n][1] for n in members],
            mode="markers+text", text=members, textposition="top center",
            textfont=dict(size=12, color="#F8FAFC"),
            name=f"Community {community}",
            marker=dict(
                size=[25+min(100, graph.nodes[n]["score"])*0.28 for n in members],
                color=PALETTE[index % len(PALETTE)],
                line=dict(color="white", width=1.8)
            ),
            hovertemplate=[
                (f"<b>Account {n}</b><br>Community: {community}"
                 f"<br>Risk: {graph.nodes[n]['risk']} ({graph.nodes[n]['score']:.0f}/100)"
                 f"<br>PageRank: {graph.nodes[n]['pagerank']:.5f}<extra></extra>")
                for n in members
            ]
        ))
    theme(fig, 690)
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, scaleanchor="x", scaleratio=1),
        hovermode="closest", legend=dict(orientation="h", y=-0.07), dragmode="pan"
    )
    return fig


st.title("Banking Fraud Intelligence Dashboard")
st.caption("Neo4j Graph Analytics  |  Louvain Communities  |  PageRank  |  Rule-Based Risk Scoring")
st.info(
    "Portfolio demonstration using synthetic banking data. "
    "Risk flags indicate activity for review, not confirmed fraud.",
    icon="ℹ️"
)

try:
    accounts = load_accounts()
    transactions = load_transactions()
    context = load_account_context()
except Exception as exc:
    st.error("Could not retrieve data from Neo4j AuraDB. Check Streamlit secrets and database availability.")
    st.exception(exc)
    st.stop()

if accounts.empty:
    st.warning("No accounts found in Neo4j.")
    st.stop()

accounts["risk_score"] = pd.to_numeric(accounts["risk_score"], errors="coerce").fillna(0)
accounts["pagerank"] = pd.to_numeric(accounts["pagerank"], errors="coerce").fillna(0)
accounts["risk_level"] = accounts["risk_level"].fillna("Unknown")
if transactions.empty:
    transactions = pd.DataFrame(columns=["source", "target", "transaction_id", "amount", "timestamp"])
transactions["amount"] = pd.to_numeric(transactions["amount"], errors="coerce").fillna(0)

with st.sidebar:
    st.header("Investigation Filters")
    risks = st.multiselect(
        "Risk level", options=["High", "Medium", "Low", "Unknown"],
        default=["High", "Medium", "Low", "Unknown"]
    )
    communities = sorted(accounts["community_id"].dropna().unique().tolist(), key=str)
    selected_communities = st.multiselect(
        "Louvain community", options=communities, default=communities
    )
    search = st.text_input("Find account ID", placeholder="e.g. A003").strip()
    st.caption(
        "Filters apply to the network, ranking and investigation table. "
        "Executive KPIs describe the full dataset."
    )
    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

filtered = accounts[
    accounts["risk_level"].isin(risks) &
    accounts["community_id"].isin(selected_communities)
].copy()
if search:
    filtered = filtered[
        filtered["account_id"].astype(str).str.contains(search, case=False, regex=False)
    ]
ids = set(filtered["account_id"])
filtered_tx = transactions[
    transactions["source"].isin(ids) & transactions["target"].isin(ids)
].copy()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Accounts", f"{len(accounts):,}")
k2.metric("Transactions", f"{len(transactions):,}")
k3.metric("Transfer Value", f"₹{transactions['amount'].sum():,.0f}")
k4.metric("High-Risk Accounts", f"{(accounts['risk_level']=='High').sum():,}")

st.divider()
left, right = st.columns(2)
with left:
    st.subheader("Account Risk Distribution")
    risk_counts = (
        accounts["risk_level"].value_counts()
        .reindex(["Low", "Medium", "High", "Unknown"], fill_value=0)
        .reset_index()
    )
    risk_counts.columns = ["Risk Level", "Accounts"]
    fig = px.bar(
        risk_counts, x="Risk Level", y="Accounts", color="Risk Level",
        text="Accounts", color_discrete_map=COLORS,
        category_orders={"Risk Level": ["Low", "Medium", "High", "Unknown"]}
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False)
    st.plotly_chart(theme(fig), use_container_width=True)
with right:
    st.subheader("Account Network Influence")
    rank = filtered.sort_values("pagerank", ascending=True)
    if rank.empty:
        st.info("No accounts match your filters.")
    else:
        fig = px.bar(
            rank, x="pagerank", y="account_id", orientation="h",
            color="risk_level", color_discrete_map=COLORS,
            hover_data=["risk_score", "community_id"]
        )
        fig.update_layout(xaxis_title="PageRank score", yaxis_title="Account")
        st.plotly_chart(theme(fig), use_container_width=True)

st.divider()
st.subheader("Interactive Banking Transaction Network")
st.caption(
    "Community = node colour; rule-based risk score = node size; arrows = transfer direction. "
    "Hover over nodes or edge midpoints for details."
)
if filtered.empty:
    st.warning("No accounts match the selected filters.")
else:
    st.plotly_chart(create_network_figure(filtered, filtered_tx), use_container_width=True)
    connection_count = (
        filtered_tx.groupby(["source", "target"]).ngroups if not filtered_tx.empty else 0
    )
    st.caption(
        f"{len(filtered)} displayed accounts · {len(filtered_tx)} displayed transactions · "
        f"{connection_count} directed connections"
    )

# --------------------------------------------------
# CONSOLIDATED FRAUD ALERT INVESTIGATION
# --------------------------------------------------
st.divider()
st.subheader("Suspicious Activity Alert Investigation")
st.caption(
    "Four read-only Neo4j rules: high-value transfers (≥ ₹50,000), "
    "devices shared by ≥ 3 customers, addresses shared by ≥ 3 customers, "
    "and three-account transfer cycles. Thresholds are illustrative."
)
try:
    alerts_df = load_fraud_alerts()
except Exception as exc:
    st.error("The alert query could not run. Other dashboard sections remain available.")
    st.exception(exc)
    alerts_df = pd.DataFrame(columns=ALERT_COLUMNS)

if alerts_df.empty:
    st.info("No suspicious activity alerts matched the configured demonstration rules.")
else:
    # The alert KPIs describe the full dataset; investigation filters apply below.
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Alert Records", f"{len(alerts_df):,}")
    a2.metric("High-Severity Alerts", f"{(alerts_df['severity']=='High').sum():,}")
    a3.metric("Medium-Severity Alerts", f"{(alerts_df['severity']=='Medium').sum():,}")
    a4.metric("Primary Accounts Flagged", f"{alerts_df['primary_account'].nunique():,}")

    f1, f2, f3 = st.columns(3)
    with f1:
        selected_severity = st.multiselect(
            "Alert severity", options=sorted(alerts_df["severity"].dropna().unique()),
            default=sorted(alerts_df["severity"].dropna().unique())
        )
    with f2:
        selected_types = st.multiselect(
            "Alert category", options=sorted(alerts_df["alert_type"].dropna().unique()),
            default=sorted(alerts_df["alert_type"].dropna().unique())
        )
    with f3:
        only_visible = st.checkbox("Match sidebar account filters", value=False)

    visible_alerts = alerts_df[
        alerts_df["severity"].isin(selected_severity) &
        alerts_df["alert_type"].isin(selected_types)
    ].copy()
    if only_visible:
        visible_alerts = visible_alerts[
            visible_alerts["primary_account"].isin(ids)
        ]

    st.dataframe(visible_alerts, use_container_width=True, hide_index=True)
    st.download_button(
        "Download investigation alerts (CSV)",
        data=visible_alerts.to_csv(index=False).encode("utf-8-sig"),
        file_name="banking_fraud_alerts.csv", mime="text/csv"
    )

    if not visible_alerts.empty:
        summary = (
            visible_alerts.groupby(["alert_type", "severity"], as_index=False)
            .size().rename(columns={"size": "alert_count"})
        )
        fig = px.bar(
            summary, x="alert_type", y="alert_count", color="severity",
            text="alert_count", color_discrete_map=COLORS,
            title="Alert Records by Detection Rule"
        )
        fig.update_layout(xaxis_title="Alert category", yaxis_title="Alert records")
        st.plotly_chart(theme(fig, 450), use_container_width=True)
        st.caption(
            "Shared-device and shared-address alerts are recorded per linked account. "
            "Counts are alert records, not unique devices, addresses or confirmed fraud cases."
        )

st.divider()
st.subheader("Account Risk Investigation")
st.dataframe(
    filtered.sort_values(["risk_score", "pagerank"], ascending=False),
    use_container_width=True, hide_index=True
)
st.download_button(
    "Download filtered accounts (CSV)",
    filtered.to_csv(index=False).encode("utf-8-sig"),
    file_name="account_risk_investigation.csv", mime="text/csv"
)

st.divider()
st.subheader("Account Drill-Down")
account_options = filtered["account_id"].tolist()
if not account_options:
    st.info("Select filters that include at least one account to investigate.")
else:
    selected = st.selectbox("Select account", account_options)
    record = accounts.loc[accounts["account_id"] == selected].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Risk Level", str(record["risk_level"]))
    c2.metric("Risk Score", f"{record['risk_score']:.0f} / 100")
    c3.metric("PageRank", f"{record['pagerank']:.5f}")
    related = transactions[
        (transactions["source"] == selected) |
        (transactions["target"] == selected)
    ].copy()
    if not related.empty:
        related["direction"] = related["source"].apply(
            lambda value: "Outgoing" if value == selected else "Incoming"
        )
    st.markdown("**Incoming and outgoing transaction history**")
    st.dataframe(related, use_container_width=True, hide_index=True)
    st.download_button(
        "Download account transactions (CSV)",
        related.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{selected}_transactions.csv", mime="text/csv"
    )
    if not context.empty and "account_id" in context.columns:
        matches = context[context["account_id"] == selected]
        if not matches.empty:
            detail = matches.iloc[0]
            st.markdown("**Linked customer, devices and registered addresses**")
            st.write({
                "customer_id": detail.get("customer_id"),
                "device_ids": detail.get("devices", []),
                "address_ids": detail.get("addresses", [])
            })
    if not alerts_df.empty:
        account_alerts = alerts_df[alerts_df["primary_account"] == selected]
        st.markdown("**Suspicious activity alerts involving this primary account**")
        if account_alerts.empty:
            st.info("No alerts list this account as the primary account.")
        else:
            st.dataframe(account_alerts, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Banking Fraud Detection & Suspicious Transaction Network Analysis · "
    "Synthetic demonstration dataset · Rule-based alerts, PageRank and "
    "network communities are investigation signals, not proof of fraud."
)
