#!/bin/bash
# Usage: ./switch_model.sh aerial|closerange|coco
set -e
MODE=${1:-}

pkill -9 -f infer_stream.py 2>/dev/null || true
sleep 1

case "$MODE" in
  aerial)
    HEF=~/larp/models/htn_r2b.hef
    EXTRA=""
    ;;
  closerange)
    HEF=~/larp/models/yolov5s_personface.hef
    EXTRA=""
    ;;
  coco)
    HEF=/usr/share/hailo-models/yolov11m_h10.hef
    EXTRA="--coco"
    ;;
  *)
    echo "Usage: $0 aerial|closerange|coco"
    exit 1
    ;;
esac

cd ~/larp/scripts
setsid nohup python3 infer_stream.py --hef "$HEF" $EXTRA > /tmp/stream_${MODE}.log 2>&1 < /dev/null &
disown
sleep 5
echo "switched to $MODE"
curl -s http://127.0.0.1:8080/fps
