import os
import math
import json
from collections import deque
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple

import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel, AutoConfig

# Target Event Categories
EVENT_CATEGORIES = [
    "Geopolitical",
    "Macroeconomic",
    "Credit Event",
    "Merger/Acquisition",
    "Product Launch",
    "Regulatory/Legal",
    "Earnings/Financial",
    "Business Operations"
]

# Event Severity Weights (0.0 to 1.0) for Impact Score calculation
EVENT_SEVERITY_WEIGHTS = {
    "Geopolitical": 0.95,
    "Macroeconomic": 0.90,
    "Credit Event": 0.85,
    "Merger/Acquisition": 0.75,
    "Regulatory/Legal": 0.70,
    "Earnings/Financial": 0.60,
    "Product Launch": 0.50,
    "Business Operations": 0.40
}

# Source Reliability Coefficients
SOURCE_RELIABILITY_SCORES = {
    "bigdata": 0.95,
    "newsapi": 0.85,
    "gdelt": 0.75,
    "default": 0.70
}


class MultiTaskFinBERT(nn.Module):
    """
    Multi-Task FinBERT architecture with shared BERT Transformer backbone
    and dual heads:
    1. Sentiment Head: 3-class logits (Positive, Negative, Neutral) -> continuous [-1.0, 1.0]
    2. Event Head: Multi-class logits over financial event categories.
    """
    def __init__(self, model_name: str = "ProsusAI/finbert", num_event_classes: int = len(EVENT_CATEGORIES)):
        super().__init__()
        self.config = AutoConfig.from_pretrained(model_name)
        self.bert = AutoModel.from_pretrained(model_name, config=self.config)
        hidden_size = self.config.hidden_size

        # Dropout layer
        self.dropout = nn.Dropout(0.2)

        # Sentiment Classifier Head (3 classes: positive, negative, neutral)
        self.sentiment_head = nn.Linear(hidden_size, 3)

        # Event Classification Head
        self.event_head = nn.Linear(hidden_size, num_event_classes)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        pooled_output = outputs.pooler_output if hasattr(outputs, 'pooler_output') and outputs.pooler_output is not None else outputs.last_hidden_state[:, 0, :]
        pooled_output = self.dropout(pooled_output)

        sentiment_logits = self.sentiment_head(pooled_output)
        event_logits = self.event_head(pooled_output)

        return sentiment_logits, event_logits


class TickerSentimentTracker:
    """Tracks the last 7 sentiment changes per ticker to capture gradual shifts and momentum."""
    def __init__(self, window_size: int = 7):
        self.window_size = window_size
        self.history: Dict[str, deque] = {}

    def add_observation(self, ticker: str, sentiment_score: float, timestamp: str):
        if ticker not in self.history:
            self.history[ticker] = deque(maxlen=self.window_size)
        
        self.history[ticker].append({
            "score": float(sentiment_score),
            "timestamp": timestamp
        })

    def get_history(self, ticker: str) -> List[Dict[str, Any]]:
        return list(self.history.get(ticker, []))

    def get_rolling_metrics(self, ticker: str) -> Dict[str, float]:
        hist = [item["score"] for item in self.history.get(ticker, [])]
        if not hist:
            return {"rolling_avg": 0.0, "momentum": 0.0, "sample_count": 0}

        rolling_avg = sum(hist) / len(hist)
        momentum = hist[-1] - hist[0] if len(hist) > 1 else 0.0

        return {
            "rolling_avg": round(rolling_avg, 4),
            "momentum": round(momentum, 4),
            "sample_count": len(hist)
        }


class ImpactScoreCalculator:
    """Calculates deterministic market impact score (1-10) using formula."""

    @staticmethod
    def calculate_score(sentiment_score: float, event_type: str, source: str) -> float:
        abs_sentiment = abs(sentiment_score)
        severity_weight = EVENT_SEVERITY_WEIGHTS.get(event_type, 0.50)
        source_reliability = SOURCE_RELIABILITY_SCORES.get(source.lower(), SOURCE_RELIABILITY_SCORES["default"])

        # Weighted combination scaled from 1.0 to 10.0
        normalized_impact = (
            0.45 * abs_sentiment +
            0.40 * severity_weight +
            0.15 * source_reliability
        )
        
        # Scale to 1-10 range
        impact_score = 1.0 + (normalized_impact * 9.0)
        return round(min(10.0, max(1.0, impact_score)), 2)


