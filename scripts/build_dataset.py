"""
Convert raw VisDrone2019-DET annotations into a single-class ("person") YOLO
dataset. VisDrone category 1=pedestrian and 2=people are merged into class 0;
every other category (vehicles, etc.) is dropped entirely.

Images are NOT copied — data/merged/images/{train,val} must be NTFS junctions
pointing at the raw VisDrone image folders (created once, see bottom of this
file's docstring). Only the filtered label .txt files are written under
data/merged/labels/{train,val}, following YOLO's images/<->labels path
convention.

Junctions (run once, PowerShell, no admin needed):
    New-Item -ItemType Junction -Path data\\merged\\images\\train `
        -Target data\\raw\\VisDrone\\VisDrone2019-DET-train\\images
    New-Item -ItemType Junction -Path data\\merged\\images\\val `
        -Target data\\raw\\VisDrone\\VisDrone2019-DET-val\\images
"""
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks")
RAW = ROOT / "data" / "raw" / "VisDrone"
MERGED = ROOT / "data" / "merged"

PERSON_CATEGORIES = {1, 2}  # pedestrian, people -> single "person" class 0
SPLITS = ["train", "val"]


def convert_split(split):
    src = RAW / f"VisDrone2019-DET-{split}"
    images_dir = src / "images"
    ann_dir = src / "annotations"
    labels_dir = MERGED / "labels" / split
    labels_dir.mkdir(parents=True, exist_ok=True)

    n_images = 0
    n_boxes = 0
    n_empty = 0
    for ann_path in sorted(ann_dir.glob("*.txt")):
        img_path = images_dir / (ann_path.stem + ".jpg")
        if not img_path.exists():
            continue
        w, h = Image.open(img_path).size

        lines = []
        for row in ann_path.read_text().strip().splitlines():
            parts = row.split(",")
            score, category = parts[4], int(parts[5])
            if score == "0" or category not in PERSON_CATEGORIES:
                continue
            x, y, bw, bh = map(int, parts[:4])
            cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
            nw, nh = bw / w, bh / h
            lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        (labels_dir / ann_path.with_suffix(".txt").name).write_text("\n".join(lines))
        n_images += 1
        n_boxes += len(lines)
        n_empty += len(lines) == 0

    print(f"{split}: {n_images} images, {n_boxes} person boxes, {n_empty} with no person")


def write_yaml():
    (MERGED / "person.yaml").write_text(
        f"path: {MERGED}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: person\n"
    )


def main():
    for split in SPLITS:
        images_dir = MERGED / "images" / split
        if not images_dir.exists():
            raise SystemExit(
                f"{images_dir} doesn't exist. Create the NTFS junction first — "
                f"see the module docstring in this file."
            )
        convert_split(split)
    write_yaml()
    print(f"\nWrote {MERGED / 'person.yaml'}")


if __name__ == "__main__":
    main()
