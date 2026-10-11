"""
Module B — Strategic Portfolio Stress Testing Engine
=====================================================
Standalone module that:
  1. Maintains a synthetic wholesale banking asset portfolio (Corporate Loans,
     Bonds, Derivatives, Sovereign Debt) with yfinance-grounded valuations.
  2. Subscribes to NLP Risk Engine outputs (reads latest_risk_signals.json /
     risk_summary_report.json written by the existing pipeline).
  3. Triggers a stress simulation when a high-impact event is detected
     (Impact Score > 7 for Geopolitical / Macroeconomic categories).
  4. Applies pre-defined asset-class shocks and returns a structured result
     dict ready to be served by the FastAPI layer.

IMPORTANT: This module does NOT import or modify any existing pipeline code.
           It only reads the JSON output files produced by the NLP Risk Engine.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional yfinance import — graceful fallback to baked-in baseline prices
# ---------------------------------------------------------------------------
try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False


# ============================================================
# CONSTANTS — output paths (mirrors the pipeline layout)
# ============================================================

_SRC_DIR = Path(__file__).parent
RISK_SIGNALS_PATH = _SRC_DIR / "output" / "risk_engine_outputs" / "latest_risk_signals.json"
RISK_SUMMARY_PATH = _SRC_DIR / "output" / "risk_engine_outputs" / "risk_summary_report.json"
STRESS_TEST_OUTPUT_PATH = _SRC_DIR / "output" / "stress_test_outputs" / "latest_stress_result.json"

IMPACT_SCORE_THRESHOLD = 7.0

STRESS_TRIGGER_EVENT_TYPES = {
    "Macro",
    "Fed | Central Banks",
    "Politics",
    "Energy | Oil",
    "Currencies",
    "Treasuries | Corporate Debt",
    "Legal | Regulation",
}

EVENT_TO_SCENARIO: Dict[str, str] = {
    "Macro": "Macroeconomic Shock",
    "Fed | Central Banks": "Central Bank Policy Shock",
    "Politics": "Geopolitical Shock",
    "Energy | Oil": "Energy Crisis Shock",
    "Currencies": "Currency Crisis Shock",
    "Treasuries | Corporate Debt": "Credit Market Shock",
    "Legal | Regulation": "Regulatory Shock",
}

# ============================================================
# SYNTHETIC WHOLESALE BANKING PORTFOLIO DEFINITION
# ============================================================

MARKET_ANCHORS: Dict[str, str] = {
    "SPY": "S&P 500 ETF",
    "TLT": "20-Year Treasury",
    "HYG": "High-Yield Corp Bond",
    "GLD": "Gold",
    "USO": "Crude Oil",
}

BASELINE_PORTFOLIO: List[Dict[str, Any]] = [
    # ── Corporate Term Loans ────────────────────────────────────
    {
        "id": "CTL-001",
        "asset_class": "Corporate Term Loan",
        "counterparty": "TechCorp Industries",
        "sector": "Technology",
        "rating": "BBB",
        "tenor_years": 5,
        "dollar_value_mm": 250.0,
        "anchor_ticker": "HYG",
        "sensitivity_tag": "credit",
    },
    {
        "id": "CTL-002",
        "asset_class": "Corporate Term Loan",
        "counterparty": "EnergyGrid Corp",
        "sector": "Energy",
        "rating": "BB+",
        "tenor_years": 7,
        "dollar_value_mm": 180.0,
        "anchor_ticker": "USO",
        "sensitivity_tag": "energy_credit",
    },
    {
        "id": "CTL-003",
        "asset_class": "Corporate Term Loan",
        "counterparty": "RetailChain Holding",
        "sector": "Consumer Discretionary",
        "rating": "B+",
        "tenor_years": 3,
        "dollar_value_mm": 120.0,
        "anchor_ticker": "SPY",
        "sensitivity_tag": "credit",
    },
    # ── Corporate Bonds ─────────────────────────────────────────
    {
        "id": "CBND-001",
        "asset_class": "Corporate Bond",
        "counterparty": "AutoMotive Global",
        "sector": "Industrials",
        "rating": "A-",
        "tenor_years": 10,
        "dollar_value_mm": 320.0,
        "anchor_ticker": "HYG",
        "sensitivity_tag": "rates_credit",
    },
    {
        "id": "CBND-002",
        "asset_class": "Corporate Bond",
        "counterparty": "PharmaGroup Ltd",
        "sector": "Healthcare",
        "rating": "AA",
        "tenor_years": 15,
        "dollar_value_mm": 200.0,
        "anchor_ticker": "TLT",
        "sensitivity_tag": "rates",
    },
    # ── Interest Rate Derivatives ────────────────────────────────
    {
        "id": "IRDR-001",
        "asset_class": "Interest Rate Swap",
        "counterparty": "National Pension Fund",
        "sector": "Financial Services",
        "rating": "AAA",
        "tenor_years": 10,
        "dollar_value_mm": 500.0,
        "anchor_ticker": "TLT",
        "sensitivity_tag": "rates",
    },
    {
        "id": "IRDR-002",
        "asset_class": "Credit Default Swap",
        "counterparty": "Hedge Fund Alpha",
        "sector": "Financial Services",
        "rating": "BBB",
        "tenor_years": 5,
        "dollar_value_mm": 150.0,
        "anchor_ticker": "HYG",
        "sensitivity_tag": "credit",
    },
    # ── Sovereign Debt ───────────────────────────────────────────
    {
        "id": "SOVD-001",
        "asset_class": "Sovereign Bond",
        "counterparty": "US Treasury",
        "sector": "Government",
        "rating": "AAA",
        "tenor_years": 10,
        "dollar_value_mm": 400.0,
        "anchor_ticker": "TLT",
        "sensitivity_tag": "rates_sovereign",
    },
    {
        "id": "SOVD-002",
        "asset_class": "Sovereign Bond",
        "counterparty": "Eurozone Sovereign",
        "sector": "Government",
        "rating": "AA",
        "tenor_years": 7,
        "dollar_value_mm": 280.0,
        "anchor_ticker": "TLT",
        "sensitivity_tag": "rates_sovereign",
    },
    {
        "id": "SOVD-003",
        "asset_class": "Sovereign Bond",
        "counterparty": "Emerging Market Government",
        "sector": "Government",
        "rating": "BB",
        "tenor_years": 5,
        "dollar_value_mm": 160.0,
        "anchor_ticker": "TLT",
        "sensitivity_tag": "em_sovereign",
    },
]

# ============================================================
# SHOCK SCENARIOS (% shocks per sensitivity_tag)
# Negative = loss, positive = flight-to-quality gain
# ============================================================

SHOCK_SCENARIOS: Dict[str, Dict[str, float]] = {
    "Macroeconomic Shock": {
        "credit":          -0.085,
        "energy_credit":   -0.12,
        "rates":           +0.035,
        "rates_credit":    -0.065,
        "rates_sovereign": +0.025,
        "em_sovereign":    -0.14,
    },
    "Central Bank Policy Shock": {
        "credit":          -0.07,
        "energy_credit":   -0.09,
        "rates":           -0.06,
        "rates_credit":    -0.095,
        "rates_sovereign": -0.055,
        "em_sovereign":    -0.18,
    },
    "Geopolitical Shock": {
        "credit":          -0.10,
        "energy_credit":   -0.15,
        "rates":           +0.04,
        "rates_credit":    -0.09,
        "rates_sovereign": +0.03,
        "em_sovereign":    -0.20,
    },
    "Energy Crisis Shock": {
        "credit":          -0.06,
        "energy_credit":   -0.22,
        "rates":           +0.02,
        "rates_credit":    -0.075,
        "rates_sovereign": +0.01,
        "em_sovereign":    -0.12,
    },
    "Currency Crisis Shock": {
        "credit":          -0.055,
        "energy_credit":   -0.08,
        "rates":           +0.025,
        "rates_credit":    -0.07,
        "rates_sovereign": +0.015,
        "em_sovereign":    -0.25,
    },
    "Credit Market Shock": {
        "credit":          -0.15,
        "energy_credit":   -0.175,
        "rates":           +0.03,
        "rates_credit":    -0.12,
        "rates_sovereign": +0.02,
        "em_sovereign":    -0.16,
    },
    "Regulatory Shock": {
        "credit":          -0.04,
        "energy_credit":   -0.06,
        "rates":           +0.01,
        "rates_credit":    -0.05,
        "rates_sovereign": +0.005,
        "em_sovereign":    -0.08,
    },
}

DEFAULT_SCENARIO = "Macroeconomic Shock"


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class StressTestResult:
    triggered: bool
    scenario_name: str
    trigger_event: str
    trigger_ticker: str
    trigger_impact_score: float
    trigger_event_type: str
    trigger_sentiment: str
    total_portfolio_value_before_mm: float
    total_portfolio_value_after_mm: float
    total_loss_mm: float
    total_loss_pct: float
    positions: List[Dict[str, Any]]
    market_anchors_snapshot: Dict[str, Any]
    generated_at: str
    notes: str = ""


# ============================================================
# MARKET DATA FETCHER
# ============================================================

def _fetch_anchor_prices(tickers: List[str]) -> Dict[str, Optional[float]]:
    prices: Dict[str, Optional[float]] = {t: None for t in tickers}
    if not _YF_AVAILABLE:
        return prices
    try:
        data = yf.download(
            tickers=tickers,
            period="2d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        # Handle both single and multi-ticker DataFrames
        try:
            close = data["Close"]
        except Exception:
            close = data
        for t in tickers:
            try:
                if hasattr(close, "columns") and t in close.columns:
                    val = float(close[t].dropna().iloc[-1])
                elif hasattr(close, "iloc"):
                    val = float(close.dropna().iloc[-1])
                else:
                    val = None
                prices[t] = round(val, 2) if val is not None else None
            except Exception:
                prices[t] = None
    except Exception:
        pass
    return prices


# ============================================================
# RISK ENGINE OUTPUT READER
# ============================================================

def _read_latest_signals() -> List[Dict[str, Any]]:
    if RISK_SIGNALS_PATH.exists():
        try:
            with RISK_SIGNALS_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("signals", [])
        except Exception:
            pass
    return []


# ============================================================
# TRIGGER DETECTION
# ============================================================

def _detect_trigger(signals: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return highest-impact qualifying signal, or None."""
    qualifying = [
        s for s in signals
        if (
            s.get("impact_score", 0) > IMPACT_SCORE_THRESHOLD
            and s.get("event_classification", "") in STRESS_TRIGGER_EVENT_TYPES
        )
    ]
    if not qualifying:
        return None
    return max(qualifying, key=lambda s: s["impact_score"])


