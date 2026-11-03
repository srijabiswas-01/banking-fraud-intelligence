
import streamlit as st
import pandas as pd
import plotly.express as px
from neo4j import GraphDatabase

# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Banking Fraud Intelligence",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------
# CUSTOM DASHBOARD DESIGN
# --------------------------------------------------

st.markdown("""
<style>

.stApp {
    background-color: #0B1120;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

h1, h2, h3 {
    color: #F8FAFC;
}

[data-testid="stMetric"] {
    background-color: #111827;
    border: 1px solid #1E293B;
    padding: 20px;
    border-radius: 12px;
}

[data-testid="stMetricLabel"] {
    color: #94A3B8;
}

[data-testid="stMetricValue"] {
    color: #F8FAFC;
}

</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# NEO4J CONNECTION
# --------------------------------------------------

@st.cache_resource
def get_driver():

    uri = st.secrets["NEO4J_URI"]
    username = st.secrets["NEO4J_USERNAME"]
    password = st.secrets["NEO4J_PASSWORD"]

    driver = GraphDatabase.driver(
        uri,
        auth=(username, password)
    )

    driver.verify_connectivity()

    return driver


# --------------------------------------------------
# LOAD ACCOUNT DATA
# --------------------------------------------------

@st.cache_data(ttl=300)
def load_accounts():

    query = """
    MATCH (a:Account)

    RETURN
        a.account_id AS account_id,
        coalesce(a.community_id, -1) AS community_id,
        coalesce(a.pagerank, 0.0) AS pagerank,
        coalesce(a.enhanced_risk_score, 0) AS risk_score,
        coalesce(a.enhanced_risk_level, 'Unknown') AS risk_level

    ORDER BY risk_score DESC
    """

    with get_driver().session() as session:
        records = session.run(query).data()

    return pd.DataFrame(records)


# --------------------------------------------------
# LOAD TRANSACTION DATA
# --------------------------------------------------

@st.cache_data(ttl=300)
def load_transactions():

    query = """
    MATCH (a1:Account)-[:INITIATED]->(t:Transaction)
          -[:SENT_TO]->(a2:Account)

    RETURN
        a1.account_id AS source,
        a2.account_id AS target,
        t.transaction_id AS transaction_id,
        t.amount AS amount
    """

    with get_driver().session() as session:
        records = session.run(query).data()

    return pd.DataFrame(records)


# --------------------------------------------------
# DASHBOARD HEADER
# --------------------------------------------------

st.title("Banking Fraud Intelligence Dashboard")

st.caption(
    "Neo4j Graph Analytics | Louvain Communities | "
    "PageRank | Enhanced Risk Scoring"
)

st.divider()

# --------------------------------------------------
# LOAD DATABASE DATA
# --------------------------------------------------

try:
    accounts = load_accounts()
    transactions = load_transactions()

except Exception as e:
    st.error("Unable to load banking data from Neo4j.")
    st.exception(e)
    st.stop()


if accounts.empty:
    st.warning("No account records were found.")
    st.stop()

# --------------------------------------------------
# EXECUTIVE KPI METRICS
# --------------------------------------------------

total_accounts = len(accounts)

total_transactions = len(transactions)

total_value = (
    pd.to_numeric(
        transactions["amount"],
        errors="coerce"
    ).sum()
    if not transactions.empty else 0
)

high_risk_accounts = (
    accounts["risk_level"] == "High"
).sum()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total Accounts",
        f"{total_accounts:,}"
    )

with col2:
    st.metric(
        "Total Transactions",
        f"{total_transactions:,}"
    )

with col3:
    st.metric(
        "Transaction Value",
        f"₹{total_value:,.0f}"
    )

with col4:
    st.metric(
        "High-Risk Accounts",
        f"{high_risk_accounts:,}"
    )

st.divider()

# --------------------------------------------------
# RISK DISTRIBUTION
# --------------------------------------------------

left, right = st.columns(2)

with left:

    st.subheader("Account Risk Distribution")

    risk_counts = (
        accounts["risk_level"]
        .value_counts()
        .reset_index()
    )

    risk_counts.columns = [
        "Risk Level",
        "Accounts"
    ]

    fig_risk = px.bar(
        risk_counts,
        x="Risk Level",
        y="Accounts",
        color="Risk Level",
        text="Accounts",
        color_discrete_map={
            "Low": "#10B981",
            "Medium": "#F59E0B",
            "High": "#EF4444",
            "Unknown": "#64748B"
        }
    )

    fig_risk.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        showlegend=False,
        height=400
    )

    st.plotly_chart(
        fig_risk,
        use_container_width=True
    )

# --------------------------------------------------
# PAGERANK ACCOUNT ANALYSIS
# --------------------------------------------------

with right:

    st.subheader("Account Network Influence")

    ranking = accounts.sort_values(
        "pagerank",
        ascending=True
    )

    fig_rank = px.bar(
        ranking,
        x="pagerank",
        y="account_id",
        orientation="h",
        color="risk_level",
        color_discrete_map={
            "Low": "#10B981",
            "Medium": "#F59E0B",
            "High": "#EF4444",
            "Unknown": "#64748B"
        },
        hover_data=["risk_score", "community_id"]
    )

    fig_rank.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111827",
        plot_bgcolor="#111827",
        height=400,
        xaxis_title="PageRank",
        yaxis_title="Account",
        legend_title="Risk Level"
    )

    st.plotly_chart(
        fig_rank,
        use_container_width=True
    )

# --------------------------------------------------
# ACCOUNT INVESTIGATION TABLE
# --------------------------------------------------

st.divider()

st.subheader("Account Risk Investigation")

st.dataframe(
    accounts,
    use_container_width=True,
    hide_index=True
)

# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()

st.caption(
    "Banking Fraud Detection & Suspicious Transaction "
    "Network Analysis | Synthetic Demonstration Dataset"
)
