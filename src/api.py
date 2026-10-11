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
_pipeline_status = {
    "status": "idle",
    "mode": "demo",
    "stage": "idle",
    "progress": 0,
    "message": "",
    "failed_stage": None,
    "error_message": None,
    "last_run": None,
}


def _update_status_cb(stage: str, progress: int, message: str):
    with _pipeline_lock:
        _pipeline_status["stage"] = stage
        _pipeline_status["progress"] = progress
        _pipeline_status["message"] = message


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
            mode = _pipeline_status["mode"]
        return {
            "num_active_tickers": 0,
            "changed_weights_latest": 0,
            "pos_sentiment_events": 0,
            "neg_sentiment_events": 0,
            "latest_timestamp": None,
            "pipeline_status": status,
            "mode": mode,
            "total_events_processed": 0,
        }

    latest = entries[-1]
    active_tickers = len({e.get("ticker") for e in entries if e.get("ticker")})
    changed_weights = sum(1 for e in entries if abs((e.get("new_weight") or 0) - (e.get("old_weight") or 0)) > 0.001)
    pos_sentiment = sum(1 for e in entries if (e.get("rolling_sentiment_avg") or 0) > 0)
    neg_sentiment = sum(1 for e in entries if (e.get("rolling_sentiment_avg") or 0) < 0)

    with _pipeline_lock:
        status = _pipeline_status["status"]
        mode = _pipeline_status["mode"]

    return {
        "num_active_tickers": active_tickers,
        "changed_weights_latest": changed_weights,
        "pos_sentiment_events": pos_sentiment,
        "neg_sentiment_events": neg_sentiment,
        "latest_timestamp": latest.get("timestamp"),
        "pipeline_status": status,
        "mode": mode,
        "total_events_processed": len(entries),
    }


@app.get("/api/dashboard/index")
async def dashboard_index():
    """Return S&P100 mock index constituents with current weights and rank movements."""
    # Load latest weights if available
    latest_weights = {}
    if LATEST_WEIGHTS_PATH.exists():
        with LATEST_WEIGHTS_PATH.open("r", encoding="utf-8") as f:
            latest_weights = json.load(f)

    raw_list = []
    for item in TOP_20_SP100_TICKERS:
        ticker = item["ticker"]
        base_weight = MOCK_MARKET_CAPS.get(ticker, 0) / _total_cap
        current_weight = latest_weights.get(ticker, base_weight)
        raw_list.append({
            "ticker": ticker,
            "name": item["name"],
            "sector": item["sector"],
            "base_weight": round(base_weight, 6),
            "current_weight": round(current_weight, 6),
            "weight_change": round(current_weight - base_weight, 6),
        })

    # Compute initial ranks (sorted by base_weight descending)
    sorted_by_base = sorted(raw_list, key=lambda x: x["base_weight"], reverse=True)
    initial_ranks = {item["ticker"]: rank + 1 for rank, item in enumerate(sorted_by_base)}

    # Compute current ranks (sorted by current_weight descending)
    sorted_by_current = sorted(raw_list, key=lambda x: x["current_weight"], reverse=True)
    current_ranks = {item["ticker"]: rank + 1 for rank, item in enumerate(sorted_by_current)}

    # Attach rank information
    for item in raw_list:
        t = item["ticker"]
        init_r = initial_ranks[t]
        curr_r = current_ranks[t]
        item["initial_rank"] = init_r
        item["current_rank"] = curr_r
        # Positive rank_change means ticker moved UP in index
        item["rank_change"] = init_r - curr_r

    return JSONResponse(content=raw_list)


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
    """Return weight history over time for charting."""
    entries = _read_ledger()
    if not entries:
        return []

    if ticker:
        entries = [e for e in entries if e.get("ticker") == ticker]

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
    """Return weight evolution data grouped by ticker."""
    entries = _read_ledger()

    all_tickers = [item["ticker"] for item in TOP_20_SP100_TICKERS]
    base_weights = {item["ticker"]: MOCK_MARKET_CAPS.get(item["ticker"], 0) / _total_cap for item in TOP_20_SP100_TICKERS}

    step_0 = {t: base_weights[t] for t in all_tickers}
    steps = [step_0]

    if entries:
        current_step_weights = dict(step_0)
        last_timestamp = None

        for e in entries:
            ts = e.get("timestamp")
            ticker = e.get("ticker")
            new_w = e.get("new_weight")

            if ticker and new_w is not None:
                if last_timestamp is not None and ts != last_timestamp:
                    steps.append(dict(current_step_weights))
                
                current_step_weights[ticker] = new_w
                last_timestamp = ts
        
        steps.append(dict(current_step_weights))

    ticker_series = {t: [] for t in all_tickers}

    for step_idx, step_weights in enumerate(steps):
        for t in all_tickers:
            curr_w = step_weights.get(t, base_weights.get(t, 0))
            base_w = base_weights.get(t, 0)
            ticker_series[t].append({
                "step": step_idx,
                "weight": round(curr_w, 6),
                "base_weight": round(base_w, 6),
                "weight_change": round(curr_w - base_w, 6),
            })

    return {
        "tickers": all_tickers,
        "series": ticker_series,
        "total_steps": len(steps) - 1,
    }


