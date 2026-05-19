import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from scripts.train_model import load_data, add_target, normalize, create_sequences, FEATURES, LOOKBACK

print("Veri yukleniyor...")
df = load_data()
df = add_target(df)
df, scaler = normalize(df)
X, y = create_sequences(df)

split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

print(f"Test seti: {len(y_test)} gun\n")

# 1. Naive — hep 0 tahmin et (degisim yok)
naive_preds = np.zeros(len(y_test))
naive_mae = mean_absolute_error(y_test, naive_preds)

# 2. Mean — train setinin ortalamasini tahmin et
mean_pred = np.full(len(y_test), y_train.mean())
mean_mae = mean_absolute_error(y_test, mean_pred)

# 3. Linear Regression — son gun feature'larini kullan
X_train_flat = X_train[:, -1, :]  # son gunu al
X_test_flat  = X_test[:, -1, :]
lr = LinearRegression()
lr.fit(X_train_flat, y_train)
lr_preds = lr.predict(X_test_flat)
lr_mae = mean_absolute_error(y_test, lr_preds)

lstm_mae = 1.3983

print("=" * 45)
print(f"{'Model':<25} {'MAE':>10} {'LSTM'}")
print("-" * 45)
print(f"{'Naive (degisim=0)':<25} {naive_mae:>9.4f}%")
print(f"{'Mean (sabit ortalama)':<25} {mean_mae:>9.4f}%")
print(f"{'Linear Regression':<25} {lr_mae:>9.4f}%")
print(f"{'LSTM + Attention':<25} {lstm_mae:>9.4f}%  <--")
print("=" * 45)

print(f"\nLSTM, Naive'e gore %{((naive_mae - lstm_mae) / naive_mae * 100):.1f} daha iyi")
print(f"LSTM, Linear Regression'a gore %{((lr_mae - lstm_mae) / lr_mae * 100):.1f} daha iyi")
