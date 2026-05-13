import asyncio
import os
import sys
import json
import uuid
import requests
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(r"C:\MarketSentimentAnalysis")
IMAGE_DIR = BASE_DIR / "data" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE_DIR))
from data.database import insert_tweet, get_connection

win_user = os.getlogin()
USER_DATA_DIR = f"C:\\Users\\{win_user}\\AppData\\Local\\Google\\Chrome\\User Data\\Default"


def load_existing_tweet_ids() -> set:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tweet_id FROM tweets")
                return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()


async def download_image(url: str, account: str) -> str:
    if not url or url == "Yok" or "profile_images" in url:
        return None
    try:
        response = requests.get(url, stream=True, timeout=15)
        if response.status_code == 200:
            file_name = f"{account}_{uuid.uuid4().hex[:8]}.jpg"
            file_path = IMAGE_DIR / file_name
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return str(file_path)
    except Exception:
        pass
    return None


async def fetch_tweets_persistent():
    existing_ids = load_existing_tweet_ids()
    print(f"Arşiv yüklendi: {len(existing_ids)} tweet DB'de mevcut.")

    async with async_playwright() as p:
        print(f"Tarayıcı profilinle açılıyor: {win_user}")
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,
                viewport={'width': 1280, 'height': 900},
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            print(f"HATA: Chrome açık olabilir! Tüm Chrome pencerelerini kapatıp tekrar dene.\n{e}")
            return

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        await asyncio.get_event_loop().run_in_executor(
            None, input, "Giriş tamam mı? Devam etmek için ENTER'a bas..."
        )

        txt_path = BASE_DIR / "scripts" / "tweet_fetcher" / "experts.txt"
        with open(txt_path, 'r', encoding='utf-8') as f:
            experts = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        for account in experts:
            try:
                print(f"@{account} taranıyor...")
                await page.goto(f"https://x.com/{account}", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(8)

                tweets = await page.query_selector_all('article[data-testid="tweet"]')
                saved = 0

                for tweet in tweets[:12]:
                    # tweet_id — permalink'ten al
                    link_el = await tweet.query_selector('a[href*="/status/"]')
                    tweet_id = None
                    if link_el:
                        href = await link_el.get_attribute('href')
                        parts = href.split('/status/')
                        if len(parts) > 1:
                            tweet_id = parts[1].split('/')[0].split('?')[0]

                    if not tweet_id or tweet_id in existing_ids:
                        continue

                    # timestamp — <time> elementinden al
                    time_el = await tweet.query_selector('time')
                    timestamp = None
                    if time_el:
                        timestamp = await time_el.get_attribute('datetime')

                    if not timestamp:
                        continue

                    # metin
                    text_el = await tweet.query_selector('[data-testid="tweetText"]')
                    text = ""
                    if text_el:
                        text = (await text_el.inner_text()).replace('\n', ' ').strip()

                    # resim
                    img_el = await tweet.query_selector('div[data-testid="tweetPhoto"] img')
                    img_url = await img_el.get_attribute('src') if img_el else None
                    local_img = await download_image(img_url, account) if img_url else None

                    if not text and not local_img:
                        continue

                    image_urls = json.dumps([local_img]) if local_img else None

                    record = {
                        'tweet_id':  tweet_id,
                        'expert_id': account,
                        'timestamp': timestamp,
                        'text':      text if text else "[Sadece Resim/Grafik]",
                        'lang':      'tr' if any(c in text for c in 'şğüıöçŞĞÜİÖÇ') else 'en',
                        'image_urls': image_urls,
                        'asset':     None,
                    }

                    if insert_tweet(record):
                        existing_ids.add(tweet_id)
                        saved += 1
                        print(f"   Kaydedildi: {text[:50]}...")

                print(f"@{account} → {saved} yeni tweet DB'ye yazıldı.")

            except Exception as e:
                print(f"@{account} hatası: {e}")

        await context.close()
        print("\nBİTTİ! Tüm tweetler PostgreSQL'e kaydedildi.")


if __name__ == "__main__":
    asyncio.run(fetch_tweets_persistent())
