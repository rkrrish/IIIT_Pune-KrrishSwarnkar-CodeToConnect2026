import os
import json
import random
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from datasets import load_dataset
from transformers import AutoTokenizer, get_linear_schedule_with_warmup
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report
from risk_engine import MultiTaskFinBERT

# Configuration
MODEL_NAME = "ProsusAI/finbert"
DATASET_NAME = "zeroshot/twitter-financial-news-topic"
BASE_MODEL_CHECKPOINT = "output/finbert_multitask_weights"
OUTPUT_DIR = "output/finbert_event_classifier"

MAX_LENGTH = 256
BATCH_SIZE = 16
EPOCHS = 30

# Differential Learning Rates
HEAD_LR = 5e-4         # Higher learning rate for randomly initialized head
BACKBONE_LR = 2e-5     # Lower learning rate for pre-trained transformer backbone
WEIGHT_DECAY = 0.005
WARMUP_RATIO = 0.2

# Unfreezing Schedule
UNFREEZE_HEAD_ONLY_EPOCHS = 7  # Train head alone for first 7 epochs
GRADUAL_LAYER_UNFREEZE = True  # Stepwise layer unfreezing vs all at once

# Dataset Split Ratios (70% Train, 15% Validation, 15% Test)
TEST_SIZE = 0.15
VAL_SIZE = 0.15
RANDOM_SEED = 42

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {DEVICE}")

def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def load_training_dataset():
    """Split dataset into Train, Validation, and Test sets."""
    ds = load_dataset(DATASET_NAME)
    full_dataset = ds["train"] if "train" in ds else ds[list(ds.keys())[0]]
    
    # Extract test set first
    split_test = full_dataset.train_test_split(test_size=TEST_SIZE, seed=RANDOM_SEED)
    test_ds = split_test["test"]
    
    # Calculate relative validation ratio from remaining training data
    val_relative_ratio = VAL_SIZE / (1.0 - TEST_SIZE)
    split_train_val = split_test["train"].train_test_split(test_size=val_relative_ratio, seed=RANDOM_SEED)
    
    train_ds = split_train_val["train"]
    val_ds = split_train_val["test"]
    
    return train_ds, val_ds, test_ds

def find_dataset_columns(dataset):
    text_column = next((c for c in ["text", "sentence", "content", "headline"] if c in dataset.column_names), None)
    if not text_column: raise ValueError("Could not identify text column.")

    label_column = next((c for c in ["label", "labels", "topic", "event_label"] if c in dataset.column_names), None)
    if not label_column: raise ValueError("Could not identify label column.")

    label_feature = dataset.features[label_column]
    label_names = label_feature.names if hasattr(label_feature, "names") else [str(lbl) for lbl in sorted(set(dataset[label_column]))]

    return text_column, label_column, label_names

def tokenize_dataset(train_dataset, val_dataset, test_dataset, tokenizer, text_column):
    tokenize = lambda batch: tokenizer(batch[text_column], truncation=True, padding="max_length", max_length=MAX_LENGTH)
    return (
        train_dataset.map(tokenize, batched=True),
        val_dataset.map(tokenize, batched=True),
        test_dataset.map(tokenize, batched=True)
    )

def create_dataloader(dataset, label_column, batch_size, shuffle):
    cols = ["input_ids", "attention_mask", label_column]
    if "token_type_ids" in dataset.column_names: cols.append("token_type_ids")
    dataset.set_format(type="torch", columns=cols)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)

def load_existing_model(num_event_classes):
    model = MultiTaskFinBERT(model_name=MODEL_NAME, num_event_classes=num_event_classes)
    
    ckpt_path = BASE_MODEL_CHECKPOINT
    if os.path.isdir(BASE_MODEL_CHECKPOINT):
        candidates = ["multitask_finbert.pt", "best_model.pt", "multitask_finbert_event_classifier.pt"]
        ckpt_path = next((os.path.join(ckpt_path, f) for f in candidates if os.path.exists(os.path.join(ckpt_path, f))), ckpt_path)
    
    if os.path.exists(ckpt_path):
        checkpoint = torch.load(ckpt_path, map_location="cpu")
        filtered_ckpt = {k: v for k, v in checkpoint.items() if not k.startswith("event_head.")}
        model.load_state_dict(filtered_ckpt, strict=False)
        print(f"[+] Loaded pre-trained backbone weights from {ckpt_path}")
    else:
        print(f"[!] Checkpoint not found at {ckpt_path}. Initializing default weights.")

    return model

