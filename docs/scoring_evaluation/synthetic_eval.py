"""Priority-weight validation on SYNTHETIC crisis scenarios.

What this is: ~50 synthetic clusters (multilingual posts + model-style confidences +
synthetic embeddings) scored by the project's real scoring code (backend/app/scoring),
compared against an urgency band fixed by a written rubric BEFORE any scoring.
What it is not: a test against real-world human judgement (the rubric author also wrote
the scenarios) and not a test of the trained models (their outputs are simulated).

Run from this folder (Python 3.10+, numpy):  python synthetic_eval.py
Writes synthetic_scenarios.csv (one row per scenario: rubric band, score terms, predicted
bands) and synthetic_results.json (all figures). Fixed seed, so every run gives the same numbers.
"""
import csv
import itertools
import json
import os
import random
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
from app.scoring import score_clusters  # noqa: E402  (the real scoring module)

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 160
NOW = 1_780_100_000.0          # common clock, so Recency differs between clusters
DIM = 32

RUBRIC = """URGENCY RUBRIC (fixed before scoring; label depends only on the scenario):
  life-threatening event (people trapped / injured / inside a fire, water entering homes) + urgent request
      Critical  if >= 3 independent reports and last report <= 6 h old
      High      if 1-2 independent reports, or last report 6-24 h old
      Medium    if last report > 24 h old
  serious harm / infrastructure failure (roads submerged, bridge damaged, wide power cut, hospital full)
      High      if >= 2 independent reports and last report <= 12 h old
      Medium    otherwise
  service disruption (water shortage, garbage, traffic)
      Medium    if >= 3 independent reports and last report <= 12 h old
      Low       otherwise
  vague / non-actionable (no concrete event, sympathy, hearsay)
      Low"""

PLACES = ["Rajajinagar", "Jayanagar", "Malleswaram", "Whitefield", "Yelahanka", "Hebbal", "Shivajinagar", "Indiranagar"]

