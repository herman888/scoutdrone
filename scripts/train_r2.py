"""HTN Wallhacks R2 — YOLO11s upgrade for higher mAP on VisDrone person detection."""
from ultralytics import YOLO

DATA = r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\data\merged\person.yaml"
OUT  = r"C:\Users\aclie\OneDrive\Documents\LARP\htn-wallhacks\models"

def main():
    model = YOLO("yolo11s.pt")
    results = model.train(
        data=DATA,
        epochs=100,
        imgsz=640,
        batch=4,
        device=0,
        project=OUT,
        name="htn_r2b",
        patience=20,
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
    print("\n=== R2 TRAINING DONE ===")
    print(f"Best mAP50:    {results.results_dict.get('metrics/mAP50(B)', 0):.4f}")
    print(f"Best mAP50-95: {results.results_dict.get('metrics/mAP50-95(B)', 0):.4f}")

    best = results.save_dir / "weights" / "best.pt"
    print(f"\nExporting ONNX from {best} ...")
    m = YOLO(str(best))
    m.export(format="onnx", imgsz=640, simplify=True)
    print("ONNX export done.")

if __name__ == "__main__":
    main()
