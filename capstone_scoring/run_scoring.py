"""
Score clustered tweets.

Usage:
  python run_scoring.py --input sample_data/clustered_sample.json --out-dir outputs
  python run_scoring.py --input my_clusters.jsonl --out-dir outputs --now 1767225600

Input: .json (list of tweet dicts) or .jsonl (one tweet dict per line).
Outputs: outputs/clusters_scored.json, outputs/tweets_scored.jsonl
"""
import argparse
import json
import os

from scoring import is_calibrated, language_fairness_report, load_calibration, score_clusters


def load_records(path):
    with open(path, encoding="utf-8") as f:
        if path.endswith(".jsonl"):
            return [json.loads(line) for line in f if line.strip()]
        return json.load(f)


def fmt(v):
    return "  -  " if v is None else f"{v:.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", default="outputs")
    ap.add_argument("--calibration", default=None, help="path to lang_confidence_ref.json")
    ap.add_argument("--now", type=float, default=None,
                    help="unix time for Recency (default: latest created_at in input)")
    args = ap.parse_args()

    tweets = load_records(args.input)
    cal = load_calibration(args.calibration)
    if not is_calibrated(cal):
        print("[note] No language calibration loaded -> raw model confidences used.\n"
              "       Run fit_calibration.py on validation predictions to fix this.\n")

    clusters, tweet_feats = score_clusters(tweets, cal, now=args.now)

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "clusters_scored.json"), "w", encoding="utf-8") as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out_dir, "tweets_scored.jsonl"), "w", encoding="utf-8") as f:
        for t in tweet_feats:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    print(f"{'cluster':<14}{'n':>3} {'band':<9}{'prio':>6} {'fake':>6}  "
          f"{'sev':>5}{'act':>5}{'corr':>5}{'cred':>5}{'rec':>5}  langs")
    for c in clusters:
        t = c["terms"]
        flag = " ⚠fake" if c["likely_fake"] else ""
        print(f"{str(c['cluster_id']):<14}{c['n_tweets']:>3} {c['band']:<9}{c['priority']:>6.2f} "
              f"{fmt(c['fake_score']):>6}  {fmt(t['severity']):>5}{fmt(t['actionability']):>5}"
              f"{fmt(t['corroboration']):>5}{fmt(t['credibility']):>5}{fmt(t['recency']):>5}  "
              f"{','.join(c['details']['languages'])}{flag}")

    if not any(c["fake_model_used"] for c in clusters):
        print("\n[note] No fake_prob in input -> Fake-Score uses the other 3 terms, re-weighted.")

    print("\nLanguage fairness check (mean per language):")
    report = language_fairness_report(tweet_feats)
    cols = ["text_quality", "specificity", "model_confidence", "credibility",
            "severity", "actionability"]
    print(f"{'lang':<12}{'n':>4}  " + "".join(f"{c[:11]:>12}" for c in cols))
    for lang, row in sorted(report.items()):
        print(f"{lang:<12}{row['n']:>4}  " + "".join(f"{fmt(row.get(c)):>12}" for c in cols))
    print(f"\nSaved to {args.out_dir}/")


if __name__ == "__main__":
    main()
