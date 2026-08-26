"""Build a full 10-class YOLO val set from raw VisDrone annotations, matching
dronefreak/visdrone-yolov11s's class order (pedestrian, people, bicycle, car,
van, truck, tricycle, awning-tricycle, bus, motor), for an apples-to-apples
benchmark against that pretrained checkpoint.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks")
RAW = ROOT / "data" / "raw" / "VisDrone" / "VisDrone2019-DET-val"
OUT = ROOT / "data" / "visdrone10"
(OUT / "labels" / "val").mkdir(parents=True, exist_ok=True)

# VisDrone raw category id -> our 0-indexed class id (0=ignored, 11=others: dropped)
CAT_MAP = {i: i - 1 for i in range(1, 11)}  # 1..10 -> 0..9

n_images = 0
n_boxes = 0
for ann_path in sorted((RAW / "annotations").glob("*.txt")):
    img_path = RAW / "images" / (ann_path.stem + ".jpg")
    if not img_path.exists():
        continue
    w, h = Image.open(img_path).size

    lines = []
    for row in ann_path.read_text().strip().splitlines():
        parts = row.split(",")
        score, category = parts[4], int(parts[5])
        if score == "0" or category not in CAT_MAP:
            continue
        x, y, bw, bh = map(int, parts[:4])
        cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
        nw, nh = bw / w, bh / h
        lines.append(f"{CAT_MAP[category]} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

    (OUT / "labels" / "val" / ann_path.with_suffix(".txt").name).write_text("\n".join(lines))
    n_images += 1
    n_boxes += len(lines)

print(f"Wrote {n_images} label files, {n_boxes} total boxes")

yaml_content = f"""path: {OUT}
train: images/val
val: images/val
names:
  0: pedestrian
  1: people
  2: bicycle
  3: car
  4: van
  5: truck
  6: tricycle
  7: awning-tricycle
  8: bus
  9: motor
"""
(OUT / "visdrone10.yaml").write_text(yaml_content)
print(f"Wrote {OUT / 'visdrone10.yaml'}")
