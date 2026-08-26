#!/bin/bash
set -e

ONNX="/mnt/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks/models/htn_r2b/weights/best.onnx"
OUT_DIR="/mnt/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks/models/htn_r2b/weights"
CALIB="/mnt/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks/models/htn_r1-3/weights/calib_set.npy"
MODEL_NAME="htn_r2b"
WORK_DIR="/tmp/hailo_compile_htn_r2b"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== Activating DFC venv ==="
source ~/hailo_env/bin/activate
export CUDA_VISIBLE_DEVICES=-1

echo ""
echo "=== Parsing ONNX ==="
hailo parser onnx "$ONNX" \
    --hw-arch hailo10h \
    --net-name "$MODEL_NAME" \
    --end-node-names /model.23/Sigmoid /model.23/Concat

echo ""
echo "=== Optimizing (real calibration set) ==="
hailo optimize "${MODEL_NAME}.har" \
    --hw-arch hailo10h \
    --calib-set-path "$CALIB"

echo ""
echo "=== Compiling to HEF ==="
hailo compiler "${MODEL_NAME}_optimized.har" \
    --hw-arch hailo10h

echo ""
echo "=== Done ==="
cp "${MODEL_NAME}.hef" "$OUT_DIR/${MODEL_NAME}.hef"
echo "HEF saved to: $OUT_DIR/${MODEL_NAME}.hef"
