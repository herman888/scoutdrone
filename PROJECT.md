# HTN Wallhacks — Aerial Person Detection

## Concept
UAV hovers at 20-40m altitude, detects people from above, transmits detection data to ground unit. Aerial ISR / overwatch.

## Hardware (same Pi)
- Raspberry Pi 5 + Hailo-10H NPU (M.2 HAT+)
- Camera: IMX219-160 (interim) → Raspberry Pi Global Shutter Camera IMX296 (target). Connected to CSI port but NOT currently detected by the kernel (`rpicam-hello --list-cameras` reports none, dmesg shows no probe) — likely a cable seating/orientation issue, needs physical inspection. See scripts/infer_pi.py, which is written and ready but untested live because of this.
- Comms: piggyback on the flight controller's existing MAVLink telemetry radio (see "Ground Comms" below) — no dedicated radio added just for detection data.

## Detection Target
- Single class: person (top-down / oblique aerial view)
- Altitude range: 20-40m
- At 20m: ~90px person height | At 40m: ~45px — tight, need good small-object detection

## Model Plan
- Base: YOLO11n (same architecture as drone project, already know the pipeline)
- Dataset: VisDrone (UAV footage, person class, multiple altitudes) — primary source
- Supplement: HERIDAL (aerial SAR), Stanford Drone Dataset
- Fine-tune from COCO pretrained weights (person class = class 0 already)

## Output
- .hef model on Pi
- Inference script outputs: bounding boxes + GPS coordinates (if GPS module added)
- Ground unit receives: JSON stream with detections + timestamp + position

## Ground Comms (decided 2026-08-23)
UAV has a flight controller with its own telemetry radio (SiK/ELRS/etc.), so detection
data rides that existing link instead of adding a dedicated radio — ground range is
whatever the FC link already achieves, nothing new to budget for.

- Wire format: standard MAVLink `DATA96` message (96-byte opaque payload slot), tagged
  with a fixed type id, so it needs no custom MAVLink dialect on either end.
- Payload: box count (1 byte) + up to 10 boxes @ 9 bytes each (x1,y1,x2,y2 uint16 pixel
  coords + conf uint8), sorted by confidence, zero-padded to 96 bytes.
- Uplink throttled to ~2 Hz independent of local inference rate, to avoid saturating a
  low-baud telemetry radio.
- Pi side: deploy/mavlink_uplink.py (`DetectionUplink` class) — connects to the FC over
  serial as a companion computer.
- Ground side: deploy/ground_receiver.py — connects via serial (radio dongle) or UDP
  (GCS-forwarded MAVLink stream), unpacks and prints detections.
- Not yet wired into deploy/infer_pi.py or tested against real hardware — needs
  pymavlink installed on the Pi (`pip install pymavlink`) and the FC's actual serial
  device path/baud once it's physically connected to the Pi.

## Pipeline (mirrors anti-drone-dome)
data/raw/      — raw downloaded datasets
data/merged/   — unified YOLO format, single class (0=person)
models/        — .pt and .hef files
scripts/       — dataset builder, training launcher
deploy/        — Pi inference script, ground unit receiver

## Status: IN PROGRESS (updated 2026-08-24)
- [x] Write COCO (yolov11m_h10.hef) person-detection inference script — scripts/infer_stream.py (live on Pi at :8080)
- [x] Live test COCO inference on Pi with IMX219-160 — camera issue noted above (line 8) resolved itself since; works fine, 30fps
- [x] Download VisDrone dataset — data/raw/VisDrone (train/val/test-dev), via scripts/download_visdrone.py directly from Ultralytics' GitHub release assets (the old Kaggle-based script 403'd and is replaced)
- [x] Build dataset merge script (filter to person class only) — scripts/build_dataset.py; produced data/merged/person.yaml, 106,396 person boxes/6,471 train images, 13,969/548 val images
- [x] Train R1 baseline — YOLO11n, 100 epochs, run `htn_r1-3`: mAP50 0.492, mAP50-95 0.193
- [x] Export R1 ONNX → .hef — compiles fine (`scripts/compile_hailo_r1.sh`) but **the resulting HEF hangs on the Pi at runtime, see "Known Issue" below**
- [ ] R2 (YOLO11s, bigger model) training in progress — see "Training Runs" below
- [x] Design ground unit comms protocol — see "Ground Comms" above; skeleton code written, untested against real FC hardware
- [ ] Switch to global shutter camera when available

