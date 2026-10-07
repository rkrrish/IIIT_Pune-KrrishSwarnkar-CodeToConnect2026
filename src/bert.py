import torch
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
from sklearn.preprocessing import OneHotEncoder, LabelBinarizer
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ==========================================
# 0. CONFIGURATION & FLAG VARIABLES
# ==========================================
# Set MODEL_FLAG to one of: 'finbert', 'roberta', 'deberta'
MODEL_FLAG = 'finbert'

MODEL_CONFIGS = {
    'finbert': 'ProsusAI/finbert',
    'roberta': 'cardiffnlp/twitter-roberta-base-sentiment-latest',
    'deberta': 'mrm8488/deberta-v3-small-finetuned-sst2'
}

DATASET_FILE = r'..\data\FinancialPhraseBank\Sentences_AllAgree.txt' # Path to your dataset file
BATCH_SIZE = 32
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

STANDARD_CLASSES = ['negative', 'neutral', 'positive']
LABEL_TO_ID = {label: i for i, label in enumerate(STANDARD_CLASSES)}


# ==========================================
# 1. DATASET FORMATTING & ONE-HOT ENCODING
# ==========================================
def parse_and_format_dataset(file_path: str) -> pd.DataFrame:
    """
    Parses '@' separated dataset into a structured DataFrame,
    encodes labels, and computes One-Hot Encodings.
    """
    data = []
    with open(file_path, 'r', encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if '@' in line:
                parts = line.rsplit('@', 1)
                sentence = parts[0].strip()
                sentiment = parts[1].strip().lower()
                data.append({'sentence': sentence, 'sentiment': sentiment})

    df = pd.DataFrame(data)

    # Standardize ground truth label IDs (0: negative, 1: neutral, 2: positive)
    df['label_id'] = df['sentiment'].map(LABEL_TO_ID)

    # One-Hot Encoding for ground truth sentiments
    ohe = OneHotEncoder(sparse_output=False, categories=[STANDARD_CLASSES])
    ohe_matrix = ohe.fit_transform(df[['sentiment']])
    ohe_cols = [f'ohe_{c}' for c in ohe.categories_[0]]
    ohe_df = pd.DataFrame(ohe_matrix, columns=ohe_cols, index=df.index)

    formatted_df = pd.concat([df, ohe_df], axis=1)
    
    # Save formatted datasets for external use
    formatted_df.to_csv('output/formatted_financial_phrasebank.csv', index=False)
    print(f"Dataset formatted successfully ({len(formatted_df)} records). Saved to 'formatted_financial_phrasebank.csv'.\n")
    return formatted_df


# ==========================================
# 2. MODEL LOADING & INFERENCE PIPELINE
# ==========================================
def load_sentiment_model(flag: str) -> Tuple[AutoTokenizer, AutoModelForSequenceClassification, Dict[int, str]]:
    """
    Loads tokenizer, model, and resolves label mapping based on flag.
    """
    if flag not in MODEL_CONFIGS:
        raise ValueError(f"Invalid MODEL_FLAG: {flag}. Choose from {list(MODEL_CONFIGS.keys())}")
    
    model_name = MODEL_CONFIGS[flag]
    print(f"Loading Model: '{flag}' -> Checkpoint: '{model_name}' on device: {DEVICE}...")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(DEVICE)
    model.eval()

    # Normalize ID-to-Label mapping across different Hugging Face models
    raw_id2label = model.config.id2label
    normalized_id2label = {}
    
    for idx, orig_label in raw_id2label.items():
        lbl_str = str(orig_label).lower()
        if 'pos' in lbl_str:
            normalized_id2label[int(idx)] = 'positive'
        elif 'neg' in lbl_str:
            normalized_id2label[int(idx)] = 'negative'
        else:
            normalized_id2label[int(idx)] = 'neutral'

    return tokenizer, model, normalized_id2label


def predict_batch(sentences: List[str], tokenizer, model, id2label: Dict[int, str], batch_size: int = 32) -> Tuple[List[str], List[float], np.ndarray]:
    """
    Runs batched inference and returns predicted labels, confidence scores, and probability distribution.
    """
    pred_labels = []
    confidence_scores = []
    all_probs = []

    for i in range(0, len(sentences), batch_size):
        batch_texts = sentences[i:i + batch_size]
        inputs = tokenizer(batch_texts, padding=True, truncation=True, max_length=128, return_tensors="pt").to(DEVICE)

        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()

        for prob in probs:
            top_idx = int(np.argmax(prob))
            pred_label = id2label[top_idx]
            conf = float(prob[top_idx])
            
            # Map probabilities to standard classes ordering: [negative, neutral, positive]
            prob_map = {id2label[idx]: prob[idx] for idx in range(len(prob))}
            std_prob = [prob_map.get(cls, 0.0) for cls in STANDARD_CLASSES]
            
            pred_labels.append(pred_label)
            confidence_scores.append(conf)
            all_probs.append(std_prob)

    return pred_labels, confidence_scores, np.array(all_probs)


# ==========================================
# 3. METRICS EVALUATION & REPORTING
# ==========================================
def evaluate_predictions(y_true_labels: List[str], y_pred_labels: List[str], pred_probs: np.ndarray):
    """
    Computes Accuracy, Precision, Recall, F1-Scores, One-Hot binarized metrics,
    and prints a detailed classification report.
    """
    y_true_ids = [LABEL_TO_ID[lbl] for lbl in y_true_labels]
    y_pred_ids = [LABEL_TO_ID[lbl] for lbl in y_pred_labels]

    # Metrics computation
    acc = accuracy_score(y_true_ids, y_pred_ids)
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(y_true_ids, y_pred_ids, average='macro', zero_division=0)
    p_weighted, r_weighted, f1_weighted, _ = precision_recall_fscore_support(y_true_ids, y_pred_ids, average='weighted', zero_division=0)

    # One-Hot Encoding for Predictions and Ground Truth
    lb = LabelBinarizer()
    lb.fit(range(len(STANDARD_CLASSES)))
    y_true_ohe = lb.transform(y_true_ids)
    y_pred_ohe = lb.transform(y_pred_ids)

    print("=" * 55)
    print(f"       EVALUATION METRICS ({MODEL_FLAG.upper()})")
    print("=" * 55)
    print(f"Accuracy           : {acc:.4f} ({acc * 100:.2f}%)")
    print(f"F1 Score (Macro)   : {f1_macro:.4f}")
    print(f"F1 Score (Weighted): {f1_weighted:.4f}")
    print(f"Precision (Macro)  : {p_macro:.4f}")
    print(f"Recall (Macro)     : {r_macro:.4f}")
    print(f"Precision (Weighted): {p_weighted:.4f}")
    print(f"Recall (Weighted)  : {r_weighted:.4f}")

    print("\n" + "=" * 55)
    print("         DETAILED CLASSIFICATION REPORT")
    print("=" * 55)
    print(classification_report(y_true_ids, y_pred_ids, target_names=STANDARD_CLASSES, digits=4))

    print("=" * 55)
    print("               CONFUSION MATRIX")
    print("=" * 55)
    cm = confusion_matrix(y_true_ids, y_pred_ids)
    cm_df = pd.DataFrame(cm, index=[f"True_{c}" for c in STANDARD_CLASSES], columns=[f"Pred_{c}" for c in STANDARD_CLASSES])
    print(cm_df)
    print("=" * 55 + "\n")


# ==========================================
# 4. MAIN EXECUTION PIPELINE
# ==========================================
if __name__ == '__main__':
    # Step 1: Format dataset
    df = parse_and_format_dataset(DATASET_FILE)

    # Step 2: Load model based on flag
    tokenizer, model, id2label = load_sentiment_model(MODEL_FLAG)

    # Step 3: Run inference across dataset
    sentences = df['sentence'].tolist()
    pred_labels, confidences, pred_probs = predict_batch(
        sentences, tokenizer, model, id2label, batch_size=BATCH_SIZE
    )

    # Attach predictions to DataFrame
    df['predicted_sentiment'] = pred_labels
    df['confidence_score'] = confidences
    
    # Add One-Hot Encodings for Predictions
    for idx, cls_name in enumerate(STANDARD_CLASSES):
        df[f'pred_prob_{cls_name}'] = pred_probs[:, idx]

    # Save detailed evaluation outputs
    df.to_csv(f'output\results_{MODEL_FLAG}.csv', index=False)
    print(f"Inference complete! Results saved to 'results_{MODEL_FLAG}.csv'.\n")

    # Step 4: Compute and display evaluation metrics
    evaluate_predictions(df['sentiment'].tolist(), df['predicted_sentiment'].tolist(), pred_probs)

    # Step 5: Test custom single-sentence inference
    sample_sentence = "Company net sales increased 16% to EUR 74.8m with strong operating profit."
    p_label, p_conf, _ = predict_batch([sample_sentence], tokenizer, model, id2label)
    print(f"Sample Input : \"{sample_sentence}\"")
    print(f"Prediction   : {p_label[0]} (Confidence Score: {p_conf[0]:.4f})")