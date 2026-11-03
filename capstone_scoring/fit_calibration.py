"""
Fit per-language confidence calibration from VALIDATION-set predictions.

Usage:
  python fit_calibration.py --input val_predictions.jsonl

Each line needs: lang, is_romanized, is_code_mixed, and any of
disaster_confidence / need_confidence / sentiment_confidence.
Use the validation split, never the test split (same overfitting trap as the
per-language threshold bug fixed earlier).
"""
import argparse
import json
import os

from run_scoring import load_records
from scoring import config, fit_calibration


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default=config.CALIBRATION_FILE)
    args = ap.parse_args()

    cal = fit_calibration(load_records(args.input))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2)

    print(f"Saved {args.out}")
    for field, by_lang in cal.items():
        print(f"  {field}: " + (", ".join(f"{k}={v}" for k, v in sorted(by_lang.items()))
                                or f"(no language had >= {config.MIN_SAMPLES_FOR_CALIBRATION} samples)"))


if __name__ == "__main__":
    main()