# Post templates per family and language ({p} place, {n} number). Texts use words the
# multilingual lexicons know, as real posts would.
TEMPLATES = {
    "flood_trapped": {
        "en": ["Flood water entering houses near {p}, {n} families trapped, need rescue urgently",
               "Water rising fast at {p}, people stuck on rooftops, please send boats now",
               "{p} flooded, elderly people trapped inside homes, emergency help needed"],
        "hi": ["{p} के पास बाढ़, घरों में पानी घुस गया, लोग फंसे हुए हैं, तुरंत मदद भेजो"],
        "kn": ["{p} ಬಳಿ ಪ್ರವಾಹ, ಮನೆಗಳಿಗೆ ನೀರು ನುಗ್ಗಿದೆ, ಜನರು ಸಿಲುಕಿದ್ದಾರೆ, ತುರ್ತು ಸಹಾಯ ಬೇಕು"],
        "ta": ["{p} பகுதியில் வெள்ளம், மக்கள் சிக்கியுள்ளனர், உடனே உதவி தேவை"],
    },
    "fire_people": {
        "en": ["Fire in apartment building at {p}, {n} people trapped inside, send fire engines now",
               "Huge fire near {p} market, smoke everywhere, people stuck on top floor, urgent",
               "Blaze at {p} complex, residents trapped, need rescue immediately"],
        "hi": ["{p} में इमारत में आग, लोग फंसे हुए हैं, तुरंत मदद भेजो"],
        "kn": ["{p} ಬಳಿ ಕಟ್ಟಡದಲ್ಲಿ ಬೆಂಕಿ, ಜನರು ಸಿಲುಕಿದ್ದಾರೆ, ತಕ್ಷಣ ಸಹಾಯ ಮಾಡಿ"],
    },
    "collapse_injured": {
        "en": ["Building collapsed near {p}, {n} injured, ambulance needed urgently",
               "Wall collapse at {p} construction site, workers injured and trapped, send help",
               "Old building fell down in {p}, people injured under debris, emergency"],
        "hi": ["{p} के पास इमारत ढह गई, कई लोग घायल, तुरंत एम्बुलेंस भेजो"],
        "kn": ["{p} ಬಳಿ ಕಟ್ಟಡ ಕುಸಿದಿದೆ, ಜನರು ಗಾಯಗೊಂಡಿದ್ದಾರೆ, ತುರ್ತು ಸಹಾಯ ಬೇಕು"],
    },
    "road_flooded": {
        "en": ["Roads submerged near {p} after heavy rain, traffic stopped for hours",
               "Bridge on the {p} road damaged by rain, vehicles not allowed",
               "Main road at {p} under water, buses not running"],
        "hi": ["{p} में बारिश से सड़कें बंद, पानी भरा है"],
        "kn": ["{p} ಬಳಿ ಭಾರೀ ಮಳೆ, ರಸ್ತೆಗಳು ಮುಳುಗಿವೆ"],
    },
    "power_outage": {
        "en": ["No electricity in {p} for {n} hours after the storm, hospital on generator",
               "Power cut across {p} since last night, transformers damaged",
               "Whole of {p} without power, electric wires fallen on the road"],
        "hi": ["{p} में {n} घंटे से बिजली नहीं है"],
        "kn": ["{p} ಪ್ರದೇಶದಲ್ಲಿ ವಿದ್ಯುತ್ ಇಲ್ಲ, ಕರೆಂಟ್ ಇಲ್ಲ"],
    },
    "hospital_full": {
        "en": ["Hospital at {p} full, no beds left, oxygen running low",
               "{p} government hospital emergency ward overcrowded, patients waiting outside",
               "No ICU beds available in {p}, ambulances turned away"],
        "hi": ["{p} अस्पताल में बेड नहीं, मरीज़ बाहर इंतज़ार कर रहे हैं"],
    },
    "water_shortage": {
        "en": ["No drinking water supply in {p} since yesterday",
               "Water shortage in {p} for {n} days, tanker not coming",
               "{p} residents complaining about no water in taps"],
        "hi": ["{p} में पानी की समस्या बहुत गंभीर है"],
        "kn": ["{p} ನಲ್ಲಿ ನೀರಿನ ಸಮಸ್ಯೆ ತೀವ್ರವಾಗಿದೆ"],
    },
    "garbage_traffic": {
        "en": ["Garbage not collected in {p} for a week, bad smell everywhere",
               "Traffic jam near {p} because the signal is not working",
               "Drainage blocked in {p}, dirty water on the street"],
        "hi": ["{p} में कचरा नहीं उठाया गया"],
    },
    "vague": {
        "en": ["something bad happening near {p} i think",
               "praying for everyone, stay safe",
               "heard there was some issue in the city today",
               "hope everyone is ok out there"],
        "hi": ["सब लोग सुरक्षित रहें"],
    },
}

# Simulated model outputs per family: (disaster_confidence, need_confidence, sentiment_negativity)
PROFILE = {
    "flood_trapped": (0.92, 0.88, 0.92), "fire_people": (0.92, 0.85, 0.92), "collapse_injured": (0.90, 0.86, 0.90),
    "road_flooded": (0.82, 0.78, 0.72), "power_outage": (0.78, 0.80, 0.70), "hospital_full": (0.75, 0.84, 0.78),
    "water_shortage": (0.62, 0.70, 0.62), "garbage_traffic": (0.55, 0.62, 0.58), "vague": (0.52, 0.25, 0.55),
}
DEPT = {
    "flood_trapped": "municipal", "fire_people": "municipal", "collapse_injured": "healthcare",
    "road_flooded": "municipal", "power_outage": "municipal", "hospital_full": "healthcare",
    "water_shortage": "municipal", "garbage_traffic": "municipal", "vague": "municipal",
}
KIND = {
    "flood_trapped": "life", "fire_people": "life", "collapse_injured": "life",
    "road_flooded": "serious", "power_outage": "serious", "hospital_full": "serious",
    "water_shortage": "disruption", "garbage_traffic": "disruption", "vague": "vague",
}