# ============================================================
# CORE STRESS SIMULATION
# ============================================================

def run_stress_test(
    force_trigger: bool = False,
    forced_scenario: Optional[str] = None,
    forced_ticker: Optional[str] = None,
) -> StressTestResult:
    """
    Run a stress test simulation.

    Parameters
    ----------
    force_trigger:   Always apply shocks (for UI manual trigger).
    forced_scenario: Override which shock scenario to apply.
    forced_ticker:   Override the displayed trigger ticker label.
    """
    signals = _read_latest_signals()

    trigger_signal: Optional[Dict[str, Any]] = None
    scenario_name = forced_scenario or DEFAULT_SCENARIO
    triggered = False
    notes = ""

    if not force_trigger:
        trigger_signal = _detect_trigger(signals)
        if trigger_signal:
            triggered = True
            event_type = trigger_signal.get("event_classification", "Macro")
            scenario_name = EVENT_TO_SCENARIO.get(event_type, DEFAULT_SCENARIO)
            if forced_scenario:
                scenario_name = forced_scenario
        else:
            notes = (
                f"No trigger detected (threshold: impact_score > {IMPACT_SCORE_THRESHOLD}). "
                "Showing baseline portfolio values. Run pipeline first, or use Force Trigger."
            )
    else:
        triggered = True
        if signals:
            trigger_signal = max(signals, key=lambda s: s.get("impact_score", 0))
            event_type = trigger_signal.get("event_classification", "Macro")
            if not forced_scenario:
                scenario_name = EVENT_TO_SCENARIO.get(event_type, DEFAULT_SCENARIO)
        else:
            trigger_signal = {
                "ticker": forced_ticker or "MACRO",
                "company_name": forced_ticker or "Macro Event",
                "impact_score": 8.5,
                "event_classification": "Macro",
                "sentiment_label": "Negative",
            }
        notes = "Stress test manually triggered from dashboard."

    # Trigger metadata
    if trigger_signal:
        trigger_ticker    = forced_ticker or trigger_signal.get("ticker", "N/A")
        trigger_impact    = round(float(trigger_signal.get("impact_score", 0)), 2)
        trigger_evt_type  = trigger_signal.get("event_classification", "N/A")
        trigger_sentiment = trigger_signal.get("sentiment_label", "Negative")
    else:
        trigger_ticker    = "N/A"
        trigger_impact    = 0.0
        trigger_evt_type  = "N/A"
        trigger_sentiment = "N/A"

    # Fetch anchor prices
    anchor_prices = _fetch_anchor_prices(list(MARKET_ANCHORS.keys()))

    # Get shock table
    shocks = SHOCK_SCENARIOS.get(scenario_name, SHOCK_SCENARIOS[DEFAULT_SCENARIO])

    # Apply shocks
    positions_out: List[Dict[str, Any]] = []
    total_before = 0.0
    total_after  = 0.0

    for raw in BASELINE_PORTFOLIO:
        book_val     = raw["dollar_value_mm"]
        sens_tag     = raw["sensitivity_tag"]
        shock_pct    = shocks.get(sens_tag, -0.05)
        applied_shock = shock_pct if triggered else 0.0

        stressed_val = round(book_val * (1.0 + applied_shock), 4)
        loss_mm      = round(book_val - stressed_val, 4)

        positions_out.append({
            "id":                  raw["id"],
            "asset_class":         raw["asset_class"],
            "counterparty":        raw["counterparty"],
            "sector":              raw["sector"],
            "rating":              raw["rating"],
            "tenor_years":         raw["tenor_years"],
            "dollar_value_mm":     book_val,
            "anchor_ticker":       raw["anchor_ticker"],
            "sensitivity_tag":     sens_tag,
            "market_price_anchor": anchor_prices.get(raw["anchor_ticker"]),
            "shock_pct":           round(applied_shock * 100, 2),
            "stressed_value_mm":   stressed_val,
            "loss_mm":             loss_mm,
            "loss_pct":            round(applied_shock * 100, 2),
        })

        total_before += book_val
        total_after  += stressed_val

    total_loss_mm  = round(total_before - total_after, 4)
    total_loss_pct = round((total_loss_mm / total_before) * 100, 2) if total_before > 0 else 0.0

    result = StressTestResult(
        triggered                       = triggered,
        scenario_name                   = scenario_name if triggered else "No Trigger — Baseline",
        trigger_event                   = trigger_evt_type,
        trigger_ticker                  = trigger_ticker,
        trigger_impact_score            = trigger_impact,
        trigger_event_type              = trigger_evt_type,
        trigger_sentiment               = trigger_sentiment,
        total_portfolio_value_before_mm = round(total_before, 4),
        total_portfolio_value_after_mm  = round(total_after, 4),
        total_loss_mm                   = total_loss_mm,
        total_loss_pct                  = total_loss_pct if triggered else 0.0,
        positions                       = positions_out,
        market_anchors_snapshot         = {k: anchor_prices.get(k) for k in MARKET_ANCHORS},
        generated_at                    = datetime.now(timezone.utc).isoformat(),
        notes                           = notes,
    )

    # Persist to disk
    STRESS_TEST_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STRESS_TEST_OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2)

    return result


