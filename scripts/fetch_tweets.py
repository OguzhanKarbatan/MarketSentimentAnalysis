import asyncio
import os
import sys
import json
import uuid
import random
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(r"C:\MarketSentimentAnalysis")
IMAGE_DIR = BASE_DIR / "data" / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE_DIR))
from data.database import insert_tweet, get_connection

win_user = os.getlogin()
USER_DATA_DIR = f"C:\\Users\\{win_user}\\AppData\\Local\\Google\\Chrome\\User Data\\Default"

LONG_BREAK_EVERY    = 10
LONG_BREAK_MIN      = 90
LONG_BREAK_MAX      = 150
BETWEEN_ACCOUNTS_MIN = 30
BETWEEN_ACCOUNTS_MAX = 60
SCROLL_DELAY_MIN    = 3
SCROLL_DELAY_MAX    = 7


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


async def is_rate_limited(page) -> bool:
    url = page.url
    content = await page.content()
    if "rate limit exceeded" in content.lower():
        return True
    if "this account doesn't exist" in content.lower():
        return False
    if "/error" in url:
        return True
    return False


async def wait_with_log(seconds: float, reason: str):
    print(f"   [{reason}] {seconds:.0f} saniye bekleniyor...")
    await asyncio.sleep(seconds)


def _run_sentiment(account: str):
    from scripts.analyse_sentiment import process_unprocessed
    n = process_unprocessed(label=account)
    if n:
        print(f"   Sentiment: {n} tweet analiz edildi.")


async def fetch_tweets_persistent(auto_mode: bool = False):
    existing_ids = load_existing_tweet_ids()
    print(f"Arsiv yuklendi: {len(existing_ids)} tweet DB'de mevcut.")

    async with async_playwright() as p:
        print(f"Tarayici profilinle aciliyor: {win_user}")
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,
                viewport={'width': 1280, 'height': 900},
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            print(f"HATA: Chrome acik olabilir! Tum Chrome pencerelerini kapatip tekrar dene.\n{e}")
            return

        page = context.pages[0] if context.pages else await context.new_page()

        if auto_mode:
            # Oturum kontrolu — giris yapilmamissa cik
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)
            if "login" in page.url or "i/flow" in page.url:
                print("HATA: Twitter oturumu acik degil. Once manuel modda calistir ve giris yap.")
                await context.close()
                return
            print("Oturum aktif, otomatik modda devam ediliyor.")
        else:
            await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
            await asyncio.get_event_loop().run_in_executor(
                None, input, "Giris tamam mi? Devam etmek icin ENTER'a bas..."
            )

        txt_path = BASE_DIR / "scripts" / "experts.txt"
        with open(txt_path, 'r', encoding='utf-8') as f:
            experts = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        cutoff = datetime.now(timezone.utc) - timedelta(hours=2) if auto_mode else None

        for idx, account in enumerate(experts):
            try:
                print(f"\n[{idx+1}/{len(experts)}] @{account} taraniyor...")
                await page.goto(f"https://x.com/{account}", wait_until="domcontentloaded", timeout=60000)
                await wait_with_log(random.uniform(4, 9), "sayfa yukleme")

                if await is_rate_limited(page):
                    pause = random.uniform(90, 150)
                    print(f"   !! Rate limit tespit edildi. {pause:.0f} saniye bekleniyor...")
                    await asyncio.sleep(pause)
                    await page.goto(f"https://x.com/{account}", wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(random.uniform(5, 10))

                max_scrolls = 20 if auto_mode else random.randint(25, 35)
                saved = 0
                seen_on_page = set()
                hit_cutoff = False

                for s in range(max_scrolls):
                    if hit_cutoff:
                        break
                    tweets = await page.query_selector_all('article[data-testid="tweet"]')
                    for tweet in tweets:
                        link_el = await tweet.query_selector('a[href*="/status/"]')
                        tweet_id = None
                        if link_el:
                            href = await link_el.get_attribute('href')
                            parts = href.split('/status/')
                            if len(parts) > 1:
                                tweet_id = parts[1].split('/')[0].split('?')[0]

                        if not tweet_id or tweet_id in existing_ids or tweet_id in seen_on_page:
                            continue
                        seen_on_page.add(tweet_id)

                        time_el = await tweet.query_selector('time')
                        timestamp = None
                        if time_el:
                            timestamp = await time_el.get_attribute('datetime')

                        if not timestamp:
                            continue

                        if cutoff:
                            tweet_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            if tweet_time < cutoff:
                                hit_cutoff = True
                                break

                        text_el = await tweet.query_selector('[data-testid="tweetText"]')
                        text = ""
                        if text_el:
                            text = (await text_el.inner_text()).replace('\n', ' ').strip()

                        img_els = await tweet.query_selector_all('div[data-testid="tweetPhoto"] img')
                        local_imgs = []
                        for img_el in img_els:
                            img_url = await img_el.get_attribute('src')
                            local_img = await download_image(img_url, account) if img_url else None
                            if local_img:
                                local_imgs.append(local_img)

                        if not text and not local_imgs:
                            continue

                        record = {
                            'tweet_id':   tweet_id,
                            'expert_id':  account,
                            'timestamp':  timestamp,
                            'text':       text if text else "[Sadece Resim/Grafik]",
                            'lang':       'tr' if any(c in text for c in 'sgüiocSGÜIOC') else 'en',
                            'image_urls': json.dumps(local_imgs) if local_imgs else None,
                            'asset':      None,
                        }

                        if insert_tweet(record):
                            existing_ids.add(tweet_id)
                            saved += 1
                            print(f"   Kaydedildi: {text[:60]}...")

                    scroll_px = random.randint(2000, 4000)
                    await page.evaluate(f"window.scrollBy(0, {scroll_px})")
                    await asyncio.sleep(random.uniform(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX))
                    if s > 0 and s % random.randint(5, 8) == 0:
                        await asyncio.sleep(random.uniform(8, 18))

                print(f"   @{account} -> {saved} yeni tweet kaydedildi.")

                if auto_mode and saved > 0:
                    _run_sentiment(account)

                if (idx + 1) % LONG_BREAK_EVERY == 0 and (idx + 1) < len(experts):
                    pause = random.uniform(30, 45) if auto_mode else random.uniform(LONG_BREAK_MIN, LONG_BREAK_MAX)
                    print(f"\n--- {LONG_BREAK_EVERY} hesap tamamlandi, {pause:.0f}s uzun mola ---")
                    await asyncio.sleep(pause)
                else:
                    pause = random.uniform(15, 30) if auto_mode else random.uniform(BETWEEN_ACCOUNTS_MIN, BETWEEN_ACCOUNTS_MAX)
                    await wait_with_log(pause, "sonraki hesap")

            except Exception as e:
                print(f"   @{account} hatasi: {e}")
                await asyncio.sleep(random.uniform(30, 60))

        await context.close()
        print("\nBITTI! Tum tweetler PostgreSQL'e kaydedildi.")


if __name__ == "__main__":
    auto = "--auto" in sys.argv
    asyncio.run(fetch_tweets_persistent(auto_mode=auto))
