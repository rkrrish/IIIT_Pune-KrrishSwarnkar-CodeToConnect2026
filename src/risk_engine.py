import os
import sys
import json
import math
from collections import deque
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple

import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification

# Ensure CUDA runtime DLLs on Windows are available for JIT compilation
if os.name == "nt":
    bin_dir = os.path.join(sys.prefix, "bin")
    if os.path.exists(bin_dir):
        os.environ["PATH"] = bin_dir + ";" + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(bin_dir)
            except Exception:
                pass


# ============================================================
# CONSTANTS & TOPIC DEFINITIONS
# ============================================================

# Canonical 20 financial topic definitions matching the fine-tuned DeBERTa classifier
TOPIC_ID_TO_NAME: Dict[int, str] = {
    0: "Analyst Update",
    1: "Fed | Central Banks",
    2: "Company | Product News",
    3: "Treasuries | Corporate Debt",
    4: "Dividend",
    5: "Earnings",
    6: "Energy | Oil",
    7: "Financials",
    8: "Currencies",
    9: "General News | Opinion",
    10: "Gold | Metals | Materials",
    11: "IPO",
    12: "Legal | Regulation",
    13: "M&A | Investments",
    14: "Macro",
    15: "Markets",
    16: "Politics",
    17: "Personnel Change",
    18: "Stock Commentary",
    19: "Stock Movement",
}

# Inherent Market Impact Severity Weights per event category (derived from empirical market sensitivity analysis)
# Scale: 0.30 (routine commentary) to 0.95 (systemic / macroeconomic shocks)
EVENT_SEVERITY_WEIGHTS: Dict[str, float] = {
    # Tier 1: Systemic, Macroeconomic & Major Structural Shocks (0.85 - 0.95)
    "Fed | Central Banks": 0.95,
    "Macro": 0.90,
    "Legal | Regulation": 0.88,
    "Earnings": 0.86,
    "M&A | Investments": 0.85,
    "Stock Movement": 0.82,
    # Tier 2: Asset Class, Sovereign Debt & Geopolitical Factors (0.65 - 0.80)
    "Treasuries | Corporate Debt": 0.78,
    "Currencies": 0.75,
    "Energy | Oil": 0.75,
    "Politics": 0.72,
    "Markets": 0.70,
    "IPO": 0.68,
    "Dividend": 0.65,
    # Tier 3: Company Fundamentals & Operating Updates (0.50 - 0.64)
    "Company | Product News": 0.60,
    "Financials": 0.60,
    "Gold | Metals | Materials": 0.58,
    "Analyst Update": 0.55,
    "Personnel Change": 0.52,
    # Tier 4: Routine Commentary & General Noise (0.35 - 0.48)
    "Stock Commentary": 0.45,
    "General News | Opinion": 0.35,
}

DEFAULT_EVENT_SEVERITY_WEIGHT = 0.55

# Source credibility and institutional coverage weights
SOURCE_RELIABILITY_SCORES: Dict[str, float] = {
    "bigdata": 0.95,       # Institutional financial market data feed
    "newsapi": 0.88,       # Curated financial journalism / wire services
    "gdelt": 0.82,         # Global news & event database
    "twitter": 0.75,       # Social media micro-stream
    "x": 0.75,             # Social media micro-stream
    "default": 0.75,
}


# ============================================================
# MODEL ARCHITECTURES
# ============================================================

