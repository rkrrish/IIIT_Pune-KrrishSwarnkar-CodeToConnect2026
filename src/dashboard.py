import streamlit as st
import pandas as pd
import json
import os
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Tactical Index Rebalancing Dashboard", layout="wide")

st.title("Module 2: Tactical Index Rebalancing Dashboard")
st.markdown("""
This dashboard visualizes the dynamic rebalancing of our mock stock index (top 20 S&P 100 stocks) based on NLP sentiment signals using the **Black-Litterman Model**.
""")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
LEDGER_PATH = os.path.join(OUTPUT_DIR, "rebalancing_outputs", "rebalance_ledger.jsonl")
SIGNALS_PATH = os.path.join(OUTPUT_DIR, "risk_engine_outputs", "latest_risk_signals.json")

@st.cache_data
def load_data():
    if not os.path.exists(LEDGER_PATH):
        return pd.DataFrame(), {}
    
    events = []
    with open(LEDGER_PATH, 'r') as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
                
    df = pd.DataFrame(events)
    
    if os.path.exists(SIGNALS_PATH):
        with open(SIGNALS_PATH, 'r') as f:
            signals_data = json.load(f)
    else:
        signals_data = {}
        
    return df, signals_data

df, signals_data = load_data()

if df.empty:
    st.warning("No rebalancing data found. Please run the pipeline first.")
    st.stop()

# Aggregate view
st.header("Aggregate Portfolio Weights")

# We pivot to show old vs new for all tickers
agg_df = df.drop_duplicates(subset=["ticker"], keep="last")
agg_df = agg_df.sort_values(by="new_weight", ascending=False)

fig_bar = go.Figure(data=[
    go.Bar(name='Original Market Cap Weight', x=agg_df['ticker'], y=agg_df['old_weight']),
    go.Bar(name='New Target Weight', x=agg_df['ticker'], y=agg_df['new_weight'])
])
fig_bar.update_layout(barmode='group', title="Weight Changes Across Index", yaxis_title="Weight")
st.plotly_chart(fig_bar, use_container_width=True)

# Individual View
st.header("Individual Stock Drill-down")
selected_ticker = st.selectbox("Select a Ticker to view specifics:", agg_df['ticker'].tolist())

stock_data = agg_df[agg_df['ticker'] == selected_ticker].iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Old Weight", f"{stock_data['old_weight']:.2%}")
col2.metric("New Weight", f"{stock_data['new_weight']:.2%}", f"{(stock_data['new_weight'] - stock_data['old_weight']):.2%}")
col3.metric("Rolling Sentiment", f"{stock_data['rolling_sentiment_avg']:.2f}")

st.subheader("Audit Trail")
st.markdown(f"**Latest Event Triggering View:** `{stock_data['latest_event_id']}`")
st.markdown(f"**Calculated Impact Score:** `{stock_data['impact_score']}`")

if "signals" in signals_data:
    st.markdown("### Recent Signals for Ticker")
    # Find signals that match the ticker
    ticker_sigs = [s for s in signals_data["signals"] if s["ticker"] == selected_ticker]
    # Sort by timestamp desc
    ticker_sigs.sort(key=lambda x: x["published_at"], reverse=True)
    
    if ticker_sigs:
        st.dataframe(pd.DataFrame(ticker_sigs)[["published_at", "source", "event_id", "sentiment_score", "sentiment_label", "event_classification", "impact_score", "text_snippet"]])
    else:
        st.info("No recent signals found for this ticker.")
