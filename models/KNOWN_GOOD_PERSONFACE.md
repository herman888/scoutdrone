# Known-good close-range deployment

Date captured: 2026-08-29

`yolov5s_personface.hef` is the verified close-range fallback for the Pi 5.
It detects people and faces using the CSI IMX219 camera at 640x480 / 30 FPS,
with Hailo-10H firmware 5.3.0 and no thermal throttling.

Launch it with:

```bash
bash ~/larp/scripts/switch_model.sh closerange
```

The low-latency stream change in `scripts/infer_stream.py` sends each newly
produced frame once and forbids client caching. Do not replace this model while
testing another HEF; keep it as the live demo fallback.

SHA-256: `dbc37c17a946444a2c0d26ce9219a5f615a2070cdea5981427181f3b9d22a910`
