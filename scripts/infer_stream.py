"""
Unified inference + MJPEG stream server with ByteTrack target tracking.
Captures from picamera2, runs Hailo NPU inference, overlays tracked boxes,
streams annotated video to http://PI_IP:8080 in any browser.

Click on the stream to lock/unlock a target. Locked target gets red corner brackets.

COCO test:
  python3 infer_stream.py --hef /usr/share/hailo-models/yolov11m_h10.hef --coco
Custom 3-class drone model:
  python3 infer_stream.py --hef ~/larp/models/r6_3class.hef

Install tracking dep on Pi:
  pip install supervision
"""
import argparse, time, threading, cv2, socket
import numpy as np
from flask import Flask, Response, request
from werkzeug.serving import WSGIRequestHandler


class NoDelayRequestHandler(WSGIRequestHandler):
    def setup(self):
        super().setup()
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass
from picamera2 import Picamera2
from picamera2.devices.hailo import Hailo

try:
    import supervision as sv
    _HAVE_SV = True
except ImportError:
    _HAVE_SV = False
    print("WARNING: supervision not installed — tracking disabled. Run: pip install supervision")

# ── class maps ────────────────────────────────────────────────────────────────
DRONE_CLASSES = {0: "drone", 1: "fpv_drone", 2: "loitering_munition"}
PERSON_CLASSES = {0: "person"}
PERSON_COLORS  = {0: (0,255,255)}
PERSONFACE_NAMES = ["person", "face"]
DRONE_COLORS  = {0: (0,255,0), 1: (0,165,255), 2: (0,0,255)}

COCO_NAMES = [
    "person","bicycle","car","motorbike","aeroplane","bus","train","truck","boat",
    "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
    "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
    "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
    "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
    "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
    "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake",
    "chair","sofa","pottedplant","bed","diningtable","toilet","tvmonitor","laptop",
    "mouse","remote","keyboard","cell phone","microwave","oven","toaster","sink",
    "refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush",
]

CONF_THRESH = 0.15
INPUT_SIZE  = 640

# ── shared state ──────────────────────────────────────────────────────────────
frame_lock   = threading.Lock()
frame_ready  = threading.Condition(frame_lock)
boxes_lock   = threading.Lock()
latest_frame = b""
frame_version = 0
latest_boxes = [[]]   # list of (x1,y1,x2,y2,conf,cls_id,label,track_id)
fps_display  = [0.0]
locked_id    = [None] # track_id of locked target
_tid_colors  = {}     # persistent per-track-id color

app = Flask(__name__)


def _track_color(tid):
    """Deterministic color per track ID, generated from hash."""
    if tid not in _tid_colors:
        rng = np.random.default_rng(abs(tid) * 2654435761 % (2**32))
        h = int(rng.integers(0, 180))
        hsv = np.uint8([[[h, 210, 230]]])
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
        _tid_colors[tid] = (int(bgr[0]), int(bgr[1]), int(bgr[2]))
    return _tid_colors[tid]


# ── Flask routes ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return (
        '<html><body style="margin:0;background:#000;color:#0f0;font-family:monospace">'
        '<div id="fps" style="position:absolute;top:8px;left:8px;font-size:14px;z-index:9"></div>'
        '<div id="sel" style="position:absolute;top:30px;left:8px;font-size:12px;z-index:9;color:#ff0"></div>'
        '<img src="/stream" id="feed" style="width:100%;height:100vh;object-fit:contain;cursor:crosshair">'
        '<script>'
        # Map click coords through object-fit:contain letterboxing to image pixel coords
        'function imgPx(img,e){'
        '  var r=img.getBoundingClientRect();'
        '  var iw=img.naturalWidth||1280,ih=img.naturalHeight||720;'
        '  var s=Math.min(img.clientWidth/iw,img.clientHeight/ih);'
        '  var ox=(img.clientWidth-iw*s)/2,oy=(img.clientHeight-ih*s)/2;'
        '  return[Math.round((e.clientX-r.left-ox)/s),Math.round((e.clientY-r.top-oy)/s)];'
        '}'
        'document.getElementById("feed").addEventListener("click",function(e){'
        '  var p=imgPx(this,e);'
        '  fetch("/select?x="+p[0]+"&y="+p[1]).then(r=>r.text()).then(t=>{'
        '    document.getElementById("sel").innerText=t;'
        '  });'
        '});'
        'setInterval(()=>{'
        '  fetch("/fps").then(r=>r.text()).then(t=>{document.getElementById("fps").innerText=t});'
        '},500);'
        '</script>'
        '</body></html>'
    )

