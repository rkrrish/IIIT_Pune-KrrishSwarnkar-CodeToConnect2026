import os
import json
from collections import deque
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple

import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel, AutoConfig


# ============================================================
# CONSTANTS & CONFIGURATION
# ============================================================

SENTIMENT_LABELS = ["Positive", "Negative", "Neutral"]
DEFAULT_EVENT_SEVERITY_WEIGHT = 0.50

SOURCE_RELIABILITY_SCORES = {
    "bigdata": 0.95,
    "newsapi": 0.85,
    "gdelt": 0.75,
    "default": 0.70,
}


# ============================================================
# MODEL & PIPELINE COMPONENTS
# ============================================================

class MultiTaskFinBERT(nn.Module):
    """FinBERT backbone with dual classification heads for sentiment and event tasks."""

    def __init__(self, model_name: str = "ProsusAI/finbert", num_event_classes: int = 1):
        super().__init__()
        self.config = AutoConfig.from_pretrained(model_name)
        self.bert = AutoModel.from_pretrained(model_name, config=self.config)
        
        hidden_size = self.config.hidden_size
        self.dropout = nn.Dropout(0.2)
        self.sentiment_head = nn.Linear(hidden_size, 3)
        self.event_head = nn.Linear(hidden_size, num_event_classes)

    def get_backbone_representation(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        """Extract shared pooled representation from FinBERT."""
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
            return outputs.pooler_output
        return outputs.last_hidden_state[:, 0, :]

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        pooled = self.dropout(self.get_backbone_representation(input_ids, attention_mask))
        return self.sentiment_head(pooled), self.event_head(pooled)


class TickerSentimentTracker:
    """Tracks historical sentiment scores and computes rolling metrics per ticker."""

    def __init__(self, window_size: int = 7):
        self.window_size = window_size
        self.history: Dict[str, deque] = {}

    def add_observation(self, ticker: str, sentiment_score: float, timestamp: str):
        if ticker not in self.history:
            self.history[ticker] = deque(maxlen=self.window_size)
        self.history[ticker].append({"score": float(sentiment_score), "timestamp": timestamp})

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
            "sample_count": len(hist),
        }


class ImpactScoreCalculator:
    """Calculates a normalized market impact score (1.0 to 10.0 scale)."""

    def __init__(self, event_severity_weights: Optional[Dict[str, float]] = None):
        self.event_severity_weights = event_severity_weights or {}

    def calculate_score(self, sentiment_score: float, event_type: str, source: str) -> float:
        abs_sentiment = abs(sentiment_score)
        severity_weight = self.event_severity_weights.get(event_type, DEFAULT_EVENT_SEVERITY_WEIGHT)
        source_reliability = SOURCE_RELIABILITY_SCORES.get(source.lower(), SOURCE_RELIABILITY_SCORES["default"])

        normalized_impact = 0.45 * abs_sentiment + 0.40 * severity_weight + 0.15 * source_reliability
        impact_score = 1.0 + normalized_impact * 9.0

        return round(min(10.0, max(1.0, impact_score)), 2)


@dataclass
class RiskSignal:
    """Container for processed risk engine outputs."""
    event_id: str
    ticker: str
    company_name: str
    source: str
    published_at: str
    text_snippet: str
    sentiment_score: float
    sentiment_label: str
    event_classification: str
    event_confidence: float
    impact_score: float
    rolling_sentiment_avg: float
    sentiment_momentum: float
    sentiment_history_window: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# MAIN RISK ENGINE
# ============================================================

