"""Run with:  pytest -q"""
import math

import pytest

from scoring import config
from scoring.calibration import calibrate, fit_calibration, lang_key
from scoring.cluster_scoring import group_reports, priority_band, score_clusters
from scoring.text_utils import CompiledLexicon, has_number, tokenize
from scoring.tweet_features import LEX, compute_tweet_features, weighted_sum

# The SAME message ("flood in our area, water entered houses, urgent help needed")
# in all 9 forms we support.
SAME_MESSAGE = {
    "en": ("Flood in our area, water entered houses, need urgent help", "en", False, False),
    "hi": ("हमारे इलाके में बाढ़, घरों में पानी घुसा, तुरंत मदद चाहिए", "hi", False, False),
    "hi_rom": ("hamare ilake me baadh, gharon me paani ghusa, turant madad chahiye", "hi", True, False),
    "kn": ("ನಮ್ಮ ಏರಿಯಾದಲ್ಲಿ ಪ್ರವಾಹ, ಮನೆಗಳಿಗೆ ನೀರು ನುಗ್ಗಿದೆ, ತುರ್ತು ಸಹಾಯ ಬೇಕು", "kn", False, False),
    "kn_rom": ("namma area alli pravaha, manege neeru bandide, turtu sahaya beku", "kn", True, False),
    "ta": ("எங்கள் பகுதியில் வெள்ளம், வீடுகளில் தண்ணீர் புகுந்தது, உடனே உதவி தேவை", "ta", False, False),
    "ta_rom": ("enga area la vellam, veetla thanni pugundhuchu, udane udhavi venum", "ta", True, False),
    "te": ("మా ప్రాంతంలో వరదలు, ఇళ్లలోకి నీరు వచ్చింది, వెంటనే సహాయం కావాలి", "te", False, False),
    "te_rom": ("maa area lo varadalu, intlo neellu vachayi, ventane sahayam kavali", "te", True, False),
}


def rec(text, lang="en", rom=False, mix=False, **kw):
    base = {"tweet_id": kw.pop("tweet_id", "t"), "text": text, "lang": lang,
            "is_romanized": rom, "is_code_mixed": mix, "disaster_confidence": 0.8,
            "need_confidence": 0.8, "sentiment_confidence": 0.8, "sentiment_negativity": 0.8}
    base.update(kw)
    return base


# ---------------- tokenizer ----------------
def test_tokenizer_keeps_indic_words_whole():
    assert tokenize("ಸಹಾಯ ಬೇಕು!") == ["ಸಹಾಯ", "ಬೇಕು"]
    assert tokenize("உதவி தேவை।") == ["உதவி", "தேவை"]


def test_indic_digits_count_as_numbers():
    for t in ["२० घर", "೨೦ ಮನೆ", "௨௦ வீடு", "౨౦ ఇళ్ళు", "20 houses"]:
        assert has_number(tokenize(t)), t


# ---------------- lexicon matching ----------------
@pytest.mark.parametrize("form", list(SAME_MESSAGE))
def test_urgency_found_in_every_language_form(form):
    text = SAME_MESSAGE[form][0]
    assert LEX["urgency"].match(tokenize(text)), f"no urgency word found for {form}"


@pytest.mark.parametrize("form", list(SAME_MESSAGE))
def test_location_and_infrastructure_found_in_every_form(form):
    toks = tokenize(SAME_MESSAGE[form][0])
    assert LEX["location"].match(toks) or LEX["place_names"].match(toks), form
    assert LEX["infrastructure"].match(toks), form


def test_prefix_match_handles_indic_suffixes():
    assert "ಸಹಾಯ*" in LEX["urgency"].match(tokenize("ಸಹಾಯಕ್ಕೆ ಬನ್ನಿ"))


def test_no_false_positive_on_similar_words():
    # ಗಾಯಕ = singer, must not count as "injured"
    assert not LEX["severity"].match(tokenize("ಗಾಯಕ ಹಾಡಿದರು"))
    # "carpet" must not match a place-name ending
    assert not LEX["place_names"].match(tokenize("new carpet"))


def test_inner_match_place_with_case_suffix():
    assert LEX["place_names"].match(tokenize("ರಾಜಾಜಿನಗರದಲ್ಲಿ ಪ್ರವಾಹ"))


def test_phrase_with_apostrophe():
    assert "media won't show" in LEX["forward_chain"].match(tokenize("Media won't show this!"))


def test_repeated_word_counts_once():
    lex = CompiledLexicon({"en": ["help"]})
    assert len(lex.match(tokenize("help help help help"))) == 1


# ---------------- fairness ----------------
def test_same_message_scores_similarly_across_languages():
    """Core fairness check: same content -> similar quality/specificity/actionability."""
    feats = {f: compute_tweet_features(rec(t, l, r, m), cal={})
             for f, (t, l, r, m) in SAME_MESSAGE.items()}
    for key in ("text_quality", "specificity", "actionability"):
        vals = [f[key] for f in feats.values()]
        assert max(vals) - min(vals) <= 0.25, (key, {k: round(f[key], 2) for k, f in feats.items()})