## R2b: best model so far (2026-08-25 early morning)
`htn_r2b` (YOLO11s, batch=4 fix for the earlier cuDNN OOM) completed all epochs cleanly
overnight: **mAP50 0.554, mAP50-95 0.228** — beats R1 (0.492/0.193). Compiled to
`htn_r2b.hef` (12.7MB, real VisDrone calibration set from the start, learned from R1's
random-calib hang) and verified with the same isolated-run test pattern: 5/5 stable
inferences at ~28ms each on the Pi. Deployment-ready, just not currently running live
(Pi stream intentionally stopped). To run: `python3 ~/larp/scripts/infer_stream.py --hef
~/larp/models/htn_r2b.hef` (auto-detects person-class via `"htn_r1" in args.hef`... NOTE:
this won't match "htn_r2b" — need to add `--person` flag explicitly or extend the
autodetect string match when next touching infer_stream.py).

## SD card failure + fresh rebuild (2026-08-26 to 2026-08-29)
The original SD card developed genuine EXT4 filesystem corruption (checksum-invalid
errors spreading across different files over time — a classic failing-media pattern,
not a one-time software glitch). Leading suspect: undervoltage during heavy write load
(the HailoRT upgrade below involves kernel module compiles + package installs +
multiple reboots in quick succession) combined with a lower-endurance card. Replaced
with a SanDisk 64GB card (initially had a write-protect issue during flashing — turned
out to be a stale/offline Windows disk state left over from an earlier WSL2
investigation, not the card itself), but ultimately used a PNY 64GB card instead for
time reasons — **worth swapping back to the SanDisk when there's time, PNY has a
weaker endurance track record for this kind of write-heavy embedded use.**