def set_parameter_freezing(model, epoch: int):
    if epoch < UNFREEZE_HEAD_ONLY_EPOCHS:
        for param in model.parameters():
            param.requires_grad = False
        for param in model.event_head.parameters():
            param.requires_grad = True
    else:
        if not GRADUAL_LAYER_UNFREEZE:
            for param in model.parameters():
                param.requires_grad = True
        else:
            for param in model.parameters():
                param.requires_grad = True
            
            unfreeze_stage = epoch - UNFREEZE_HEAD_ONLY_EPOCHS
            if hasattr(model, "bert") and hasattr(model.bert, "encoder"):
                total_layers = len(model.bert.encoder.layer)
                layers_to_unfreeze = min(total_layers, (unfreeze_stage + 1) * 3)
                cutoff = total_layers - layers_to_unfreeze
                
                for idx, layer in enumerate(model.bert.encoder.layer):
                    requires_grad = (idx >= cutoff)
                    for p in layer.parameters():
                        p.requires_grad = requires_grad

def get_optimizer_param_groups(model):
    no_decay = ["bias", "LayerNorm.weight"]
    
    head_params_decay = [p for n, p in model.event_head.named_parameters() if not any(nd in n for nd in no_decay) and p.requires_grad]
    head_params_no_decay = [p for n, p in model.event_head.named_parameters() if any(nd in n for nd in no_decay) and p.requires_grad]
    
    backbone_params_decay = [p for n, p in model.named_parameters() if not n.startswith("event_head.") and not any(nd in n for nd in no_decay) and p.requires_grad]
    backbone_params_no_decay = [p for n, p in model.named_parameters() if not n.startswith("event_head.") and any(nd in n for nd in no_decay) and p.requires_grad]
    
    param_groups = []
    
    if head_params_decay:
        param_groups.append({"params": head_params_decay, "lr": HEAD_LR, "weight_decay": WEIGHT_DECAY})
    if head_params_no_decay:
        param_groups.append({"params": head_params_no_decay, "lr": HEAD_LR, "weight_decay": 0.0})
        
    if backbone_params_decay:
        param_groups.append({"params": backbone_params_decay, "lr": BACKBONE_LR, "weight_decay": WEIGHT_DECAY})
    if backbone_params_no_decay:
        param_groups.append({"params": backbone_params_no_decay, "lr": BACKBONE_LR, "weight_decay": 0.0})

    return param_groups

def get_event_logits(model, batch):
    input_ids, attn_mask = batch["input_ids"].to(DEVICE), batch["attention_mask"].to(DEVICE)
    _, event_logits = model(input_ids=input_ids, attention_mask=attn_mask)
    return event_logits

@torch.no_grad()
def evaluate_model(model, dataloader, label_column):
    model.eval()
    all_preds, all_labels = [], []

    for batch in dataloader:
        event_logits = get_event_logits(model, batch)
        preds = torch.argmax(event_logits, dim=-1)
        labels = batch[label_column].to(DEVICE)
        
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(labels.cpu().numpy())

    acc = accuracy_score(all_labels, all_preds)
    prec, rec, f1, _ = precision_recall_fscore_support(all_labels, all_preds, average="macro", zero_division=0)
    
    return {"accuracy": float(acc), "precision": float(prec), "recall": float(rec), "f1": float(f1), "labels": all_labels, "predictions": all_preds}

def build_optimizer_and_scheduler(model, remaining_epochs, train_loader):
    param_groups = get_optimizer_param_groups(model)
    optimizer = torch.optim.AdamW(param_groups)
    total_steps = len(train_loader) * remaining_epochs
    warmup_steps = int(total_steps * WARMUP_RATIO)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)
    return optimizer, scheduler

