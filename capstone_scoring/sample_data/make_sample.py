"""Builds sample_data/clustered_sample.json — synthetic, for demo/testing only.
Embeddings are tiny 16-d fake vectors (real IndicSBERT ones are 768-d)."""
import json, numpy as np
rng = np.random.default_rng(7)
T0 = 1_780_000_000  # fake simulator clock
def emb(base, noise): return (base + rng.normal(0, noise, base.shape)).round(4).tolist()
A, B, C, D = (rng.normal(0, 1, 16) for _ in range(4))

def tw(i, cid, text, lang, base, noise, t, rom=False, mix=False, dconf=0.9, nconf=0.9,
       sconf=0.85, neg=0.85, needs=None, origin=None):
    return {"tweet_id": f"tw_{i:03d}", "cluster_id": cid, "origin_id": origin, "text": text,
            "lang": lang, "is_romanized": rom, "is_code_mixed": mix,
            "is_disaster": True, "disaster_confidence": dconf,
            "needs": needs or {"healthcare": 0.1, "municipal": 0.95, "tourism": 0.02, "law": 0.05},
            "need_confidence": nconf, "sentiment_label": "negative",
            "sentiment_confidence": sconf, "sentiment_negativity": neg,
            "created_at": T0 + t, "embedding": emb(base, noise)}

data = [
 # Cluster 0 — real multilingual flood, independent reports
 tw(1, 0, "Flood in our area near Rajajinagar, water entered 20 houses, need urgent help", "en", A, .55, 0),
 tw(2, 0, "ರಾಜಾಜಿನಗರದಲ್ಲಿ ಪ್ರವಾಹ, ಮನೆಗಳಿಗೆ ನೀರು ನುಗ್ಗಿದೆ, ತುರ್ತು ಸಹಾಯ ಬೇಕು", "kn", A, .55, 600, dconf=.62, nconf=.6, sconf=.6),
 tw(3, 0, "hamare area me baadh aa gayi hai, log gharon me phanse hai, turant madad bhejo", "hi", A, .55, 1500, rom=True, mix=True, dconf=.7, nconf=.65),
 tw(4, 0, "எங்கள் பகுதியில் வெள்ளம், வீடுகளில் தண்ணீர் புகுந்தது, உடனே உதவி தேவை", "ta", A, .55, 2400, dconf=.6, nconf=.58, sconf=.62),
 tw(5, 0, "మా ప్రాంతంలో వరదలు, ఇళ్లలోకి నీరు వచ్చింది, వెంటనే సహాయం కావాలి", "te", A, .55, 3000, dconf=.63, nconf=.6, sconf=.6),
 tw(6, 0, "namma area alli pravaha, manege neeru bandide, ippo turtu sahaya beku", "kn", A, .55, 3600, rom=True, dconf=.55, nconf=.5, sconf=.55),
 # translated copy of tw_001 from the dataset (same origin) -> must count once
 tw(7, 0, "राजाजीनगर के पास हमारे इलाके में बाढ़, 20 घरों में पानी घुसा, तुरंत मदद चाहिए", "hi", A, .05, 3700, origin="tw_001", dconf=.66, nconf=.6),
 # Cluster 1 — copy-paste dam rumour
 tw(8, 1, "BREAKING!!! Dam broke, whole city will flood tonight. FORWARD TO ALL, media won't show", "en", B, .02, 0, dconf=.8, nconf=.5, neg=.9),
 tw(9, 1, "BREAKING!!! Dam broke, whole city will flood tonight. FORWARD TO ALL, media won't show", "en", B, .02, 60, dconf=.8, nconf=.5, neg=.9),
 tw(10, 1, "BREAKING!!! Dam broke, whole city will flood tonight. FORWARD TO ALL, media won't show", "en", B, .02, 90, dconf=.8, nconf=.5, neg=.9),
 tw(11, 1, "बांध टूट गया, आज रात पूरा शहर डूबेगा, सबको भेजो, सुना है सरकार छुपा रही है", "hi", B, .03, 150, dconf=.6, nconf=.45),
 tw(12, 1, "dam toot gaya bhai, sabko bhejo jaldi, suna hai sarkar chupa rahi hai", "hi", B, .03, 200, rom=True, mix=True, dconf=.6, nconf=.45),
 # Cluster 2 — older, milder power cut
 tw(13, 2, "No power in our colony since morning after the rain", "en", C, .3, -36000, dconf=.55, nconf=.7, neg=.6),
 tw(14, 2, "ಮಳೆಯಿಂದ ಬೆಳಿಗ್ಗೆಯಿಂದ ಕರೆಂಟ್ ಇಲ್ಲ", "kn", C, .3, -35000, dconf=.45, nconf=.55, neg=.55),
 # Noise (HDBSCAN -1) — vague single tweet
 tw(15, -1, "something bad happening i think", "en", D, .3, 3000, dconf=.4, nconf=.3, neg=.6),
]
json.dump(data, open("sample_data/clustered_sample.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(data), "tweets written")