class DebertaEventClassifier(nn.Module):
    """
    DeBERTa-v3 backbone with mean-pooling and classification head for 20-class financial topic classification.
    Matches the exact architecture used in training (src/train_event_classifier_deberta.py).
    """

    def __init__(
        self,
        model_name: str = "microsoft/deberta-v3-base",
        num_event_classes: int = 20,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name)
        hidden = self.backbone.config.hidden_size
        self.event_head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden, num_event_classes),
        )

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        hidden_states = self.backbone(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden_states.dtype)
        pooled = (hidden_states * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        return self.event_head(pooled)


# ============================================================
# SENTIMENT TRACKER & IMPACT CALCULATOR
# ============================================================

class TickerSentimentTracker:
    """
    Tracks historical sentiment scores per ticker and computes rolling metrics,
    including Exponentially Weighted Moving Average (EWMA), momentum, and volatility.
    """

    def __init__(self, window_size: int = 7, alpha: Optional[float] = None):
        self.window_size = window_size
        # EWMA smoothing factor: alpha = 2 / (N + 1) if not explicitly set
        self.alpha = alpha if alpha is not None else (2.0 / (window_size + 1.0))
        self.history: Dict[str, deque] = {}
        self.ewma_state: Dict[str, float] = {}

    def add_observation(
        self,
        ticker: str,
        sentiment_score: float,
        timestamp: str,
        event_id: str = "",
        impact_score: float = 1.0,
        event_type: str = "",
    ):
        if ticker not in self.history:
            self.history[ticker] = deque(maxlen=self.window_size)
            self.ewma_state[ticker] = float(sentiment_score)
        else:
            # Update EWMA: S_i(t) = alpha * Sentiment_i(t) + (1 - alpha) * S_i(t-1)
            prev_ewma = self.ewma_state[ticker]
            self.ewma_state[ticker] = self.alpha * float(sentiment_score) + (1.0 - self.alpha) * prev_ewma

        self.history[ticker].append({
            "event_id": event_id,
            "score": float(sentiment_score),
            "impact": float(impact_score),
            "event_type": event_type,
            "timestamp": timestamp,
        })

    def get_history(self, ticker: str) -> List[Dict[str, Any]]:
        return list(self.history.get(ticker, []))

    def get_ewma(self, ticker: str) -> float:
        return round(self.ewma_state.get(ticker, 0.0), 4)

    def get_rolling_metrics(self, ticker: str) -> Dict[str, float]:
        hist = [item["score"] for item in self.history.get(ticker, [])]
        if not hist:
            return {
                "rolling_avg": 0.0,
                "ewma_sentiment": 0.0,
                "momentum": 0.0,
                "sentiment_volatility": 0.0,
                "sample_count": 0,
            }

        rolling_avg = sum(hist) / len(hist)
        ewma_val = self.ewma_state.get(ticker, rolling_avg)
        momentum = hist[-1] - hist[0] if len(hist) > 1 else 0.0

        if len(hist) > 1:
            variance = sum((x - rolling_avg) ** 2 for x in hist) / len(hist)
            volatility = math.sqrt(variance)
        else:
            volatility = 0.0

        return {
            "rolling_avg": round(rolling_avg, 4),
            "ewma_sentiment": round(ewma_val, 4),
            "momentum": round(momentum, 4),
            "sentiment_volatility": round(volatility, 4),
            "sample_count": len(hist),
        }


class ImpactScoreCalculator:
    """
    Calculates deterministic, data-calibrated market impact scores on a [1.0, 10.0] scale.
    Formulation incorporates:
      - Sentiment intensity (|Sentiment Score|)
      - Inherent event type severity weight
      - Data source reliability score
      - Event classification confidence
    """

    def __init__(
        self,
        event_severity_weights: Optional[Dict[str, float]] = None,
        source_reliability_scores: Optional[Dict[str, float]] = None,
    ):
        self.event_severity_weights = event_severity_weights or EVENT_SEVERITY_WEIGHTS
        self.source_reliability_scores = source_reliability_scores or SOURCE_RELIABILITY_SCORES

    def calculate_score(
        self,
        sentiment_score: float,
        event_type: str,
        source: str,
        event_confidence: float = 1.0,
    ) -> float:
        abs_sentiment = min(1.0, abs(sentiment_score))
        severity_weight = self.event_severity_weights.get(event_type, DEFAULT_EVENT_SEVERITY_WEIGHT)
        source_reliability = self.source_reliability_scores.get(
            source.lower(), self.source_reliability_scores["default"]
        )
        conf = min(1.0, max(0.0, event_confidence))

        # Balanced multi-factor normalized impact: [0.0, 1.0]
        # Sentiment Polarization (40%) + Event Type Shock (35%) + Source Credibility (15%) + Model Confidence (10%)
        normalized_impact = (
            0.40 * abs_sentiment
            + 0.35 * severity_weight
            + 0.15 * source_reliability
            + 0.10 * conf
        )

        # Map to 1.0 - 10.0 scale
        impact_score = 1.0 + normalized_impact * 9.0
        return round(min(10.0, max(1.0, impact_score)), 2)


# ============================================================
# STRUCTURED DATA CONTAINER
# ============================================================

@dataclass
class RiskSignal:
    """Standardized machine-readable risk signal for downstream consumption."""
    event_id: str
    ticker: str
    company_name: str
    source: str
    published_at: str
    text_snippet: str
    sentiment_score: float                      # Continuous score in [-1.0, 1.0]
    sentiment_label: str                        # "Positive", "Negative", or "Neutral"
    sentiment_probs: Dict[str, float]           # Detailed class probability distribution
    event_classification: str                   # Categorical financial topic label
    event_category_id: int                      # Numeric class ID (0..19)
    event_confidence: float                     # Classification softmax probability
    impact_score: float                         # Predicted market impact severity [1.0, 10.0]
    ewma_sentiment: float                       # Multi-period exponentially weighted sentiment
    rolling_sentiment_avg: float                # Rolling window arithmetic mean
    sentiment_momentum: float                   # Short-term sentiment delta
    sentiment_volatility: float                 # Sentiment dispersion in window
    sentiment_history_window: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# MAIN NLP RISK ENGINE
# ============================================================

class FinBERTRiskEngine:
    """
    Unified AI/NLP Risk Engine:
    - Sentiment Analysis: FinBERT (ProsusAI/finbert) mapping to [-1.0, +1.0]
    - Event Classification: Fine-tuned DeBERTa-v3 model across 20 financial topic categories
    - Impact Severity Scoring: Multi-factor deterministic calibration
    - Rolling Multi-Period Memory: EWMA and windowed tracking per ticker
    """

    def __init__(
        self,
        finbert_model_name: str = "ProsusAI/finbert",
        deberta_model_name: str = "microsoft/deberta-v3-base",
        deberta_checkpoint_path: Optional[str] = None,
        event_label_mapping_path: Optional[str] = None,
        device: Optional[str] = None,
        window_size: int = 7,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[+] Initializing FinBERTRiskEngine on device: {self.device}")

        # ----------------------------------------------------
        # 1. Load FinBERT Sentiment Model & Tokenizer
        # ----------------------------------------------------
        print(f"[+] Loading FinBERT sentiment backbone ({finbert_model_name})...")
        self.finbert_tokenizer = AutoTokenizer.from_pretrained(finbert_model_name)
        self.finbert_model = AutoModelForSequenceClassification.from_pretrained(finbert_model_name)
        self.finbert_model = self.finbert_model.to(self.device)
        self.finbert_model.eval()

        # Map FinBERT label IDs to standard [positive, negative, neutral]
        self.finbert_id2label = {
            int(k): str(v).lower() for k, v in self.finbert_model.config.id2label.items()
        }

        # ----------------------------------------------------
        # 2. Load DeBERTa Event Classifier & Checkpoint
        # ----------------------------------------------------
        deberta_dir = self._resolve_deberta_path(deberta_checkpoint_path)
        print(f"[+] Loading DeBERTa event classifier from: {deberta_dir}")

        self.topic_id_to_name = self._load_topic_mapping(event_label_mapping_path, deberta_dir)
        num_classes = len(self.topic_id_to_name)

        # Load DeBERTa tokenizer
        if os.path.exists(os.path.join(deberta_dir, "tokenizer_config.json")):
            self.deberta_tokenizer = AutoTokenizer.from_pretrained(deberta_dir)
        else:
            self.deberta_tokenizer = AutoTokenizer.from_pretrained(deberta_model_name)

        # Initialize DeBERTa architecture and load weights
        self.deberta_model = DebertaEventClassifier(
            model_name=deberta_model_name,
            num_event_classes=num_classes,
            dropout=0.1,
        )

        checkpoint_file = self._find_checkpoint_file(deberta_dir)
        self._load_deberta_weights(checkpoint_file)
        self.deberta_model = self.deberta_model.to(self.device)
        self.deberta_model.eval()

        # ----------------------------------------------------
        # 3. Initialize Tracking & Scoring Engines
        # ----------------------------------------------------
        self.tracker = TickerSentimentTracker(window_size=window_size)
        self.impact_calc = ImpactScoreCalculator()

        print(f"[+] FinBERTRiskEngine ready. Loaded {num_classes} event categories.")

    @staticmethod
    def _resolve_deberta_path(path: Optional[str]) -> str:
        candidates = [
            path,
            "src/output/deberta_event_classifier",
            "output/deberta_event_classifier",
            "../output/deberta_event_classifier",
            "output/deberta_event_classifier/best_model.pt",
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c if os.path.isdir(c) else os.path.dirname(c)
        return "src/output/deberta_event_classifier"

    @staticmethod
    def _find_checkpoint_file(directory: str) -> str:
        if os.path.isfile(directory):
            return directory
        candidates = ["best_model.pt", "deberta_event_classifier.pt"]
        for f in candidates:
            p = os.path.join(directory, f)
            if os.path.exists(p):
                return p
        raise FileNotFoundError(f"No DeBERTa checkpoint (.pt) found in {directory}")

    @staticmethod
    def _load_topic_mapping(path: Optional[str], fallback_dir: str) -> Dict[int, str]:
        """Loads topic names mapping, falling back to the canonical 20-topic financial dictionary."""
        candidate_paths = [
            path,
            os.path.join(fallback_dir, "event_label_mapping.json"),
            "src/output/deberta_event_classifier/event_label_mapping.json",
            "output/deberta_event_classifier/event_label_mapping.json",
        ]
        for p in candidate_paths:
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if "id_to_label" in data:
                        raw_map = data["id_to_label"]
                        mapping = {}
                        for k, v in raw_map.items():
                            idx = int(k)
                            if str(v).isdigit() and int(v) in TOPIC_ID_TO_NAME:
                                mapping[idx] = TOPIC_ID_TO_NAME[int(v)]
                            else:
                                mapping[idx] = TOPIC_ID_TO_NAME.get(idx, str(v))
                        return mapping
                except Exception as e:
                    print(f"[!] Warning reading {p}: {e}")

        return TOPIC_ID_TO_NAME

    def _load_deberta_weights(self, checkpoint_path: str):
        print(f"[+] Loading DeBERTa state dict: {checkpoint_path}")
        try:
            state_dict = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        except Exception:
            state_dict = torch.load(checkpoint_path, map_location="cpu", weights_only=False)

        missing_keys, unexpected_keys = self.deberta_model.load_state_dict(state_dict, strict=False)
        if missing_keys:
            print(f"[!] Missing DeBERTa keys ({len(missing_keys)}): {missing_keys[:3]}")
        if unexpected_keys:
            print(f"[!] Unexpected DeBERTa keys ({len(unexpected_keys)}): {unexpected_keys[:3]}")
        print("[+] DeBERTa weights successfully loaded.")

    def compute_sentiment(self, text: str) -> Tuple[float, str, Dict[str, float]]:
        """
        Runs FinBERT inference and calculates sentiment score in [-1.0, 1.0].
        Returns (sentiment_score, sentiment_label, probability_dict).
        """
        inputs = self.finbert_tokenizer(
            text, max_length=128, padding=True, truncation=True, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            outputs = self.finbert_model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1).squeeze(0)

        prob_dict = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        for idx, val in enumerate(probs):
            lbl_name = self.finbert_id2label.get(idx, "")
            if "pos" in lbl_name:
                prob_dict["positive"] = round(val.item(), 4)
            elif "neg" in lbl_name:
                prob_dict["negative"] = round(val.item(), 4)
            else:
                prob_dict["neutral"] = round(val.item(), 4)

        sentiment_score = round(prob_dict["positive"] - prob_dict["negative"], 4)

        if sentiment_score >= 0.15:
            sentiment_label = "Positive"
        elif sentiment_score <= -0.15:
            sentiment_label = "Negative"
        else:
            sentiment_label = "Neutral"

        return sentiment_score, sentiment_label, prob_dict

    def classify_event(self, text: str) -> Tuple[str, int, float]:
        """
        Runs DeBERTa event classifier on text.
        Returns (event_name, event_category_id, confidence).
        """
        inputs = self.deberta_tokenizer(
            text, max_length=128, padding=True, truncation=True, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            logits = self.deberta_model(inputs["input_ids"], inputs["attention_mask"]).squeeze(0)
            probs = torch.softmax(logits, dim=-1)
            top_prob, top_idx_t = torch.max(probs, dim=0)

        top_id = top_idx_t.item()
        event_name = self.topic_id_to_name.get(top_id, f"Topic_{top_id}")
        confidence = round(top_prob.item(), 4)

        return event_name, top_id, confidence

    def analyze_text(
        self,
        text: str,
        ticker: str,
        company_name: str = "",
        source: str = "newsapi",
        published_at: str = "",
        event_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RiskSignal:
        """
        Processes text through dual models (FinBERT + DeBERTa), computes impact severity,
        updates rolling EWMA sentiment history, and outputs a complete RiskSignal.
        """
        cleaned_text = text.strip()
        if not cleaned_text:
            cleaned_text = f"Market update for {ticker}"

        # 1. Parallel / Dual Model Inference
        sentiment_score, sentiment_label, sent_probs = self.compute_sentiment(cleaned_text)
        event_name, event_id_num, event_conf = self.classify_event(cleaned_text)

        # 2. Market Impact Score
        impact_score = self.impact_calc.calculate_score(
            sentiment_score=sentiment_score,
            event_type=event_name,
            source=source,
            event_confidence=event_conf,
        )

        # 3. Multi-Period Sentiment Tracking & Memory
        self.tracker.add_observation(
            ticker=ticker,
            sentiment_score=sentiment_score,
            timestamp=published_at,
            event_id=event_id,
            impact_score=impact_score,
            event_type=event_name,
        )
        metrics = self.tracker.get_rolling_metrics(ticker)

        return RiskSignal(
            event_id=event_id,
            ticker=ticker,
            company_name=company_name or ticker,
            source=source,
            published_at=published_at,
            text_snippet=cleaned_text[:300],
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            sentiment_probs=sent_probs,
            event_classification=event_name,
            event_category_id=event_id_num,
            event_confidence=event_conf,
            impact_score=impact_score,
            ewma_sentiment=metrics["ewma_sentiment"],
            rolling_sentiment_avg=metrics["rolling_avg"],
            sentiment_momentum=metrics["momentum"],
            sentiment_volatility=metrics["sentiment_volatility"],
            sentiment_history_window=self.tracker.get_history(ticker),
            metadata=metadata or {},
        )

    def analyze_batch(
        self,
        items: List[Dict[str, Any]],
    ) -> List[RiskSignal]:
        """
        High-throughput batched inference over a stream of incoming items.
        Each item dict should contain: 'text', 'ticker', 'company_name', 'source', 'published_at', 'event_id'.
        """
        if not items:
            return []

        texts = [item.get("text", "") for item in items]

        # 1. Batched FinBERT sentiment
        fb_inputs = self.finbert_tokenizer(
            texts, max_length=128, padding=True, truncation=True, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            fb_outputs = self.finbert_model(**fb_inputs)
            fb_probs = torch.softmax(fb_outputs.logits, dim=-1)

        # 2. Batched DeBERTa event classification
        db_inputs = self.deberta_tokenizer(
            texts, max_length=128, padding=True, truncation=True, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            db_logits = self.deberta_model(db_inputs["input_ids"], db_inputs["attention_mask"])
            db_probs = torch.softmax(db_logits, dim=-1)

        results: List[RiskSignal] = []

        for i, item in enumerate(items):
            text = texts[i]
            ticker = item.get("ticker", "UNKNOWN")
            company_name = item.get("company_name", ticker)
            source = item.get("source", "newsapi")
            published_at = item.get("published_at", "")
            event_id = item.get("event_id", f"evt_{i}")

            # Extract FinBERT sentiment
            curr_fb = fb_probs[i]
            prob_dict = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
            for idx in range(len(curr_fb)):
                lbl_name = self.finbert_id2label.get(idx, "")
                if "pos" in lbl_name:
                    prob_dict["positive"] = round(curr_fb[idx].item(), 4)
                elif "neg" in lbl_name:
                    prob_dict["negative"] = round(curr_fb[idx].item(), 4)
                else:
                    prob_dict["neutral"] = round(curr_fb[idx].item(), 4)

            sentiment_score = round(prob_dict["positive"] - prob_dict["negative"], 4)
            if sentiment_score >= 0.15:
                sentiment_label = "Positive"
            elif sentiment_score <= -0.15:
                sentiment_label = "Negative"
            else:
                sentiment_label = "Neutral"

            # Extract DeBERTa event
            curr_db = db_probs[i]
            top_id = int(torch.argmax(curr_db).item())
            event_name = self.topic_id_to_name.get(top_id, f"Topic_{top_id}")
            event_conf = round(curr_db[top_id].item(), 4)

            # Impact Score
            impact_score = self.impact_calc.calculate_score(
                sentiment_score=sentiment_score,
                event_type=event_name,
                source=source,
                event_confidence=event_conf,
            )

            # Tracking
            self.tracker.add_observation(
                ticker=ticker,
                sentiment_score=sentiment_score,
                timestamp=published_at,
                event_id=event_id,
                impact_score=impact_score,
                event_type=event_name,
            )
            metrics = self.tracker.get_rolling_metrics(ticker)

            signal = RiskSignal(
                event_id=event_id,
                ticker=ticker,
                company_name=company_name,
                source=source,
                published_at=published_at,
                text_snippet=text[:300],
                sentiment_score=sentiment_score,
                sentiment_label=sentiment_label,
                sentiment_probs=prob_dict,
                event_classification=event_name,
                event_category_id=top_id,
                event_confidence=event_conf,
                impact_score=impact_score,
                ewma_sentiment=metrics["ewma_sentiment"],
                rolling_sentiment_avg=metrics["rolling_avg"],
                sentiment_momentum=metrics["momentum"],
                sentiment_volatility=metrics["sentiment_volatility"],
                sentiment_history_window=self.tracker.get_history(ticker),
                metadata=item.get("metadata", {}),
            )
            results.append(signal)

        return results