**Full rebuild procedure that worked (fresh Raspberry Pi OS Lite 64-bit, Debian 13
Trixie), in order:**
1. Flash via Raspberry Pi Imager, Advanced Options (Ctrl+Shift+X) pre-configured:
   hostname `larp-pi`, SSH enabled, username `evanl1307`, WiFi SSID "This is the way" +
   country CA. Skip Raspberry Pi Connect (unnecessary cloud dependency, plain SSH is
   all that's used).
2. First boot: camera wasn't detected at all (`rpicam-hello --list-cameras` → "No
   cameras available", zero CSI-related dmesg activity). Root cause was the physical
   ribbon cable connection, not software — `camera_auto_detect=1` was already correctly
   set in `/boot/firmware/config.txt`. Fixed by physically reseating the cable (fully
   open the CSI port's latch, reseat straight, close latch firmly) — the Pi 5 has two
   CSI ports (CAM/DISP 0 and 1); this camera lives on **CAM1**. Along the way, also
   explicitly added `dtoverlay=imx219` to config.txt (belt-and-suspenders alongside
   auto-detect; not required once the physical connection was fixed, but doesn't
   hurt and got us a much more useful `-EREMOTEIO` I2C error instead of total silence
   while debugging).
3. `ssh-keygen -R <pi-ip>` on the client machine first — a fresh OS means a new SSH
   host key, which will otherwise hard-block the connection with a MITM warning.
4. Install HailoRT 5.3.0 (matching DFC) from
   `hailo.ai/developer-zone/software-downloads/` → Accelerators → Hailo-10H → HailoRT
   sub-package → **ARM64** architecture (not x86 — that's only for the DFC compiler on
   the PC) → Linux. Three files needed: `hailort-pcie-driver_*_all.deb` (driver +
   firmware), `hailort_*_arm64.deb` (runtime library), `hailort-*-cp313-cp313-linux_aarch64.whl`
   (Python bindings — check `python3 --version` on the Pi first to match the cp3xx tag).
   No older/version-matched DFC is available on the portal (only latest is listed,
   and the download page 403s without login) — upgrading the Pi to match DFC turned
   out easier than downgrading DFC to match the Pi.
5. `sudo dpkg -i` the driver .deb — **will fail** the DKMS kernel module build with
   `error: implicit declaration of function 'del_timer_sync'` (a real bug: Hailo's
   driver source uses a pre-6.x Linux timer API function that newer kernels removed).
   Fix (safe, well-known rename, not a hack):
   ```
   sudo apt install -y dkms   # often not preinstalled
   sudo sed -i 's/del_timer_sync/timer_delete_sync/' /usr/src/hailort-pcie-driver/linux/vdma/monitor.c
   sudo sed -i 's/del_timer_sync/timer_delete_sync/' /usr/src/hailo1x_pci-5.3.0/linux/vdma/monitor.c
   sudo sed -i 's/del_timer_sync/timer_delete_sync/' /var/lib/dkms/hailo1x_pci/5.3.0/build/linux/vdma/monitor.c
   sudo dpkg --configure -a
   ```
   `sudo dkms status` should then show `installed`.
6. `sudo dpkg -i` the runtime .deb, `sudo apt install -y python3-pip` (not present on
   Lite by default — if it 404s on a sub-dependency, just `sudo apt update` first, it's
   a stale index issue not a real problem), then
   `python3 -m pip install --break-system-packages ~/hailort-*.whl`.
7. `sudo reboot` (needed for the driver/firmware; not needed again for the pip step).
8. WiFi power-save fix (this is what actually fixes the "randomly drops off the
   network entirely" symptom, not anything code-side):
   ```
   sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf << 'EOF'
   [connection]
   wifi.powersave = 2
   EOF
   sudo systemctl restart NetworkManager
   ```
9. Restore `~/larp/scripts/` and `~/larp/models/` from the PC backup (kept at
   `htn-wallhacks/pi_backup_2026-08-26/`) via `scp -r`.
10. Install the picamera2/opencv/Flask stack — **use apt, not pip**, for
    picamera2/opencv specifically (proper libcamera/GPU integration on Pi):
    ```
    sudo apt install -y python3-opencv python3-picamera2 python3-flask
    python3 -m pip install --break-system-packages supervision
    ```
11. `bash ~/larp/scripts/switch_model.sh aerial` — confirmed working end to end
    (camera + NPU + model + stream, 30fps, no errors) as of 2026-08-29.

## Official Hailo personface model deployed as interim option (2026-08-26)
While DFC/HailoRT fix is pending (needs account/Pi access, see below), found and deployed
Hailo's own official pre-compiled `yolov5s_personface.hef` (person+face, YOLOv5s-based) from
their public S3 model zoo — no login needed:
`https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.4.0/hailo10h/yolov5s_personface.hef`
Verified working (5/5 stable inference, ~13ms — faster than any of our own models) and now
**live on the Pi** at `http://192.168.2.185:8080`. Not aerial-trained (general person+face,
not VisDrone), but a real working person-specific alternative to full 80-class COCO while
R4's deployment is blocked. `infer_stream.py` patched to support it (NMS-output path,
`PERSONFACE_NAMES = ["person", "face"]`, autodetected via `"personface" in args.hef`) — note
the console print still says "COCO yolov11m" for this model (cosmetic log bug only, actual
detection/box labels are correct).

Also checked: no public pip index for `hailo-dataflow-compiler` (confirmed not on PyPI, the
`hailo-extras-3.29.0` URL from the old anti-drone compile script returns nothing), and the
`hailo compiler`/`hailo optimize` CLI has no flag to target an older HEF/runtime version —
so there's genuinely no unsupervised path to fix R3/R4's deployment beyond what's below.

## BLOCKED: R3 .hef hangs on Pi, root cause likely DFC/HailoRT version mismatch (2026-08-25)
`htn_r3.hef` compiles fine but hangs on `hailo.run()` on the Pi — same symptom as R1's
original hang, but this time using real calibration data from the start (which fixed R1),
so calibration type is NOT the explanation here. Three real fixes tried, all failed:
1. Real calibration set (same one that fixed R1_v2/R2b) — still hangs.
2. From-scratch recompile — produced a byte-identical HEF (deterministic partition search),
   confirms retrying blindly won't help.
3. `--model-script` with `performance_param(compiler_optimization_level=max)` — produced a
   genuinely different HEF (different hash, 1h39m compile vs ~17min normally) — still hangs.
4. ONNX weight sanity check (NaN/Inf/extreme values) — clean, no anomaly found.

Likely root cause: Hailo's own docs state DFC 5.3.0 requires matching **HailoRT 5.3.0**,
but the Pi runs **HailoRT 5.1.1**. This was flagged as a risk back when DFC was first set up
([[hailo-dfc-compile]]) and never resolved. It's not a hard/consistent failure though —
R1_v2 and R2b were compiled with the identical DFC 5.3.0 and run perfectly on this same Pi,
so the mismatch only seems to bite certain models (likely tied to specific weight
distributions from R3's more diverse mixed-domain training data).

Real fixes, neither attempted (both need deliberate human decision, not autonomous action):
- Get a DFC version matching HailoRT 5.1.1 — requires a Hailo developer account login
  (the download page returns 403 without auth, same as how DFC 5.3.0 had to be manually
  downloaded originally) — needs the user.
- Upgrade the Pi's HailoRT to 5.3.0 to match — didn't want to attempt unsupervised, real
  risk of breaking the currently-working COCO/R1_v2/R2b setups if it goes wrong while no
  one's around to fix it.

**R4 (rebalanced mixed dataset, currently training) will very likely hit this same wall**
when compiled, since it's the same architecture/export path on the same mixed-domain data.
Don't be surprised if its .hef hangs too.

**Current safe recommendation: deploy R2b for production use.** It's proven, verified
working, and has the best pure-aerial accuracy of anything so far (mAP50 0.554). R3/R4 are
real, valid trained models with genuinely better PC-side accuracy/versatility — they're just
not currently deployable to this specific Pi without one of the two fixes above.

## In progress: R3, mixed close+aerial range (1-40m) dataset
Started 2026-08-25 after user wanted a more versatile model (not just 20-40m aerial) —
R1/R2 only ever saw VisDrone (aerial-only) data and completely fail on close-range/indoor
shots (confirmed empirically: whiffed on a close-up face test that COCO handled fine).
Fix: mix in CrowdHuman (close/medium-range person dataset, ~15k train images) alongside
VisDrone. Pipeline: `scripts/download_build_crowdhuman.sh` downloads CrowdHuman from
`huggingface.co/datasets/sshao0516/CrowdHuman` (the earlier Mendeley YOLO-format mirror
had no scriptable direct-download link, unusable for unattended automation), converts
ODGT annotations to YOLO format via `scripts/build_mixed_dataset.py`, and writes
`data/mixed/person_mixed.yaml` using explicit image-list .txt files (not directory
paths) for train/val — deliberately avoids Ultralytics' images<->labels path-swap
convention, which silently resolved to the wrong location once already tonight (see
below) when directories/junctions were involved. Once built, launch with
`scripts/train_r3.py` (YOLO11s, batch=4, 40 epochs — fewer than R2's 100 since the
combined dataset is ~3x larger per epoch).

## RESOLVED: R1 .hef now runs live on Pi (2026-08-24 night)
`htn_r1_v2.hef` — recompiled with a **real 64-image VisDrone calibration set** instead of
`--use-random-calib-set` — works. Confirmed 10/10 stable inference calls (~24ms each) and
now running live in `infer_stream.py --hef ~/larp/models/htn_r1_v2.hef` at 30fps,
auto-labeled "HTN person" (the `"htn_r1" in args.hef` autodetect still matches the `_v2`
suffix). It's still a 4-5 context HEF (same as the v1 that hung) — so the earlier
multi-context/firmware-mismatch theory was probably wrong, or at least not the whole story.
More likely: `--use-random-calib-set` produced degenerate/garbage quantized weights (noise
in, noise out) that triggered some firmware edge case on `run()`; real calibration data
avoided it. One quirk noted: device teardown (`VDevice.__exit__`) timed out
(`HAILO_TIMEOUT`) after repeated rapid-fire test calls — doesn't affect actual inference,
but avoid relying on clean process exit; `pkill -9` between restarts is fine.

**Not yet verified**: whether the 640x480 capture mode (see "Latency tuning" below) uses the
same sensor FOV as the 720p mode it replaced — the startup log shows a *different* selected
sensor readout mode per resolution (720p path selected a 1080p sensor mode then scaled down;
480p path selected native 640x480 sensor readout) — worth a real side-by-side check before
trusting this for the actual 20-40m altitude small-person case.

## (historical) Known Issue: R1 .hef hangs on Pi (multi-context / firmware mismatch)
`htn_r1.hef` (from run `htn_r1-3`) compiles successfully but `hailo.run()` never returns on
the Pi — confirmed via an isolated test script (opens device fine, correct 640x640x3 input
shape, but hangs indefinitely even on a dummy zero tensor). The older `r6_3class.hef` (drone
project) still runs a real inference in ~25ms on the same Pi, so it's not an environment
problem.

Root cause: the model didn't fit in a single Hailo context during compile (needed 152
logical compute units vs. 80 available) and DFC fell back to a 4-context HEF. The Pi runs
**HailoRT 5.1.1** firmware/driver; the HEF was compiled with **DFC 5.3.0**. Multi-context
scheduling is the most version-sensitive part of the Hailo toolchain, so this version gap is
the leading suspect — single-context HEFs (like `r6_3class.hef`) are simpler and appear to
be backward-compatible, multi-context ones aren't.

Compile notes if retrying:
- Default `hailo parser onnx` fails on this ONNX with `UnsupportedShuffleLayerError` on the
  DFL decode head — need `--end-node-names /model.23/Sigmoid /model.23/Concat` (this is what
  the parser's own error message recommends).
- `hailo optimize` on WSL2 fails with `libdevice not found` if TensorFlow tries to use the
  GPU for quantization — set `CUDA_VISIBLE_DEVICES=-1` first.
- First attempt used `--use-random-calib-set` (fast but garbage calibration). Second attempt
  (in progress as of this writing) uses a real 64-image calibration set built from VisDrone
  train images (`scripts/build_calib_set.py` → `models/htn_r1-3/weights/calib_set.npy`),
  hoping tighter quantization shrinks resource usage below the single-context budget. Result
  unknown as of this doc update — check `models/htn_r1-3/weights/compile_hailo_v2.log` and
  whether `htn_r1_v2.hef` actually runs (test with the isolated-run-only script pattern
  above before trusting it in `infer_stream.py`, to avoid a repeat hang).
- Fallback options if the real-calib retry also hangs: update Pi's HailoRT to match DFC
  5.3.0 (risk: could break the already-working COCO/r6 setups), or downgrade DFC to a
  5.1.1-compatible release.
- Current live demo on the Pi uses the pre-built COCO model
  (`/usr/share/hailo-models/yolov11m_h10.hef --coco`) as a working fallback while this gets
  sorted — same script, `--coco` flag.

## Training Runs (models/ dir)
- `htn_r1`, `htn_r1-2`: early R1 attempts that died early (epoch 0 and epoch 12) — ignore.
- `htn_r1-3`: **the R1 result that matters** — YOLO11n, completed all 100 epochs
  2026-08-23. mAP50 0.492, mAP50-95 0.193, precision 0.635, recall 0.448.
- `htn_r2`: YOLO11s attempt, batch=8, crashed at epoch 17/100 with
  `CUDNN_STATUS_INTERNAL_ERROR_HOST_ALLOCATION_FAILED` — likely VRAM-starved (RTX 3050, only
  4GB). Also note: launching training needs the Python at
  `C:\Users\aclie\AppData\Local\Python\pythoncore-3.14-64\python.exe` specifically (has
  ultralytics/torch installed) — the `python`/`py` on PATH resolve to an unrelated venv
  without ultralytics.
- `htn_r2b`: retry of R2 with batch=4 instead of 8, otherwise identical config
  (`scripts/train_r2.py`). Kicked off 2026-08-24 night, running overnight. First epoch
  completed clean with no cuDNN error, so the smaller batch appears to have fixed the OOM.

## Ground Test Preview Stream (scripts/infer_stream.py, not part of the real drone data path)
This runs a live MJPEG browser preview at `http://<pi-ip>:8080` for **testing on the ground
only** — the actual deployed UAV doesn't use this at all; it sends bounding boxes over
MAVLink `DATA96` telemetry (see "Ground Comms" above), not video. Useful notes:
- **Click-to-lock**: click a detection box in the browser to "lock" it — uses ByteTrack
  (via the `supervision` package) to keep a persistent ID per target across frames, then
  draws red corner brackets on whichever ID is locked. Purely a debug/demo aid, not used by
  the real detection pipeline.
- **Latency tuning (2026-08-24)**: capture resolution dropped 1280x720 → 640x480, JPEG
  quality 80 → 65, removed a redundant `cv2.putText` FPS overlay that was drawing on top of
  the JS-updated FPS div (was the garbled overlapping text seen on stream). FPS went from
  ~25-28 to ~30.
  - The JPEG quality change costs nothing — encoding happens *after* inference, so it only
    affects the browser preview, never detection accuracy.
  - The capture resolution change is more subtle but NOT a detection quality downgrade with
    this script: the Hailo model always takes a 640x640 input via `letterbox()`, so a
    1280x720 capture was being shrunk 2x to fit anyway (a 90px person arrived at the model
    as 45px). Capturing at 640-wide means `letterbox()`'s scale factor is ~1.0 (no
    shrinking), so effective pixels-on-target at the model input are the same or better than
    before, not worse.
  - **Unverified assumption**: this assumes the Pi camera's 480p mode covers the same field
    of view as 720p (just fewer pixels via binning), not a narrower crop. Worth confirming
    with a real side-by-side before trusting it for the small/distant-person case at 40m
    altitude — if 480p mode narrows the FOV instead, that would hurt real detection range.
- Every restart of `infer_stream.py` on the Pi needs `pkill -9 -f infer_stream.py` first if
  one's already running (only one process can hold the Hailo device at a time), then
  `setsid nohup python3 infer_stream.py --hef ... > log 2>&1 < /dev/null &` — plain `&` from
  an SSH one-liner leaves the SSH session hanging even after `disown` (Flask's dev server
  seems to keep something attached to the SSH pty); `setsid` fully detaches it.

## Notes
- The old scripts/download_visdrone.py had a Kaggle API key hardcoded in plaintext. It's
  been replaced (no Kaggle dependency at all now), but if that key is still valid it should
  be rotated/revoked on Kaggle's account settings.