def test_short_kannada_tweet_not_penalized_for_length():
    f = compute_tweet_features(rec("ಪ್ರವಾಹ ಬಂದಿದೆ ಸಹಾಯ ಬೇಕು", "kn"), cal={})
    assert f["tq_length"] == 1.0          # 4 tokens is a complete Kannada sentence


def test_code_mixed_not_penalized_by_script_check():
    f = compute_tweet_features(rec("ಮನೆಗೆ water bandide help maadi", "kn", mix=True), cal={})
    assert f["tq_script"] == 1.0


def test_calibration_lifts_low_confidence_language():
    cal = {"disaster_confidence": {"en": 0.9, "kn": 0.6}}
    assert calibrate(0.6, "disaster_confidence", "kn", cal) == pytest.approx(1.0)
    assert calibrate(0.6, "disaster_confidence", "en", cal) == pytest.approx(0.6 / 0.9)
    # romanized Kannada not fitted -> falls back to native Kannada reference
    assert calibrate(0.3, "disaster_confidence", "kn_rom", cal) == pytest.approx(0.5)


def test_fit_calibration_needs_enough_samples():
    recs = [{"lang": "kn", "disaster_confidence": 0.6}] * config.MIN_SAMPLES_FOR_CALIBRATION
    recs += [{"lang": "ta", "disaster_confidence": 0.5}] * 3
    cal = fit_calibration(recs)
    assert cal["disaster_confidence"] == {"kn": 0.6}


def test_lang_key():
    assert lang_key("kn", True, False) == "kn_rom"
    assert lang_key("hi", True, True) == "code_mixed"
    assert lang_key("en", True, False) == "en"


# ---------------- formulas ----------------
def test_weighted_sum_renormalizes_missing_terms():
    w = {"a": 0.5, "b": 0.5}
    assert weighted_sum({"a": 1.0, "b": None}, w) == pytest.approx(1.0)
    assert weighted_sum({"a": None, "b": None}, w) is None


def test_locked_weights_sum_to_one():
    for w in (config.PRIORITY_WEIGHTS, config.FAKE_WEIGHTS, config.CREDIBILITY_WEIGHTS):
        assert math.isclose(sum(w.values()), 1.0)


@pytest.mark.parametrize("score,band", [(0.75, "Critical"), (0.749, "High"), (0.55, "High"),
                                        (0.54, "Medium"), (0.35, "Medium"), (0.34, "Low")])
def test_bands(score, band):
    assert priority_band(score) == band


# ---------------- clusters ----------------
def _vec(seed, n=16):
    import numpy as np
    return np.random.default_rng(seed).normal(0, 1, n).tolist()


def test_translations_of_same_origin_count_once():
    members = [rec(t, l, r, m, tweet_id=f, origin_id="src_1") for f, (t, l, r, m) in SAME_MESSAGE.items()]
    report_idx, groups = group_reports(members)
    assert len(report_idx) == 1 and len(groups) == 1


def test_multilingual_independent_reports_beat_copy_paste():
    import numpy as np
    base = np.array(_vec(1))
    rng = np.random.default_rng(2)
    real = [dict(rec(t, l, r, m, tweet_id=f, cluster_id="real", created_at=1000 + i * 600),
                 embedding=(base + rng.normal(0, 0.6, 16)).tolist())
            for i, (f, (t, l, r, m)) in enumerate(SAME_MESSAGE.items())]
    copy_text = "BREAKING!!! dam broke, forward to all, media won't show"
    fake = [dict(rec(copy_text, "en", tweet_id=f"c{i}", cluster_id="copy", created_at=1000 + i * 30),
                 embedding=_vec(9)) for i in range(6)]
    clusters, _ = score_clusters(real + fake, cal={}, now=6000)
    by_id = {c["cluster_id"]: c for c in clusters}
    assert by_id["real"]["terms"]["corroboration"] > by_id["copy"]["terms"]["corroboration"]
    assert by_id["copy"]["terms"]["amplification_risk"] > by_id["real"]["terms"]["amplification_risk"]
    assert by_id["copy"]["fake_score"] > by_id["real"]["fake_score"]
    assert by_id["real"]["priority"] > by_id["copy"]["priority"]
    assert len(by_id["real"]["details"]["languages"]) == 5


def test_noise_tweets_become_singletons():
    clusters, _ = score_clusters([rec("help", tweet_id="x", cluster_id=-1)], cal={})
    assert clusters[0]["cluster_id"] == "single_x"


def test_missing_embeddings_still_score():
    clusters, _ = score_clusters([rec("flood near school help", tweet_id="a", cluster_id=1),
                                  rec("ಶಾಲೆ ಬಳಿ ಪ್ರವಾಹ", "kn", tweet_id="b", cluster_id=1)], cal={})
    assert 0.0 <= clusters[0]["priority"] <= 1.0
