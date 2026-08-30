#!/bin/bash
set -e

# R4 = YOLO11s trained on the rebalanced mixed VisDrone + CrowdHuman dataset.
# This script uses the real VisDrone calibration set and DFC's default
# optimization level. The resulting HEF is retained for analysis only: it
# deadlocks at hailo.run() on the Pi, so do not deploy it over a working model.

ONNX="/mnt/c/Users/aclie/OneDrive/Documents/LARP/scoutdrone/models/htn_r4/weights/best.onnx"
OUT_DIR="/mnt/c/Users/aclie/OneDrive/Documents/LARP/scoutdrone/models/htn_r4/weights"
CALIB="/mnt/c/Users/aclie/OneDrive/Documents/LARP/scoutdrone/models/htn_r1-3/weights/calib_set.npy"
MODEL_NAME="htn_r4"
WORK_DIR="/tmp/hailo_compile_htn_r4"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

source ~/hailo_env/bin/activate
export CUDA_VISIBLE_DEVICES=-1

hailo parser onnx "$ONNX" \
  --hw-arch hailo10h \
  --net-name "$MODEL_NAME" \
  --end-node-names /model.23/Sigmoid /model.23/Concat

hailo optimize "${MODEL_NAME}.har" \
  --hw-arch hailo10h \
  --calib-set-path "$CALIB"

hailo compiler "${MODEL_NAME}_optimized.har" --hw-arch hailo10h
cp "${MODEL_NAME}.hef" "$OUT_DIR/${MODEL_NAME}.hef"