# ── Pipeline control endpoints ──────────────────────────────────────────────

@app.post("/api/pipeline/run")
async def run_pipeline_endpoint(background_tasks: BackgroundTasks):
    """Run the full pipeline (demo mode) in background with status tracking."""
    with _pipeline_lock:
        if _pipeline_status["status"] == "running":
            return JSONResponse(
                status_code=409,
                content={"status": "error", "message": "Pipeline already running"}
            )
        _pipeline_status["status"] = "running"
        _pipeline_status["mode"] = "demo"
        _pipeline_status["stage"] = "nlp_risk_engine"
        _pipeline_status["progress"] = 10
        _pipeline_status["message"] = "Demo pipeline batch started"
        _pipeline_status["failed_stage"] = None
        _pipeline_status["error_message"] = None

    def _run():
        try:
            import sys, os
            src_dir = os.path.dirname(os.path.abspath(__file__))
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from pipeline import RiskEnginePipeline
            pipeline = RiskEnginePipeline(mode="demo")
            pipeline.run_pipeline(status_callback=_update_status_cb)
            with _pipeline_lock:
                _pipeline_status["status"] = "idle"
                _pipeline_status["stage"] = "complete"
                _pipeline_status["progress"] = 100
                _pipeline_status["message"] = "Pipeline completed successfully"
                _pipeline_status["last_run"] = datetime.now(timezone.utc).isoformat()
        except Exception as ex:
            with _pipeline_lock:
                current_stage = _pipeline_status.get("stage", "unknown")
                _pipeline_status["status"] = "error"
                _pipeline_status["failed_stage"] = current_stage
                _pipeline_status["error_message"] = str(ex)
                _pipeline_status["message"] = f"Pipeline error during {current_stage}: {str(ex)}"

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
        _pipeline_status["mode"] = "demo"
        _pipeline_status["stage"] = "nlp_risk_engine"
        _pipeline_status["progress"] = 20
        _pipeline_status["message"] = "Processing next timestep..."
        _pipeline_status["failed_stage"] = None
        _pipeline_status["error_message"] = None

    def _run():
        try:
            import sys, os
            src_dir = os.path.dirname(os.path.abspath(__file__))
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from pipeline import RiskEnginePipeline
            pipeline = RiskEnginePipeline(mode="demo")
            pipeline.run_pipeline(max_payloads=1, clear_previous_stream=False, status_callback=_update_status_cb)
            with _pipeline_lock:
                _pipeline_status["status"] = "idle"
                _pipeline_status["stage"] = "complete"
                _pipeline_status["progress"] = 100
                _pipeline_status["message"] = "Timestep processed"
                _pipeline_status["last_run"] = datetime.now(timezone.utc).isoformat()
        except Exception as ex:
            with _pipeline_lock:
                current_stage = _pipeline_status.get("stage", "unknown")
                _pipeline_status["status"] = "error"
                _pipeline_status["failed_stage"] = current_stage
                _pipeline_status["error_message"] = str(ex)
                _pipeline_status["message"] = f"Timestep error during {current_stage}: {str(ex)}"

    background_tasks.add_task(_run)
    return {"status": "next timestep started"}


