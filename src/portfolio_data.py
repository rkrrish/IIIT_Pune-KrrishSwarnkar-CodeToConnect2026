import numpy as np
import pandas as pd

TICKERS = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK.B",
    "LLY", "JPM", "WMT", "V", "XOM", "JNJ", "COST", "MA", "PG", "UNH", "HD", "AVGO"
]

# Mock Market Cap Weights (normalized to 1.0)
MOCK_MARKET_CAPS = {
    "AAPL": 3000, "MSFT": 3000, "NVDA": 2200, "GOOGL": 1800, "AMZN": 1800,
    "META": 1200, "TSLA": 600, "BRK.B": 800, "LLY": 700, "JPM": 500,
    "WMT": 400, "V": 500, "XOM": 400, "JNJ": 350, "COST": 350,
    "MA": 400, "PG": 350, "UNH": 450, "HD": 350, "AVGO": 600
}

total_cap = sum(MOCK_MARKET_CAPS.values())
MKT_WEIGHTS = np.array([MOCK_MARKET_CAPS[t] / total_cap for t in TICKERS])

# Generate a synthetic positive semi-definite covariance matrix
np.random.seed(42)
num_assets = len(TICKERS)
# Simple factor model: Market factor + idiosyncratic noise
market_factor = np.random.normal(0, 0.02, 252) # 1 year of daily returns for market
betas = np.random.uniform(0.8, 1.5, num_assets)
idiosyncratic_risk = np.random.normal(0, 0.01, (num_assets, 252))

returns = betas[:, np.newaxis] * market_factor + idiosyncratic_risk
COV_MATRIX = np.cov(returns)

# Convert to DataFrame for easy indexing
COV_MATRIX_DF = pd.DataFrame(COV_MATRIX, index=TICKERS, columns=TICKERS)
