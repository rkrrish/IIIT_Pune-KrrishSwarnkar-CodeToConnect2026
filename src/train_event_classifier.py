import os
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from transformers import get_linear_schedule_with_warmup, AutoTokenizer
from risk_engine import MultiTaskFinBERT, EVENT_CATEGORIES

"""
DATASET REQUIREMENTS FOR TRAINING CUSTOM CLASSIFIER HEADS:
----------------------------------------------------------
To fine-tune the multi-task model, assemble a CSV or JSONL dataset with the following schema:

Required Columns:
1. `text`: String containing news headline, article excerpt, or financial filing clause.
2. `sentiment_label`: Integer (0: Positive, 1: Negative, 2: Neutral).
3. `event_label`: Integer corresponding to index in EVENT_CATEGORIES:
   [0: Geopolitical, 1: Macroeconomic, 2: Credit Event, 3: Merger/Acquisition,
    4: Product Launch, 5: Regulatory/Legal, 6: Earnings/Financial, 7: Business Operations]

Recommended Free Open-Source Datasets:
- Financial PhraseBank (for Sentiment)
- SEC EDGAR 8-K Event Dataset (for Event Classification)
- HuggingFace `financial_phrasebank` & `financial_news`
"""

class MultiTaskFinancialDataset(Dataset):
    def __init__(self, data_list, tokenizer, max_len=256):
        self.data = data_list
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        encoding = self.tokenizer(
            item["text"],
            truncation=True,
            padding="max_length",
            max_length=self.max_len,
            return_tensors="pt"
        )
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "sentiment_label": torch.tensor(item["sentiment_label"], dtype=torch.long),
            "event_label": torch.tensor(item["event_label"], dtype=torch.long)
        }


def train_multitask_finbert(
    train_data: list,
    output_dir: str = "./finbert_multitask_weights",
    epochs: int = 3,
    batch_size: int = 16,
    lr: float = 2e-5
):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[*] Training MultiTask FinBERT on device: {device}")

    tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    model = MultiTaskFinBERT(model_name="ProsusAI/finbert").to(device)

    dataset = MultiTaskFinancialDataset(train_data, tokenizer)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = len(dataloader) * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(total_steps * 0.1), num_training_steps=total_steps)

    sentiment_criterion = nn.CrossEntropyLoss()
    event_criterion = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for step, batch in enumerate(dataloader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            sentiment_labels = batch["sentiment_label"].to(device)
            event_labels = batch["event_label"].to(device)

            optimizer.zero_grad()

            sent_logits, event_logits = model(input_ids, attention_mask)

            loss_sent = sentiment_criterion(sent_logits, sentiment_labels)
            loss_event = event_criterion(event_logits, event_labels)

            # Combined multi-task loss
            loss = loss_sent + loss_event

            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()

            total_loss += loss.item()

            if (step + 1) % 10 == 0:
                print(f"Epoch [{epoch+1}/{epochs}] Step [{step+1}/{len(dataloader)}] - Loss: {loss.item():.4f}")

    os.makedirs(output_dir, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(output_dir, "multitask_finbert.pt"))
    tokenizer.save_pretrained(output_dir)
    print(f"[+] Model weights saved successfully to {output_dir}")


if __name__ == "__main__":
    mock_training_data = [
        {
            "text": "NVIDIA announces massive revenue surge driven by high demand for AI chips.",
            "sentiment_label": 0,
            "event_label": 6
        },
        {
            "text": "Federal Reserve raises interest rates by 50 basis points amidst rising inflation.",
            "sentiment_label": 1,
            "event_label": 1
        },
        {
            "text": "Regulatory authorities launch anti-trust investigation into tech giant practices.",
            "sentiment_label": 1,
            "event_label": 5
        }
    ]
    print("[*] Starting sample fine-tuning routine demonstration...")
    train_multitask_finbert(mock_training_data, epochs=1, batch_size=2)