## 1. Project Overview / Problem Statement & Approach
This project implements an AI/NLP-driven Risk Engine and a Tactical Index Rebalancing system. In the financial domain, rapidly reacting to unstructured data (like news and social media sentiment) is crucial for managing portfolio risk and seizing momentum. The solution ingests time-series text feeds, analyzes them in real-time to generate sentiment and impact scores, and dynamically rebalances a mock stock index (top 20 S&P 100 stocks) to optimize risk-adjusted returns.

The approach utilizes a dual-model NLP architecture (FinBERT for sentiment and DeBERTa for event classification) to create structured, machine-readable risk signals. These signals are then fed into a Black-Litterman optimization model that blends the sentiment views with market-cap equilibriums to systematically reweight the portfolio without extreme fluctuations.

## 2. Architecture & Tech Stack
- **Module 1 (NLP Risk Engine)**: Ingests raw data from APIs or a mock datastore, processes it through HuggingFace transformers (`FinBERT`, `DeBERTa`), and tracks state using Exponentially Weighted Moving Averages (EWMA) to filter transient noise.
- **Module 2 (Tactical Rebalancing)**: Employs the Black-Litterman model to map sentiment signals into dynamic views (Q matrix) and adjust the target weights of the 20-stock index considering inter-stock covariances.
- **Module 3 (Visualization)**: A Streamlit-based interactive dashboard to visualize weight changes and provide a granular audit trail linking portfolio adjustments back to the originating text payload.
- **Tech Stack**: Python 3.10, PyTorch, Transformers (HuggingFace), NumPy, Pandas, Plotly, Streamlit.

## 3. Dataset Used
- **Mock Store (Demo Mode)**: Pre-fetched financial news articles and event data stored in `data/mock_store_2` to simulate a real-time time-series feed.
- **Event Classification Training**: The DeBERTa classifier was fine-tuned on the `zeroshot/twitter-financial-news-topic` dataset (available on HuggingFace).
- **Assumptions**: The mock data simulates a continuous feed for 20 S&P 100 tickers. Covariance matrices used in the rebalancing module are synthetically generated for demonstration.

## 4. Quickstart & Installation
Runtime: Python 3.10 on Windows

Step-by-step commands to set up the environment and run your code locally:
```bash
# 1. Setup the environment
conda create -n py310 python=3.10
conda activate py310

# 2. Install dependencies
pip install torch transformers numpy pandas streamlit plotly

# 3. Set up mock data source for demo mode
# Put the data files as it is in the folder: src/mock_data_store 
# Or to generate a new mock data store, update .env with API keys and run:
# python src/gen_mock_source.py

# 4. Run the Pipeline (Module 1 & 2)
python src/pipeline.py --mode demo

# 5. Run the Interactive Dashboard
streamlit run src/dashboard.py
```

## 5. Key Results & Domain Impact
- **Outputs**: The system outputs structured JSON risk signals (`latest_risk_signals.json`), an audit ledger (`signals_history_ledger.jsonl`), and target portfolio weights (`rebalance_ledger.jsonl`). An interactive dashboard visualizes the changes.
- **Domain Impact**: Proves the viability of algorithmic trading and dynamic asset allocation driven by real-time NLP, avoiding the pitfalls of traditional mean-variance corner solutions via the Black-Litterman framework.

### Event Classification Training Results
- **Approach**: Fine-tuned a DeBERTa model with a custom classifier head. FinBERT was initially tested, but DeBERTa demonstrated superior performance across the 20 financial event categories. Output labels include 'positive earnings', 'legal/regulatory issues', 'mergers & acquisitions', 'product/service launch', etc.

**FinBERT Final Test Metrics**:
`{'accuracy': 0.9128, 'precision': 0.8846, 'recall': 0.9162, 'f1': 0.8972}`

**DeBERTa Final Test Metrics (Chosen Model)**:
`{'accuracy': 0.9298, 'precision': 0.9263, 'recall': 0.9293, 'f1': 0.9269}`

*Training complete. Final artifacts saved to output/deberta_event_classifier*