class FinBERTRiskEngine:
    """Main interface for tokenizing text, evaluating risk metrics, and producing RiskSignals."""

    def __init__(
        self,
        model_name_or_path: str = "ProsusAI/finbert",
        checkpoint_path: Optional[str] = None,
        event_label_mapping_path: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[+] Initializing FinBERTRiskEngine on device: {self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)

        # Resolve path to event label mapping
        if event_label_mapping_path is None and checkpoint_path and os.path.isdir(checkpoint_path):
            candidate = os.path.join(checkpoint_path, "event_label_mapping.json")
            if os.path.exists(candidate):
                event_label_mapping_path = candidate

        self.event_label_mapping = self._load_event_label_mapping(event_label_mapping_path)
        self.event_categories = self.event_label_mapping["id_to_label"]
        num_event_classes = len(self.event_categories)

        if num_event_classes == 0:
            raise ValueError("No event categories were found.")

        # Initialize model and load parameters
        self.model = MultiTaskFinBERT(model_name=model_name_or_path, num_event_classes=num_event_classes)
        if checkpoint_path is not None:
            self._load_checkpoint(checkpoint_path)

        self.model = self.model.to(self.device)
        self.model.eval()

        self.tracker = TickerSentimentTracker(window_size=7)
        self.impact_calc = ImpactScoreCalculator()
        print(f"[+] Loaded {num_event_classes} event categories")

    @staticmethod
    def _load_event_label_mapping(path: Optional[str]) -> Dict[str, Any]:
        """Loads JSON label mapping and casts dictionary ID keys to integers."""
        if path is None:
            raise ValueError("event_label_mapping_path is required for the trained event classifier.")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Event label mapping not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        if "id_to_label" not in mapping:
            raise ValueError("event_label_mapping.json must contain 'id_to_label'.")

        mapping["id_to_label"] = {int(k): v for k, v in mapping["id_to_label"].items()}
        return mapping

    def _load_checkpoint(self, checkpoint_path: str):
        """Finds and loads the model state dict from a checkpoint path or folder."""
        if os.path.isdir(checkpoint_path):
            candidates = ["best_model.pt", "multitask_finbert_event_classifier.pt", "multitask_finbert.pt"]
            checkpoint_file = next((os.path.join(checkpoint_path, f) for f in candidates if os.path.exists(os.path.join(checkpoint_path, f))), None)
            if checkpoint_file is None:
                raise FileNotFoundError(f"No model checkpoint found in {checkpoint_path}")
        else:
            checkpoint_file = checkpoint_path

        print(f"[+] Loading checkpoint: {checkpoint_file}")
        state_dict = torch.load(checkpoint_file, map_location="cpu")
        missing_keys, unexpected_keys = self.model.load_state_dict(state_dict, strict=False)

        if missing_keys:
            print(f"[!] Missing checkpoint keys:\n  " + "\n  ".join(missing_keys))
        if unexpected_keys:
            print(f"[!] Unexpected checkpoint keys:\n  " + "\n  ".join(unexpected_keys))
        print("[+] Checkpoint loaded.")

    def classify_event(self, event_logits: torch.Tensor) -> Tuple[str, float]:
        """Applies softmax to event logits and returns predicted label and confidence."""
        event_probs = torch.softmax(event_logits, dim=-1).squeeze(0)
        max_prob, event_idx = torch.max(event_probs, dim=0)
        event_id = event_idx.item()
        event_class = self.event_categories.get(event_id, f"Unknown_{event_id}")
        return event_class, round(max_prob.item(), 4)

    def analyze_text(
        self,
        text: str,
        ticker: str,
        company_name: str = "",
        source: str = "newsapi",
        published_at: str = "",
        event_id: str = "",
    ) -> RiskSignal:
        """Processes input text through multi-task model to build and return a complete RiskSignal."""
        inputs = self.tokenizer(text, max_length=256, padding="max_length", truncation=True, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            sent_logits, event_logits = self.model(inputs["input_ids"], inputs["attention_mask"])

            # Calculate sentiment score (Positive Prob - Negative Prob)
            sent_probs = torch.softmax(sent_logits, dim=-1).squeeze(0)
            sentiment_score = round(sent_probs[0].item() - sent_probs[1].item(), 4)

            if sentiment_score > 0.15:
                sentiment_label = "Positive"
            elif sentiment_score < -0.15:
                sentiment_label = "Negative"
            else:
                sentiment_label = "Neutral"

            event_class, event_conf = self.classify_event(event_logits)

        # Compute additional impact and rolling metrics
        impact_score = self.impact_calc.calculate_score(sentiment_score, event_class, source)
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
            sentiment_history_window=self.tracker.get_history(ticker),
        )