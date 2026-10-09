import os
import json
import random
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from datasets import load_dataset, ClassLabel
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report

# ============================ Configuration ============================
MODEL_NAME = "microsoft/deberta-v3-base"
DATASET_NAME = "zeroshot/twitter-financial-news-topic"
OUTPUT_DIR = "output/deberta_event_classifier"

MAX_LENGTH = 128
BATCH_SIZE = 16
EPOCHS = 20
EARLY_STOP_PATIENCE = 3

HEAD_LR = 2e-4
BACKBONE_LR = 1.5e-5
WEIGHT_DECAY = 0.05
WARMUP_RATIO = 0.1
MAX_GRAD_NORM = 1.0
HEAD_DROPOUT = 0.1

HEAD_ONLY_EPOCHS = 2
GRADUAL_LAYER_UNFREEZE = True
LAYERS_PER_STAGE = 4

LABEL_SMOOTHING = 0.1
FOCAL_GAMMA = 0
CLASS_WEIGHT_POWER = 0.5
MAX_CLASS_WEIGHT = 8.0

# Official "validation" split is the held-out test set; val is carved from official "train"
VAL_SIZE = 0.15
RANDOM_SEED = 42

TRAIN_EVAL_SUBSET = 3000

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {DEVICE}")


# ============================ Utilities ============================
def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def safe_torch_load(path, map_location):
    try:
        return torch.load(path, map_location=map_location, weights_only=True)
    except Exception:
        return torch.load(path, map_location=map_location, weights_only=False)


# ============================ Data ============================
def load_training_dataset():
    ds = load_dataset(DATASET_NAME)
    train_full, test_ds = ds["train"], ds["validation"]

    label_col = find_dataset_columns(train_full)[1]
    num_classes = max(train_full.unique(label_col)) + 1
    label_feature = ClassLabel(names=[str(i) for i in range(num_classes)])
    train_full = train_full.cast_column(label_col, label_feature)
    test_ds = test_ds.cast_column(label_col, label_feature)

    split = train_full.train_test_split(test_size=VAL_SIZE, seed=RANDOM_SEED, stratify_by_column=label_col)
    return split["train"], split["test"], test_ds


def find_dataset_columns(dataset):
    text_column = next((c for c in ["text", "sentence", "content", "headline"] if c in dataset.column_names), None)
    if not text_column:
        raise ValueError("Could not identify text column.")

    label_column = next((c for c in ["label", "labels", "topic", "event_label"] if c in dataset.column_names), None)
    if not label_column:
        raise ValueError("Could not identify label column.")

    label_feature = dataset.features[label_column]
    label_names = label_feature.names if hasattr(label_feature, "names") else [str(l) for l in sorted(set(dataset[label_column]))]
    return text_column, label_column, label_names


def tokenize_dataset(datasets_, tokenizer, text_column):
    tokenize = lambda batch: tokenizer(batch[text_column], truncation=True, padding="max_length", max_length=MAX_LENGTH)
    return tuple(d.map(tokenize, batched=True) for d in datasets_)


def create_dataloader(dataset, label_column, batch_size, shuffle):
    cols = ["input_ids", "attention_mask", label_column]
    if "token_type_ids" in dataset.column_names:
        cols.append("token_type_ids")
    dataset.set_format(type="torch", columns=cols)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


def compute_class_weights(labels, num_classes):
    counts = np.bincount(np.asarray(labels), minlength=num_classes).astype(np.float64)
    counts = np.maximum(counts, 1.0)
    weights = (1.0 / counts) ** CLASS_WEIGHT_POWER
    weights = weights / weights.mean()
    weights = np.minimum(weights, MAX_CLASS_WEIGHT)
    weights = weights / weights.mean()
    return torch.tensor(weights, dtype=torch.float32), counts


