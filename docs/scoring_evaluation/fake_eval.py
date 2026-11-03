"""Fake-score sanity test on SYNTHETIC clusters.

52 genuine scenarios (from synthetic_eval.py) + 10 tricky genuine clusters + 21 rumour
clusters, scored by the real scoring module. The model term is empty (no fake-news model),
so the score in use is 0.385·(1−Credibility) + 0.231·ContentRisk + 0.385·AmplificationRisk.

Limitation: the rumours were written by the same team that designed the score, so this
checks that the score behaves as designed — it does not measure real misinformation detection.

Run from this folder:  python fake_eval.py
"""
import itertools
import json
import os
import random

import numpy as np

from synthetic_eval import DIM, NOW, PLACES, build_scenarios, score_clusters, unit

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 161
FLAG = 0.60
WEIGHTS = {"inv_credibility": 0.25, "content_risk": 0.15, "amplification_risk": 0.25}  # model slot empty

RUMOURS = {
    "copy_chain": {  # one message pasted many times within minutes
        "en": ["FORWARD TO ALL!!! Dam broke near {p}, whole city will flood tonight, 100% true",
               "BREAKING!!! Share this, {p} lake wall collapsed, water coming, media won't show"],
        "hi": ["सबको भेजो!!! {p} का बांध टूट गया, आज रात पूरा शहर डूब जाएगा"],
    },
    "hearsay_wave": {  # separately written posts repeating hearsay
        "en": ["heard that {p} hospital is closed and all doctors left",
               "people saying the water supply in {p} is poisoned, don't drink",
               "apparently army is evacuating {p} tonight, someone said",
               "rumour going around that {p} bridge will be blown up"],
        "hi": ["सुना है {p} में पानी में ज़हर मिला है"],
    },
    "translated_forward": {  # same message forwarded in several languages
        "en": ["Forward this to everyone: {p} reservoir gates opened, evacuate now"],
        "hi": ["सबको भेजो: {p} जलाशय के गेट खुल गए, तुरंत निकलो"],
        "kn": ["ಎಲ್ಲರಿಗೂ ಕಳುಹಿಸಿ: {p} ಜಲಾಶಯದ ಗೇಟ್ ತೆರೆದಿದೆ, ತಕ್ಷಣ ಹೊರಡಿ"],
    },
    "calm_rumour": {  # official-sounding, no forward words, spread slowly (hard case)
        "en": ["Government has announced all schools in {p} closed for two weeks due to flood",
               "Officials confirmed {p} metro will stop running from tomorrow"],
    },
}
TRICKY_GENUINE = {
    "urgent_share": {  # real emergency, posts ask people to share
        "en": ["Please share, flood water entering houses near {p}, families trapped, need boats",
               "Share this, {p} road flooded, people stuck in their cars, send help",
               "Please share widely, elderly people trapped by flood at {p}, rescue needed"],
        "hi": ["कृपया शेयर करें, {p} में बाढ़, लोग फंसे हुए हैं, मदद भेजो"],
    },
    "viral_genuine": {  # real fire, independent reports plus quick near-copies
        "en": ["Fire in apartment building at {p}, people trapped inside, send fire engines",
               "Huge fire near {p} market, smoke everywhere, people stuck on top floor",
               "Blaze at {p} complex, residents trapped, need rescue"],
    },
}


def post(cid, i, text, lang, created_at, emb, rng, nrng, disaster, need, neg):
    needs = {k: 0.05 for k in ("healthcare", "municipal", "tourism", "law")}
    needs["municipal"] = round(need, 3)
    return {"tweet_id": f"{cid}_{i}", "text": text, "lang": lang, "is_romanized": False, "is_code_mixed": False,
            "disaster_confidence": round(disaster, 3), "need_confidence": round(need, 3),
            "sentiment_confidence": round(max(neg, 1 - neg), 3), "sentiment_negativity": round(neg, 3),
            "needs": needs, "created_at": created_at, "embedding": emb.tolist(), "cluster_id": cid}