def rubric_band(kind, n_independent, age_h):
    if kind == "life":
        if age_h > 24:
            return "Medium"
        return "Critical" if n_independent >= 3 and age_h <= 6 else "High"
    if kind == "serious":
        return "High" if n_independent >= 2 and age_h <= 12 else "Medium"
    if kind == "disruption":
        return "Medium" if n_independent >= 3 and age_h <= 12 else "Low"
    return "Low"


def unit(v):
    return v / np.linalg.norm(v)


def make_cluster(cid, family, n_ind, n_copies, n_langs, age_h, rng, nrng):
    langs_available = [l for l in ("en", "hi", "kn", "ta") if l in TEMPLATES[family]]
    langs = ["en"] + [l for l in langs_available if l != "en"][: max(0, n_langs - 1)]
    place = rng.choice(PLACES)
    d0, n0, s0 = PROFILE[family]
    base = unit(nrng.normal(size=DIM))
    last = NOW - age_h * 3600
    posts = []
    for i in range(n_ind):
        lang = langs[i % len(langs)]
        text = rng.choice(TEMPLATES[family][lang]).format(p=place, n=rng.randint(3, 40))
        under = 0.15 if lang in ("hi", "kn") else 0.0   # known under-confidence on Indic text
        dc = float(np.clip(d0 - under + nrng.normal(0, 0.07), 0.05, 0.99))
        nc = float(np.clip(n0 + nrng.normal(0, 0.07), 0.02, 0.99))
        neg = float(np.clip(s0 + nrng.normal(0, 0.07), 0.02, 0.99))
        needs = {k: 0.05 for k in ("healthcare", "municipal", "tourism", "law")}
        needs[DEPT[family]] = round(nc, 3)
        emb = unit(base + nrng.normal(0, 0.55, size=DIM))   # independent reports: similar, not identical
        posts.append({
            "tweet_id": f"{cid}_p{i}", "text": text, "lang": lang, "is_romanized": False, "is_code_mixed": False,
            "disaster_confidence": round(dc, 3), "need_confidence": round(nc, 3),
            "sentiment_confidence": round(max(neg, 1 - neg), 3), "sentiment_negativity": round(neg, 3),
            "needs": needs, "created_at": last - (n_ind - 1 - i) * rng.uniform(300, 1800),
            "embedding": emb.tolist(), "cluster_id": cid,
        })
    for j in range(n_copies):  # copy-pastes of the first report (not independent)
        posts.append({**posts[0], "tweet_id": f"{cid}_c{j}", "created_at": posts[0]["created_at"] + 60 * (j + 1)})
    return {"cluster_id": cid, "family": family, "kind": KIND[family], "n_independent": n_ind,
            "n_copies": n_copies, "languages": langs, "age_hours": age_h,
            "label": rubric_band(KIND[family], n_ind, age_h), "posts": posts}


def build_scenarios():
    rng, nrng = random.Random(SEED), np.random.default_rng(SEED)
    # (family, n_independent, n_copies, n_languages, age_hours) — spread over the rubric's cases
    plan = []
    for fam in ("flood_trapped", "fire_people", "collapse_injured"):
        plan += [(fam, 6, 1, 3, 1), (fam, 4, 0, 2, 3), (fam, 3, 2, 1, 5), (fam, 2, 0, 1, 2),
                 (fam, 1, 0, 1, 1), (fam, 5, 0, 2, 14), (fam, 4, 1, 2, 30)]
    for fam in ("road_flooded", "power_outage", "hospital_full"):
        plan += [(fam, 7, 1, 3, 2), (fam, 3, 0, 2, 6), (fam, 2, 0, 1, 10), (fam, 1, 0, 1, 3), (fam, 4, 0, 2, 20)]
    for fam in ("water_shortage", "garbage_traffic"):
        plan += [(fam, 6, 0, 2, 4), (fam, 3, 1, 1, 8), (fam, 2, 0, 1, 2), (fam, 4, 0, 2, 26), (fam, 1, 0, 1, 1)]
    plan += [("vague", n, 0, 1, a) for n, a in ((1, 1), (2, 2), (3, 1), (1, 8), (4, 3), (2, 14))]
    return [make_cluster(f"S{i:02d}", *p, rng, nrng) for i, p in enumerate(plan, 1)]