# ============================ Model ============================
class DebertaEventClassifier(nn.Module):
    def __init__(self, model_name, num_event_classes, dropout=0.1):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_name)
        hidden = self.backbone.config.hidden_size
        self.event_head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, num_event_classes))

    def forward(self, input_ids, attention_mask):
        hidden_states = self.backbone(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden_states.dtype)
        pooled = (hidden_states * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        return self.event_head(pooled)


class WeightedFocalLabelSmoothingLoss(nn.Module):
    def __init__(self, class_weights, gamma=1.0, label_smoothing=0.1):
        super().__init__()
        self.register_buffer("class_weights", class_weights)
        self.gamma = gamma
        self.eps = label_smoothing

    def forward(self, logits, targets):
        log_probs = F.log_softmax(logits, dim=-1)
        target_log_probs = log_probs.gather(1, targets.unsqueeze(1)).squeeze(1)

        smooth_ce = -(1.0 - self.eps) * target_log_probs - self.eps * log_probs.mean(dim=-1)
        focal = (1.0 - target_log_probs.exp()).clamp(min=0.0) ** self.gamma if self.gamma > 0 else 1.0

        w = self.class_weights[targets]
        return (w * focal * smooth_ce).sum() / w.sum()


def set_parameter_freezing(model, epoch: int):
    if epoch < HEAD_ONLY_EPOCHS:
        for p in model.parameters():
            p.requires_grad = False
        for p in model.event_head.parameters():
            p.requires_grad = True
        return "head_only"

    if not GRADUAL_LAYER_UNFREEZE:
        for p in model.parameters():
            p.requires_grad = True
        return "all"

    for n, p in model.named_parameters():
        p.requires_grad = n.startswith("event_head.")

    encoder = model.backbone.encoder
    layers = encoder.layer
    total = len(layers)
    k = min(total, (epoch - HEAD_ONLY_EPOCHS + 1) * LAYERS_PER_STAGE)
    cutoff = total - k

    for idx, layer in enumerate(layers):
        for p in layer.parameters():
            p.requires_grad = idx >= cutoff

    # Encoder-level params shared by all layers (relative position embeddings, LayerNorm)
    for n, p in encoder.named_parameters():
        if not n.startswith("layer."):
            p.requires_grad = True

    if k == total:
        for p in model.backbone.embeddings.parameters():
            p.requires_grad = True
    return f"top_{k}_layers"


def build_optimizer_and_scheduler(model, steps_per_epoch):
    no_decay = ("bias", "LayerNorm.weight", "LayerNorm.bias")
    groups = {"head_decay": [], "head_no_decay": [], "bb_decay": [], "bb_no_decay": []}

    for n, p in model.named_parameters():
        is_head = n.startswith("event_head.")
        nd = any(x in n for x in no_decay)
        key = ("head" if is_head else "bb") + ("_no_decay" if nd else "_decay")
        groups[key].append(p)

    param_groups = []
    for key, params in groups.items():
        if not params:
            continue
        lr = HEAD_LR if key.startswith("head") else BACKBONE_LR
        wd = 0.0 if key.endswith("no_decay") else WEIGHT_DECAY
        param_groups.append({"params": params, "lr": lr, "weight_decay": wd})

    optimizer = torch.optim.AdamW(param_groups)
    total_steps = steps_per_epoch * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)
    return optimizer, scheduler


# ============================ Train / eval ============================
def get_event_logits(model, batch):
    return model(input_ids=batch["input_ids"].to(DEVICE), attention_mask=batch["attention_mask"].to(DEVICE))


@torch.no_grad()
def evaluate_model(model, dataloader, label_column):
    model.eval()
    all_preds, all_labels = [], []
    for batch in dataloader:
        logits = get_event_logits(model, batch)
        all_preds.extend(torch.argmax(logits, dim=-1).cpu().numpy())
        all_labels.extend(batch[label_column].cpu().numpy())

    acc = accuracy_score(all_labels, all_preds)
    prec, rec, f1, _ = precision_recall_fscore_support(all_labels, all_preds, average="macro", zero_division=0)
    return {"accuracy": float(acc), "precision": float(prec), "recall": float(rec), "f1": float(f1),
            "labels": all_labels, "predictions": all_preds}


