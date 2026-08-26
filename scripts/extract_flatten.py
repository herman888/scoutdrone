"""Extract a zip and flatten all .jpg files it contains into a target dir,
regardless of internal folder structure. Used for CrowdHuman zips whose
internal layout isn't known in advance."""
import sys
import zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
dest_dir = Path(sys.argv[2])
dest_dir.mkdir(parents=True, exist_ok=True)

n = 0
with zipfile.ZipFile(zip_path) as zf:
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".jpg"):
            continue
        name = Path(info.filename).name
        target = dest_dir / name
        if target.exists():
            continue
        with zf.open(info) as src, open(target, "wb") as dst:
            dst.write(src.read())
        n += 1

print(f"extracted {n} jpg files from {zip_path.name} -> {dest_dir}")
