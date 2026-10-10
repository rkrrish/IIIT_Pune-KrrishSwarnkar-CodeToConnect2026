from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timezone

app = FastAPI(title="S&P 100 NLP Risk Engine Dashboard API")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = Path(__file__).parent / "output"
LEDGER_PATH = OUTPUT_DIR / "rebalancing_outputs" / "rebalance_ledger.jsonl"
RISK_SIGNALS_PATH = OUTPUT_DIR / "risk_engine_outputs" / "latest_risk_signals.json"
RISK_SUMMARY_PATH = OUTPUT_DIR / "risk_engine_outputs" / "risk_summary_report.json"
SIGNALS_LEDGER_PATH = OUTPUT_DIR / "risk_engine_outputs" / "signals_history_ledger.jsonl"
LATEST_WEIGHTS_PATH = OUTPUT_DIR / "rebalancing_outputs" / "latest_weights.json"

# ── Pipeline state (thread-safe) ───────────────────────────────────────────
_pipeline_lock = threading.Lock()
_pipeline_status = {"status": "idle", "message": "", "last_run": None}

TOP_20_SP100_TICKERS = [
    {"ticker": "NVDA", "name": "NVIDIA", "sector": "Technology"},
    {"ticker": "AAPL", "name": "Apple", "sector": "Technology"},
    {"ticker": "MSFT", "name": "Microsoft", "sector": "Technology"},
    {"ticker": "AMZN", "name": "Amazon", "sector": "Consumer Cyclical"},
    {"ticker": "GOOGL", "name": "Alphabet Google", "sector": "Communication Services"},
    {"ticker": "META", "name": "Meta Platforms Facebook", "sector": "Communication Services"},
    {"ticker": "TSLA", "name": "Tesla", "sector": "Consumer Cyclical"},
    {"ticker": "BRK.B", "name": "Berkshire Hathaway", "sector": "Financial Services"},
    {"ticker": "LLY", "name": "Eli Lilly", "sector": "Healthcare"},
    {"ticker": "JPM", "name": "JPMorgan Chase", "sector": "Financial Services"},
    {"ticker": "WMT", "name": "Walmart", "sector": "Consumer Defensive"},
    {"ticker": "V", "name": "Visa", "sector": "Financial Services"},
    {"ticker": "XOM", "name": "ExxonMobil", "sector": "Energy"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
    {"ticker": "COST", "name": "Costco", "sector": "Consumer Defensive"},
    {"ticker": "MA", "name": "Mastercard", "sector": "Financial Services"},
    {"ticker": "PG", "name": "Procter & Gamble", "sector": "Consumer Defensive"},
    {"ticker": "UNH", "name": "UnitedHealth Group", "sector": "Healthcare"},
    {"ticker": "HD", "name": "Home Depot", "sector": "Consumer Cyclical"},
    {"ticker": "AVGO", "name": "Broadcom", "sector": "Technology"},
]

# Mock market cap weights (same as portfolio_data.py)
MOCK_MARKET_CAPS = {
    "AAPL": 3000, "MSFT": 3000, "NVDA": 2200, "GOOGL": 1800, "AMZN": 1800,
    "META": 1200, "TSLA": 600, "BRK.B": 800, "LLY": 700, "JPM": 500,
    "WMT": 400, "V": 500, "XOM": 400, "JNJ": 350, "COST": 350,
    "MA": 400, "PG": 350, "UNH": 450, "HD": 350, "AVGO": 600,
}
_total_cap = sum(MOCK_MARKET_CAPS.values())


def _read_ledger():
    """Read ledger JSONL and return list of dicts."""
    entries = []
    if LEDGER_PATH.exists():
        with LEDGER_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _read_risk_signals():
    """Read the latest risk signals JSON."""
    if RISK_SIGNALS_PATH.exists():
        with RISK_SIGNALS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _read_risk_summary():
    """Read the risk summary report."""
    if RISK_SUMMARY_PATH.exists():
        with RISK_SUMMARY_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── Dashboard endpoints ─────────────────────────────────────────────────────

@app.get("/api/dashboard/summary")
async def dashboard_summary():
    """Return high-level stats for the dashboard KPI cards."""
    entries = _read_ledger()

    if not entries:
        with _pipeline_lock:
            status = _pipeline_status["status"]
        return {
            "num_active_tickers": 0,
            "changed_weights_latest": 0,
            "pos_sentiment_events": 0,
            "neg_sentiment_events": 0,
            "latest_timestamp": None,
            "pipeline_status": status,
            "total_events_processed": 0,
        }

    latest = entries[-1]
    active_tickers = len({e.get("ticker") for e in entries if e.get("ticker")})
    changed_weights = sum(1 for e in entries if abs((e.get("new_weight") or 0) - (e.get("old_weight") or 0)) > 0.001)
    pos_sentiment = sum(1 for e in entries if (e.get("rolling_sentiment_avg") or 0) > 0)
    neg_sentiment = sum(1 for e in entries if (e.get("rolling_sentiment_avg") or 0) < 0)

    with _pipeline_lock:
        status = _pipeline_status["status"]

    return {
        "num_active_tickers": active_tickers,
        "changed_weights_latest": changed_weights,
        "pos_sentiment_events": pos_sentiment,
        "neg_sentiment_events": neg_sentiment,
        "latest_timestamp": latest.get("timestamp"),
        "pipeline_status": status,
        "total_events_processed": len(entries),
    }


@app.get("/api/dashboard/index")
async def dashboard_index():
    """Return S&P100 mock index constituents with current weights from latest pipeline output."""
    # Load latest weights if available
    latest_weights = {}
    if LATEST_WEIGHTS_PATH.exists():
        with LATEST_WEIGHTS_PATH.open("r", encoding="utf-8") as f:
            latest_weights = json.load(f)

    result = []
    for item in TOP_20_SP100_TICKERS:
        ticker = item["ticker"]
        base_weight = MOCK_MARKET_CAPS.get(ticker, 0) / _total_cap
        current_weight = latest_weights.get(ticker, base_weight)
        result.append({
            "ticker": ticker,
            "name": item["name"],
            "sector": item["sector"],
            "base_weight": round(base_weight, 6),
            "current_weight": round(current_weight, 6),
            "weight_change": round(current_weight - base_weight, 6),
        })

    return JSONResponse(content=result)


@app.get("/api/pipeline/status")
async def pipeline_status():
    """Return current pipeline execution status."""
    with _pipeline_lock:
        return _pipeline_status.copy()


# ── Ledger endpoints ────────────────────────────────────────────────────────

@app.get("/api/ledger")
async def get_ledger():
    """Read the rebalance ledger JSONL and return as list of objects with IDs."""
    entries = _read_ledger()
    # Add an index-based ID for inspection
    for i, entry in enumerate(entries):
        entry["_id"] = i
    return entries


@app.get("/api/ledger/{entry_id}")
async def get_ledger_entry(entry_id: int):
    """Get a specific ledger entry with enriched inspection data."""
    entries = _read_ledger()
    if entry_id < 0 or entry_id >= len(entries):
        return JSONResponse(status_code=404, content={"error": "Ledger entry not found"})

    entry = entries[entry_id]
    entry["_id"] = entry_id
    ticker = entry.get("ticker")

    # Enrich with risk signal data for this ticker
    risk_data = _read_risk_signals()
    ticker_signals = []
    if "signals" in risk_data:
        ticker_signals = [s for s in risk_data["signals"] if s.get("ticker") == ticker]
        # Only keep most recent 20 signals for the modal
        ticker_signals = ticker_signals[-20:]

    # Enrich with ticker summary from risk report
    summary = _read_risk_summary()
    ticker_summary = {}
    if "ticker_summaries" in summary:
        ticker_summary = summary["ticker_summaries"].get(ticker, {})

    return {
        "entry": entry,
        "risk_signals": ticker_signals,
        "ticker_summary": ticker_summary,
    }


@app.get("/api/ledger/stream")
async def ledger_stream():
    """SSE stream that pushes new ledger entries as they arrive."""
    async def event_generator():
        last_count = len(_read_ledger())
        while True:
            await asyncio.sleep(2)
            entries = _read_ledger()
            current_count = len(entries)
            if current_count > last_count:
                new_entries = entries[last_count:]
                for i, entry in enumerate(new_entries):
                    entry["_id"] = last_count + i
                    yield f"data: {json.dumps(entry)}\n\n"
                last_count = current_count

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Graph / Chart endpoints ─────────────────────────────────────────────────

@app.get("/api/dashboard/graph")
async def dashboard_graph(ticker: str = None):
    """Return weight history over time for charting. Optionally filter by ticker."""
    entries = _read_ledger()
    if not entries:
        return []

    if ticker:
        entries = [e for e in entries if e.get("ticker") == ticker]

    # Build time-series: group by timestamp, each group has weights per ticker
    result = []
    for i, e in enumerate(entries):
        result.append({
            "index": i,
            "timestamp": e.get("timestamp", ""),
            "ticker": e.get("ticker", ""),
            "new_weight": e.get("new_weight", 0),
            "old_weight": e.get("old_weight", 0),
            "weight_change": round((e.get("new_weight") or 0) - (e.get("old_weight") or 0), 6),
            "rolling_sentiment_avg": e.get("rolling_sentiment_avg", 0),
            "impact_score": e.get("impact_score", 0),
        })

    return result


@app.get("/api/dashboard/weight-history")
async def weight_history():
    """Return weight evolution data grouped by ticker for multi-line charting."""
    entries = _read_ledger()
    if not entries:
        return {"tickers": [], "series": {}}

    # Group entries by ticker, tracking weight over time
    from collections import defaultdict
    ticker_series = defaultdict(list)

    for i, e in enumerate(entries):
        ticker = e.get("ticker", "")
        ticker_series[ticker].append({
            "step": i,
            "timestamp": e.get("timestamp", ""),
            "weight": e.get("new_weight", 0),
            "old_weight": e.get("old_weight", 0),
            "sentiment": e.get("rolling_sentiment_avg", 0),
        })

    return {
        "tickers": list(ticker_series.keys()),
        "series": dict(ticker_series),
    }


# ── Pipeline control endpoints ──────────────────────────────────────────────

@app.post("/api/pipeline/run")
async def run_pipeline_endpoint(background_tasks: BackgroundTasks):
    """Run the full pipeline (demo mode) in background and return immediate ack."""
    with _pipeline_lock:
        if _pipeline_status["status"] == "running":
            return JSONResponse(
                status_code=409,
                content={"status": "error", "message": "Pipeline already running"}
            )
        _pipeline_status["status"] = "running"
        _pipeline_status["message"] = "Full pipeline batch started"

    def _run():
        try:
            import sys, os
            src_dir = os.path.dirname(os.path.abspath(__file__))
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from pipeline import RiskEnginePipeline
            pipeline = RiskEnginePipeline(mode="demo")
            pipeline.run_pipeline()
            with _pipeline_lock:
                _pipeline_status["status"] = "idle"
                _pipeline_status["message"] = "Pipeline completed successfully"
                _pipeline_status["last_run"] = datetime.now(timezone.utc).isoformat()
        except Exception as ex:
            with _pipeline_lock:
                _pipeline_status["status"] = "error"
                _pipeline_status["message"] = str(ex)

    background_tasks.add_task(_run)
    return {"status": "pipeline started"}


@app.post("/api/pipeline/next")
async def next_timestep_endpoint(background_tasks: BackgroundTasks):
    """Process the next timestep (single mock event) incrementally."""
    with _pipeline_lock:
        if _pipeline_status["status"] == "running":
            return JSONResponse(
                status_code=409,
                content={"status": "error", "message": "Pipeline already running"}
            )
        _pipeline_status["status"] = "running"
        _pipeline_status["message"] = "Processing next timestep..."

    def _run():
        try:
            import sys, os
            src_dir = os.path.dirname(os.path.abspath(__file__))
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from pipeline import RiskEnginePipeline
            pipeline = RiskEnginePipeline(mode="demo")
            pipeline.run_pipeline(max_payloads=1, clear_previous_stream=False)
            with _pipeline_lock:
                _pipeline_status["status"] = "idle"
                _pipeline_status["message"] = "Timestep processed"
                _pipeline_status["last_run"] = datetime.now(timezone.utc).isoformat()
        except Exception as ex:
            with _pipeline_lock:
                _pipeline_status["status"] = "error"
                _pipeline_status["message"] = str(ex)

    background_tasks.add_task(_run)
    return {"status": "next timestep started"}


@app.post("/api/pipeline/reset")
async def reset_demo_endpoint():
    """Reset the demo by deleting ledger and clearing output directories."""
    # Clear rebalancing outputs
    rebal_dir = OUTPUT_DIR / "rebalancing_outputs"
    if rebal_dir.exists():
        for f in rebal_dir.iterdir():
            f.unlink()

    # Clear risk engine outputs
    risk_dir = OUTPUT_DIR / "risk_engine_outputs"
    if risk_dir.exists():
        for f in risk_dir.iterdir():
            if f.is_file():
                f.unlink()

    with _pipeline_lock:
        _pipeline_status["status"] = "idle"
        _pipeline_status["message"] = "Demo reset completed"
        _pipeline_status["last_run"] = None

    return {"status": "reset completed"}


@app.get("/api/ping")
async def ping():
    return {"ping": "pong"}
