# HTN Wallhacks — Hardware Inventory

Compiled 2026-08-27 from live device queries + prior sessions. Items marked
**(unverified)** are from memory/inference, not a live check — worth confirming
once the Pi is back up on the new SD card.

## Compute
- **Raspberry Pi 5** — confirmed via kernel (`BCM2712` SoC, `rpi-2712` kernel
  variant) and `/proc/device-tree/model` in prior sessions.
- **RAM**: 8GB (confirmed via `free -h`: 7.9Gi total)

## AI Accelerator
- **Hailo-10H NPU**, attached via **M.2 HAT+** — confirmed multiple times via
  `hailortcli fw-control identify` (`Device Architecture: HAILO10H`).
  **Explicitly NOT Hailo-8L** — this was flagged early on as an easy mix-up to
  avoid (Hailo-8L is a different, more common chip; ours is the newer 10H).
- **7.2GB onboard chip RAM** — confirmed via `hailortcli monitor` (idle: 87MB /
  7221MB used).
- Runs over **PCIe** (confirmed: device shows as `pci/0001:01:00.0`, not USB).

## Camera
- **Sony IMX219-160** — confirmed via `rpicam-hello --list-cameras`
  (`imx219 [3280x2464 10-bit]`). The "160" denotes a 160° wide-angle FOV variant
  of the standard IMX219 sensor (the same sensor as the original Raspberry Pi
  Camera Module 2, just a wide-FOV lens variant).
- Connected on the **CAM1** port.
- Currently mounted **physically upside down** relative to normal use —
  compensated in software (`cv2.rotate(bgr, cv2.ROTATE_180)` in
  `infer_stream.py`) as of tonight, but worth physically correcting when the
  Pi's opened up for the SD card swap if convenient.
- **This is the "interim" camera** — original project plan called for
  swapping to a **Raspberry Pi Global Shutter Camera (IMX296)** for the final
  build, to reduce rolling-shutter blur during actual flight. That swap has
  **not happened yet**.

## Cooling
- **Active fan present** — confirmed behaviorally (turns on above ~60°C, off
  below, 45°C idle is normal) but exact model **(unverified)** — likely the
  official Raspberry Pi 5 Active Cooler if using a standard case/HAT stack,
  but not confirmed via a part number check.

## Power
- **27W+ USB-C power delivery required.** Confirmed critical: weaker supplies
  (e.g. phone chargers) cause undervoltage, visible as a **red power LED**.
  This is a leading suspect for tonight's SD card corruption — a brownout
  mid-write is one of the most common causes of exactly the kind of ext4
  corruption we hit. Worth being strict about using the proper supply going
  forward.

## Storage
- **microSD card** — the original card developed genuine filesystem
  corruption (ext4 checksum errors, spreading across multiple files over
  time) as of 2026-08-26/27, root cause undetermined for certain (leading
  theory: undervoltage during heavy write load, possibly combined with a
  marginal/lower-endurance card). Being replaced with a new card as of this
  session. **Recommendation**: use an "A1"/"A2" application-class or
  endurance-rated card (e.g. SanDisk Extreme, Samsung PRO Endurance) rather
  than a basic consumer card, given this project does heavier-than-typical
  write workloads (model deployment, occasional driver/kernel work).

## Networking
- **Built-in WiFi** (Broadcom BCM4345/6 chipset, confirmed via `dmesg`).
- Connected to network **"This is the way"** (confirmed via `nmcli`).
- WiFi power-save has been **disabled** (`/etc/NetworkManager/conf.d/wifi-powersave-off.conf`,
  `wifi.powersave = 2`) as of 2026-08-26 — it was causing the WiFi radio to
  intermittently drop the connection entirely under sustained streaming load.
  **This setting lives on the SD card and will need to be redone on the new
  card** — see the setup checklist for the fresh install.
- IP is DHCP-assigned and has flip-flopped between `.185` and `.186`
  historically — always verify via `arp -a` (MAC `2c-cf-67-c2-c6-c8`) rather
  than assuming.

## Flight controller / MAVLink integration
- **Not yet connected.** No flight controller confirmed physically wired to
  the Pi as of 2026-08-26 (checked: no `/dev/ttyUSB*`/`/dev/ttyACM*` present,
  only the Pi's own onboard `/dev/ttyAMA10` GPIO UART, which doesn't by itself
  indicate anything is plugged in). `pymavlink` is not installed. The
  ground-comms code (`deploy/mavlink_uplink.py`, `deploy/ground_receiver.py`)
  exists but has never been tested against real hardware. This is bench-test
  stage, not field-integration stage, as of this session.
