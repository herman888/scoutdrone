"""Build a mixed close-range + aerial person dataset for full 1-40m coverage.

Converts CrowdHuman (ODGT format, close/medium range) to YOLO single-class
labels, then writes explicit train/val image-list .txt files combining
CrowdHuman with the existing VisDrone-derived person data. Using list files
(rather than directory paths) sidesteps Ultralytics' images<->labels path
substitution entirely — each listed image path gets resolved independently,
no reliance on directory/junction structure.
"""
import json
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks")
CH_RAW = ROOT / "data" / "raw" / "CrowdHuman"
CH_IMAGES = CH_RAW / "images"
CH_LABELS = CH_RAW / "labels"
VISDRONE_TRAIN_IMAGES = ROOT / "data" / "raw" / "VisDrone" / "VisDrone2019-DET-train" / "images"
VISDRONE_VAL_IMAGES = ROOT / "data" / "raw" / "VisDrone" / "VisDrone2019-DET-val" / "images"
OUT = ROOT / "data" / "mixed"


def convert_crowdhuman_split(odgt_path):
    """Write YOLO labels for every image referenced in this odgt file.
    Returns list of image IDs successfully converted (has image + >=0 boxes)."""
    CH_LABELS.mkdir(parents=True, exist_ok=True)
    ids = []
    n_boxes = 0
    n_missing = 0
    with open(odgt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            img_id = rec["ID"]
            img_path = CH_IMAGES / f"{img_id}.jpg"
            if not img_path.exists():
                n_missing += 1
                continue
            try:
                w, h = Image.open(img_path).size
            except Exception:
                n_missing += 1
                continue

            lines = []
            for box in rec.get("gtboxes", []):
                if box.get("tag") != "person":
                    continue
                if box.get("extra", {}).get("ignore", 0) == 1:
                    continue
                x, y, bw, bh = box["fbox"]
                if bw <= 0 or bh <= 0:
                    continue
                x = max(0, x)
                y = max(0, y)
                bw = min(bw, w - x)
                bh = min(bh, h - y)
                if bw <= 0 or bh <= 0:
                    continue
                cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
                nw, nh = bw / w, bh / h
                lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            (CH_LABELS / f"{img_id}.txt").write_text("\n".join(lines))
            ids.append(img_id)
            n_boxes += len(lines)

    print(f"  {len(ids)} images converted, {n_boxes} boxes, {n_missing} missing/unreadable")
    return ids


def write_list(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(str(e) for e in entries))
    print(f"  wrote {len(entries)} lines -> {path}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("=== Converting CrowdHuman train (odgt -> YOLO labels) ===")
    ch_train_ids = convert_crowdhuman_split(CH_RAW / "annotation_train.odgt")
    print("=== Converting CrowdHuman val (odgt -> YOLO labels) ===")
    ch_val_ids = convert_crowdhuman_split(CH_RAW / "annotation_val.odgt")

    if not ch_train_ids or not ch_val_ids:
        print("ERROR: CrowdHuman conversion produced zero images for train or val. Aborting.")
        sys.exit(1)

    print("=== Writing image list files ===")
    write_list(OUT / "crowdhuman_train.txt", [CH_IMAGES / f"{i}.jpg" for i in ch_train_ids])
    write_list(OUT / "crowdhuman_val.txt", [CH_IMAGES / f"{i}.jpg" for i in ch_val_ids])

    visdrone_train_imgs = sorted(VISDRONE_TRAIN_IMAGES.glob("*.jpg"))
    visdrone_val_imgs = sorted(VISDRONE_VAL_IMAGES.glob("*.jpg"))
    if not visdrone_train_imgs or not visdrone_val_imgs:
        print("ERROR: VisDrone image lists are empty. Aborting.")
        sys.exit(1)
    write_list(OUT / "visdrone_train.txt", visdrone_train_imgs)
    write_list(OUT / "visdrone_val.txt", visdrone_val_imgs)

    yaml_content = f"""path: {OUT}
train:
  - visdrone_train.txt
  - crowdhuman_train.txt
val:
  - visdrone_val.txt
  - crowdhuman_val.txt
names:
  0: person
"""
    (OUT / "person_mixed.yaml").write_text(yaml_content)
    print(f"=== Wrote {OUT / 'person_mixed.yaml'} ===")
    print("DATASET BUILD COMPLETE")


if __name__ == "__main__":
    main()
