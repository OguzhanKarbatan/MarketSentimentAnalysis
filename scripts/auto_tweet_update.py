import sys
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

PYTHON = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
LOG_FILE = BASE_DIR / "logs" / "tweet_update.log"
LOG_FILE.parent.mkdir(exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(script: str, desc: str, extra_args: list = None) -> bool:
    cmd = [PYTHON, str(BASE_DIR / "scripts" / script)] + (extra_args or [])
    log(f"Basliyor: {desc}")
    result = subprocess.run(
        cmd,
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
    log("=== 2 saatlik tweet guncellemesi basladi ===")
    if not run("fetch_tweets.py", "Tweet cekme + sentiment (auto)", extra_args=["--auto"]):
        log("Tweet pipeline basarisiz, build_features atlandi.")
        return
    run("build_features.py", "Daily features")
    log("=== Tweet guncellemesi tamamlandi ===")


if __name__ == "__main__":
    main()
