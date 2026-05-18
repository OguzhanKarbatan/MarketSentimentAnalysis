import sys
import subprocess
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

PYTHON = str(BASE_DIR / "venv" / "Scripts" / "python.exe")


def run(script: str, desc: str):
    print(f"\n--- {desc} ---")
    result = subprocess.run([PYTHON, str(BASE_DIR / "scripts" / script)], cwd=str(BASE_DIR))
    if result.returncode != 0:
        print(f"HATA: {desc} basarisiz oldu.")
        return False
    return True


def main():
    print(f"Gunluk guncelleme basliyor: {date.today()}")

    if not run("fetch_prices.py", "Fiyat verisi guncelleniyor"):
        return
    if not run("analyse_sentiment.py", "Sentiment analizi yapiliyor"):
        return
    if not run("build_features.py", "Daily features guncelleniyor"):
        return

    print(f"\nGuncelleme tamamlandi: {date.today()}")


if __name__ == "__main__":
    main()