@app.route('/fps')
def fps_route():
    lid = locked_id[0]
    lock_str = f"  LOCKED #{lid}" if lid is not None else ""
    return f"FPS: {fps_display[0]:.1f}{lock_str}"

@app.route('/stream')
def stream():
    def gen():
        # Emit only newly-produced frames. Repeating the same JPEG in a tight
        # loop lets browsers and iOS WebViews buffer stale video.
        last_version = -1
        while True:
            with frame_ready:
                frame_ready.wait_for(lambda: frame_version != last_version, timeout=1.0)
                if frame_version == last_version:
                    continue
                frame = latest_frame
                last_version = frame_version
            if frame:
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
    return Response(
        gen(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )

@app.route('/lock')
def lock_target():
    tid = request.args.get('id', type=int)
    locked_id[0] = tid
    return f"Locked target #{tid}"

@app.route('/unlock')
def unlock_target():
    locked_id[0] = None
    return "Unlocked"

@app.route('/select')
def select_target():
    """Called when user clicks the stream — finds which box was clicked."""
    px = request.args.get('x', type=float)
    py = request.args.get('y', type=float)
    if px is None or py is None:
        return "bad coords", 400
    with boxes_lock:
        boxes = list(latest_boxes[0])
    for x1, y1, x2, y2, conf, cls_id, label, tid in boxes:
        if x1 <= px <= x2 and y1 <= py <= y2:
            locked_id[0] = tid
            return f"Locked: {label} #{tid} ({conf:.2f})"
    locked_id[0] = None
    return "Unlocked"

@app.route('/tracks')
def tracks_route():
    """JSON-like list of current active tracks — useful for debugging."""
    with boxes_lock:
        boxes = list(latest_boxes[0])
    lines = [f"#{t} {lbl} {c:.2f} [{x1},{y1},{x2},{y2}]"
             for x1, y1, x2, y2, c, cls_id, lbl, t in boxes]
    return "\n".join(lines) or "no detections"


# ── inference helpers ─────────────────────────────────────────────────────────
def letterbox(img, size=640):
    h, w = img.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (nw, nh))
    pad = np.zeros((size, size, 3), dtype=np.uint8)
    py, px = (size - nh) // 2, (size - nw) // 2
    pad[py:py+nh, px:px+nw] = resized
    return pad, scale, px, py


def parse_nms_output(raw, orig_shape, scale, px, py, class_names, class_filter=None):
    """Parse Hailo NMS BY CLASS output → list of (x1,y1,x2,y2,conf,cls_id,label)."""
    oh, ow = orig_shape[:2]
    detections = []
    for cls_id, class_dets in enumerate(raw):
        if class_filter is not None and cls_id not in class_filter:
            continue
        if class_dets is None:
            continue
        arr = np.array(class_dets)
        if arr.ndim == 0 or arr.size == 0:
            continue
        if arr.ndim == 1:
            arr = arr.reshape(-1, 5)
        for det in arr:
            if len(det) < 5:
                continue
            y1n, x1n, y2n, x2n, conf = det[:5]
            if conf < CONF_THRESH:
                continue
            x1 = int(np.clip((x1n * INPUT_SIZE - px) / scale, 0, ow))
            y1 = int(np.clip((y1n * INPUT_SIZE - py) / scale, 0, oh))
            x2 = int(np.clip((x2n * INPUT_SIZE - px) / scale, 0, ow))
            y2 = int(np.clip((y2n * INPUT_SIZE - py) / scale, 0, oh))
            label = class_names.get(cls_id, str(cls_id)) if isinstance(class_names, dict) else class_names[cls_id]
            detections.append((x1, y1, x2, y2, float(conf), cls_id, label))
    return detections


