import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from transformers import pipeline
from deep_translator import GoogleTranslator
from data.database import get_unprocessed_tweets, insert_sentiment, get_connection

finbert = None


def load_model():
    global finbert
    if finbert is None:
        print("FinBERT yukleniyor...")
        finbert = pipeline("text-classification", model="ProsusAI/finbert", top_k=3)
        print("Model hazir.")


def translate_to_english(text: str) -> str:
    try:
        return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception:
        return text


def analyse_tweet(text: str) -> dict:
    load_model()
    translated = translate_to_english(text)
    results = finbert(translated[:512])

    scores = {r['label']: r['score'] for r in results[0]}
    pos = scores.get('positive', 0)
    neg = scores.get('negative', 0)
    neu = scores.get('neutral',  0)

    sentiment_score = pos - neg

    if sentiment_score > 0.1:
        label = 'bullish'
    elif sentiment_score < -0.1:
        label = 'bearish'
    else:
        label = 'neutral'

    return {
        'sentiment_score': round(sentiment_score, 4),
        'label':           label,
        'raw_positive':    round(pos, 4),
        'raw_negative':    round(neg, 4),
        'raw_neutral':     round(neu, 4),
    }


def process_unprocessed(label: str = "") -> int:
    """Veritabanindaki tum islenmemis tweetleri analiz eder."""
    load_model()
    islenen = 0
    while True:
        tweets = get_unprocessed_tweets(limit=100)
        if not tweets:
            break
        for tweet in tweets:
            try:
                result = analyse_tweet(tweet['text'])
                insert_sentiment({
                    'tweet_id':        tweet['tweet_id'],
                    'expert_id':       tweet['expert_id'],
                    'asset':           tweet['asset'] or 'XAU',
                    'timestamp':       tweet['timestamp'],
                    'sentiment_score': result['sentiment_score'],
                    'label':           result['label'],
                    'raw_positive':    result['raw_positive'],
                    'raw_negative':    result['raw_negative'],
                    'raw_neutral':     result['raw_neutral'],
                    'model':           'finbert',
                })
                islenen += 1
                prefix = f"[{label}] " if label else ""
                print(f"  {prefix}{tweet['expert_id']}: {result['label']} ({result['sentiment_score']:+.3f})")
            except Exception as e:
                print(f"  HATA - {tweet['tweet_id']}: {e}")
    return islenen


def run():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tweets WHERE processed = FALSE")
            toplam = cur.fetchone()[0]
    print(f"Toplam islenmemis tweet: {toplam}")
    islenen = process_unprocessed()
    print(f"Tamamlandi. {islenen} tweet islendi.")


if __name__ == "__main__":
    run()
