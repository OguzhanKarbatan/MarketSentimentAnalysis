import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "findb"),
    "user":     os.getenv("DB_USER", "finuser"),
    "password": os.getenv("DB_PASSWORD", "finpass123"),
}

@contextmanager
def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS tweets (
                id            SERIAL PRIMARY KEY,
                tweet_id      TEXT UNIQUE NOT NULL,
                expert_id     TEXT NOT NULL,
                timestamp     TIMESTAMPTZ NOT NULL,
                text          TEXT NOT NULL,
                lang          TEXT DEFAULT 'en',
                image_urls    JSONB,
                asset         TEXT,
                processed     BOOLEAN DEFAULT FALSE,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS sentiments (
                id              SERIAL PRIMARY KEY,
                tweet_id        TEXT NOT NULL REFERENCES tweets(tweet_id),
                expert_id       TEXT NOT NULL,
                asset           TEXT NOT NULL,
                timestamp       TIMESTAMPTZ NOT NULL,
                sentiment_score FLOAT NOT NULL,
                label           TEXT NOT NULL,
                raw_positive    FLOAT,
                raw_negative    FLOAT,
                raw_neutral     FLOAT,
                model           TEXT DEFAULT 'finbert',
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS prices (
                id          SERIAL PRIMARY KEY,
                date        DATE NOT NULL,
                asset       TEXT NOT NULL,
                open        FLOAT,
                high        FLOAT,
                low         FLOAT,
                close       FLOAT NOT NULL,
                volume      FLOAT,
                change_pct  FLOAT,
                UNIQUE(date, asset)
            );

            CREATE TABLE IF NOT EXISTS daily_features (
                id              SERIAL PRIMARY KEY,
                date            DATE UNIQUE NOT NULL,
                xau_close       FLOAT,
                xau_change_pct  FLOAT,
                xag_close       FLOAT,
                dxy_close       FLOAT,
                dxy_change_pct  FLOAT,
                eur_usd_close   FLOAT,
                usd_try_close   FLOAT,
                sentiment_avg   FLOAT,
                sentiment_std   FLOAT,
                bullish_ratio   FLOAT,
                tweet_count     INTEGER,
                expert_count    INTEGER,
                rsi             FLOAT,
                macd            FLOAT,
                macd_signal     FLOAT,
                bb_position     FLOAT,
                ma7             FLOAT,
                ma20            FLOAT,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_tweets_expert
                ON tweets(expert_id);
            CREATE INDEX IF NOT EXISTS idx_tweets_processed
                ON tweets(processed) WHERE processed = FALSE;
            CREATE INDEX IF NOT EXISTS idx_sentiments_timestamp
                ON sentiments(timestamp);
            CREATE INDEX IF NOT EXISTS idx_prices_date
                ON prices(date, asset);
            CREATE INDEX IF NOT EXISTS idx_features_date
                ON daily_features(date);
            """)
    print("PostgreSQL DB hazır.")

def insert_tweet(tweet: dict) -> bool:
    sql = """
        INSERT INTO tweets
            (tweet_id, expert_id, timestamp, text, lang, image_urls, asset)
        VALUES
            (%(tweet_id)s, %(expert_id)s, %(timestamp)s, %(text)s,
             %(lang)s, %(image_urls)s, %(asset)s)
        ON CONFLICT (tweet_id) DO NOTHING
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tweet)
            return cur.rowcount > 0

def insert_sentiment(s: dict):
    sql = """
        INSERT INTO sentiments
            (tweet_id, expert_id, asset, timestamp, sentiment_score,
             label, raw_positive, raw_negative, raw_neutral, model)
        VALUES
            (%(tweet_id)s, %(expert_id)s, %(asset)s, %(timestamp)s,
             %(sentiment_score)s, %(label)s, %(raw_positive)s,
             %(raw_negative)s, %(raw_neutral)s, %(model)s)
        ON CONFLICT DO NOTHING
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, s)
            cur.execute(
                "UPDATE tweets SET processed=TRUE WHERE tweet_id=%s",
                (s["tweet_id"],)
            )

def insert_price(p: dict):
    sql = """
        INSERT INTO prices (date, asset, open, high, low, close, volume, change_pct)
        VALUES (%(date)s, %(asset)s, %(open)s, %(high)s, %(low)s,
                %(close)s, %(volume)s, %(change_pct)s)
        ON CONFLICT (date, asset) DO UPDATE SET
            close      = EXCLUDED.close,
            change_pct = EXCLUDED.change_pct
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, p)

def upsert_daily_features(f: dict):
    sql = """
        INSERT INTO daily_features
            (date, xau_close, xau_change_pct, xag_close, dxy_close,
             dxy_change_pct, eur_usd_close, usd_try_close,
             sentiment_avg, sentiment_std, bullish_ratio,
             tweet_count, expert_count,
             rsi, macd, macd_signal, bb_position, ma7, ma20)
        VALUES
            (%(date)s, %(xau_close)s, %(xau_change_pct)s, %(xag_close)s,
             %(dxy_close)s, %(dxy_change_pct)s, %(eur_usd_close)s,
             %(usd_try_close)s, %(sentiment_avg)s, %(sentiment_std)s,
             %(bullish_ratio)s, %(tweet_count)s, %(expert_count)s,
             %(rsi)s, %(macd)s, %(macd_signal)s, %(bb_position)s, %(ma7)s, %(ma20)s)
        ON CONFLICT (date) DO UPDATE SET
            sentiment_avg  = EXCLUDED.sentiment_avg,
            sentiment_std  = EXCLUDED.sentiment_std,
            bullish_ratio  = EXCLUDED.bullish_ratio,
            tweet_count    = EXCLUDED.tweet_count,
            expert_count   = EXCLUDED.expert_count,
            rsi            = EXCLUDED.rsi,
            macd           = EXCLUDED.macd,
            macd_signal    = EXCLUDED.macd_signal,
            bb_position    = EXCLUDED.bb_position,
            ma7            = EXCLUDED.ma7,
            ma20           = EXCLUDED.ma20
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, f)

def get_unprocessed_tweets(limit: int = 50) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM tweets
                WHERE processed = FALSE
                ORDER BY timestamp ASC
                LIMIT %s
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]

def get_daily_sentiments(date: str) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM sentiments
                WHERE timestamp::date = %s
            """, (date,))
            return [dict(r) for r in cur.fetchall()]

def get_features_for_lstm(days: int = 60) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM daily_features
                ORDER BY date DESC
                LIMIT %s
            """, (days,))
            rows = cur.fetchall()
            return [dict(r) for r in reversed(rows)]

def reset_tweets_and_sentiments():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE sentiments RESTART IDENTITY CASCADE")
            cur.execute("TRUNCATE TABLE tweets RESTART IDENTITY CASCADE")
    print("tweets ve sentiments tabloları temizlendi.")

if __name__ == "__main__":
    init_db()