def parse_raw_output(raw, orig_shape, scale, px, py, class_names):
    """Parse raw YOLO tensor (no on-chip NMS) → list of detections. For custom .hef."""
    oh, ow = orig_shape[:2]
    arr = list(raw.values())[0]
    if arr.ndim == 3:
        arr = arr[0]
    preds = arr.T
    boxes = preds[:, :4]
    scores = preds[:, 4:]
    cls_ids = np.argmax(scores, axis=1)
    confs = scores[np.arange(len(scores)), cls_ids]
    mask = confs > CONF_THRESH
    boxes, confs, cls_ids = boxes[mask], confs[mask], cls_ids[mask]
    if len(boxes) == 0:
        return []
    cx, cy, w, h = boxes.T
    x1 = ((cx - w/2) - px) / scale
    y1 = ((cy - h/2) - py) / scale
    x2 = ((cx + w/2) - px) / scale
    y2 = ((cy + h/2) - py) / scale
    x1, x2 = np.clip([x1, x2], 0, ow)
    y1, y2 = np.clip([y1, y2], 0, oh)
    idxs = cv2.dnn.NMSBoxes(
        [[float(x1[i]),float(y1[i]),float(x2[i]-x1[i]),float(y2[i]-y1[i])] for i in range(len(x1))],
        confs.tolist(), CONF_THRESH, 0.45
    )
    detections = []
    for i in (idxs.flatten() if len(idxs) else []):
        cls = int(cls_ids[i])
        label = class_names.get(cls, str(cls))
        detections.append((int(x1[i]),int(y1[i]),int(x2[i]),int(y2[i]),float(confs[i]),cls,label))
    return detections


def apply_tracker(detections, tracker, class_names):
    """Run ByteTracker and return list of (x1,y1,x2,y2,conf,cls_id,label,track_id)."""
    if not _HAVE_SV or tracker is None or not detections:
        return [(x1,y1,x2,y2,c,cls,lbl,-1) for x1,y1,x2,y2,c,cls,lbl in detections]
    xyxy = np.array([[d[0],d[1],d[2],d[3]] for d in detections], dtype=float)
    conf = np.array([d[4] for d in detections])
    cls_ids = np.array([d[5] for d in detections], dtype=int)
    sv_dets = sv.Detections(xyxy=xyxy, confidence=conf, class_id=cls_ids)
    tracked = tracker.update_with_detections(sv_dets)
    result = []
    for i in range(len(tracked)):
        x1, y1, x2, y2 = tracked.xyxy[i].astype(int)
        c = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
        cls = int(tracked.class_id[i]) if tracked.class_id is not None else 0
        tid = int(tracked.tracker_id[i]) if tracked.tracker_id is not None else -1
        if isinstance(class_names, dict):
            label = class_names.get(cls, str(cls))
        else:
            label = class_names[cls] if cls < len(class_names) else str(cls)
        result.append((x1, y1, x2, y2, c, cls, label, tid))
    return result


