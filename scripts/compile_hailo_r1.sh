#!/bin/bash
# Converts R1 person-detector ONNX -> .hef for Hailo-10H using Hailo DFC in WSL2
# Run from Windows: wsl -d Ubuntu-24.04 -- bash "/mnt/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks/scripts/compile_hailo_r1.sh"

set -e

ONNX="/mnt/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks/models/htn_r1-3/weights/best.onnx"
OUT_DIR="/mnt/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks/models/htn_r1-3/weights"
MODEL_NAME="htn_r1_v2"
WORK_DIR="/tmp/hailo_compile_htn_r1_v2"

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
    --calib-set-path "${OUT_DIR}/calib_set.npy"

echo ""
echo "=== Compiling to HEF ==="
hailo compiler "${MODEL_NAME}_optimized.har" \
    --hw-arch hailo10h

echo ""
echo "=== Done ==="
cp "${MODEL_NAME}.hef" "$OUT_DIR/${MODEL_NAME}.hef"
echo "HEF saved to: $OUT_DIR/${MODEL_NAME}.hef"