def get_latest_stress_result() -> Optional[Dict[str, Any]]:
    """Return last persisted stress result, or None."""
    if STRESS_TEST_OUTPUT_PATH.exists():
        try:
            with STRESS_TEST_OUTPUT_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def list_scenarios() -> List[Dict[str, str]]:
    """Return scenario catalog for frontend dropdown."""
    descriptions = {
        "Macroeconomic Shock":       "Broad macro contraction — widening spreads, EM flight, duration rally.",
        "Central Bank Policy Shock": "Aggressive rate hike / pivot — duration losses, EM outflows.",
        "Geopolitical Shock":        "Armed conflict / sanctions — energy spike, safe-haven surge.",
        "Energy Crisis Shock":       "Oil supply disruption — energy credit collapse, inflation spike.",
        "Currency Crisis Shock":     "Dollar surge / EM devaluation — severe EM sovereign losses.",
        "Credit Market Shock":       "Spread blow-out — systematic corporate / EM repricing.",
        "Regulatory Shock":          "Major regulatory action — moderate repricing across credit.",
    }
    return [{"name": n, "description": d} for n, d in descriptions.items()]


# ============================================================
# CLI ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Module B — Stress Test Engine")
    parser.add_argument("--force", action="store_true",
                        help="Force-trigger simulation even without detected signal.")
    parser.add_argument("--scenario", type=str, default=None,
                        choices=list(SHOCK_SCENARIOS.keys()),
                        help="Override stress scenario (implies --force).")
    args = parser.parse_args()

    result = run_stress_test(
        force_trigger=args.force or bool(args.scenario),
        forced_scenario=args.scenario,
    )
    print(f"\n{'='*62}")
    print(f"  MODULE B — STRESS TEST RESULT")
    print(f"{'='*62}")
    print(f"  Triggered:           {result.triggered}")
    print(f"  Scenario:            {result.scenario_name}")
    print(f"  Trigger:             {result.trigger_event_type} @ {result.trigger_ticker}")
    print(f"  Impact Score:        {result.trigger_impact_score}")
    print(f"  Portfolio Before:    ${result.total_portfolio_value_before_mm:.1f}M")
    print(f"  Portfolio After:     ${result.total_portfolio_value_after_mm:.1f}M")
    print(f"  Total Loss:          ${result.total_loss_mm:.1f}M  ({result.total_loss_pct:.2f}%)")
    print(f"{'='*62}")
    for pos in result.positions:
        print(
            f"  [{pos['id']}] {pos['asset_class']:24s} | "
            f"${pos['dollar_value_mm']:.0f}M -> ${pos['stressed_value_mm']:.0f}M "
            f"| shock {pos['shock_pct']:+.1f}%"
        )
    print(f"\n  Output: {STRESS_TEST_OUTPUT_PATH}\n")
