import sys
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

PYTHON = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
LOG_FILE = BASE_DIR / "logs" / "price_update.log"
LOG_FILE.parent.mkdir(exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(script: str, desc: str) -> bool:
    log(f"Basliyor: {desc}")
    result = subprocess.run(
        [PYTHON, str(BASE_DIR / "scripts" / script)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        log(f"HATA: {desc}\n{result.stderr[-500:]}")
        return False
    log(f"Tamam: {desc}")
    return True


def main():
    log("=== Saatlik fiyat guncellemesi basladi ===")
    if not run("fetch_prices.py", "Fiyat verisi"):
        log("Fiyat cekme basarisiz, build_features atlandi.")
        return
    run("build_features.py", "Daily features")
    log("=== Fiyat guncellemesi tamamlandi ===")


if __name__ == "__main__":
    main()
