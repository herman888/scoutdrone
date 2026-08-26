"""
Download VisDrone2019-DET (train/val/test-dev) directly from Ultralytics' GitHub
release assets. No Kaggle account/API key needed — Kaggle re-uploads of VisDrone
are inconsistent and unverified; this is the same source ultralytics' own
VisDrone.yaml downloads from.
"""
import zipfile
from pathlib import Path

import requests

ASSETS_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0"
OUT = Path(r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\data\raw\VisDrone")
OUT.mkdir(parents=True, exist_ok=True)

SPLITS = ["train", "val", "test-dev"]


def download(url, dest):
    if dest.exists():
        print(f"  already downloaded: {dest.name}")
        return
    print(f"  GET {url}")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                pct = 100 * done / total if total else 0
                print(f"\r  {done / 1e6:8.1f} MB / {total / 1e6:8.1f} MB ({pct:5.1f}%)", end="", flush=True)
        print()
        tmp.rename(dest)


def extract(zip_path, dest_dir):
    if dest_dir.exists() and any(dest_dir.iterdir()):
        print(f"  already extracted: {dest_dir.name}")
        return
    print(f"  extracting {zip_path.name} ...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(OUT)


def main():
    for split in SPLITS:
        name = f"VisDrone2019-DET-{split}"
        zip_path = OUT / f"{name}.zip"
        print(f"\n{name}")
        download(f"{ASSETS_URL}/{name}.zip", zip_path)
        extract(zip_path, OUT / name)

    print("\nDone. Raw data in", OUT)


if __name__ == "__main__":
    main()
