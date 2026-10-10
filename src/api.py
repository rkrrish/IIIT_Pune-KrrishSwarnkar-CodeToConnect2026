from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
import json
from pathlib import Path

app = FastAPI()

# Path to the ledger JSONL file (adjust if needed)
LEDGER_PATH = Path(__file__).parent.parent / "output" / "rebalancing_outputs" / "rebalance_ledger.jsonl"

# Mock index constituents data (replace with real source if available)
MOCK_INDEX = [
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology", "current_weight": 0.065},
    {"ticker": "MSFT", "name": "Microsoft Corp.", "sector": "Technology", "current_weight": 0.058},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "sector": "Communication Services", "current_weight": 0.045},
    # Add more mock entries as needed to resemble S&P100 layout
]

@app.get("/api/dashboard/summary")
async def dashboard_summary():
    """Return a JSON object with high‑level stats for the dashboard cards.
    For simplicity we compute a few basic metrics from the ledger.
    """
    if not LEDGER_PATH.exists():
        # No ledger yet – return defaults
        return {
            "num_active_tickers": 0,
            "changed_weights_latest": 0,
            "pos_sentiment_events": 0,
            "neg_sentiment_events": 0,
            "latest_timestamp": None,
            "pipeline_status": "idle",
        }
    # Load ledger lines
    entries = []
    with LEDGER_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not entries:
        return {
            "num_active_tickers": 0,
            "changed_weights_latest": 0,
            "pos_sentiment_events": 0,
            "neg_sentiment_events": 0,
            "latest_timestamp": None,
            "pipeline_status": "idle",
        }
    latest = entries[-1]
    # Compute simple aggregates
    active_tickers = len({e.get("ticker") for e in entries if e.get("ticker")})
    changed_weights = sum(1 for e in entries if e.get("new_weight") != e.get("old_weight"))
    pos_sentiment = sum(1 for e in entries if (e.get("rolling_sentiment_avg") or 0) > 0)
    neg_sentiment = sum(1 for e in entries if (e.get("rolling_sentiment_avg") or 0) < 0)
    return {
        "num_active_tickers": active_tickers,
        "changed_weights_latest": changed_weights,
        "pos_sentiment_events": pos_sentiment,
        "neg_sentiment_events": neg_sentiment,
        "latest_timestamp": latest.get("timestamp"),
        "pipeline_status": "running",
    }

@app.get("/api/dashboard/index")
async def dashboard_index():
    """Return mock index constituents – mimic S&P100 style data."""
    return JSONResponse(content=MOCK_INDEX)

# New endpoints for pipeline control
from fastapi import BackgroundTasks
import subprocess
from pathlib import Path
import json

@app.post("/api/pipeline/run")
async def run_pipeline_endpoint(background_tasks: BackgroundTasks):
    """Run the full pipeline (demo mode) in background and return immediate ack."""
    def _run():
        # Import and execute the pipeline synchronously
        from src.pipeline import RiskEnginePipeline
        pipeline = RiskEnginePipeline(mode="demo")
        pipeline.run_pipeline()
    background_tasks.add_task(_run)
    return {"status": "pipeline started"}

@app.post("/api/pipeline/next")
async def next_timestep_endpoint(background_tasks: BackgroundTasks):
    """Process the next timestep (single event) without clearing previous ledger."""
    def _run():
        from src.pipeline import RiskEnginePipeline
        pipeline = RiskEnginePipeline(mode="demo")
        pipeline.run_pipeline(max_events=1, clear_previous_stream=False)
    background_tasks.add_task(_run)
    return {"status": "next timestep started"}

@app.post("/api/pipeline/reset")
async def reset_demo_endpoint():
    """Reset the demo by deleting ledger and clearing output directories."""
    ledger_path = Path(__file__).parent.parent / "output" / "rebalancing_outputs" / "rebalance_ledger.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()
    # Also clear risk engine outputs if needed
    risk_dir = Path(__file__).parent.parent / "output" / "risk_engine_outputs"
    if risk_dir.exists():
        for f in risk_dir.iterdir():
            f.unlink()
    return {"status": "reset completed"}

@app.get("/api/ledger")
async def get_ledger():
    """Read the rebalance ledger JSONL and return as list of objects."""
    ledger_path = Path(__file__).parent.parent / "output" / "rebalancing_outputs" / "rebalance_ledger.jsonl"
    entries = []
    if ledger_path.exists():
        with ledger_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries
@app.get("/api/ping")
async def ping():
    return {"ping": "pong"}
