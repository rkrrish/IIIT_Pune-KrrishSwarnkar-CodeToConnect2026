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
from gen_mock_source import RawDataIngestor, TOP_20_SP100_TICKERS
from rebalancing_engine import BlackLittermanEngine

# Output directories and file locations
OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "risk_engine_outputs")
STRUCTURED_SIGNALS_FILE = os.path.join(OUTPUT_DIR, "latest_risk_signals.json")
STREAM_LOG_FILE = os.path.join(OUTPUT_DIR, "signals_history_ledger.jsonl")
SUMMARY_REPORT_FILE = os.path.join(OUTPUT_DIR, "risk_summary_report.json")


class MockStoreReader:
    """
    Reads time-series payloads from data/mock_store_2 in chronological / stream order,
    resolving raw payload paths robustly across operating systems.
    """

    def __init__(self, mock_dir: Optional[str] = r"data\mock_store_2"):
        self.mock_dir = mock_dir
        self.index_file = os.path.join(self.mock_dir, "index.json")

        if not os.path.exists(self.index_file):
            raise FileNotFoundError(f"Mock store index not found at: {self.index_file}")

        with open(self.index_file, "r", encoding="utf-8") as f:
            self.catalog: List[Dict[str, Any]] = json.load(f)

    def stream_events(self) -> Generator[Dict[str, Any], None, None]:
        """Yields raw catalog metadata and content dictionaries."""
        for entry in self.catalog:
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
    - WORK mode: Real-time ingestion from live news & financial APIs.
    """

    def __init__(
        self,
        mode: str = "demo",
        device: Optional[str] = None,
        batch_size: int = 16,
    ):
        self.mode = mode.lower()
        self.batch_size = batch_size
        self.mock_store_dir = r"./data/mock_store_2"
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        print(f"[+] Initializing RiskEnginePipeline (Mode: {self.mode.upper()})")
        print(f"[+] Mock Store Directory: {self.mock_store_dir}")
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
                })

        return articles

    def run_pipeline(
        self,
        max_events: Optional[int] = None,
        clear_previous_stream: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Executes the full risk signal generation pipeline and exports structured results.
        """
        print(f"\n==================================================================")
        print(f"  RUNNING NLP RISK ENGINE [{self.mode.upper()}] PIPELINE")
        print(f"==================================================================\n")

        if clear_previous_stream and os.path.exists(STREAM_LOG_FILE):
            open(STREAM_LOG_FILE, "w").close()

        processed_signals: List[Dict[str, Any]] = []
        event_count = 0
        start_time = time.time()

        if self.mode == "demo":
            reader = MockStoreReader(self.mock_store_dir)
            incoming_queue: List[Dict[str, Any]] = []

            for item in reader.stream_events():
                meta = item["meta"]
                payload = item["payload"]
                ticker = meta.get("ticker", "UNKNOWN")
                source = meta.get("source", "newsapi")

                comp_info = next(
                    (c for c in TOP_20_SP100_TICKERS if c["ticker"] == ticker),
                    {"name": ticker, "ticker": ticker},
                )
                company_name = comp_info["name"]

                extracted = self.extract_articles_from_payload(source, ticker, payload)

                for art in extracted:
                    event_count += 1
                    event_id = f"evt_{source}_{ticker}_{event_count:04d}"

                    incoming_queue.append({
                        "event_id": event_id,
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

                    if max_events and event_count >= max_events:
                        break

                if max_events and event_count >= max_events:
                    break

            print(f"[+] Ingested {len(incoming_queue)} total items from mock feed. Running parallel inference...")

            # Run batch inference for performance
            for i in range(0, len(incoming_queue), self.batch_size):
                batch_items = incoming_queue[i : i + self.batch_size]
                signals = self.engine.analyze_batch(batch_items)

                for sig in signals:
                    sig_dict = sig.to_dict()
                    processed_signals.append(sig_dict)

                    # Append to streaming ledger
                    with open(STREAM_LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(sig_dict) + "\n")

                    # Live log
                    print(
                        f"[{sig.source.upper():7s}] {sig.ticker:5s} | "
                        f"Sent: {sig.sentiment_score:+0.2f} ({sig.sentiment_label:8s}) | "
                        f"EWMA: {sig.ewma_sentiment:+0.2f} | "
                        f"Event: {sig.event_classification:22s} | "
                        f"Impact: {sig.impact_score:4.1f}/10"
                    )

        elif self.mode == "work":
            raw_ingestor = RawDataIngestor()
            print("[*] Ingesting live feeds for Top 20 S&P 100 Companies...")

            for comp in TOP_20_SP100_TICKERS:
                print(f"[*] Ingesting: {comp['ticker']} ({comp['name']})")
                raw_ingestor.fetch_newsapi(comp)
                raw_ingestor.fetch_gdelt(comp)
                raw_ingestor.fetch_bigdata_stub(comp)
                time.sleep(1)

            # Replay ingested items
            reader = MockStoreReader(self.mock_store_dir)
            for item in reader.stream_events():
                meta = item["meta"]
                payload = item["payload"]
                ticker = meta["ticker"]
                source = meta["source"]

                comp_info = next(
                    (c for c in TOP_20_SP100_TICKERS if c["ticker"] == ticker),
                    {"name": ticker},
                )
                extracted = self.extract_articles_from_payload(source, ticker, payload)

                for idx, art in enumerate(extracted):
                    event_count += 1
                    event_id = f"evt_live_{source}_{ticker}_{event_count:04d}"

                    sig = self.engine.analyze_text(
                        text=art["text"],
                        ticker=ticker,
                        company_name=comp_info["name"],
                        source=source,
                        published_at=art["published_at"],
                        event_id=event_id,
                        metadata={"article_url": art["url"]},
                    )
                    sig_dict = sig.to_dict()
                    processed_signals.append(sig_dict)

                    with open(STREAM_LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(sig_dict) + "\n")

        elapsed = round(time.time() - start_time, 2)

        # ----------------------------------------------------
        # Generate Aggregated Summary Report & JSON Output
        # ----------------------------------------------------
        summary_report = self._build_summary_report(processed_signals, elapsed)

        output_payload = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "mode": self.mode,
                "total_signals_generated": len(processed_signals),
                "processing_time_seconds": elapsed,
                "throughput_events_per_sec": round(len(processed_signals) / max(0.001, elapsed), 2),
            },
            "ticker_summaries": summary_report["ticker_summaries"],
            "signals": processed_signals,
        }

        # Write latest risk signals JSON
        with open(STRUCTURED_SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2)

        # Write tactical summary report for Module 2 and Module 3
        with open(SUMMARY_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(summary_report, f, indent=2)

        print(f"\n==================================================================")
        print(f"  PROCESSING COMPLETE: {len(processed_signals)} signals in {elapsed}s")
        print(f"  1. Latest Risk Signals  -> {STRUCTURED_SIGNALS_FILE}")
        print(f"  2. Stream Ledger (.jsonl)-> {STREAM_LOG_FILE}")
        print(f"  3. Risk Summary Report  -> {SUMMARY_REPORT_FILE}")
        print(f"==================================================================\n")

        # ----------------------------------------------------
        # Run Rebalancing Engine (Module 2)
        # ----------------------------------------------------
        print("\n[*] Running Tactical Index Rebalancing (Module 2)...")
        bl_engine = BlackLittermanEngine()
        rebalance_events = bl_engine.rebalance(summary_report["ticker_summaries"])
        
        rebalancing_out_dir = os.path.join(CURRENT_DIR, "output", "rebalancing_outputs")
        bl_engine.save_ledger(rebalance_events, rebalancing_out_dir)
        print(f"[*] Rebalancing complete. Ledger saved to: {rebalancing_out_dir}\n")

        return processed_signals

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