@app.post("/api/pipeline/live/run")
async def run_live_pipeline_endpoint(background_tasks: BackgroundTasks):
    """
    Triggers Live Mode execution:
    Fetches real-time market articles (NewsAPI, GDELT, BigData) for the 20 tickers,
    deduplicates them, saves raw payloads to data/live_mode_fetched, and rebalances portfolio.
    """
    with _pipeline_lock:
        if _pipeline_status["status"] == "running":
            return JSONResponse(
                status_code=409,
                content={"status": "error", "message": "Pipeline execution already in progress"}
            )
        _pipeline_status["status"] = "running"
        _pipeline_status["mode"] = "live"
        _pipeline_status["stage"] = "fetching_live_data"
        _pipeline_status["progress"] = 10
        _pipeline_status["message"] = "Live mode started: fetching real-time market feeds..."
        _pipeline_status["failed_stage"] = None
        _pipeline_status["error_message"] = None

    def _run():
        try:
            import sys, os
            src_dir = os.path.dirname(os.path.abspath(__file__))
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from pipeline import RiskEnginePipeline
            pipeline = RiskEnginePipeline(mode="live")
            pipeline.run_pipeline(status_callback=_update_status_cb)
            with _pipeline_lock:
                _pipeline_status["status"] = "idle"
                _pipeline_status["stage"] = "complete"
                _pipeline_status["progress"] = 100
                _pipeline_status["message"] = "Live Mode pipeline completed successfully"
                _pipeline_status["last_run"] = datetime.now(timezone.utc).isoformat()
        except Exception as ex:
            with _pipeline_lock:
                current_stage = _pipeline_status.get("stage", "unknown")
                _pipeline_status["status"] = "error"
                _pipeline_status["failed_stage"] = current_stage
                _pipeline_status["error_message"] = str(ex)
                _pipeline_status["message"] = f"Live Mode failed at stage '{current_stage}': {str(ex)}"

    background_tasks.add_task(_run)
    return {"status": "live pipeline started"}


@app.post("/api/pipeline/reset")
async def reset_demo_endpoint():
    """Reset the demo by deleting ledger and clearing output directories."""
    rebal_dir = OUTPUT_DIR / "rebalancing_outputs"
    if rebal_dir.exists():
        for f in rebal_dir.iterdir():
            f.unlink()

    risk_dir = OUTPUT_DIR / "risk_engine_outputs"
    if risk_dir.exists():
        for f in risk_dir.iterdir():
            if f.is_file():
                f.unlink()

    with _pipeline_lock:
        _pipeline_status["status"] = "idle"
        _pipeline_status["mode"] = "demo"
        _pipeline_status["stage"] = "idle"
        _pipeline_status["progress"] = 0
        _pipeline_status["message"] = "Demo reset completed"
        _pipeline_status["failed_stage"] = None
        _pipeline_status["error_message"] = None
        _pipeline_status["last_run"] = None

    return {"status": "reset completed"}


@app.get("/api/ping")
async def ping():
    return {"ping": "pong"}


# ── Module B: Stress Test endpoints ────────────────────────────────────────

@app.get("/api/stress-test/latest")
async def stress_test_latest():
    """
    Return the most recently computed stress test result from disk.
    Returns 404 if no result has been generated yet.
    """
    try:
        import sys as _sys
        _src = str(Path(__file__).parent)
        if _src not in _sys.path:
            _sys.path.insert(0, _src)
        from module_b_stress_test import get_latest_stress_result
        result = get_latest_stress_result()
        if result is None:
            return JSONResponse(status_code=404, content={"error": "No stress test result yet. Run the pipeline first, then trigger a stress test."})
        return result
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/stress-test/run")
async def stress_test_run(
    background_tasks: BackgroundTasks,
    force: bool = True,
    scenario: str = None,
):
    """
    Trigger a stress test simulation.
    - force=true  : always apply shocks (manual dashboard trigger).
    - scenario    : override which shock scenario to apply.
    Runs synchronously (fast — no ML inference needed).
    """
    try:
        import sys as _sys
        _src = str(Path(__file__).parent)
        if _src not in _sys.path:
            _sys.path.insert(0, _src)
        from module_b_stress_test import run_stress_test, SHOCK_SCENARIOS
        # Validate scenario name
        if scenario and scenario not in SHOCK_SCENARIOS:
            return JSONResponse(
                status_code=422,
                content={"error": f"Unknown scenario '{scenario}'. Valid: {list(SHOCK_SCENARIOS.keys())}"}
            )
        result = run_stress_test(force_trigger=force, forced_scenario=scenario)
        from dataclasses import asdict
        return asdict(result)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/stress-test/scenarios")
async def stress_test_scenarios():
    """Return the catalog of available stress scenarios for the frontend dropdown."""
    try:
        import sys as _sys
        _src = str(Path(__file__).parent)
        if _src not in _sys.path:
            _sys.path.insert(0, _src)
        from module_b_stress_test import list_scenarios
        return list_scenarios()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

#---------------------last changes
# ── Static Frontend Serving (Standalone / Single-Container mode) ───────────
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse(status_code=404, content={"detail": "API endpoint not found"})
        target = FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(target)
        index_file = FRONTEND_DIST / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(status_code=404, content={"detail": "Frontend not found"})

