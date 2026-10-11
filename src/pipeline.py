import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Generator

# Add local src directory to path if needed
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from risk_engine import FinBERTRiskEngine, RiskSignal
from gen_mock_source import RawDataIngestor, TOP_20_SP100_TICKERS, deduplicate_articles
from rebalancing_engine import BlackLittermanEngine

# Output directories and file locations
OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "risk_engine_outputs")
STRUCTURED_SIGNALS_FILE = os.path.join(OUTPUT_DIR, "latest_risk_signals.json")
STREAM_LOG_FILE = os.path.join(OUTPUT_DIR, "signals_history_ledger.jsonl")
SUMMARY_REPORT_FILE = os.path.join(OUTPUT_DIR, "risk_summary_report.json")
STATE_FILE = os.path.join(OUTPUT_DIR, "pipeline_state.json")

LIVE_STORE_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "data", "live_mode_fetched")
LIVE_FETCHED_FILE = os.path.join(LIVE_STORE_DIR, "live_mode_fetched.json")


def load_pipeline_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"current_payload_index": 0}


def save_pipeline_state(state: Dict[str, Any]):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


class MockStoreReader:
    """
    Reads time-series payloads from a store directory (mock_store_2 or live_mode_fetched),
    resolving raw payload paths robustly across operating systems.
    """

    def __init__(self, mock_dir: Optional[str] = None):
        if mock_dir is None or not os.path.exists(mock_dir):
            mock_dir = os.path.join(os.path.dirname(CURRENT_DIR), "data", "mock_store_2")
        self.mock_dir = os.path.abspath(mock_dir)
        self.index_file = os.path.join(self.mock_dir, "index.json")

        if not os.path.exists(self.index_file):
            raise FileNotFoundError(f"Store index not found at: {self.index_file}")

        with open(self.index_file, "r", encoding="utf-8") as f:
            self.catalog: List[Dict[str, Any]] = json.load(f)

    def stream_events(
        self, start_index: int = 0, count: Optional[int] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """Yields raw catalog metadata and content dictionaries."""
        catalog_slice = self.catalog[start_index:]
        if count is not None:
            catalog_slice = catalog_slice[:count]

        for entry in catalog_slice:
            rel_or_abs_path = entry["filepath"]
            # Handle Windows vs Unix relative path delimiters
            filename = entry.get("file_id") or os.path.basename(rel_or_abs_path)
            candidate_path = os.path.join(self.mock_dir, "raw_payloads", filename)

            if not os.path.exists(candidate_path):
                # Fallback to direct filepath
                candidate_path = os.path.abspath(rel_or_abs_path)

            if os.path.exists(candidate_path):
                with open(candidate_path, "r", encoding="utf-8") as f:
                    try:
                        raw_payload = json.load(f)
                    except json.JSONDecodeError as e:
                        print(f"[!] Warning: Failed decoding {candidate_path}: {e}")
                        continue

                yield {
                    "meta": entry,
                    "payload": raw_payload,
                    "filepath": candidate_path,
                }
            else:
                print(f"[!] Warning: Missing payload file: {candidate_path}")


class RiskEnginePipeline:
    """
    Main Risk Engine execution pipeline supporting:
    - DEMO mode: Replay from data/mock_store_2 time-series stream.
    - LIVE mode: Real-time ingestion from live news & financial APIs into data/live_mode_fetched.
    """

    def __init__(
        self,
        mode: str = "demo",
        device: Optional[str] = None,
        batch_size: int = 16,
    ):
        self.mode = mode.lower()
        self.batch_size = batch_size
        if self.mode in ["live", "work"]:
            self.store_dir = LIVE_STORE_DIR
        else:
            self.store_dir = os.path.join(os.path.dirname(CURRENT_DIR), "data", "mock_store_2")
            
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        if os.path.exists(os.path.join(self.store_dir, "index.json")):
            self._reader = MockStoreReader(self.store_dir)
        else:
            self._reader = None

        print(f"[+] Initializing RiskEnginePipeline (Mode: {self.mode.upper()})")
        print(f"[+] Store Directory: {self.store_dir}")
        print(f"[+] Output Directory: {OUTPUT_DIR}")

        self.engine = FinBERTRiskEngine(device=device)

    def extract_articles_from_payload(
        self, source: str, ticker: str, payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extracts individual normalized articles from raw API JSON payloads."""
        articles = []

        if source == "newsapi":
            raw_arts = payload.get("articles", [])
            for art in raw_arts:
                title = art.get("title") or ""
                description = art.get("description") or ""
                content = art.get("content") or ""
                text = f"{title}. {description}".strip(". ")
                if not text:
                    text = f"{title}. {content}".strip(". ")

                if text:
                    articles.append({
                        "text": text,
                        "published_at": art.get("publishedAt", datetime.now(timezone.utc).isoformat()),
                        "url": art.get("url", ""),
                        "source": "newsapi",
                        "title": title,
                        "ticker": ticker,
                    })

        elif source == "gdelt":
            raw_arts = payload.get("articles", [])
            for art in raw_arts:
                title = art.get("title") or ""
                if title:
                    articles.append({
                        "text": title,
                        "published_at": art.get("seendate", datetime.now(timezone.utc).isoformat()),
                        "url": art.get("url", ""),
                        "source": "gdelt",
                        "title": title,
                        "ticker": ticker,
                    })

        elif source == "bigdata":
            raw_results = payload.get("results", [])
            for res in raw_results:
                headline = res.get("headline") or ""
                body = res.get("body") or ""
                text = f"{headline}. {body}".strip(". ")
                if text:
                    articles.append({
                        "text": text,
                        "published_at": res.get("published_at", datetime.now(timezone.utc).isoformat()),
                        "url": f"https://bigdata.com/{res.get('id')}",
                        "source": "bigdata",
                        "title": headline,
                        "ticker": ticker,
                    })

        else:
            # Generic fallback
            items = payload.get("articles", payload if isinstance(payload, list) else [])
            for itm in items:
                text = itm.get("text") or itm.get("title") or str(itm)
                articles.append({
                    "text": text,
                    "published_at": itm.get("published_at", datetime.now(timezone.utc).isoformat()),
                    "url": itm.get("url", ""),
                    "source": source,
                    "title": itm.get("title", ""),
                    "ticker": ticker,
                })

        return articles

    def run_pipeline(
        self,
        max_events: Optional[int] = None,
        max_payloads: Optional[int] = None,
        clear_previous_stream: bool = True,
        status_callback=None,
    ) -> List[Dict[str, Any]]:
        """
        Executes the full risk signal generation pipeline and exports structured results.
        """
        def update_status(stage: str, progress: int, msg: str):
            if status_callback:
                status_callback(stage, progress, msg)

        print(f"\n==================================================================")
        print(f"  RUNNING NLP RISK ENGINE [{self.mode.upper()}] PIPELINE")
        print(f"==================================================================\n")

        rebal_dir = os.path.join(CURRENT_DIR, "output", "rebalancing_outputs")
        rebal_ledger = os.path.join(rebal_dir, "rebalance_ledger.jsonl")
        latest_weights = os.path.join(rebal_dir, "latest_weights.json")

        if clear_previous_stream:
            if os.path.exists(STREAM_LOG_FILE):
                open(STREAM_LOG_FILE, "w").close()
            if os.path.exists(rebal_ledger):
                open(rebal_ledger, "w").close()
            if os.path.exists(latest_weights):
                try:
                    os.remove(latest_weights)
                except Exception:
                    pass
            state = {"current_payload_index": 0}
            save_pipeline_state(state)
        else:
            state = load_pipeline_state()

        processed_signals: List[Dict[str, Any]] = []
        start_time = time.time()

        if self.mode == "demo":
            update_status("nlp_risk_engine", 20, "Ingesting mock data payloads...")
            if not self._reader:
                self._reader = MockStoreReader(self.store_dir)
            start_payload_index = 0 if clear_previous_stream else state.get("current_payload_index", 0)
            total_catalog_payloads = len(self._reader.catalog)

            if start_payload_index >= total_catalog_payloads:
                print(f"[!] All {total_catalog_payloads} mock payloads have already been processed.")
                all_signals = []
                if os.path.exists(STREAM_LOG_FILE):
                    with open(STREAM_LOG_FILE, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                try:
                                    all_signals.append(json.loads(line))
                                except Exception:
                                    pass
                return all_signals

            incoming_queue: List[Dict[str, Any]] = []
            payloads_processed_count = 0

            for item in self._reader.stream_events(start_index=start_payload_index, count=max_payloads):
                meta = item["meta"]
                payload = item["payload"]
                ticker = meta.get("ticker", "UNKNOWN")
                source = meta.get("source", "newsapi")
                comp_info = next((c for c in TOP_20_SP100_TICKERS if c["ticker"] == ticker), {"name": ticker})
                company_name = comp_info["name"]
                extracted = self.extract_articles_from_payload(source, ticker, payload)

                for art in extracted:
                    incoming_queue.append({
                        "event_id": f"evt_{source}_{ticker}_{len(incoming_queue)+1:04d}",
                        "text": art["text"],
                        "ticker": ticker,
                        "company_name": company_name,
                        "source": source,
                        "published_at": art["published_at"],
                        "metadata": {
                            "article_url": art["url"],
                            "title": art.get("title", ""),
                            "raw_file": meta.get("file_id", ""),
                        },
                    })
                    if max_events is not None and len(incoming_queue) >= max_events:
                        break

                payloads_processed_count += 1
                if max_events is not None and len(incoming_queue) >= max_events:
                    break

            print(f"[+] Ingested {len(incoming_queue)} items from {payloads_processed_count} payload file(s). Running inference...")
            update_status("nlp_risk_engine", 50, f"Analyzing {len(incoming_queue)} events with FinBERT...")

            # Run batch inference
            for i in range(0, len(incoming_queue), self.batch_size):
                batch_items = incoming_queue[i : i + self.batch_size]
                signals = self.engine.analyze_batch(batch_items)

                for sig in signals:
                    sig_dict = sig.to_dict()
                    processed_signals.append(sig_dict)

                    with open(STREAM_LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(sig_dict) + "\n")

            state["current_payload_index"] = start_payload_index + payloads_processed_count
            save_pipeline_state(state)

        elif self.mode in ["live", "work"]:
            update_status("fetching_live_data", 10, "Fetching live market news from NewsAPI, GDELT, and BigData...")
            os.makedirs(LIVE_STORE_DIR, exist_ok=True)
            raw_ingestor = RawDataIngestor(store_dir=LIVE_STORE_DIR)

            total_tickers = len(TOP_20_SP100_TICKERS)
            for idx, comp in enumerate(TOP_20_SP100_TICKERS):
                prog = 10 + int((idx / total_tickers) * 25)
                update_status("fetching_live_data", prog, f"Fetching live feeds for {comp['ticker']} ({comp['name']})...")
                print(f"[*] Ingesting live data for {comp['ticker']} ({comp['name']})")
                raw_ingestor.fetch_newsapi(comp)
                raw_ingestor.fetch_gdelt(comp)
                raw_ingestor.fetch_bigdata_stub(comp)

            # Deduplication phase
            update_status("deduplicating_data", 40, "Deduplicating incoming articles across sources...")
            reader = MockStoreReader(LIVE_STORE_DIR)
            all_extracted = []

            for item in reader.stream_events():
                meta = item["meta"]
                payload = item["payload"]
                ticker = meta.get("ticker", "UNKNOWN")
                source = meta.get("source", "newsapi")
                extracted = self.extract_articles_from_payload(source, ticker, payload)
                all_extracted.extend(extracted)

            deduped_articles = deduplicate_articles(all_extracted)
            print(f"[+] Deduplication complete: {len(all_extracted)} raw articles -> {len(deduped_articles)} unique articles.")

            # Save deduplicated articles into live_mode_fetched.json
            with open(LIVE_FETCHED_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "total_raw_articles": len(all_extracted),
                    "total_deduped_articles": len(deduped_articles),
                    "articles": deduped_articles,
                }, f, indent=2)

            update_status("nlp_risk_engine", 55, f"Running FinBERT Risk Engine on {len(deduped_articles)} deduplicated live articles...")

            incoming_queue = []
            for idx, art in enumerate(deduped_articles):
                ticker = art["ticker"]
                source = art["source"]
                comp_info = next((c for c in TOP_20_SP100_TICKERS if c["ticker"] == ticker), {"name": ticker})
                incoming_queue.append({
                    "event_id": f"evt_live_{source}_{ticker}_{idx+1:04d}",
                    "text": art["text"],
                    "ticker": ticker,
                    "company_name": comp_info["name"],
                    "source": source,
                    "published_at": art["published_at"],
                    "metadata": {
                        "article_url": art.get("url", ""),
                        "title": art.get("title", ""),
                    },
                })

            for i in range(0, len(incoming_queue), self.batch_size):
                batch_items = incoming_queue[i : i + self.batch_size]
                signals = self.engine.analyze_batch(batch_items)

                for sig in signals:
                    sig_dict = sig.to_dict()
                    processed_signals.append(sig_dict)

                    with open(STREAM_LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(sig_dict) + "\n")

        # Read ALL cumulative signals from STREAM_LOG_FILE
        all_signals: List[Dict[str, Any]] = []
        if os.path.exists(STREAM_LOG_FILE):
            with open(STREAM_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            all_signals.append(json.loads(line))
                        except Exception:
                            pass
        else:
            all_signals = processed_signals

        elapsed = round(time.time() - start_time, 2)

        # ----------------------------------------------------
        # Generate Aggregated Summary Report & JSON Output
        # ----------------------------------------------------
        update_status("rebalancing_portfolio", 80, "Calculating tactical Black-Litterman index rebalancing...")
        summary_report = self._build_summary_report(all_signals, elapsed)

        output_payload = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "mode": self.mode,
                "total_signals_generated": len(all_signals),
                "new_signals_this_run": len(processed_signals),
                "current_payload_index": state.get("current_payload_index", 0),
                "processing_time_seconds": elapsed,
                "throughput_events_per_sec": round(len(processed_signals) / max(0.001, elapsed), 2),
            },
            "ticker_summaries": summary_report["ticker_summaries"],
            "signals": all_signals,
        }

        # Write latest risk signals JSON
        with open(STRUCTURED_SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2)

        # Write tactical summary report for Module 2 and Module 3
        with open(SUMMARY_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(summary_report, f, indent=2)

        print(f"\n==================================================================")
        print(f"  PROCESSING COMPLETE: {len(processed_signals)} new signals ({len(all_signals)} total) in {elapsed}s")
        print(f"==================================================================\n")

        # ----------------------------------------------------
        # Run Rebalancing Engine (Module 2)
        # ----------------------------------------------------
        bl_engine = BlackLittermanEngine()
        rebalance_events = bl_engine.rebalance(summary_report["ticker_summaries"])

        rebalancing_out_dir = os.path.join(CURRENT_DIR, "output", "rebalancing_outputs")
        bl_engine.save_ledger(rebalance_events, rebalancing_out_dir)

        update_status("complete", 100, f"Pipeline execution completed successfully ({len(processed_signals)} signals processed).")
        return all_signals

    def _build_summary_report(
        self, signals: List[Dict[str, Any]], elapsed_time: float
    ) -> Dict[str, Any]:
        """Builds aggregated quantitative summary metrics per ticker and across the index."""
        from collections import defaultdict, Counter

        ticker_data = defaultdict(list)
        event_distribution = Counter()
        sentiment_distribution = Counter()

        for s in signals:
            ticker_data[s["ticker"]].append(s)
            event_distribution[s["event_classification"]] += 1
            sentiment_distribution[s["sentiment_label"]] += 1

        ticker_summaries = {}
        for ticker, sigs in ticker_data.items():
            latest = sigs[-1]
            scores = [x["sentiment_score"] for x in sigs]
            impacts = [x["impact_score"] for x in sigs]
            top_events = Counter(x["event_classification"] for x in sigs).most_common(2)

            ticker_summaries[ticker] = {
                "company_name": latest["company_name"],
                "total_events_observed": len(sigs),
                "latest_sentiment_score": latest["sentiment_score"],
                "latest_sentiment_label": latest["sentiment_label"],
                "ewma_sentiment": latest["ewma_sentiment"],
                "rolling_sentiment_avg": latest["rolling_sentiment_avg"],
                "sentiment_momentum": latest["sentiment_momentum"],
                "sentiment_volatility": latest["sentiment_volatility"],
                "average_impact_score": round(sum(impacts) / len(impacts), 2),
                "max_impact_score": max(impacts),
                "dominant_event_types": [e[0] for e in top_events],
                "latest_event_id": latest["event_id"],
                "latest_timestamp": latest["published_at"],
            }

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "total_signals": len(signals),
            "total_tickers": len(ticker_summaries),
            "processing_time_seconds": elapsed_time,
            "sentiment_distribution": dict(sentiment_distribution),
            "event_distribution": dict(event_distribution.most_common()),
            "ticker_summaries": ticker_summaries,
        }


def parse_args():
    parser = argparse.ArgumentParser(description="NLP Risk Engine Pipeline")
    parser.add_argument(
        "--mode",
        type=str,
        default="demo",
        choices=["demo", "work"],
        help="Pipeline execution mode: 'demo' (data/mock_store_2) or 'work' (live APIs).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Inference batch size.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Maximum events to process (for testing/benchmarking).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Compute device ('cuda' or 'cpu').",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    pipeline = RiskEnginePipeline(
        mode=args.mode,
        device=args.device,
        batch_size=args.batch_size,
    )
    pipeline.run_pipeline(max_events=args.max_events)
