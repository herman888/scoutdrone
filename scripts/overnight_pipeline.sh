#!/bin/bash
# Overnight orchestration: verify+cleanup archive copy, download+convert CrowdHuman,
# build mixed 1-40m dataset, wait for R2b to finish, launch R3 training.
set -uo pipefail

PROJ="/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks"
PY="/c/Users/aclie/AppData/Local/Python/pythoncore-3.14-64/python.exe"
ROBOCOPY_LOG="$PROJ/models/robocopy_archive2.log"
ANTI_DRONE_DATA="/c/Users/aclie/OneDrive/Documents/LARP/defenderproject/anti-drone-dome/data"
CH_RAW="$PROJ/data/raw/CrowdHuman"
HF_BASE="https://huggingface.co/datasets/sshao0516/CrowdHuman/resolve/main"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "=== STAGE 1: waiting for archive robocopy to finish ==="
while ! grep -q "Ended :" "$ROBOCOPY_LOG" 2>/dev/null; do
    sleep 15
done
if grep -qi "ERROR" "$ROBOCOPY_LOG"; then
    log "FATAL: robocopy log contains ERROR, aborting pipeline. Check $ROBOCOPY_LOG"
    exit 1
fi
log "robocopy finished cleanly, verifying file counts..."

SRC_COUNT=$(find "$ANTI_DRONE_DATA" -type f | wc -l)
DST_COUNT=$(find "/d/anti-drone-dome-data-2026-08-25" -type f | wc -l)
log "source files: $SRC_COUNT, dest files: $DST_COUNT"
if [ "$DST_COUNT" -lt "$SRC_COUNT" ]; then
    log "FATAL: dest has fewer files than source, NOT deleting source. Aborting pipeline."
    exit 1
fi

log "verified OK, deleting source from C: to free space"
rm -rf "$ANTI_DRONE_DATA"/archive "$ANTI_DRONE_DATA"/public "$ANTI_DRONE_DATA"/merged_r6
log "source deleted. free space now:"
df -h /c

FREE_KB=$(df /c | tail -1 | awk '{print $4}')
FREE_GB=$((FREE_KB / 1024 / 1024))
if [ "$FREE_GB" -lt 15 ]; then
    log "FATAL: only ${FREE_GB}GB free after cleanup, need at least 15GB for CrowdHuman. Aborting pipeline (R3 will NOT launch)."
    exit 1
fi
log "confirmed ${FREE_GB}GB free, proceeding"

log "=== STAGE 2: downloading CrowdHuman (train01/02/03, val, odgt) ==="
mkdir -p "$CH_RAW/images" "$CH_RAW/zips"
cd "$CH_RAW/zips" || exit 1

for f in annotation_train.odgt annotation_val.odgt; do
    log "downloading $f"
    if ! curl -f -L --retry 5 --retry-delay 10 -o "$CH_RAW/$f" "$HF_BASE/$f"; then
        log "FATAL: curl failed downloading $f. Aborting pipeline."
        exit 1
    fi
    if [ ! -s "$CH_RAW/$f" ]; then
        log "FATAL: $f is empty after download. Aborting pipeline."
        exit 1
    fi
    if ! head -n1 "$CH_RAW/$f" | "$PY" -c "import json,sys; json.loads(sys.stdin.readline())" 2>/dev/null; then
        log "FATAL: $f does not look like valid odgt JSON lines. Aborting pipeline."
        exit 1
    fi
done

for z in CrowdHuman_train01.zip CrowdHuman_train02.zip CrowdHuman_train03.zip CrowdHuman_val.zip; do
    log "downloading $z"
    if ! curl -f -L --retry 5 --retry-delay 10 -o "$z" "$HF_BASE/$z"; then
        log "FATAL: curl failed downloading $z. Aborting pipeline."
        exit 1
    fi
    if [ ! -s "$z" ]; then
        log "FATAL: $z is empty after download. Aborting pipeline."
        exit 1
    fi
    log "extracting $z"
    if ! "$PY" "$PROJ/scripts/extract_flatten.py" "$z" "$CH_RAW/images"; then
        log "FATAL: extraction of $z failed. Aborting pipeline."
        exit 1
    fi
    rm -f "$z"
    FREE_KB=$(df /c | tail -1 | awk '{print $4}')
    FREE_GB=$((FREE_KB / 1024 / 1024))
    log "free space after $z: ${FREE_GB}GB"
    if [ "$FREE_GB" -lt 3 ]; then
        log "FATAL: only ${FREE_GB}GB free, too risky to continue (R2b training is still writing checkpoints). Aborting pipeline."
        exit 1
    fi
done

log "=== STAGE 3: building mixed 1-40m dataset ==="
"$PY" "$PROJ/scripts/build_mixed_dataset.py"
if [ $? -ne 0 ]; then
    log "FATAL: build_mixed_dataset.py failed. Aborting pipeline (R3 will NOT launch)."
    exit 1
fi

log "=== STAGE 4: waiting for R2b training to finish before starting R3 (GPU is single-use) ==="
while ps aux 2>/dev/null | grep -v grep | grep -q "pythoncore-3.14-64"; do
    sleep 60
done
log "R2b process no longer running. Waiting 30s buffer for GPU memory to release..."
sleep 30

log "=== STAGE 5: launching R3 (mixed close+aerial range) training ==="
cd "$PROJ" || exit 1
"$PY" scripts/train_r3.py > models/train_r3.log 2> models/train_r3_err.log
log "R3 training process exited. Check models/train_r3.log and train_r3_err.log"

log "=== PIPELINE COMPLETE ==="
