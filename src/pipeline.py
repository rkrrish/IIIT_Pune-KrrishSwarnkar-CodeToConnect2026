import os
import json
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from gen_mock_source import RawDataIngestor, MockPipelineIngestor, TOP_20_SP100_TICKERS
from risk_engine import FinBERTRiskEngine

OUTPUT_DIR = "output/risk_engine_outputs"
STRUCTURED_SIGNALS_FILE = os.path.join(OUTPUT_DIR, "latest_risk_signals.json")
STREAM_LOG_FILE = os.path.join(OUTPUT_DIR, "signals_history_ledger.jsonl")


class RiskEnginePipeline:
    """
    Main Risk Engine execution pipeline supporting:
    - DEMO mode: Replay from mock raw payload store.
    - WORK mode: Real-time ingestion from live APIs.
    """

    def __init__(self, mode: str = "demo"):
        self.mode = mode.lower()
        self.engine = FinBERTRiskEngine()
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def extract_articles_from_payload(self, source: str, ticker: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        articles = []
        
        if source == "newsapi":
            raw_arts = payload.get("articles", [])
            for art in raw_arts:
                text = f"{art.get('title', '')}. {art.get('description', '')}"
                if text.strip(". "):
                    articles.append({
                        "text": text,
                        "published_at": art.get("publishedAt", datetime.now(timezone.utc).isoformat()),
                        "url": art.get("url", ""),
                        "source": "newsapi"
                    })

        elif source == "gdelt":
            raw_arts = payload.get("articles", [])
            for art in raw_arts:
                text = art.get("title", "")
                if text:
                    articles.append({
                        "text": text,
                        "published_at": art.get("seendate", datetime.now(timezone.utc).isoformat()),
                        "url": art.get("url", ""),
                        "source": "gdelt"
                    })

        elif source == "bigdata":
            raw_results = payload.get("results", [])
            for res in raw_results:
                text = f"{res.get('headline', '')}. {res.get('body', '')}"
                articles.append({
                    "text": text,
                    "published_at": res.get("published_at", datetime.now(timezone.utc).isoformat()),
                    "url": f"https://bigdata.com/{res.get('id')}",
                    "source": "bigdata"
                })

        return articles

    def run_pipeline(self):
        print(f"\n==================================================")
        print(f"  RUNNING NLP RISK ENGINE IN [{self.mode.upper()}] MODE")
        print(f"==================================================\n")

        processed_signals: List[Dict[str, Any]] = []

        if self.mode == "demo":
            mock_ingestor = MockPipelineIngestor()
            event_count = 0

            for item in mock_ingestor.stream_raw_events():
                meta = item["meta"]
                payload = item["payload"]
                ticker = meta["ticker"]
                source = meta["source"]

                # Resolve company name
                comp_info = next((c for c in TOP_20_SP100_TICKERS if c["ticker"] == ticker), {"name": ticker})
                company_name = comp_info["name"]

                articles = self.extract_articles_from_payload(source, ticker, payload)

                for idx, art in enumerate(articles):
                    event_count += 1
                    event_id = f"evt_{source}_{ticker}_{event_count:04d}"

                    signal = self.engine.analyze_text(
                        text=art["text"],
                        ticker=ticker,
                        company_name=company_name,
                        source=source,
                        published_at=art["published_at"],
                        event_id=event_id
                    )

                    signal_dict = signal.to_dict()
                    signal_dict["article_url"] = art["url"]
                    processed_signals.append(signal_dict)

                    # Log to stream file
                    with open(STREAM_LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(json.dumps(signal_dict) + "\n")

                    print(
                        f"[{source.upper()}] Ticker: {ticker:5s} | "
                        f"Sentiment: {signal.sentiment_score:+0.2f} ({signal.sentiment_label:8s}) | "
                        f"Event: {signal.event_classification:20s} | "
                        f"Impact: {signal.impact_score:4.1f}/10"
                    )

        elif self.mode == "work":
            raw_ingestor = RawDataIngestor()
            print("[*] Ingesting real-time feeds across 20 S&P 100 Tickers...")

            for comp in TOP_20_SP100_TICKERS:
                raw_ingestor.fetch_newsapi(comp)
                raw_ingestor.fetch_gdelt(comp)
                raw_ingestor.fetch_bigdata_stub(comp)

            # Replay ingested streams
            mock_ingestor = MockPipelineIngestor()
            for item in mock_ingestor.stream_raw_events():
                meta = item["meta"]
                payload = item["payload"]
                ticker = meta["ticker"]
                source = meta["source"]

                comp_info = next((c for c in TOP_20_SP100_TICKERS if c["ticker"] == ticker), {"name": ticker})
                articles = self.extract_articles_from_payload(source, ticker, payload)

                for idx, art in enumerate(articles):
                    signal = self.engine.analyze_text(
                        text=art["text"],
                        ticker=ticker,
                        company_name=comp_info["name"],
                        source=source,
                        published_at=art["published_at"],
                        event_id=f"evt_work_{ticker}_{idx}"
                    )
                    processed_signals.append(signal.to_dict())

        # Save structured export for Module A and Module B
        output_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "total_signals_generated": len(processed_signals),
            "signals": processed_signals
        }

        with open(STRUCTURED_SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2)

        print(f"\n[+] Processing complete. Output structured risk signals written to:")
        print(f"    -> {STRUCTURED_SIGNALS_FILE}")


if __name__ == "__main__":
    # Default execution runs DEMO mode using mock store
    pipeline = RiskEnginePipeline(mode="demo")
    pipeline.run_pipeline()