def train_event_classifier(model, train_loader, train_eval_loader, val_loader, label_column, label_names):
    model.to(DEVICE)
    criterion = nn.CrossEntropyLoss()
    
    best_f1 = -1.0
    best_model_path = os.path.join(OUTPUT_DIR, "best_model.pt")

    set_parameter_freezing(model, epoch=0)
    optimizer, scheduler = build_optimizer_and_scheduler(model, EPOCHS, train_loader)

    for epoch in range(EPOCHS):
        set_parameter_freezing(model, epoch)
        
        if epoch == UNFREEZE_HEAD_ONLY_EPOCHS or (GRADUAL_LAYER_UNFREEZE and epoch > UNFREEZE_HEAD_ONLY_EPOCHS):
            remaining_epochs = EPOCHS - epoch
            optimizer, scheduler = build_optimizer_and_scheduler(model, remaining_epochs, train_loader)
            print(f"\n[>>>] Unfreezing stage reached at Epoch {epoch + 1}. Backbone params active with LR: {BACKBONE_LR}")

        model.train()
        running_loss = 0.0

        for step, batch in enumerate(train_loader):
            optimizer.zero_grad(set_to_none=True)
            logits = get_event_logits(model, batch)
            loss = criterion(logits, batch[label_column].to(DEVICE))
            
            loss.backward()
            
            trainable_params = [p for p in model.parameters() if p.requires_grad]
            torch.nn.utils.clip_grad_norm_(trainable_params, max_norm=1.0)
            
            optimizer.step()
            scheduler.step()
            
            running_loss += loss.item()
            if (step + 1) % 50 == 0:
                avg_loss = running_loss / (step + 1)
                print(f"Epoch [{epoch + 1}/{EPOCHS}] Step [{step + 1}/{len(train_loader)}] Loss: {loss.item():.4f} (Avg: {avg_loss:.4f})")

        # Evaluate on both Train and Validation sets at the end of each epoch
        train_metrics = evaluate_model(model, train_eval_loader, label_column)
        val_metrics = evaluate_model(model, val_loader, label_column)
        
        print(f"\n--- Epoch {epoch + 1}/{EPOCHS} Evaluation Metrics ---")
        print(f"Train | Acc: {train_metrics['accuracy']:.4f} | Prec: {train_metrics['precision']:.4f} | Rec: {train_metrics['recall']:.4f} | F1: {train_metrics['f1']:.4f}")
        print(f"Val   | Acc: {val_metrics['accuracy']:.4f} | Prec: {val_metrics['precision']:.4f} | Rec: {val_metrics['recall']:.4f} | F1: {val_metrics['f1']:.4f}")
        
        # Save best checkpoint based on Validation F1 score
        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            torch.save(model.state_dict(), best_model_path)
            print(f"[+] Saved new best model checkpoint (Val F1: {best_f1:.4f})")

    return model

def main():
    set_seed(RANDOM_SEED)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    train_ds, val_ds, test_ds = load_training_dataset()
    text_col, label_col, label_names = find_dataset_columns(train_ds)
    num_classes = len(label_names)
    
    mapping = {"dataset": DATASET_NAME, "num_classes": num_classes, "id_to_label": {str(k): v for k, v in enumerate(label_names)}}
    with open(os.path.join(OUTPUT_DIR, "event_label_mapping.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=4, ensure_ascii=False)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_ds, val_ds, test_ds = tokenize_dataset(train_ds, val_ds, test_ds, tokenizer, text_col)
    
    # DataLoaders
    train_loader = create_dataloader(train_ds, label_col, BATCH_SIZE, shuffle=True)
    train_eval_loader = create_dataloader(train_ds, label_col, BATCH_SIZE, shuffle=False)
    val_loader = create_dataloader(val_ds, label_col, BATCH_SIZE, shuffle=False)
    test_loader = create_dataloader(test_ds, label_col, BATCH_SIZE, shuffle=False)

    model = load_existing_model(num_event_classes=num_classes)

    train_event_classifier(model, train_loader, train_eval_loader, val_loader, label_col, label_names)
    
    # Load best checkpoint (saved based on validation performance)
    best_model_path = os.path.join(OUTPUT_DIR, "best_model.pt")
    model.load_state_dict(torch.load(best_model_path, map_location=DEVICE))
    model.to(DEVICE)
    
    # Final evaluation on Train and Test sets
    final_train_metrics = evaluate_model(model, train_eval_loader, label_col)
    final_test_metrics = evaluate_model(model, test_loader, label_col)
    
    print("\n================ FINAL TRAIN METRICS ================")
    print({k: v for k, v in final_train_metrics.items() if k not in ["labels", "predictions"]})
    
    print("\n================ FINAL TEST METRICS ================")
    print({k: v for k, v in final_test_metrics.items() if k not in ["labels", "predictions"]})
    
    print("\n================ TRAIN CLASSIFICATION REPORT ================\n", 
          classification_report(final_train_metrics["labels"], final_train_metrics["predictions"], target_names=label_names, zero_division=0))

    print("\n================ TEST CLASSIFICATION REPORT ================\n", 
          classification_report(final_test_metrics["labels"], final_test_metrics["predictions"], target_names=label_names, zero_division=0))

    # Save metrics to JSON
    metrics_out = {
        "train": {f"{k}_macro" if k != "accuracy" else k: v for k, v in final_train_metrics.items() if k not in ["labels", "predictions"]},
        "test": {f"{k}_macro" if k != "accuracy" else k: v for k, v in final_test_metrics.items() if k not in ["labels", "predictions"]}
    }
    with open(os.path.join(OUTPUT_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics_out, f, indent=4)

    torch.save(model.state_dict(), os.path.join(OUTPUT_DIR, "multitask_finbert_event_classifier.pt"))
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"\n[+] Training complete. Final artifacts saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()