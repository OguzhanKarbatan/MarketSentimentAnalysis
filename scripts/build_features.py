import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, timedelta

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from data.database import get_connection, upsert_daily_features


def compute_indicators(conn) -> dict:
    """XAU fiyat serisinden teknik göstergeleri hesapla, {date: {rsi, macd, ...}} döndür."""
    with conn.cursor() as cur:
        cur.execute("SELECT date, close FROM prices WHERE asset = 'XAU' ORDER BY date ASC")
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=['date', 'close'])
    df = df.set_index('date').sort_index()
    close = df['close']

    # RSI (14 günlük)
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema12       = close.ewm(span=12, adjust=False).mean()
    ema26       = close.ewm(span=26, adjust=False).mean()
    macd        = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()

    # Bollinger Bands (20 günlük)
    ma20    = close.rolling(20).mean()
    std20   = close.rolling(20).std()
    bb_up   = ma20 + 2 * std20
    bb_low  = ma20 - 2 * std20
    bb_pos  = (close - bb_low) / (bb_up - bb_low).replace(0, np.nan)

    # Hareketli ortalamalar
    ma7 = close.rolling(7).mean()

    result = {}
    for d in df.index:
        result[d] = {
            'rsi':         None if pd.isna(rsi.get(d))         else round(float(rsi[d]), 4),
            'macd':        None if pd.isna(macd.get(d))        else round(float(macd[d]), 4),
            'macd_signal': None if pd.isna(macd_signal.get(d)) else round(float(macd_signal[d]), 4),
            'bb_position': None if pd.isna(bb_pos.get(d))      else round(float(bb_pos[d]), 4),
            'ma7':         None if pd.isna(ma7.get(d))         else round(float(ma7[d]), 4),
            'ma20':        None if pd.isna(ma20.get(d))        else round(float(ma20[d]), 4),
        }
    return result


def build_features(start_date: date = None, end_date: date = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if not start_date or not end_date:
                cur.execute("SELECT MIN(date), MAX(date) FROM prices")
                start_date, end_date = cur.fetchone()

        print(f"{start_date} -- {end_date} arasi isleniyor...")
        print("Teknik gostergeler hesaplaniyor...")
        indicators = compute_indicators(conn)

        with conn.cursor() as cur:
            current = start_date
            islenen = 0
            atlanan = 0

            while current <= end_date:
                cur.execute("""
                    SELECT asset, close, change_pct
                    FROM prices WHERE date = %s
                """, (current,))
                fiyatlar = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

                if 'XAU' not in fiyatlar:
                    current += timedelta(days=1)
                    atlanan += 1
                    continue

                cur.execute("""
                    SELECT
                        AVG(sentiment_score),
                        STDDEV(sentiment_score),
                        COUNT(*),
                        COUNT(DISTINCT expert_id),
                        SUM(CASE WHEN label = 'bullish' THEN 1 ELSE 0 END)::float / COUNT(*)
                    FROM sentiments
                    WHERE timestamp::date = %s
                """, (current,))
                s = cur.fetchone()

                ind = indicators.get(current, {})

                xau_close, xau_change = fiyatlar.get('XAU', (None, None))
                xag_close, _          = fiyatlar.get('XAG', (None, None))
                dxy_close, dxy_change = fiyatlar.get('DXY', (None, None))
                eur_usd_close, _      = fiyatlar.get('EUR_USD', (None, None))
                usd_try_close, _      = fiyatlar.get('USD_TRY', (None, None))

                upsert_daily_features({
                    'date':           current,
                    'xau_close':      xau_close,
                    'xau_change_pct': xau_change,
                    'xag_close':      xag_close,
                    'dxy_close':      dxy_close,
                    'dxy_change_pct': dxy_change,
                    'eur_usd_close':  eur_usd_close,
                    'usd_try_close':  usd_try_close,
                    'sentiment_avg':  round(float(s[0]), 4) if s[0] else 0.0,
                    'sentiment_std':  round(float(s[1]), 4) if s[1] else 0.0,
                    'tweet_count':    s[2] or 0,
                    'expert_count':   s[3] or 0,
                    'bullish_ratio':  round(float(s[4]), 4) if s[4] else 0.0,
                    'rsi':            ind.get('rsi'),
                    'macd':           ind.get('macd'),
                    'macd_signal':    ind.get('macd_signal'),
                    'bb_position':    ind.get('bb_position'),
                    'ma7':            ind.get('ma7'),
                    'ma20':           ind.get('ma20'),
                })

                islenen += 1
                if islenen % 50 == 0:
                    print(f"  {current} islendi ({islenen} gun tamamlandi)...")

                current += timedelta(days=1)

    print(f"\nTamamlandi: {islenen} gun islendi, {atlanan} gun atlandi.")


if __name__ == "__main__":
    build_features()
