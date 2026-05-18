import sys
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import MinMaxScaler
from sqlalchemy import create_engine
from pathlib import Path
from dotenv import load_dotenv
import pickle
import os

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

LOOKBACK   = 60
BATCH_SIZE = 32
EPOCHS     = 100
LR         = 0.001
PATIENCE   = 15   # early stopping: bu kadar epoch iyileşme olmazsa dur

QUANTILES = [0.1, 0.5, 0.9]

FEATURES = [
    'xau_change_pct',
    'xag_close',
    'dxy_close',
    'dxy_change_pct',
    'eur_usd_close',
    'usd_try_close',
    'sentiment_avg',
    'sentiment_std',
    'bullish_ratio',
    'tweet_count',
    'rsi',
    'macd',
    'macd_signal',
    'bb_position',
    'ma7',
    'ma20',
]


def get_engine():
    host     = os.getenv("DB_HOST", "localhost")
    port     = os.getenv("DB_PORT", "5432")
    dbname   = os.getenv("DB_NAME", "findb")
    user     = os.getenv("DB_USER", "finuser")
    password = os.getenv("DB_PASSWORD", "finpass123")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}")


def load_data() -> pd.DataFrame:
    engine = get_engine()
    df = pd.read_sql("""
        SELECT date, xau_close, xau_change_pct, xag_close,
               dxy_close, dxy_change_pct, eur_usd_close, usd_try_close,
               sentiment_avg, sentiment_std, bullish_ratio, tweet_count,
               rsi, macd, macd_signal, bb_position, ma7, ma20
        FROM daily_features
        ORDER BY date ASC
    """, engine)
    df['date'] = pd.to_datetime(df['date'])
    df = df.fillna(0)
    print(f"Yuklenen veri: {len(df)} gun, {df['date'].min().date()} -- {df['date'].max().date()}")
    return df


def add_target(df: pd.DataFrame) -> pd.DataFrame:
    df['target'] = df['xau_change_pct'].shift(-1)
    df = df.dropna()
    return df


def normalize(df: pd.DataFrame):
    scaler = MinMaxScaler()
    df[FEATURES] = scaler.fit_transform(df[FEATURES])
    return df, scaler


def create_sequences(df: pd.DataFrame):
    X, y = [], []
    values  = df[FEATURES].values
    targets = df['target'].values
    for i in range(LOOKBACK, len(df)):
        X.append(values[i - LOOKBACK:i])
        y.append(targets[i])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


class TweetDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.tensor(X)
        self.y = torch.tensor(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


class Attention(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.attn = nn.Linear(hidden_size, 1)

    def forward(self, lstm_out):
        # lstm_out: (batch, seq_len, hidden)
        # Her zaman adımına bir skor ver, softmax ile ağırlığa çevir
        scores  = self.attn(lstm_out).squeeze(-1)          # (batch, seq_len)
        weights = torch.softmax(scores, dim=1).unsqueeze(-1) # (batch, seq_len, 1)
        # Ağırlıklı ortalama — önemli günlere daha fazla odaklan
        context = (lstm_out * weights).sum(dim=1)          # (batch, hidden)
        return context, weights.squeeze(-1)


class LSTMModel(nn.Module):
    def __init__(self, input_size, hidden_size=128, num_layers=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout
        )
        self.attention = Attention(hidden_size)
        self.bn = nn.BatchNorm1d(hidden_size)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, len(QUANTILES))
        )

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        context, _  = self.attention(lstm_out)
        context     = self.bn(context)
        return self.fc(context)


def quantile_loss(preds, target, quantiles):
    loss = 0
    for i, q in enumerate(quantiles):
        err = target - preds[:, i]
        loss += torch.mean(torch.max(q * err, (q - 1) * err))
    return loss


def train_epoch(model, loader, optimizer, device):
    model.train()
    total_loss = 0
    for X_batch, y_batch in loader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        pred = model(X_batch)
        loss = quantile_loss(pred, y_batch, QUANTILES)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)


def evaluate(model, loader, device):
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for X_batch, y_batch in loader:
            X_batch = X_batch.to(device)
            pred = model(X_batch).cpu().numpy()
            all_preds.extend(pred.tolist())
            all_labels.extend(y_batch.numpy().tolist())
    return np.array(all_preds), np.array(all_labels)


def run():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Cihaz: {device}")

    df = load_data()
    df = add_target(df)
    df, scaler = normalize(df)
    X, y = create_sequences(df)

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    print(f"Egitim: {len(X_train)} ornek | Test: {len(X_test)} ornek")

    train_loader = DataLoader(TweetDataset(X_train, y_train), batch_size=BATCH_SIZE, shuffle=True)
    test_loader  = DataLoader(TweetDataset(X_test, y_test),  batch_size=BATCH_SIZE)

    model     = LSTMModel(input_size=len(FEATURES)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

    print(f"\n{EPOCHS} epoch egitiliyor (early stopping: {PATIENCE} epoch)...\n")
    best_loss    = float('inf')
    no_improve   = 0

    for epoch in range(1, EPOCHS + 1):
        loss = train_epoch(model, train_loader, optimizer, device)
        preds, labels = evaluate(model, test_loader, device)
        mae = np.mean(np.abs(preds[:, 1] - labels))
        scheduler.step(loss)

        if epoch % 5 == 0:
            print(f"Epoch {epoch:3d} | Loss: {loss:.4f} | MAE: {mae:.4f}%")

        if loss < best_loss:
            best_loss  = loss
            no_improve = 0
            torch.save(model.state_dict(), MODEL_DIR / "lstm_best.pt")
        else:
            no_improve += 1
            if no_improve >= PATIENCE:
                print(f"\nEarly stopping: {epoch}. epoch'ta duruldu.")
                break

    model.load_state_dict(torch.load(MODEL_DIR / "lstm_best.pt"))
    preds, labels = evaluate(model, test_loader, device)

    mae      = np.mean(np.abs(preds[:, 1] - labels))
    coverage = np.mean((labels >= preds[:, 0]) & (labels <= preds[:, 2]))

    print(f"\n--- SONUCLAR ---")
    print(f"Merkez tahmin MAE : {mae:.4f}%")
    print(f"Aralik coverage   : {coverage:.2%}")
    print(f"\nOrnek tahminler (son 5 gun):")
    for i in range(-5, 0):
        print(f"  Gercek: {labels[i]:+.2f}%  |  Tahmin: [{preds[i,0]:+.2f}%, {preds[i,1]:+.2f}%, {preds[i,2]:+.2f}%]")

    with open(MODEL_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    print(f"\nModel kaydedildi: {MODEL_DIR / 'lstm_best.pt'}")


if __name__ == "__main__":
    run()
