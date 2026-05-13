import pandas as pd
from ntscraper import Nitter
import os
import sys

def analyse_specific_user(username):
    # Sadece bu satırı değiştiriyoruz:
    scraper = Nitter(log_level=1, skip_instance_check=False)
    print(f"--- @{username} Özel Analizi Başlıyor ---")
    
    results = scraper.get_tweets(username, mode='user', number=50)
    
    if not results['tweets']:
        print("Tweet bulunamadı veya hesap gizli.")
        return

    tweets_data = [{'date': t['date'], 'text': t['text']} for t in results['tweets']]
    
    df = pd.DataFrame(tweets_data)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(current_dir, '..', '..', 'data', f'custom_{username}_tweets.csv')
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"✅ @{username} verileri 'data/custom_{username}_tweets.csv' olarak kaydedildi.")

if __name__ == "__main__":
    # Terminalden isim girilmezse varsayılan bir isim kullan
    target_user = sys.argv[1] if len(sys.argv) > 1 else "ozgurdemirtas"
    analyse_specific_user(target_user)