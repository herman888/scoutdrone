#!/bin/bash
set -uo pipefail

PROJ="/c/Users/aclie/OneDrive/Documents/LARP/htn-wallhacks"
PY="/c/Users/aclie/AppData/Local/Python/pythoncore-3.14-64/python.exe"
CH_RAW="$PROJ/data/raw/CrowdHuman"
HF_BASE="https://huggingface.co/datasets/sshao0516/CrowdHuman/resolve/main"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

mkdir -p "$CH_RAW/images" "$CH_RAW/zips"
cd "$CH_RAW/zips" || exit 1

log "=== downloading odgt annotations ==="
for f in annotation_train.odgt annotation_val.odgt; do
    log "downloading $f"
    if ! curl -f -L --retry 5 --retry-delay 10 -o "$CH_RAW/$f" "$HF_BASE/$f"; then
        log "FATAL: curl failed downloading $f."
        exit 1
    fi
    if [ ! -s "$CH_RAW/$f" ]; then
        log "FATAL: $f is empty after download."
        exit 1
    fi
    if ! head -n1 "$CH_RAW/$f" | "$PY" -c "import json,sys; json.loads(sys.stdin.readline())" 2>/dev/null; then
        log "FATAL: $f does not look like valid odgt JSON lines."
        exit 1
    fi
done

log "=== downloading + extracting image zips ==="
for z in CrowdHuman_train01.zip CrowdHuman_train02.zip CrowdHuman_train03.zip CrowdHuman_val.zip; do
    log "downloading $z"
    if ! curl -f -L --retry 5 --retry-delay 10 -o "$z" "$HF_BASE/$z"; then
        log "FATAL: curl failed downloading $z."
        exit 1
    fi
    if [ ! -s "$z" ]; then
        log "FATAL: $z is empty after download."
        exit 1
    fi
    log "extracting $z"
    if ! "$PY" "$PROJ/scripts/extract_flatten.py" "$z" "$CH_RAW/images"; then
        log "FATAL: extraction of $z failed."
        exit 1
    fi
    rm -f "$z"
    FREE_KB=$(df /c | tail -1 | awk '{print $4}')
    FREE_GB=$((FREE_KB / 1024 / 1024))
    log "free space after $z: ${FREE_GB}GB"
    if [ "$FREE_GB" -lt 3 ]; then
        log "FATAL: only ${FREE_GB}GB free, stopping."
        exit 1
    fi
done

log "=== building mixed 1-40m dataset ==="
if ! "$PY" "$PROJ/scripts/build_mixed_dataset.py"; then
    log "FATAL: build_mixed_dataset.py failed."
    exit 1
fi

log "=== CROWDHUMAN_BUILD_COMPLETE ==="