@dataclass
class RiskSignal:
    event_id: str
    ticker: str
    company_name: str
    source: str
    published_at: str
    text_snippet: str
    sentiment_score: float  # Range [-1.0, 1.0]
    sentiment_label: str    # Positive, Negative, Neutral
    event_classification: str
    event_confidence: float
    impact_score: float     # Range [1.0, 10.0]
    rolling_sentiment_avg: float
    sentiment_momentum: float
    sentiment_history_window: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FinBERTRiskEngine:
    """Main Risk Engine interface for batch and real-time processing."""

    def __init__(self, model_name_or_path: str = "ProsusAI/finbert", device: Optional[str] = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[+] Initializing FinBERTRiskEngine on device: {self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        self.model = MultiTaskFinBERT(model_name="ProsusAI/finbert").to(self.device)
        self.model.eval()

        self.tracker = TickerSentimentTracker(window_size=7)
        self.impact_calc = ImpactScoreCalculator()

        # Keyword rules for zero-shot fallback event classifier if custom head is un-tuned
        self.keyword_rules = {
            "Geopolitical": ["tariff", "war", "sanction", "trade deal", "geopolitical", "conflict", "election"],
            "Macroeconomic": ["inflation", "fed", "interest rate", "gdp", "recession", "central bank", "cpi"],
            "Credit Event": ["default", "downgrade", "debt", "bankruptcy", "bond yield", "credit rating"],
            "Merger/Acquisition": ["acquisition", "merger", "buyout", "takeover", "acquire", "deal"],
            "Product Launch": ["launch", "unveil", "release", "new product", "feature", "announces"],
            "Regulatory/Legal": ["lawsuit", "sec", "investigation", "fine", "regulatory", "compliance", "court"],
            "Earnings/Financial": ["earnings", "revenue", "profit", "quarterly", "eps", "guidance", "fiscal"]
        }

    def _rule_based_event_classify(self, text: str) -> Tuple[str, float]:
        text_lower = text.lower()
        scores = {}
        for category, keywords in self.keyword_rules.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > 0:
                scores[category] = count

        if scores:
            best_cat = max(scores, key=scores.get)
            return best_cat, min(0.90, 0.50 + 0.15 * scores[best_cat])
        return "Business Operations", 0.60

    def analyze_text(
        self,
        text: str,
        ticker: str,
        company_name: str = "",
        source: str = "newsapi",
        published_at: str = "",
        event_id: str = ""
    ) -> RiskSignal:
        inputs = self.tokenizer(
            text,
            max_length=256,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            sent_logits, event_logits = self.model(inputs["input_ids"], inputs["attention_mask"])

            # 1. Calculate Sentiment Score in [-1.0, 1.0]
            sent_probs = torch.softmax(sent_logits, dim=-1).squeeze(0)
            # ProsusAI/finbert outputs logits for [positive, negative, neutral]
            p_pos, p_neg, p_neu = sent_probs[0].item(), sent_probs[1].item(), sent_probs[2].item()
            sentiment_score = round(p_pos - p_neg, 4)

            if sentiment_score > 0.15:
                sentiment_label = "Positive"
            elif sentiment_score < -0.15:
                sentiment_label = "Negative"
            else:
                sentiment_label = "Neutral"

            # 2. Event Classification
            event_probs = torch.softmax(event_logits, dim=-1).squeeze(0)
            max_prob, event_idx = torch.max(event_probs, dim=0)

            # Fallback to keyword matching if untrained head yields low confidence
            if max_prob.item() < 0.35:
                event_class, event_conf = self._rule_based_event_classify(text)
            else:
                event_class = EVENT_CATEGORIES[event_idx.item()]
                event_conf = round(max_prob.item(), 4)

        # 3. Compute Deterministic Impact Score
        impact_score = self.impact_calc.calculate_score(
            sentiment_score=sentiment_score,
            event_type=event_class,
            source=source
        )

        # 4. Update Rolling History Tracker
        self.tracker.add_observation(ticker, sentiment_score, published_at)
        rolling_metrics = self.tracker.get_rolling_metrics(ticker)

        return RiskSignal(
            event_id=event_id,
            ticker=ticker,
            company_name=company_name or ticker,
            source=source,
            published_at=published_at,
            text_snippet=text[:300],
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            event_classification=event_class,
            event_confidence=event_conf,
            impact_score=impact_score,
            rolling_sentiment_avg=rolling_metrics["rolling_avg"],
            sentiment_momentum=rolling_metrics["momentum"],
            sentiment_history_window=self.tracker.get_history(ticker)
        )