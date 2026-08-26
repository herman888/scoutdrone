"""Build a real-image calibration set (.npy) for Hailo DFC optimize step.
Samples N random VisDrone train images, letterboxes to 640x640 RGB uint8.
"""
import cv2
import numpy as np
import random
from pathlib import Path

IMG_DIR = Path(__file__).parent.parent / "data" / "merged" / "images" / "train"
OUT_PATH = Path(__file__).parent.parent / "models" / "htn_r1-3" / "weights" / "calib_set.npy"
N = 64
SIZE = 640

def letterbox(img, size=640):
    h, w = img.shape[:2]
    scale = min(size / h, size / w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (nw, nh))
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    top = (size - nh) // 2
    left = (size - nw) // 2
    canvas[top:top+nh, left:left+nw] = resized
    return canvas

random.seed(0)
files = sorted(IMG_DIR.glob("*.jpg"))
sample = random.sample(files, N)

arr = np.zeros((N, SIZE, SIZE, 3), dtype=np.uint8)
for i, f in enumerate(sample):
    bgr = cv2.imread(str(f))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    arr[i] = letterbox(rgb, SIZE)

np.save(OUT_PATH, arr)
print(f"Saved {arr.shape} to {OUT_PATH}")
