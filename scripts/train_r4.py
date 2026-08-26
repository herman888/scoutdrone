"""HTN Wallhacks R4 -- rebalanced mixed close+aerial range person detector.
Same as R3 but VisDrone is oversampled 2x in the training mix to counter
CrowdHuman's ~2.3x numerical majority, aiming to recover aerial accuracy
lost in R3 (0.554 -> 0.463 mAP50 on VisDrone-only) without losing R3's
close-range gain (0.831 mAP50 on CrowdHuman-only)."""
from ultralytics import YOLO

DATA = r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\data\mixed\person_mixed_balanced.yaml"
OUT = r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\models"

def main():
    model = YOLO("yolo11s.pt")
    results = model.train(
        data=DATA,
        epochs=40,
        imgsz=640,
        batch=4,
        device=0,
        project=OUT,
        name="htn_r4",
        patience=15,
        workers=2,
        mosaic=1.0,
        scale=0.5,
        flipud=0.5,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        translate=0.2,
    )
    print("\n=== R4 TRAINING DONE ===")
    print(f"Best mAP50:    {results.results_dict.get('metrics/mAP50(B)', 0):.4f}")
    print(f"Best mAP50-95: {results.results_dict.get('metrics/mAP50-95(B)', 0):.4f}")

    best = results.save_dir / "weights" / "best.pt"
    print(f"\nExporting ONNX from {best} ...")
    m = YOLO(str(best))
    m.export(format="onnx", imgsz=640, simplify=True)
    print("ONNX export done.")

if __name__ == "__main__":
    main()