def make(cid, family, templates, fake, rng, nrng):
    place = rng.choice(PLACES)
    base = unit(nrng.normal(size=DIM))
    end = NOW - rng.uniform(0.2, 3) * 3600
    noisy = lambda x: float(np.clip(x + nrng.normal(0, 0.06), 0.05, 0.99))
    posts = []
    if family == "copy_chain":                       # 1 message, 4-7 copies within ~4 min
        lang = rng.choice(list(templates))
        text = rng.choice(templates[lang]).format(p=place)
        for i in range(rng.randint(5, 8)):
            posts.append(post(cid, i, text, lang, end - 240 + i * 30, base, rng, nrng, noisy(0.85), noisy(0.5), noisy(0.85)))
    elif family == "translated_forward":             # same message in 2-3 languages, minutes apart
        langs = list(templates)[: rng.randint(2, 3)]
        for i in range(rng.randint(4, 6)):
            lang = langs[i % len(langs)]
            emb = unit(base + nrng.normal(0, 0.05, size=DIM))   # translations: near-identical meaning
            posts.append(post(cid, i, templates[lang][0].format(p=place), lang, end - 600 + i * 90, emb,
                              rng, nrng, noisy(0.85), noisy(0.55), noisy(0.8)))
    elif family == "hearsay_wave":                   # separately written, over 30-90 min
        n = rng.randint(3, 5)
        for i in range(n):
            lang = "hi" if i == n - 1 else "en"
            text = rng.choice(templates[lang]).format(p=place)
            emb = unit(base + nrng.normal(0, 0.55, size=DIM))
            posts.append(post(cid, i, text, lang, end - rng.uniform(1800, 5400) + i, emb, rng, nrng,
                              noisy(0.7), noisy(0.45), noisy(0.7)))
    elif family == "calm_rumour":                    # few copies, spread over hours
        text = rng.choice(templates["en"]).format(p=place)
        for i in range(rng.randint(2, 4)):
            posts.append(post(cid, i, text, "en", end - i * 3600 * rng.uniform(1, 2), base, rng, nrng,
                              noisy(0.7), noisy(0.5), noisy(0.55)))
    elif family == "urgent_share":                   # independent genuine reports that say "share"
        for i in range(rng.randint(3, 5)):
            lang = "hi" if i == 2 else "en"
            emb = unit(base + nrng.normal(0, 0.55, size=DIM))
            posts.append(post(cid, i, rng.choice(templates[lang]).format(p=place), lang,
                              end - rng.uniform(0, 3600), emb, rng, nrng, noisy(0.92), noisy(0.88), noisy(0.92)))
    elif family == "viral_genuine":                  # 3 independent reports + 3-4 quick copies of one
        for i, text in enumerate(templates["en"]):
            emb = unit(base + nrng.normal(0, 0.55, size=DIM))
            posts.append(post(cid, i, text.format(p=place), "en", end - 1800 + i * 600, emb, rng, nrng,
                              noisy(0.92), noisy(0.85), noisy(0.9)))
        for j in range(rng.randint(3, 4)):
            posts.append({**posts[0], "tweet_id": f"{cid}_c{j}", "created_at": posts[0]["created_at"] + 60 * (j + 1)})
    return {"cluster_id": cid, "family": family, "fake": fake, "posts": posts}


def fake_score(terms, weights):
    values = {"inv_credibility": None if terms["credibility"] is None else 1 - terms["credibility"],
              "content_risk": terms["content_risk"], "amplification_risk": terms["amplification_risk"]}
    pairs = [(w, values[k]) for k, w in weights.items() if w > 0 and values[k] is not None]
    return sum(w * v for w, v in pairs) / sum(w for w, _ in pairs)


