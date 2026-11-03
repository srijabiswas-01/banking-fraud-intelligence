# Banking Fraud Intelligence Dashboard

**Graph-based suspicious transaction monitoring and investigation using Neo4j AuraDB, Python, NetworkX, Plotly and Streamlit.**

> **Portfolio proof of concept.** This project uses synthetic banking data. Alerts, risk scores and network metrics are illustrative signals for investigation—not confirmed fraud, validated predictions or fraud probabilities.

**Live dashboard:** [Launch Banking Fraud Intelligence](https://banking-fraud-intelligence-dashboardvisual.streamlit.app/)

![Banking Fraud Intelligence Dashboard](assets/dashboard-overview.png)

## Executive summary

Traditional transaction tables reveal individual payments but can obscure relationships between accounts. This project models customers, accounts, transactions, devices and addresses as a graph in **Neo4j AuraDB**. A Python analytics workflow calculates Louvain communities, PageRank and heuristic account-risk scores; a hosted **Streamlit** application visualises the resulting network and provides account investigation tools.

The latest dashboard also generates **four categories of read-only, rule-based suspicious activity alerts** directly from Neo4j: high-value transfers, shared devices, shared addresses and three-account transfer cycles. Analysts can filter and export alert records and inspect alerts associated with a selected primary account.

### Business questions

- Which accounts have the highest rule-based risk scores?
- Which accounts transfer funds to one another, and in what direction?
- Which communities and structurally influential accounts warrant further examination?
- Which transfers exceed the demonstration high-value threshold?
- Which accounts are associated with shared devices, addresses or directed transfer cycles?
- What evidence and transaction history are available for an investigation?

## Dashboard capabilities

| Area | Capability | Analyst value |
| --- | --- | --- |
| Executive overview | Total accounts, transaction count, transfer value, high-risk account count | Establish dataset scope |
| Risk distribution | Interactive chart of account risk classifications | Compare risk groups |
| Network influence | PageRank account ranking | Explore relative network centrality |
| Interactive network | Directed account-to-account graph, hover details, zoom and pan | Trace money flows |
| Community analysis | Louvain community colours | Explore structural clusters |
| Sidebar filters | Risk level, community and account-ID search | Focus network and account views |
| **Suspicious activity alerts** | Four Cypher detection rules | Surface activity requiring review |
| **Alert KPIs** | Alert records by severity and distinct primary accounts | Summarise investigation workload |
| **Alert filters** | Severity, category and optional sidebar-account matching | Prioritise specific alerts |
| **Alert chart** | Plotly counts by alert type and severity | Compare alert categories |
| **Account-level alerts** | Alerts listing the selected account as primary account | Provide rule-based context |
| Account drill-down | Risk score, PageRank and incoming/outgoing transaction history | Examine individual accounts |
| Customer context | Linked customer, device and registered-address IDs | Inspect shared identifiers |
| CSV exports | Account, transaction and alert exports | Support offline review |
| Data refresh | Clear cached data and rerun queries | Retrieve updated Neo4j records |

**Filter behaviour:** Executive KPIs and the risk-distribution chart describe the full dataset. The sidebar filters affect the PageRank ranking, transaction network and account investigation table. Network edges appear only when **both endpoint accounts** match the filters. The account drill-down displays the selected account's transactions from the full transaction dataset. Alert KPIs count all alert records; alert-table filters are independent, with an optional checkbox to match sidebar-selected accounts.

## Live dashboard preview

The screenshot is expected at `assets/dashboard-overview.png`. If it is not yet uploaded, add it to the repository or remove the image line above to avoid a broken image.

## Technology stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| Graph database | Neo4j AuraDB | Stores banking entities and relationships |
| Graph queries | Cypher | Retrieves data and evaluates alert rules |
| Data preparation | Python, pandas | Tabular processing and aggregation |
| Graph analytics | NetworkX | Upstream Louvain/PageRank workflow; dashboard spring layout |
| Interactive visualisation | Plotly | Risk charts, alert chart and transaction network |
| Application | Streamlit | Filters, KPIs, drill-down and exports |
| Deployment | Streamlit Community Cloud | Public demonstration hosting |
| Source control | GitHub | Application code and documentation |

## Graph data model

| Node | Meaning | Initial count |
| --- | --- | ---: |
| `Customer` | Synthetic banking customer | 10 |
| `Account` | Customer-owned account | 10 |
| `Transaction` | Transfer event | 15 |
| `Device` | Customer-associated device | 7 |
| `Address` | Registered address | 7 |
| `Merchant` | Merchant node (not currently used in dashboard) | 5 |
| **Total nodes** | | **54** |

**Initial relationships:** 83.

```cypher
(:Customer)-[:OWNS]->(:Account)
(:Customer)-[:USES]->(:Device)
(:Customer)-[:REGISTERED_AT]->(:Address)
(:Account)-[:INITIATED]->(:Transaction)
(:Transaction)-[:SENT_TO]->(:Account)
(:Account)-[:TRANSFERRED_TO]->(:Account)
(:Customer)-[:SHARED_DEVICE_WITH]->(:Customer)
(:Customer)-[:SHARED_ADDRESS_WITH]->(:Customer)
```

**Transaction counting:** Dashboard totals use the `Account → INITIATED → Transaction → SENT_TO → Account` representation. The separate `TRANSFERRED_TO` relationships are used to identify directed three-account cycles; they are **not** added to transaction totals.

These counts describe the initial synthetic dataset; current database totals may differ.

## Analytics methodology

### Louvain community detection

The upstream Python workflow applies Louvain community detection to an undirected representation of the account-transfer network and writes `community_id` to account nodes. The dashboard reads those stored IDs and colours nodes accordingly. **A community is not a confirmed fraud ring.**

### PageRank

The upstream workflow computes PageRank and stores it in `Account.pagerank`. The dashboard uses the values for influence ranking and account drill-down. **PageRank is not a fraud probability.**

### Enhanced rule-based risk scoring

The earlier Python analysis workflow assigned illustrative points:

| Indicator | Points |
| --- | ---: |
| Device shared with at least two other customers | 25 |
| Address shared with at least two other customers | 15 |
| At least one outgoing transfer of ₹50,000 or more | 20 |
| Participation in a rapid three-account transfer cycle | 25 |
| PageRank above the dataset's 80th percentile | 15 |
| **Maximum** | **100** |

Illustrative risk categories: **Low 0–39**, **Medium 40–69**, **High 70–100**.

The application reads `enhanced_risk_score` and `enhanced_risk_level` when available, falling back to `risk_score` and `risk_level`. It does not recalculate these scores on every page load. These weights and cut-offs were not trained or validated on labelled fraud outcomes.

## Suspicious activity alert engine

The updated application queries Neo4j directly and produces an alert table with `alert_id`, `alert_type`, `severity`, `primary_account`, `related_accounts` and `evidence`.

| Detection rule | Trigger | Severity | Output granularity |
| --- | --- | --- | --- |
| `HIGH_VALUE_TRANSFER` | Individual transfer ≥ ₹50,000 | High | One record per qualifying transaction |
| `SHARED_DEVICE` | Device used by ≥ 3 distinct customers | Medium | One record per linked account |
| `SHARED_ADDRESS` | Address registered to ≥ 3 distinct customers | Medium | One record per linked account |
| `CIRCULAR_TRANSFER` | Directed cycle across three distinct accounts | High | One record per detected cycle representation |

**Interpretation notes:**

- Thresholds and severities are **illustrative** and are not calibrated banking policies.
- Shared-device/address alert counts represent **account-level alert records**, not unique devices or addresses.
- The circular alert rule checks **graph structure**, not transfer timestamps or velocity. It should not be described as detecting *rapid* cycles without a separate temporal check.
- The selected account's alert section shows records where it is the **primary account**. An account named only in `related_accounts` may not appear there.
- Alert queries are **read-only**; this implementation does not persist alert cases, statuses or analyst notes.
- The alert engine is separate from the previously calculated account risk score; generating an alert does not automatically update that score.

## Illustrative investigation scenario

The synthetic graph includes a directed transfer cycle:

```text
A003 ──▶ A004
  ▲         │
  │         ▼
  └────── A005
```

A directed cycle may warrant review alongside transfer amounts, timestamps, counterparties and legitimate business context. **A cycle alone does not prove fraudulent behaviour.**

An analyst can review the account network, inspect the alert table, filter for `CIRCULAR_TRANSFER`, select a primary account in the drill-down, examine incoming and outgoing transactions, and export the relevant records.

## Project structure

```text
banking-fraud-intelligence/
├── app.py                    # Streamlit app, Neo4j queries and alert rules
├── requirements.txt          # Python dependencies
├── README.md                 # Project documentation
├── .gitignore                # Excludes local secrets and environment files
└── assets/
    └── dashboard-overview.png
```

The `assets/` directory is optional until a screenshot is uploaded. The upstream Colab analysis notebook is not included in this structure unless you add it to the repository.

## Run locally

**Prerequisites:** Python 3.10+ and access to a Neo4j AuraDB instance containing the expected graph schema and stored account analytics.

1. Clone your GitHub repository:

   ```bash
   git clone YOUR_GITHUB_REPOSITORY_URL
   cd banking-fraud-intelligence
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # macOS / Linux:
   # source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a local `.streamlit/secrets.toml` file:

   ```toml
   NEO4J_URI = "neo4j+s://YOUR_INSTANCE.databases.neo4j.io"
   NEO4J_USERNAME = "neo4j"
   NEO4J_PASSWORD = "YOUR_DATABASE_PASSWORD"
   ```

5. Launch:

   ```bash
   streamlit run app.py
   ```

The app uses `driver.session()` without a hard-coded database name, allowing Aura to select its default database.

### `requirements.txt`

```text
streamlit
neo4j
pandas
plotly
networkx
numpy
```

### `.gitignore`

```gitignore
.streamlit/secrets.toml
.env
.env.*
.venv/
__pycache__/
*.pyc
.ipynb_checkpoints/
```

## Deploy to Streamlit Community Cloud

1. Push `app.py`, `requirements.txt` and `README.md` to your GitHub repository.
2. In Streamlit Community Cloud, select the repository, branch and `app.py` entry point.
3. Configure `NEO4J_URI`, `NEO4J_USERNAME` and `NEO4J_PASSWORD` in the application's private Secrets settings.
4. Deploy and verify that the executive metrics, network, alert table and account drill-down load successfully.
5. Test the sidebar filters, CSV exports and refresh action.

**Security:** Never commit Neo4j passwords, `.streamlit/secrets.toml`, real customer data or other credentials. Rotate credentials immediately if exposed. Use synthetic or appropriately authorised data, and least-privilege database access where supported.

## Validation checklist

- [ ] Live dashboard loads without Neo4j errors.
- [ ] KPI transaction count matches the intended transaction records.
- [ ] Network nodes and directed connections render correctly.
- [ ] Risk and community filters work as expected.
- [ ] High-value, shared-device, shared-address and cycle queries execute successfully.
- [ ] Alert filters, counts and CSV export work.
- [ ] Account drill-down shows transactions and linked customer context.
- [ ] No credentials are present in public repository files.
- [ ] Dashboard screenshot appears in the README.

## Limitations and responsible use

- **Synthetic, small dataset:** The initial graph has 10 accounts and 15 transactions, which is insufficient to establish real-world fraud detection effectiveness.
- **No validated model performance:** Precision, recall, false-positive rates and ROC-AUC have not been evaluated against labelled outcomes.
- **Illustrative heuristics:** Risk points, thresholds and alert severities are not calibrated or independently validated.
- **No real-time ingestion:** The application queries stored Neo4j data, with cached results generally refreshed every five minutes or on demand.
- **No production case management:** There are no persistent case statuses, analyst notes, approvals, audit logs or regulatory reporting workflows.
- **Limited graph scale:** NetworkX spring layouts are suitable for a small demonstration but can become slow or crowded on larger networks.
- **No fraud determination:** Community membership, PageRank, shared identifiers, high-value transfers and cycles can all occur for legitimate reasons.

The application is a **graph analytics and suspicious-activity investigation portfolio project**, not a production fraud decision engine or regulatory compliance platform.

## Future enhancements

- Add realistic synthetic scenarios and labelled evaluation datasets.
- Introduce time-windowed transfer velocity and temporal cycle detection.
- Create persistent investigation cases with ownership, status, notes and audit history.
- Evaluate alert precision, recall and false-positive rates on labelled scenarios.
- Add authentication, role-based permissions, monitoring and automated deployment tests.
- Optimise queries and network rendering for larger datasets.

## Project status

**Implemented in code:** Neo4j-backed Streamlit dashboard, executive KPIs, PageRank and Louvain visualisations, directed transaction network, account drill-down, customer context, CSV exports and a four-rule suspicious activity alert engine.

**Final verification:** Confirm that the latest alert-enabled `app.py` is deployed and that all four Cypher alert rules run against the live AuraDB graph.

---

**Disclaimer:** All demonstration customers, accounts and transactions are synthetic. Suspicious-activity flags indicate patterns for analytical review, not established fraudulent conduct.
