## 1. Project Overview

Act as a senior frontend engineer, financial dashboard designer, and data visualization specialist. Build a professional, responsive, web-based dashboard for a **Sentiment-Driven Dynamic Stock Index Rebalancing System**.

The application monitors financial news, social media posts, and other integrated data feeds. An existing NLP Risk Engine analyzes incoming information and produces sentiment scores, impact scores, event classifications, and other risk metrics. A downstream rebalancing engine uses a series of sentiment observations, event significance, and relationships between stocks to dynamically adjust portfolio weights.

Your primary responsibility is to build the **visualization and user interaction layer** that makes the system understandable, verifiable, and usable by financial analysts, portfolio managers, researchers, and system evaluators.

### Critical development requirement

First, inspect the existing codebase, its framework, available APIs, data models, and the implementations of the NLP Risk Engine and rebalancing engine.

Do not rewrite, duplicate, or replace existing engine logic. Integrate with the existing modules through their actual interfaces. If a required API is not yet available, create a clearly separated adapter or mock implementation for demonstration purposes.

The application must support two operating modes:

- **Demo Mode:** A deterministic, step-by-step simulation using historical or synthetic input data.
- **Live Mode:** Fetch new data through the APIs already integrated into the codebase, execute the existing NLP and rebalancing pipelines, and display the updated index state.

The interface must never suggest that simulated data is live market data.

---

## 2. Design Direction and Visual Identity

Create a polished financial analytics web application with a clean, professional, institutional appearance.

### Visual style

- Use a light theme with a white or warm off-white background.
- Use navy blue, slate, muted blue, soft teal, and restrained green and red accents.
- Use green for positive changes and red for negative changes, with neutral colors for unchanged values.
- Avoid dark neon colors, excessive gradients, glowing elements, excessive shadows, and decorative animations.
- Use a modern sans-serif font such as Inter, or the font already used by the project.
- Use thin borders, subtle card backgrounds, consistent spacing, and clear typographic hierarchy.
- Keep tables and charts information-dense but readable.
- Use consistent number formatting for percentages, scores, prices, and portfolio weights.

The design should resemble a modern institutional portfolio analytics platform rather than a cryptocurrency trading terminal.

### Layout

Build the application as a responsive webpage with:

1. A persistent top navigation/header.
2. A compact left sidebar or navigation rail.
3. A central dashboard workspace.
4. Expandable detail panels, drawers, or modals for stock-level information and audit trails.

On smaller screens, collapse the sidebar and allow tables to scroll horizontally where necessary.

---

## 3. Header and Global Controls

Create a top header containing:

- Application logo and name: **Sentiment Index Monitor**
- Current operating mode indicator: `DEMO` or `LIVE`
- Active index selector.
- Last successful update timestamp.
- Data connection status.
- Current simulation timestep in demo mode.
- Primary action buttons.

### Operating mode selector

Provide a visible mode switch between Demo and Live.

Switching modes must be explicit. If switching to Live mode requires API credentials or connections that are unavailable, show a clear connection/setup message instead of silently falling back to mock data.

### Primary buttons

**A. Next Timestep — Demo Mode Only**

Advance the simulation cursor to the next predefined timestep.

Expected behavior:

- Move to the next simulation timestep.
- Load the input feeds associated with that timestep.
- Update the current timestep indicator.
- Update the displayed input-feed data.
- Do not automatically execute the NLP or rebalancing engines unless the existing implementation explicitly couples these operations.

If the simulation reaches its final timestep, disable the button or provide a clearly labeled restart option.

**B. Refresh / Run Pipeline**

In Demo Mode:

- Execute the NLP Risk Engine using the input feeds for the current timestep.
- Display the resulting sentiment and risk outputs.
- Execute the rebalancing engine using the appropriate sentiment history and current portfolio state.
- Update portfolio weights, index metrics, recent changes, and charts.
- Record the execution result and timestamp.

The button must visibly distinguish between an idle, running, successful, and failed state.

In Live Mode:

- Fetch new news, social media feeds, and other available data through the integrated APIs.
- Normalize and validate incoming records.
- Run the existing NLP Risk Engine.
- Pass its output to the rebalancing engine.
- Update the index state and visualizations.
- Record a timestamped execution summary.

Prevent accidental duplicate pipeline execution while a run is already in progress.

If a pipeline stage fails, display the failed stage, an understandable error message, and a retry option. Do not show a successful rebalance when execution has failed.