def train_event_classifier(model, train_loader, train_monitor_loader, val_loader, label_column, class_weights):
    model.to(DEVICE)
    criterion = WeightedFocalLabelSmoothingLoss(class_weights.to(DEVICE), gamma=FOCAL_GAMMA, label_smoothing=LABEL_SMOOTHING).to(DEVICE)

    best_f1, epochs_no_improve = -1.0, 0
    best_model_path = os.path.join(OUTPUT_DIR, "best_model.pt")
    history = []

    set_parameter_freezing(model, 0)
    optimizer, scheduler = build_optimizer_and_scheduler(model, len(train_loader))
    last_stage = None

    for epoch in range(EPOCHS):
        stage = set_parameter_freezing(model, epoch)
        if stage != last_stage:
            print(f"\n[>>>] Epoch {epoch + 1}: trainable stage -> {stage}")
            last_stage = stage

        model.train()
        running_loss = 0.0

        for step, batch in enumerate(train_loader):
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(get_event_logits(model, batch), batch[label_column].to(DEVICE))
            loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], MAX_GRAD_NORM)
            optimizer.step()
            scheduler.step()

            running_loss += loss.item()
            if (step + 1) % 100 == 0:
                lrs = scheduler.get_last_lr()
                print(f"Epoch [{epoch + 1}/{EPOCHS}] Step [{step + 1}/{len(train_loader)}] "
                      f"Loss: {loss.item():.4f} (Avg: {running_loss / (step + 1):.4f}) LR[head/backbone]: {lrs[0]:.2e}/{lrs[-1]:.2e}")

        train_metrics = evaluate_model(model, train_monitor_loader, label_column)
        val_metrics = evaluate_model(model, val_loader, label_column)

        print(f"\n--- Epoch {epoch + 1}/{EPOCHS} Evaluation Metrics ---")
        print(f"Train* | Acc: {train_metrics['accuracy']:.4f} | Prec: {train_metrics['precision']:.4f} | Rec: {train_metrics['recall']:.4f} | F1: {train_metrics['f1']:.4f}")
        print(f"Val    | Acc: {val_metrics['accuracy']:.4f} | Prec: {val_metrics['precision']:.4f} | Rec: {val_metrics['recall']:.4f} | F1: {val_metrics['f1']:.4f}")
        print(f"Gap (train F1 - val F1): {train_metrics['f1'] - val_metrics['f1']:.4f}   (*train subset)")

        history.append({"epoch": epoch + 1, "train_loss": running_loss / len(train_loader),
                        "train_f1": train_metrics["f1"], "val_f1": val_metrics["f1"], "val_acc": val_metrics["accuracy"]})

        if val_metrics["f1"] > best_f1:
            best_f1, epochs_no_improve = val_metrics["f1"], 0
            torch.save(model.state_dict(), best_model_path)
            print(f"[+] Saved new best model checkpoint (Val F1: {best_f1:.4f})")
        else:
            epochs_no_improve += 1
            if epoch >= HEAD_ONLY_EPOCHS and epochs_no_improve >= EARLY_STOP_PATIENCE:
                print(f"[!] Early stopping at epoch {epoch + 1} (no val F1 improvement for {EARLY_STOP_PATIENCE} epochs)")
                break

    with open(os.path.join(OUTPUT_DIR, "history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)
    return model


# ============================ Main ============================
def main():
    set_seed(RANDOM_SEED)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    train_ds, val_ds, test_ds = load_training_dataset()
    text_col, label_col, label_names = find_dataset_columns(train_ds)
    num_classes = len(label_names)

    class_weights, counts = compute_class_weights(train_ds[label_col], num_classes)
    print("Class counts :", counts.astype(int).tolist())
    print("Class weights:", [round(w, 2) for w in class_weights.tolist()])

    mapping = {"dataset": DATASET_NAME, "backbone": MODEL_NAME, "num_classes": num_classes,
               "id_to_label": {str(k): v for k, v in enumerate(label_names)},
               "train_class_counts": counts.astype(int).tolist(),
               "class_weights": [float(w) for w in class_weights]}
    with open(os.path.join(OUTPUT_DIR, "event_label_mapping.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=4, ensure_ascii=False)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_ds, val_ds, test_ds = tokenize_dataset((train_ds, val_ds, test_ds), tokenizer, text_col)

    rng = np.random.RandomState(RANDOM_SEED)
    subset_idx = rng.choice(len(train_ds), size=min(TRAIN_EVAL_SUBSET, len(train_ds)), replace=False).tolist()
    train_monitor_ds = train_ds.select(subset_idx)

    train_loader = create_dataloader(train_ds, label_col, BATCH_SIZE, shuffle=True)
    train_eval_loader = create_dataloader(train_ds, label_col, BATCH_SIZE * 2, shuffle=False)
    train_monitor_loader = create_dataloader(train_monitor_ds, label_col, BATCH_SIZE * 2, shuffle=False)
    val_loader = create_dataloader(val_ds, label_col, BATCH_SIZE * 2, shuffle=False)
    test_loader = create_dataloader(test_ds, label_col, BATCH_SIZE * 2, shuffle=False)

    model = DebertaEventClassifier(MODEL_NAME, num_event_classes=num_classes, dropout=HEAD_DROPOUT)
    train_event_classifier(model, train_loader, train_monitor_loader, val_loader, label_col, class_weights)

    best_model_path = os.path.join(OUTPUT_DIR, "best_model.pt")
    model.load_state_dict(safe_torch_load(best_model_path, DEVICE))
    model.to(DEVICE)

    final_train = evaluate_model(model, train_eval_loader, label_col)
    final_val = evaluate_model(model, val_loader, label_col)
    final_test = evaluate_model(model, test_loader, label_col)

    strip = lambda m: {k: v for k, v in m.items() if k not in ("labels", "predictions")}
    print("\n================ FINAL TRAIN METRICS ================\n", strip(final_train))
    print("\n================ FINAL VAL METRICS ================\n", strip(final_val))
    print("\n================ FINAL TEST METRICS ================\n", strip(final_test))

    print("\n================ TEST CLASSIFICATION REPORT ================\n",
          classification_report(final_test["labels"], final_test["predictions"], target_names=label_names, zero_division=0))

    test_report = classification_report(final_test["labels"], final_test["predictions"],
                                        target_names=label_names, zero_division=0, output_dict=True)
    metrics_out = {
        "train": {f"{k}_macro" if k != "accuracy" else k: v for k, v in strip(final_train).items()},
        "val": {f"{k}_macro" if k != "accuracy" else k: v for k, v in strip(final_val).items()},
        "test": {f"{k}_macro" if k != "accuracy" else k: v for k, v in strip(final_test).items()},
        "test_per_class": test_report,
    }
    with open(os.path.join(OUTPUT_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics_out, f, indent=4)

    torch.save(model.state_dict(), os.path.join(OUTPUT_DIR, "deberta_event_classifier.pt"))
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"\n[+] Training complete. Final artifacts saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()