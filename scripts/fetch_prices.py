import sys
import yfinance as yf
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from data.database import insert_price

ASSETS = {
    'XAU':     'GC=F',
    'XAG':     'SI=F',
    'USD_TRY': 'USDTRY=X',
    'DXY':     'DX-Y.NYB',
    'EUR_USD': 'EURUSD=X',
}

def download_and_store():
    print("Veriler cekiliyor...")
    data = yf.download(list(ASSETS.values()), start='2023-01-01', auto_adjust=True)
    prices = data['Close'].rename(columns={v: k for k, v in ASSETS.items()})
    prices = prices.dropna()

    total = 0
    for asset in ASSETS:
        series = prices[asset]
        pct = series.pct_change() * 100
        for date, close in series.items():
            insert_price({
                'date':       str(date.date()),
                'asset':      asset,
                'open':       None,
                'high':       None,
                'low':        None,
                'close':      float(close),
                'volume':     None,
                'change_pct': None if pd.isna(pct[date]) else round(float(pct[date]), 4),
            })
            total += 1

    print(f"DB'ye yazildi: {total} satir")

if __name__ == "__main__":
    download_and_store()
