import sys
import pickle
import numpy as np
import torch
import torch.nn as nn
import yfinance as yf
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, timedelta, datetime

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from data.database import get_connection
from scripts.train_model import LSTMModel, Attention, FEATURES, LOOKBACK, QUANTILES

app = FastAPI(title="Market Sentiment API")

# Uygulama başlarken model ve scaler yüklenir
MODEL_DIR = BASE_DIR / "models"
device = torch.device("cpu")

model = LSTMModel(input_size=len(FEATURES)).to(device)
model.load_state_dict(torch.load(MODEL_DIR / "lstm_best.pt", map_location=device))
model.eval()

with open(MODEL_DIR / "scaler.pkl", "rb") as f:
    scaler = pickle.load(f)


# -----------------------------------------------------------
# Ortak: son LOOKBACK günlük feature'ları DB'den çek
# accounts filtresi varsa sadece o hesapların sentimenti alınır
# -----------------------------------------------------------
def get_recent_features(accounts: Optional[List[str]] = None) -> np.ndarray:
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Son LOOKBACK günlük fiyat + teknik göstergeler
            cur.execute("""
                SELECT date, xau_change_pct, xag_close, dxy_close, dxy_change_pct,
                       eur_usd_close, usd_try_close,
                       rsi, macd, macd_signal, bb_position, ma7, ma20
                FROM daily_features
                ORDER BY date DESC
                LIMIT %s
            """, (LOOKBACK,))
            rows = cur.fetchall()

    if len(rows) < LOOKBACK:
        raise HTTPException(status_code=503, detail="Yeterli veri yok.")

    rows = list(reversed(rows))  # eskiden yeniye sırala

    result = []
    for row in rows:
        gun = row[0]

        # Sentiment — hesap filtresi varsa sadece onların verisi
        with get_connection() as conn:
            with conn.cursor() as cur:
                if accounts:
                    cur.execute("""
                        SELECT AVG(sentiment_score), STDDEV(sentiment_score),
                               COUNT(*),
                               SUM(CASE WHEN label='bullish' THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*),0)
                        FROM sentiments
                        WHERE timestamp::date = %s AND expert_id = ANY(%s)
                    """, (gun, accounts))
                else:
                    cur.execute("""
                        SELECT AVG(sentiment_score), STDDEV(sentiment_score),
                               COUNT(*),
                               SUM(CASE WHEN label='bullish' THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*),0)
                        FROM sentiments
                        WHERE timestamp::date = %s
                    """, (gun,))
                s = cur.fetchone()

        sentiment_avg   = float(s[0]) if s[0] else 0.0
        sentiment_std   = float(s[1]) if s[1] else 0.0
        tweet_count     = float(s[2]) if s[2] else 0.0
        bullish_ratio   = float(s[3]) if s[3] else 0.0

        feature_row = [
            row[1] or 0,   # xau_change_pct
            row[2] or 0,   # xag_close
            row[3] or 0,   # dxy_close
            row[4] or 0,   # dxy_change_pct
            row[5] or 0,   # eur_usd_close
            row[6] or 0,   # usd_try_close
            sentiment_avg,
            sentiment_std,
            bullish_ratio,
            tweet_count,
            row[7] or 0,   # rsi
            row[8] or 0,   # macd
            row[9] or 0,   # macd_signal
            row[10] or 0,  # bb_position
            row[11] or 0,  # ma7
            row[12] or 0,  # ma20
        ]
        result.append(feature_row)

    arr = np.array(result, dtype=np.float32)
    arr = scaler.transform(arr)
    return arr


def predict(features: np.ndarray) -> dict:
    x = torch.tensor(features).unsqueeze(0).to(device)
    with torch.no_grad():
        out = model(x).cpu().numpy()[0]
    return {
        "alt":    round(float(out[0]), 2),
        "merkez": round(float(out[1]), 2),
        "ust":    round(float(out[2]), 2),
    }


# -----------------------------------------------------------
# ENDPOINT 1: Acemi modu — tüm hesaplarla tahmin
# -----------------------------------------------------------
@app.get("/predict")
def predict_default():
    features = get_recent_features()
    result   = predict(features)
    return {
        "asset": "XAU",
        "tarih": str(date.today()),
        "tahmin": result,
        "yorum": f"Altın yarın %{result['alt']} ile %{result['ust']} arasında değişmesi bekleniyor (merkez: %{result['merkez']:+.2f})"
    }


# -----------------------------------------------------------
# ENDPOINT 2: Uzman modu — seçilen hesaplarla tahmin
# -----------------------------------------------------------
class ExpertRequest(BaseModel):
    accounts: List[str]

@app.post("/predict/custom")
def predict_custom(req: ExpertRequest):
    if not req.accounts:
        raise HTTPException(status_code=400, detail="En az bir hesap girin.")

    # Seçilen hesapların DB'de olup olmadığını kontrol et
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT expert_id FROM sentiments WHERE expert_id = ANY(%s)", (req.accounts,))
            bulunan = [r[0] for r in cur.fetchall()]

    if not bulunan:
        raise HTTPException(status_code=404, detail="Seçilen hesaplara ait veri bulunamadı.")

    features = get_recent_features(accounts=bulunan)
    result   = predict(features)
    return {
        "asset":          "XAU",
        "tarih":          str(date.today()),
        "kullanilan_hesaplar": bulunan,
        "tahmin":         result,
        "yorum": f"Altın yarın %{result['alt']} ile %{result['ust']} arasında değişmesi bekleniyor (merkez: %{result['merkez']:+.2f})"
    }


# -----------------------------------------------------------
# ENDPOINT 3: Mevcut hesap listesi
# -----------------------------------------------------------
@app.get("/accounts")
def list_accounts():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT expert_id FROM sentiments ORDER BY expert_id")
            accounts = [r[0] for r in cur.fetchall()]
    return {"accounts": accounts}


@app.get("/prices/live")
def live_prices():
    try:
        tickers = yf.download(["GC=F", "SI=F"], period="1d", interval="1m", auto_adjust=True, progress=False)
        close = tickers["Close"].iloc[-1]
        xau = round(float(close["GC=F"]), 2)
        xag = round(float(close["SI=F"]), 2)
        return {
            "guncelleme": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "XAU": {"fiyat": xau, "birim": "USD/oz"},
            "XAG": {"fiyat": xag, "birim": "USD/oz"},
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Fiyat alinamadi: {str(e)}")


@app.get("/health")
def health():
    return {"status": "ok"}