**C. Reset Simulation — Demo Mode**

Restore the initial simulation timestep and initial portfolio state. Confirm before resetting if the current simulation contains changes that would otherwise be lost.

---

## 4. Main Dashboard Overview

The default landing page should answer five questions immediately:

1. What is the current state of the index?
2. Which stocks have changed the most?
3. How have the portfolio weights evolved over time?
4. Which sentiment events caused the changes?
5. Has the latest pipeline run completed successfully?

### KPI cards

Display a row of summary cards containing:

- Number of stocks in the active index.
- Number of stocks whose weights changed in the latest rebalance.
- Number of significant positive sentiment events.
- Number of significant negative sentiment events.
- Latest rebalance timestamp.
- Pipeline status.

Where supported by the existing data model, also display the aggregate portfolio sentiment or risk score.

Every score should have a tooltip explaining its meaning and scale. Do not invent financial metrics that the backend does not calculate.

---

## 5. Top 10–15 Indexes and Index Selection

Display the **10–15 most indexes** in a dedicated index overview sectionS&P 100These are examples only. Display an index only when it is supported by the application or can be explicitly configured.

For a prototype, create configurable index entries and mock data where necessary. Do not imply that all listed indexes are connected to real-time feeds or directly rebalanced by this system.

Each index card or table row should show:

- Index name and symbol.
- Number of constituents.
- Current aggregate sentiment, if available.
- Latest rebalance timestamp.
- Number of constituents whose weights changed.
- Change in a supported index performance or risk metric.
- Current status: Normal, Processing, Warning, or Error.

Use a compact card grid or sortable table rather than oversized cards.

For indexes that are reference benchmarks rather than managed portfolios, label them as benchmarks and distinguish their actual weights from the weights of the application's simulated portfolio.

---

## 6. Portfolio Constituents and Weight Table

For the selected index, display a comprehensive table of its constituent stocks.

The table should include:

| Column          | Description                                  |
| --------------- | -------------------------------------------- |
| Rank            | Current position by portfolio weight         |
| Stock           | Company name                                 |
| Ticker          | Trading symbol                               |
| Current Weight  | Latest portfolio allocation percentage       |
| Previous Weight | Allocation before the latest rebalance       |
| Weight Change   | Absolute percentage-point difference         |
| Relative Change | Relative percentage change, where meaningful |
| Sentiment Score | Latest aggregated sentiment                  |
| Impact Score    | Latest event impact or risk score            |
| Sentiment Trend | Positive, Negative, Mixed, or Neutral        |
| Change Reason   | Concise explanation of the rebalance         |
| Last Updated    | Timestamp of the latest relevant update      |

Requirements:

- Support sorting by current weight, weight change, sentiment, and impact.
- Provide ticker and company-name search.
- Support filters for positive, negative, mixed, and neutral sentiment.
- Highlight meaningful weight changes without making minor changes visually dominant.
- Display positive and negative changes using restrained green and red indicators.
- Allow the user to click any stock to open its detailed analysis page or side panel.
- Display values with consistent precision.
- Distinguish missing data from zero values.

Make the most important columns visible by default. Move secondary fields into expandable details if the table becomes too wide.

---

## 7. Main Visualization: Portfolio Weight Changes Over Time

Create a prominent, interactive chart that visualizes how the portfolio's stock weights evolve across simulation timesteps or historical timestamps.

### Chart requirements

Use a charting library already installed in the project. If none exists, use a suitable React-compatible library such as Recharts, provided it fits the existing framework.

Provide the following chart modes:

**A. All Stocks Together**

- Show the weight history of all constituent stocks.
- Use a multi-series line chart for individual stock weights.
- Provide a legend and hover tooltips.
- Allow the user to toggle individual stocks on or off.
- Support selecting a subset of stocks.
- Keep colors distinguishable without using neon colors.

For 10–20 constituents, display all series where legibility permits.

**B. Individual Stock View**

When a stock is selected, display a larger chart of its weight over time.

Include:

- Portfolio weight at each timestep.
- Previous and current weight.
- Sentiment score over time, where available.
- Markers for rebalance events.
- Markers for significant sentiment events.
- Hover details containing timestamps and relevant values.

Use a secondary axis for sentiment only if it remains clear which scale belongs to which metric.

**C. Weight Change View**

Provide a bar chart showing the weight change from the previous rebalance to the current rebalance.