def metrics(clusters, weights, threshold):
    tp = sum(1 for c in clusters if c["fake"] and fake_score(c["terms"], weights) >= threshold)
    fp = sum(1 for c in clusters if not c["fake"] and fake_score(c["terms"], weights) >= threshold)
    fn = sum(1 for c in clusters if c["fake"] and fake_score(c["terms"], weights) < threshold)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def main():
    rng, nrng = random.Random(SEED), np.random.default_rng(SEED)
    clusters = [{"cluster_id": s["cluster_id"], "family": s["family"], "fake": False, "posts": s["posts"]}
                for s in build_scenarios()]
    plan = [("copy_chain", 6), ("hearsay_wave", 6), ("translated_forward", 5), ("calm_rumour", 4)]
    for family, n in plan:
        clusters += [make(f"R_{family}_{i}", family, RUMOURS[family], True, rng, nrng) for i in range(n)]
    for family, n in (("urgent_share", 5), ("viral_genuine", 5)):
        clusters += [make(f"G_{family}_{i}", family, TRICKY_GENUINE[family], False, rng, nrng) for i in range(n)]
    for c in clusters:
        scored, _ = score_clusters(c["posts"], {}, now=NOW)
        c["terms"], c["fake_score"] = scored[0]["terms"], scored[0]["fake_score"]
        assert abs(fake_score(c["terms"], WEIGHTS) - c["fake_score"]) < 1e-3

    n_fake = sum(c["fake"] for c in clusters)
    print(f"clusters: {len(clusters)} ({len(clusters) - n_fake} genuine, {n_fake} rumours)\n")

    print("fake score by group (min / median / max):")
    groups = {}
    for c in clusters:
        key = c["family"] if c["family"] in RUMOURS or c["family"] in TRICKY_GENUINE else "genuine (52 scenarios)"
        groups.setdefault(key, []).append(c["fake_score"])
    for key in ["genuine (52 scenarios)", "urgent_share", "viral_genuine", *RUMOURS]:
        xs = sorted(groups[key])
        flagged = sum(x >= FLAG for x in xs)
        print(f"  {key:<24} n={len(xs):>2}  {xs[0]:.2f} / {xs[len(xs) // 2]:.2f} / {xs[-1]:.2f}   flagged {flagged}/{len(xs)}")

    m = metrics(clusters, WEIGHTS, FLAG)
    print(f"\nat the 0.60 flag: precision {m['precision']:.0%}  recall {m['recall']:.0%}  F1 {m['f1']:.2f}"
          f"   (caught {m['tp']}, false alarms {m['fp']}, missed {m['fn']})")

    print("\nthreshold sweep:")
    sweep = []
    for t in (0.40, 0.45, 0.50, 0.55, 0.60, 0.65):
        r = metrics(clusters, WEIGHTS, t)
        sweep.append({"threshold": t, **r})
        print(f"  {t:.2f}  precision {r['precision']:.0%}  recall {r['recall']:.0%}  F1 {r['f1']:.2f}")

    terms = list(WEIGHTS)
    moves = []
    for a, b in itertools.permutations(terms, 2):
        w = dict(WEIGHTS)
        w[a] -= 0.05
        w[b] += 0.05
        moves.append(metrics(clusters, w, FLAG)["f1"])
    print(f"\nsensitivity (move 0.05 between two terms, 6 variations): F1 {min(moves):.2f} – {max(moves):.2f}")

    print("ablation (remove one term, F1 at 0.60):")
    ablation = {}
    for t in terms:
        ablation[t] = metrics(clusters, {k: v for k, v in WEIGHTS.items() if k != t}, FLAG)
        print(f"  without {t:<20} F1 {ablation[t]['f1']:.2f}  (recall {ablation[t]['recall']:.0%}, "
              f"false alarms {ablation[t]['fp']})")

    json.dump({"groups": {k: sorted(v) for k, v in groups.items()}, "at_flag": m, "sweep": sweep,
               "sensitivity_f1": [min(moves), max(moves)], "ablation": ablation},
              open(os.path.join(HERE, "fake_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
