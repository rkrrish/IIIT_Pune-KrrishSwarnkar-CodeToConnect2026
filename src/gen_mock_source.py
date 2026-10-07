import os
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()
GDELT_MIN_INTERVAL = 6
# Top 20 S&P 100 Companies by Market Cap
TOP_20_SP100_TICKERS = [
    {"ticker": "NVDA", "name": "NVIDIA"},
    {"ticker": "AAPL", "name": "Apple"},
    {"ticker": "MSFT", "name": "Microsoft"},
    {"ticker": "AMZN", "name": "Amazon"},
    {"ticker": "GOOGL", "name": "Alphabet Google"},
    {"ticker": "META", "name": "Meta Platforms Facebook"},
    {"ticker": "TSLA", "name": "Tesla"},
    {"ticker": "BRK.B", "name": "Berkshire Hathaway"},
    {"ticker": "LLY", "name": "Eli Lilly"},
    {"ticker": "JPM", "name": "JPMorgan Chase"},
    {"ticker": "WMT", "name": "Walmart"},
    {"ticker": "V", "name": "Visa"},
    {"ticker": "XOM", "name": "ExxonMobil"},
    {"ticker": "JNJ", "name": "Johnson & Johnson"},
    {"ticker": "COST", "name": "Costco"},
    {"ticker": "MA", "name": "Mastercard"},
    {"ticker": "PG", "name": "Procter & Gamble"},
    {"ticker": "UNH", "name": "UnitedHealth Group"},
    {"ticker": "HD", "name": "Home Depot"},
    {"ticker": "AVGO", "name": "Broadcom"}
]

MOCK_STORE_DIR = "../data/mock_store_2"
RAW_DATA_DIR = os.path.join(MOCK_STORE_DIR, "raw_payloads")
INDEX_FILE = os.path.join(MOCK_STORE_DIR, "index.json")