- Positive bars indicate increased allocation.
- Negative bars indicate reduced allocation.
- Sort by absolute weight change or allow the user to select a sorting order.
- Include exact percentage-point changes in tooltips.

**D. Portfolio Allocation View**

Provide an optional stacked area chart showing the relative allocation of constituent stocks over time.

Use this to visualize the redistribution of capital across the portfolio. Ensure the weights are valid and normalized when the application requires a fully invested portfolio.

### Chart interactions

- Hover to reveal exact values and timestamps.
- Click a chart series to open that stock's detail panel.
- Click a rebalance marker to inspect the corresponding rebalance event.
- Support a selectable time range.
- Preserve the selected index and stock when changing chart modes where practical.
- Show an informative empty state if historical observations do not exist.

Do not animate every data point or use decorative animation that interferes with analytical use.

---

## 8. Recent Rebalancing Activity

Create a **Recent Rebalancing Activity** panel on the main dashboard.

Show the latest 10–20 rebalance events, with pagination or an expandable history view for older events.

Each event should contain:

- Timestamp.
- Index name.
- Stock ticker.
- Previous weight.
- New weight.
- Weight change in percentage points.
- Direction of change.
- Primary reason.
- Related sentiment or risk event.
- Pipeline run ID.

Allow the user to click an event to open a detailed audit view.

The event history must be based on recorded engine outputs rather than reconstructed from the latest portfolio state.

Include an empty state for a new simulation and an error state if the event history cannot be retrieved.

---

## 9. Demo Mode: Input Feed, NLP Output, and Rebalancing Output

Build a dedicated **Simulation Inspector** view that lets users verify each timestep from raw input through to the final portfolio changes.

Use three clearly labeled stages.

### Stage 1: Input Feeds

Display the input records associated with the current timestep.

For each record, show:

- Source platform or provider.
- Headline or post text.
- Author or publisher, if available.
- Publication timestamp.
- Stock ticker or entity references.
- Source URL, when available.
- Record ID.
- Data ingestion status.

Support opening the original article or post through its source URL.

Where a feed is synthetic, clearly label it `SIMULATED DATA` and do not invent real source URLs.

Provide filters by ticker, source, and event category.

### Stage 2: NLP Risk Engine Output

For each processed input, display the actual output returned by the existing engine.

Possible fields include:

- Sentiment classification.
- Sentiment score.
- Impact score.
- Event classification.
- Affected stocks.
- Confidence score, if supported.
- Risk flags.
- Processing timestamp.
- NLP result ID.
- Reference to the original input record.

Make it possible to select an NLP result and inspect the corresponding input feed.

Clearly separate raw engine output from any explanatory text generated by the frontend.

Do not create fake NLP outputs when the actual engine has not run. Before execution, show a `Not processed` state.

### Stage 3: Rebalancing Engine Output

Display the actual output returned by the rebalancing engine.

For every affected stock, show:

- Previous portfolio weight.
- Proposed portfolio weight.
- Applied portfolio weight.
- Weight change.
- Aggregated sentiment evidence.
- Relevant historical sentiment observations.
- Related event IDs.
- Relevant stock-to-stock relationship effects, if available.
- Rebalancing rule or reason code, if exposed by the backend.
- Execution status.

If the engine returns a breakdown of direct sentiment effects and cross-stock effects, visualize those separately.

Include a clear before-and-after comparison of the portfolio.

Provide a JSON inspection panel for the raw input, NLP output, and rebalancing result, with syntax highlighting if supported. Include a copy-to-clipboard action.

The inspector should make it easy to follow the complete chain:

**Original Feed → NLP Risk Result → Aggregated Sentiment Evidence → Rebalancing Decision → Updated Portfolio Weight**

Each stage should expose stable record IDs that connect it to the next stage.

---

## 10. Sentiment Aggregation and Single-Event Overrides

The interface must reflect that rebalancing is based primarily on a series of sentiment observations rather than one isolated positive or negative post.

For every stock, provide a sentiment evidence panel containing:

- Recent sentiment observations.
- Sentiment trend over the selected period.
- Aggregated sentiment score, if available.
- Number of supporting observations.
- Event impact distribution.
- Confidence or evidence-quality indicators, if available.
- The most influential observations.
- The time window used for aggregation, if exposed by the engine.

Where the engine supports exceptional high-impact events, clearly identify when a single event has triggered a special adjustment.

Distinguish between:

