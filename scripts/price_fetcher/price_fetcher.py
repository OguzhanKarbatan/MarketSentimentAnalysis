import yfinance as yf
import pandas as pd
import os

def download_market_data():
    # Çekmek istediğimiz varlıklar ve Yahoo Finance sembolleri
    assets = {
        'Gold': 'GC=F',       # Altın Ons (Vadeli)
        'Silver': 'SI=F',     # Gümüş Ons
        'USD_TRY': 'USDTRY=X' # Dolar/TL Kuru
    }
    
    print("--- Veriler Çekiliyor... ---")
    
    # 2023 başından bugüne kadar olan veriyi çekiyoruz
    # 'auto_adjust=True' fiyatları temettü vb. için düzeltir
    data = yf.download(list(assets.values()), start='2023-01-01', auto_adjust=True)
    
    # Bize sadece Kapanış (Close) fiyatları lazım
    prices = data['Close']
    
    # Sembol isimlerini (GC=F vb.) bizim anlayacağımız isimlere (Gold vb.) çevirelim
    inv_assets = {v: k for k, v in assets.items()}
    prices = prices.rename(columns=inv_assets)
    
    # Eksik verileri (hafta sonları vb.) temizleyelim
    prices = prices.dropna()
    
    # Veriyi kaydetmeden önce terminalde bir önizleme görelim
    print("\nVerinin ilk 5 satırı:")
    print(prices.head())
    
  # scripts/price_fetcher/price_fetcher.py içindeki ilgili kısmı şöyle değiştir:

# Dosyanın bulunduğu klasörü bul (price_fetcher klasörü)
    current_dir = os.path.dirname(os.path.abspath(__file__))

# 2 kat yukarı çık (scripts ve sonra MarketSentimentAnalysis) ve data klasörüne gir
    output_path = os.path.join(current_dir, '..', '..', 'data', 'market_prices.csv')

# Şimdi kaydet
    prices.to_csv(output_path)
    
    print(f"\n✅ Başarılı! Veriler 'data/market_prices.csv' olarak kaydedildi.")

if __name__ == "__main__":
    download_market_data()