class RawDataIngestor:
    """Fetches raw data from news & media endpoints and stores unaltered JSON for pipeline replay."""

    def __init__(self, newsapi_key: str = None, bigdata_key: str = None):
        self.newsapi_key = newsapi_key or os.getenv("NEWSAPI_KEY")
        self.bigdata_key = bigdata_key or os.getenv("BIGDATA_KEY")
        self._last_gdelt_call = 0.0

        os.makedirs(RAW_DATA_DIR, exist_ok=True)
        self.catalog = self._load_catalog()

    def _load_catalog(self) -> List[Dict[str, Any]]:
        if os.path.exists(INDEX_FILE):
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_catalog(self):
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(self.catalog, f, indent=2)

    def _write_raw_file(self, source: str, ticker: str, raw_data: Dict[str, Any]) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{source}_{ticker}_{timestamp}.json"
        filepath = os.path.join(RAW_DATA_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2)

        catalog_entry = {
            "file_id": filename,
            "filepath": filepath,
            "source": source,
            "ticker": ticker,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "record_count": (
                len(raw_data.get("articles", []))
                if "articles" in raw_data
                else len(raw_data.get("articles", raw_data))
            )
        }

        self.catalog.append(catalog_entry)
        self._save_catalog()
        return filepath

    def fetch_newsapi(self, ticker_info: Dict[str, str], days_back: int = 2):
        """Fetches raw news payloads from NewsAPI.org."""
        if not self.newsapi_key:
            print("[-] NewsAPI key missing. Skipping NewsAPI fetch.")
            return

        ticker = ticker_info["ticker"]
        query = f"{ticker_info['name']} OR {ticker}"
        from_date = (
            datetime.now(timezone.utc) - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")

        url = "https://newsapi.org/v2/everything"

        params = {
            "q": query,
            "from": from_date,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 50,
            "apiKey": self.newsapi_key
        }

        try:
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                raw_json = response.json()
                path = self._write_raw_file(
                    "newsapi",
                    ticker,
                    raw_json
                )
                print(
                    f"[+] [NewsAPI] Saved {ticker} payload -> {path}"
                )
            else:
                print(
                    f"[-] [NewsAPI] Error {response.status_code} "
                    f"for {ticker}: {response.text}"
                )

        except Exception as e:
            print(
                f"[!] [NewsAPI] Exception fetching {ticker}: {str(e)}"
            )

    def fetch_gdelt(self, ticker_info, max_retries=3):
        ticker = ticker_info["ticker"]
        # Use a clean search name; add "gdelt_query" to your ticker dicts where needed
        # (e.g. "Alphabet", "Meta Platforms", "Berkshire Hathaway")
        name = ticker_info.get("gdelt_query", ticker_info["name"])

        url = "https://api.gdeltproject.org/api/v2/doc/doc"
        params = {
        "query": f'"{name}" sourcelang:english',
        "mode": "artlist",
        "maxrecords": 50,
        "format": "json",
        "sort": "datedesc",
            "timespan": "2d",          # avoids the 3-month default
        }

        for attempt in range(1, max_retries + 1):
            # Enforce spacing between ANY two GDELT calls
            wait = GDELT_MIN_INTERVAL - (time.time() - self._last_gdelt_call)
            if wait > 0:
                time.sleep(wait)
            self._last_gdelt_call = time.time()

            try:
                r = requests.get(url, params=params, timeout=(10, 60))

                if r.status_code == 429:
                    print(f"[~] [GDELT] 429 for {ticker}, retry {attempt}/{max_retries}")
                    time.sleep(10 * attempt)
                    continue

                if r.status_code != 200:
                    print(f"[-] [GDELT] Error {r.status_code} for {ticker}")
                    return

                try:
                    raw_json = r.json()
                except ValueError:
                    print(f"[-] [GDELT] Non-JSON response for {ticker}: {r.text[:150]}")
                    return

                if not raw_json.get("articles"):
                    print(f"[*] [GDELT] No articles for {ticker}")
                    return

                path = self._write_raw_file("gdelt", ticker, raw_json)
                print(f"[+] [GDELT] Saved {ticker} payload -> {path}")
                return

            except (requests.Timeout, requests.ConnectionError) as e:
                print(f"[~] [GDELT] {type(e).__name__} for {ticker}, retry {attempt}/{max_retries}")
                time.sleep(5 * attempt)

        print(f"[!] [GDELT] Gave up on {ticker}")

    def fetch_bigdata_stub(self, ticker_info: Dict[str, str]):
        """Stub for BigData.com API endpoint integration."""

        if not self.bigdata_key:
            print(
                f"[*] [BigData.com] Key not set. Creating realistic "
                f"fallback stub payload for {ticker_info['ticker']}."
            )

            stub_payload = {
                "source": "bigdata.com",
                "status": "mock_generated",
                "ticker": ticker_info["ticker"],
                "results": [
                    {
                        "id": f"bd_{ticker_info['ticker']}_001",
                        "headline": (
                            f"Quarterly earnings update for "
                            f"{ticker_info['name']}"
                        ),
                        "body": (
                            f"Analysts predict shifted revenue trajectories "
                            f"for {ticker_info['name']} following new market "
                            f"dynamics."
                        ),
                        "published_at": (
                            datetime.now(timezone.utc).isoformat()
                        )
                    }
                ]
            }

            self._write_raw_file(
                "bigdata",
                ticker_info["ticker"],
                stub_payload
            )


class MockPipelineIngestor:
    """Downstream Simulator Engine: Reads stored raw datasets as if receiving real-time API calls."""

    def __init__(self, mock_dir: str = MOCK_STORE_DIR):
        self.index_path = os.path.join(mock_dir, "index.json")

        if not os.path.exists(self.index_path):
            raise FileNotFoundError(
                "Mock store index not found. "
                "Run RawDataIngestor first."
            )

        with open(self.index_path, "r", encoding="utf-8") as f:
            self.catalog = json.load(f)

    def stream_raw_events(self):
        """Yields raw ingested datasets sequentially to simulate real-time ingestion."""

        for entry in self.catalog:
            filepath = entry["filepath"]

            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    raw_content = json.load(f)

                yield {
                    "meta": entry,
                    "payload": raw_content
                }


if __name__ == "__main__":
    # Supply API keys here or via environment variables
    NEWSAPI_KEY = os.getenv(
        "NEWSAPI_KEY",
        "YOUR_NEWSAPI_KEY_HERE"
    )

    BIGDATA_KEY = os.getenv(
        "BIGDATA_KEY",
        "YOUR_BIGDATA_KEY_HERE"
    )

    ingestor = RawDataIngestor(
        newsapi_key=NEWSAPI_KEY,
        bigdata_key=BIGDATA_KEY
    )

    print(
        "=== Starting Raw Data Collection for "
        "Top 20 S&P 100 Tickers ==="
    )

    for comp in TOP_20_SP100_TICKERS:

        print(
            f"\nProcessing Ticker: "
            f"{comp['ticker']} ({comp['name']})"
        )

        ingestor.fetch_newsapi(comp)

        # GDELT Project API
        ingestor.fetch_gdelt(comp)

        ingestor.fetch_bigdata_stub(comp)

        time.sleep(2)  # Respect API rate limits

    print(
        "\n=== Collection Complete. "
        "Testing Mock Pipeline Replay ==="
    )

    mock_engine = MockPipelineIngestor()

    stream_count = 0

    for item in mock_engine.stream_raw_events():
        stream_count += 1

        meta = item["meta"]

        print(
            f"Simulating Event Stream #{stream_count}: "
            f"Source={meta['source']} | "
            f"Ticker={meta['ticker']} | "
            f"File={meta['file_id']}"
        )