- Normal adjustments driven by accumulated evidence.
- Significant single-event overrides.
- Changes influenced by cross-stock relationships.
- No-change outcomes despite incoming sentiment.

Do not implement new aggregation rules in the frontend. Display the existing engine's reasoning and decision metadata. If a particular field is unavailable, omit it or mark it as unavailable rather than calculating an alternative that could misrepresent the engine.

---

## 11. Cross-Stock Influence and Relationship Visualization

Because sentiment concerning one company may influence related companies, add an optional **Stock Relationship Analysis** view.

When relationship data is available, display a network graph or relationship table.

Each node represents a stock. Connections represent relationships recognized by the existing engine, such as sector exposure, supply-chain dependencies, or model-defined relationships.

Use:

- Node size to represent portfolio weight.
- Node color to represent the selected sentiment state.
- Edge direction to represent the direction of influence, if directional data exists.
- Edge thickness to represent influence strength, if quantified by the engine.

Clicking a node should display:

- Direct sentiment evidence for that stock.
- Related stocks.
- Incoming and outgoing influences.
- Any recorded indirect effect on its weight.

Provide a fallback table if the graph becomes too complex or the required relationship data is unavailable.

Never infer causal relationships solely from correlated stock movements. Label model-derived relationships according to their actual meaning.

---

## 12. Audit Trail and Explainability

Auditability is a core product requirement.

Every applied weight change must be traceable to the engine outputs and source records that contributed to it.

Create a detailed **Rebalance Audit Drawer** with the following sections:

1. Rebalance event ID and execution timestamp.
2. Previous and updated portfolio weights.
3. Relevant input feed records.
4. NLP output records.
5. Aggregated sentiment evidence.
6. Event impact and classification details.
7. Direct and indirect stock effects, where provided.
8. Rebalancing engine output and reason codes.
9. Pipeline execution status.
10. Source links and record identifiers.

Provide navigation between linked records. For example, a user should be able to click a weight change, inspect the rebalancing decision, open the associated sentiment result, and then view the original article or post.

If multiple records contributed to a decision, display all available references instead of presenting only one source.

Do not claim that a particular source caused a weight change unless the engine provides sufficient attribution. Where attribution is incomplete, label the evidence as related rather than definitively causal.

---

## 13. Live Mode: Data Refresh and Pipeline Monitoring

Live Mode must use the existing API integrations and backend pipeline.

Create a pipeline execution panel with stages such as:

1. Fetching external data.
2. Validating and normalizing feeds.
3. Running the NLP Risk Engine.
4. Aggregating sentiment evidence.
5. Running the rebalancing engine.
6. Validating portfolio constraints.
7. Persisting the updated portfolio.
8. Refreshing the dashboard.

Show the actual status of each stage when the backend exposes it.

Display:

- Latest execution ID.
- Execution start and completion times.
- Number of records fetched.
- Number of records processed.
- Number of affected stocks.
- Number of applied weight changes.
- Warnings and failures.

If the backend exposes only a single synchronous operation, show the actual operation's status without inventing individual pipeline stages or fake progress percentages.

Use the application's existing polling, event-streaming, or WebSocket mechanism where available. Do not introduce unnecessary polling if the existing architecture already provides updates.

A failed refresh must preserve the last successfully persisted portfolio and visibly indicate that the displayed data is stale.

Include the last successful update timestamp so users can distinguish fresh data from previously available data.

---

### Implementation workflow

1. Inspect the repository and report the existing framework, entry point, engine interfaces, and available API integrations.
2. Identify which required features can be connected directly and which require mock adapters.
3. Implement the dashboard layout and navigation.
4. Implement the index overview, constituent table, and historical weight visualizations.
5. Implement demo timestep controls and the three-stage simulation inspector.
6. Integrate the audit trail and cross-stock relationship views.
7. Connect live refresh to the existing backend.
8. Add validation, error handling, responsive behavior, and tests.
9. Run the application and verify the principal user workflows.
10. Summarize the implemented features, changed files, startup command, integration assumptions, and remaining backend dependencies.

**Final objective:** Build a trustworthy, attractive, analyst-friendly financial dashboard that makes dynamic sentiment-based index rebalancing observable, explainable, and auditable. Every displayed portfolio change should be traceable to recorded engine outputs, and users should be able to move seamlessly from the overall index to an individual stock, its sentiment history, the contributing input feeds, and the resulting rebalancing decision.
