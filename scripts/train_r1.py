"""HTN Wallhacks R1 — aerial person detection baseline on VisDrone."""
from ultralytics import YOLO

DATA  = r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\data\merged\person.yaml"
OUT   = r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\models"

LAST_CKPT = r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\models\htn_r1-2\weights\last.pt"

def main():
    import os
    # Resume from checkpoint if it exists, otherwise start fresh
    start = LAST_CKPT if os.path.exists(LAST_CKPT) else "yolo11n.pt"
    model = YOLO(start)
    results = model.train(
        data=DATA,
        epochs=100,
        imgsz=640,
        batch=8,          # was 16 — VisDrone has 50-200 boxes/image, OOMs at 16
        device=0,
        project=OUT,
        name="htn_r1",
        patience=20,
        workers=2,        # was 4
        mosaic=1.0,
        scale=0.5,
        flipud=0.5,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        translate=0.2,
    )
    print("\n=== R1 TRAINING DONE ===")
    print(f"Best mAP50:    {results.results_dict.get('metrics/mAP50(B)', 'N/A'):.4f}")
    print(f"Best mAP50-95: {results.results_dict.get('metrics/mAP50-95(B)', 'N/A'):.4f}")

    best = results.save_dir / "weights" / "best.pt"
    print(f"\nExporting ONNX from {best} ...")
    m = YOLO(str(best))
    m.export(format="onnx", imgsz=640, simplify=True)
    print("ONNX export done.")

if __name__ == "__main__":
    main()