def draw(frame, tracked_dets, class_colors):
    lid = locked_id[0]
    for x1, y1, x2, y2, conf, cls, label, tid in tracked_dets:
        is_locked = (lid is not None and tid == lid)
        if is_locked:
            color, thickness = (0, 0, 255), 3
        elif isinstance(class_colors, dict) and cls in class_colors:
            color, thickness = class_colors[cls], 2
        elif tid >= 0:
            color, thickness = _track_color(tid), 2
        else:
            color, thickness = (0, 255, 0), 2

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        id_str = f" #{tid}" if tid >= 0 else ""
        cv2.putText(frame, f"{label}{id_str} {conf:.2f}", (x1, max(y1-6, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        if is_locked:
            bl = max(12, min(20, (x2-x1)//5, (y2-y1)//5))
            for cx, cy, sx, sy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
                cv2.line(frame, (cx, cy), (cx+sx*bl, cy), (0,0,255), 3)
                cv2.line(frame, (cx, cy), (cx, cy+sy*bl), (0,0,255), 3)


def inference_loop(hef_path, is_coco, is_person=False, use_usb=False):
    global latest_frame, frame_version
    _BT = getattr(sv, "ByteTrack", None) or getattr(sv, "ByteTracker", None)
    tracker = _BT(lost_track_buffer=30) if (_HAVE_SV and _BT) else None

    picam2 = None
    usb_cap = None
    if use_usb:
        usb_cap = cv2.VideoCapture("/dev/video8")
        usb_cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        usb_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        usb_cap.set(cv2.CAP_PROP_FPS, 30)
        if not usb_cap.isOpened():
            raise RuntimeError("Failed to open USB camera /dev/video8")
    else:
        picam2 = Picamera2()
        cfg = picam2.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            controls={"FrameRate": 30}
        )
        picam2.configure(cfg)
        picam2.start()
        time.sleep(1)

    with Hailo(hef_path) as hailo:
        t0 = time.time()
        frames = 0
        model_desc = "COCO yolov11m" if is_coco else ("HTN person" if is_person else "R6 3-class")
        print(f"Inference on {model_desc}. View at http://0.0.0.0:8080")
        print("Click stream to lock a target. /lock?id=N  /unlock  /tracks")
        try:
            while True:
                if use_usb:
                    ok, bgr = usb_cap.read()
                    if not ok:
                        continue
                else:
                    bgr = picam2.capture_array()  # picamera2 RGB888 is actually BGR
                    bgr = cv2.rotate(bgr, cv2.ROTATE_180)  # CSI camera is physically mounted upside down
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                lb, scale, px, py = letterbox(rgb)
                raw = hailo.run(lb)

                if is_coco:
                    names = PERSONFACE_NAMES if "personface" in hef_path else COCO_NAMES
                    dets = parse_nms_output(raw, rgb.shape, scale, px, py, names)
                    if "personface" not in hef_path:
                        dets = [d for d in dets if d[5] == 0]  # person-only, drop other 79 COCO classes
                    class_names, colors = names, {}
                elif is_person:
                    dets = parse_raw_output(raw, rgb.shape, scale, px, py, PERSON_CLASSES)
                    class_names, colors = PERSON_CLASSES, PERSON_COLORS
                else:
                    dets = parse_raw_output(raw, rgb.shape, scale, px, py, DRONE_CLASSES)
                    class_names, colors = DRONE_CLASSES, DRONE_COLORS

                tracked = apply_tracker(dets, tracker, class_names)
                with boxes_lock:
                    latest_boxes[0] = tracked

                display = bgr.copy()
                draw(display, tracked, colors)

                frames += 1
                fps = frames / max(time.time() - t0, 0.001)
                fps_display[0] = fps


                _, buf = cv2.imencode('.jpg', display, [cv2.IMWRITE_JPEG_QUALITY, 65])
                with frame_ready:
                    latest_frame = buf.tobytes()
                    frame_version += 1
                    frame_ready.notify_all()
        except KeyboardInterrupt:
            pass
        finally:
            if use_usb:
                usb_cap.release()
            else:
                picam2.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hef", default="/usr/share/hailo-models/yolov11m_h10.hef")
    ap.add_argument("--coco", action="store_true", help="Use COCO NMS output format")
    ap.add_argument("--person", action="store_true", help="Use single-class person model")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--usb", action="store_true", help="Use USB camera (/dev/video8) instead of CSI camera")
    args = ap.parse_args()

    is_coco = args.coco or "yolov11m_h10" in args.hef or "yolov8m_h10" in args.hef or "personface" in args.hef
    is_person = args.person or "htn_r" in args.hef  # matches htn_r1/r2b/r3/r4 (all single-class person models)

    t = threading.Thread(target=inference_loop, args=(args.hef, is_coco, is_person, args.usb), daemon=True)
    t.start()
    time.sleep(3)
    app.run(host="0.0.0.0", port=args.port, threaded=True, request_handler=NoDelayRequestHandler)


if __name__ == "__main__":
    main()
