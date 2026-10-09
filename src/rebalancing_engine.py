import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json
import os
from portfolio_data import TICKERS, MKT_WEIGHTS, COV_MATRIX_DF

@dataclass
class RebalanceEvent:
    timestamp: str
    ticker: str
    new_weight: float
    old_weight: float
    rolling_sentiment_avg: float
    impact_score: float
    latest_event_id: str

class BlackLittermanEngine:
    def __init__(self, risk_aversion: float = 2.5, tau: float = 0.05, view_scale: float = 0.01):
        self.risk_aversion = risk_aversion
        self.tau = tau
        self.view_scale = view_scale
        self.tickers = TICKERS
        self.w_mkt = MKT_WEIGHTS
        self.cov_matrix = COV_MATRIX_DF.values
        # Implied Equilibrium Returns: Pi = risk_aversion * Sigma * w_mkt
        self.pi = self.risk_aversion * np.dot(self.cov_matrix, self.w_mkt)
        self.current_weights = self.w_mkt.copy()
        
    def rebalance(self, ticker_summaries: Dict[str, dict]) -> List[RebalanceEvent]:
        """
        Takes the ticker summaries from latest_risk_signals.json and generates new target weights.
        """
        active_tickers = []
        Q_list = []
        uncertainties = []
        
        for i, ticker in enumerate(self.tickers):
            if ticker in ticker_summaries:
                summary = ticker_summaries[ticker]
                if summary.get("total_events_observed", 0) > 0:
                    active_tickers.append(i)
                    
                    # Q = sentiment * impact * scale
                    sentiment = summary.get("rolling_sentiment_avg", 0.0)
                    impact = summary.get("average_impact_score", 5.0)
                    view_val = sentiment * impact * self.view_scale
                    Q_list.append(view_val)
                    
                    # Uncertainty Omega proportional to volatility or inverse of events count
                    vol = summary.get("sentiment_volatility", 0.5)
                    count = summary.get("total_events_observed", 1)
                    omega_val = (vol ** 2) / count
                    # Add a baseline uncertainty to prevent overconfidence
                    uncertainties.append(omega_val + 0.001)
                    
        k = len(active_tickers)
        if k == 0:
            return []
            
        P = np.zeros((k, len(self.tickers)))
        for idx, t_idx in enumerate(active_tickers):
            P[idx, t_idx] = 1.0
            
        Q = np.array(Q_list)
        Omega = np.diag(uncertainties)
        
        # Black Litterman formula
        # Posterior estimate of returns:
        # E[R] = [ (tau * Sigma)^-1 + P^T * Omega^-1 * P ]^-1 * [ (tau * Sigma)^-1 * Pi + P^T * Omega^-1 * Q ]
        tau_sigma = self.tau * self.cov_matrix
        tau_sigma_inv = np.linalg.inv(tau_sigma)
        
        omega_inv = np.linalg.inv(Omega)
        
        left_term = np.linalg.inv(tau_sigma_inv + np.dot(np.dot(P.T, omega_inv), P))
        right_term = np.dot(tau_sigma_inv, self.pi) + np.dot(np.dot(P.T, omega_inv), Q)
        
        posterior_returns = np.dot(left_term, right_term)
        
        # New target weights: W = (risk_aversion * Sigma)^-1 * posterior_returns
        sigma_inv = np.linalg.inv(self.cov_matrix)
        new_weights = np.dot(sigma_inv, posterior_returns) / self.risk_aversion
        
        # Normalize weights so they sum to 1 and prevent extreme shorting if desired
        new_weights = np.clip(new_weights, 0, None)  # No short selling for index
        if np.sum(new_weights) > 0:
            new_weights = new_weights / np.sum(new_weights)
        else:
            new_weights = self.w_mkt.copy()
            
        events = []
        for i, ticker in enumerate(self.tickers):
            if ticker in ticker_summaries:
                summary = ticker_summaries[ticker]
                events.append(RebalanceEvent(
                    timestamp=summary.get("latest_timestamp", ""),
                    ticker=ticker,
                    new_weight=new_weights[i],
                    old_weight=self.current_weights[i],
                    rolling_sentiment_avg=summary.get("rolling_sentiment_avg", 0.0),
                    impact_score=summary.get("average_impact_score", 5.0),
                    latest_event_id=summary.get("latest_event_id", "")
                ))
        
        self.current_weights = new_weights.copy()
        return events

    def save_ledger(self, events: List[RebalanceEvent], output_dir: str):
        os.makedirs(output_dir, exist_ok=True)
        ledger_path = os.path.join(output_dir, "rebalance_ledger.jsonl")
        
        with open(ledger_path, "a", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(asdict(event)) + "\n")
        
        # Also save latest weights as json for quick load by dashboard
        latest_path = os.path.join(output_dir, "latest_weights.json")
        weights_dict = {ticker: weight for ticker, weight in zip(self.tickers, self.current_weights)}
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(weights_dict, f, indent=2)