# ---------------------------------------------------------------- scoring + formulas
BANDS = ["Low", "Medium", "High", "Critical"]
CUTS = [("Critical", 0.75), ("High", 0.55), ("Medium", 0.35), ("Low", 0.0)]
TERMS = ["severity", "actionability", "corroboration", "credibility", "recency"]
FINAL = {"severity": 0.30, "actionability": 0.25, "corroboration": 0.20, "credibility": 0.15, "recency": 0.10}


CURRENT_CUTS = (0.75, 0.55, 0.35)  # Critical / High / Medium lower bounds


def band(score):
    return next(name for name, lo in CUTS if score >= lo)


def cut_band(score, cuts):
    """Band index (0 = Low .. 3 = Critical) for alternative cut-offs."""
    critical, high, medium = cuts
    return 3 if score >= critical else 2 if score >= high else 1 if score >= medium else 0


def spearman(a, b):
    def ranks(v):
        order, out, i = sorted(range(len(v)), key=lambda k: v[k]), [0.0] * len(v), 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    return cov / (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5


def weighted(values, weights):
    pairs = [(w, values[k]) for k, w in weights.items() if values.get(k) is not None and w > 0]
    total = sum(w for w, _ in pairs)
    return sum(w * v for w, v in pairs) / total if total else 0.0


def top3(xs):
    xs = sorted((x for x in xs if x is not None), reverse=True)[:3]
    return sum(xs) / len(xs) if xs else None


def score_all(scenarios):
    for s in scenarios:
        scored, feats = score_clusters(s["posts"], {}, now=NOW)
        c = scored[0]
        s["terms"] = c["terms"]
        s["fake_score"], s["likely_fake"] = c["fake_score"], c["likely_fake"]
        need = top3([p["need_confidence"] for p in s["posts"]])
        urg = top3([f["urgency_kw"] for f in feats])
        s["old"] = {"need_severity": need, "sentiment": top3([p["sentiment_negativity"] for p in s["posts"]]),
                    "urgency": urg, "keyword": top3([f["severity_kw"] for f in feats]),
                    "need_urgency": (need + urg) / 2, "credibility": c["terms"]["credibility"],
                    "recency": c["terms"]["recency"]}


FORMULAS = {
    "v1 (Review 1)": lambda s: weighted(s["old"], {"need_urgency": 0.40, "sentiment": 0.20, "keyword": 0.15, "recency": 0.15}),
    "v2 (ESA)": lambda s: weighted(s["old"], {"need_severity": 0.35, "sentiment": 0.25, "urgency": 0.20,
                                             "credibility": 0.10, "recency": 0.10}),
    "current final": lambda s: weighted(s["terms"], FINAL),
}


def agreement(items, fn):
    exact = within = err = 0
    for s in items:
        p, h = BANDS.index(band(fn(s))), BANDS.index(s["label"])
        exact += p == h
        within += abs(p - h) <= 1
        err += abs(p - h)
    return {"exact": exact / len(items), "within_one": within / len(items), "band_error": err / len(items), "n": len(items)}


def grid():
    for a, b, c, d in itertools.product(range(1, 18), repeat=4):
        e = 20 - a - b - c - d
        if e >= 1:
            yield dict(zip(TERMS, (a / 20, b / 20, c / 20, d / 20, e / 20)))


GRID = list(grid())


def tune(items):
    def key(w):
        r = agreement(items, lambda s: weighted(s["terms"], w))
        return (-r["exact"], r["band_error"], sum(abs(w[k] - FINAL[k]) for k in TERMS))
    return min(GRID, key=key)


def stratified(items, k, seed):
    rng, by = random.Random(seed), defaultdict(list)
    for s in items:
        by[s["label"]].append(s)
    out, i = [[] for _ in range(k)], 0
    for label in sorted(by):
        group = by[label]
        rng.shuffle(group)
        for s in group:
            out[i % k].append(s)
            i += 1
    return out


def fmt(w):
    return "  ".join(f"{k} {w[k]:.2f}" for k in TERMS)


def main():
    scenarios = build_scenarios()
    score_all(scenarios)
    print(RUBRIC, "\n")
    print(f"scenarios: {len(scenarios)}   rubric labels: {dict(Counter(s['label'] for s in scenarios))}\n")

    parts = stratified(scenarios, 5, SEED)
    test = parts[0] + parts[1]                          # ~40 % untouched
    tune_set = [s for p in parts[2:] for s in p]        # ~60 % for the search
    best = tune(tune_set)
    formulas = {**FORMULAS, "best on tuning set": lambda s: weighted(s["terms"], best)}

    print(f"weight search: {len(GRID)} combinations (0.05 steps, every term >= 0.05)")
    print(f"best on tuning set ({len(tune_set)}): {fmt(best)}")
    print(f"current final weights:         {fmt(FINAL)}\n")
    print(f"{'formula':<20}{'tuning exact':>13}{'held-out exact':>16}{'held-out ±1':>13}{'held-out err':>14}")
    results = {}
    for name, fn in formulas.items():
        a, b = agreement(tune_set, fn), agreement(test, fn)
        results[name] = {"tuning": a, "held_out": b}
        print(f"{name:<20}{a['exact']:>13.0%}{b['exact']:>16.0%}{b['within_one']:>13.0%}{b['band_error']:>14.2f}")

    cv = []
    for i in range(5):
        train = [s for j, p in enumerate(parts) if j != i for s in p]
        w = tune(train)
        cv.append({"weights": w,
                   "tuned": agreement(parts[i], lambda s, w=w: weighted(s["terms"], w))["exact"],
                   **{n: agreement(parts[i], f)["exact"] for n, f in FORMULAS.items()}})
    print("\n5-fold cross-validation (exact band agreement on the left-out fold):")
    for key in ("tuned", *FORMULAS):
        xs = [r[key] for r in cv]
        print(f"  {key:<16} mean {sum(xs) / 5:.0%}   folds " + " ".join(f"{x:.0%}" for x in xs))
    print("  weights chosen in each fold:")
    for r in cv:
        print("   ", fmt(r["weights"]))

    full = agreement(scenarios, FORMULAS["current final"])["exact"]
    print(f"\nall {len(scenarios)} scenarios, current final formula: {full:.0%} exact")
    print("remove one term (others rescaled):")
    ablation = {}
    for t in TERMS:
        w = {k: v for k, v in FINAL.items() if k != t}
        ablation[t] = agreement(scenarios, lambda s, w=w: weighted(s["terms"], w))["exact"]
        print(f"  without {t:<14}{ablation[t]:.0%}")
    moves = []
    for a, b in itertools.permutations(TERMS, 2):
        w = dict(FINAL)
        w[a] -= 0.05
        w[b] += 0.05
        moves.append((agreement(scenarios, lambda s, w=w: weighted(s["terms"], w))["exact"], a, b))
    print(f"sensitivity: any single 0.05 shift between two terms gives {min(moves)[0]:.0%} – {max(moves)[0]:.0%}")

    print("\nheld-out confusion, current final formula (rows = rubric band, columns = predicted):")
    conf = Counter((s["label"], band(FORMULAS["current final"](s))) for s in test)
    print("            " + "".join(f"{b:>10}" for b in reversed(BANDS)))
    for h in reversed(BANDS):
        print(f"  {h:<10}" + "".join(f"{conf[(h, p)]:>10}" for p in reversed(BANDS)))

    # Where do the misses come from? Score ranges per rubric band, ranking quality, cut-offs.
    current = FORMULAS["current final"]
    print("\npriority (current formula) by rubric band:")
    ranges = {}
    for b in reversed(BANDS):
        xs = sorted(current(s) for s in scenarios if s["label"] == b)
        ranges[b] = (xs[0], xs[len(xs) // 2], xs[-1])
        print(f"  {b:<9} n={len(xs):>2}  min {xs[0]:.2f}  median {xs[len(xs) // 2]:.2f}  max {xs[-1]:.2f}")
    rho = spearman([current(s) for s in scenarios], [BANDS.index(s["label"]) for s in scenarios])
    print(f"rank correlation (Spearman) between priority and rubric urgency: {rho:.2f}")

    cut_grid = [(c / 100, h / 100, m / 100) for c in range(50, 91) for h in range(35, c) for m in range(20, h)]
    by_cuts = lambda items, cuts: sum(cut_band(current(s), cuts) == BANDS.index(s["label"]) for s in items) / len(items)
    pick = lambda items: max(cut_grid, key=lambda cuts: (by_cuts(items, cuts),
                                                        -sum(abs(a - b) for a, b in zip(cuts, CURRENT_CUTS))))
    best_cuts = pick(tune_set)
    print(f"\nband cut-offs (current weights): current {CURRENT_CUTS}: tuning {by_cuts(tune_set, CURRENT_CUTS):.0%}"
          f", held-out {by_cuts(test, CURRENT_CUTS):.0%}")
    print(f"                                 best on tuning {best_cuts}: tuning {by_cuts(tune_set, best_cuts):.0%}"
          f", held-out {by_cuts(test, best_cuts):.0%}")
    cut_cv = []
    for i in range(5):
        train = [s for j, p in enumerate(parts) if j != i for s in p]
        cuts = pick(train)
        cut_cv.append({"cuts": cuts, "tuned": by_cuts(parts[i], cuts), "current": by_cuts(parts[i], CURRENT_CUTS)})
    print(f"5-fold CV: tuned cut-offs mean {sum(r['tuned'] for r in cut_cv) / 5:.0%} vs current "
          f"{sum(r['current'] for r in cut_cv) / 5:.0%}; chosen per fold: {[r['cuts'] for r in cut_cv]}")

    flagged = [s["cluster_id"] for s in scenarios if s["likely_fake"]]
    print(f"\nfake flag on these genuine scenarios: {len(flagged)} of {len(scenarios)} flagged {flagged}")

    with open(os.path.join(HERE, "synthetic_scenarios.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cluster_id", "family", "independent_reports", "copies", "languages", "age_hours",
                    "rubric_band", *TERMS, "priority_current", "band_current", "priority_best", "band_best",
                    "split", "example_post"])
        test_ids = {s["cluster_id"] for s in test}
        for s in scenarios:
            pc, pb = FORMULAS["current final"](s), weighted(s["terms"], best)
            w.writerow([s["cluster_id"], s["family"], s["n_independent"], s["n_copies"], "/".join(s["languages"]),
                        s["age_hours"], s["label"], *[round(s["terms"][t], 3) for t in TERMS],
                        round(pc, 3), band(pc), round(pb, 3), band(pb),
                        "held-out" if s["cluster_id"] in test_ids else "tuning", s["posts"][0]["text"]])
    json.dump({"rubric": RUBRIC, "best_weights": best, "current_weights": FINAL, "results": results,
               "cv": cv, "ablation": ablation, "full_exact": full,
               "sensitivity_range": [min(moves)[0], max(moves)[0]], "fake_flagged": flagged,
               "priority_ranges_by_band": ranges, "spearman": rho,
               "cutoffs": {"best_on_tuning": best_cuts, "cv": cut_cv}},
              open(os.path.join(HERE, "synthetic_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
