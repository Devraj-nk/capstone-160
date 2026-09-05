"""Tests for the pipeline handoff's Steps 3-6: Disaster Classification gate,
Language Detection, Sentiment Analysis, Need Detection, and the Combine step
that merges them into the record Clustering (Step 8) will consume.

The four Hugging Face model calls are mocked to safe, deterministic defaults
for every test via the mock_ml_inference autouse fixture in conftest.py, so
none of this requires downloading a model or having torch/transformers
installed. Tests below override that default locally with their own
monkeypatch.setattr call whenever the specific output value matters.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.analysis import combine, disaster_classification, need_detection, sentiment
from app.main import app
from app.preprocessing import language

client = TestClient(app)


def _show(step: str, text: str, output: object) -> None:
    """Quick eyeball helper: prints what went into a (mocked) model call and
    what came out, so `pytest -s` gives a readable input/output trace for
    each step. Doesn't affect pass/fail — run with -s to actually see it."""
    message = f"\n[{step}] IN:  {text!r}\n[{step}] OUT: {output!r}"
    try:
        print(message)
    except UnicodeEncodeError:
        # Windows terminals on a non-UTF-8 codepage can't print native-script
        # test strings directly — fall back to an ASCII-escaped form.
        print(message.encode("ascii", "backslashreplace").decode("ascii"))


# --- Step 4: language detection ---


def test_detect_by_script_recognizes_native_hindi_text():
    assert language.detect_by_script("यह बहुत ज़रूरी है") == "hi"


def test_detect_by_script_recognizes_native_kannada_text():
    assert language.detect_by_script("ಇದು ಬಹಳ ಮುಖ್ಯ") == "kn"


def test_detect_by_script_returns_none_for_latin_only_text():
    assert language.detect_by_script("this is plain english text") is None


def test_check_code_mixed_requires_both_native_and_latin_characters():
    assert language.check_code_mixed("this is plain english text") is False
    assert language.check_code_mixed("बहुत ज़रूरी है लेकिन traffic is really bad today") is True


def test_detect_language_final_native_script_skips_the_classifier(monkeypatch):
    calls = []
    monkeypatch.setattr(language, "_predict_with_classifier", lambda text: calls.append(text) or "xx")

    result = language.detect_language_final("यह बहुत ज़रूरी है")
    _show("language", "यह बहुत ज़रूरी है", result)

    assert result == {"lang": "hi", "is_romanized": False, "is_code_mixed": False}
    assert calls == []  # native-script text never reaches the model


def test_detect_language_final_romanized_text_uses_classifier_fallback(monkeypatch):
    monkeypatch.setattr(language, "_predict_with_classifier", lambda text: "kn")

    result = language.detect_language_final("nan yen madthidini gottilla")
    _show("language", "nan yen madthidini gottilla", result)

    assert result["lang"] == "kn"
    assert result["is_romanized"] is True  # classifier said kn, not en


def test_detect_language_final_english_is_not_flagged_romanized(monkeypatch):
    monkeypatch.setattr(language, "_predict_with_classifier", lambda text: "en")

    result = language.detect_language_final("flooding near the river bridge")
    _show("language", "flooding near the river bridge", result)

    assert result["lang"] == "en"
    assert result["is_romanized"] is False


def test_detect_language_final_handles_empty_text():
    assert language.detect_language_final("   ") == {
        "lang": None,
        "is_romanized": False,
        "is_code_mixed": False,
    }


# --- Step 3: disaster classification gate ---


def test_classify_disaster_passes_gate_above_threshold(monkeypatch):
    monkeypatch.setattr(disaster_classification, "_predict_disaster_probability", lambda text: 0.9)

    result = disaster_classification.classify_disaster("flood in my area", "en")
    _show("disaster", "flood in my area", result)

    assert result == {"is_disaster": True, "disaster_confidence": 0.9}


def test_classify_disaster_fails_gate_below_threshold(monkeypatch):
    monkeypatch.setattr(disaster_classification, "_predict_disaster_probability", lambda text: 0.2)

    result = disaster_classification.classify_disaster("nice weather today", "en")
    _show("disaster", "nice weather today", result)

    assert result["is_disaster"] is False


def test_classify_disaster_uses_per_language_threshold_when_configured(monkeypatch):
    monkeypatch.setattr(disaster_classification, "_predict_disaster_probability", lambda text: 0.6)
    monkeypatch.setitem(disaster_classification.PER_LANG_THRESHOLDS, "kn", 0.7)

    below_kn_threshold = disaster_classification.classify_disaster("something", "kn")
    _show("disaster (kn threshold=0.7)", "something", below_kn_threshold)
    assert below_kn_threshold["is_disaster"] is False  # 0.6 < 0.7 kn-specific threshold

    above_default_threshold = disaster_classification.classify_disaster("something", "en")
    _show("disaster (default threshold=0.5)", "something", above_default_threshold)
    assert above_default_threshold["is_disaster"] is True  # 0.6 >= 0.5 default, no en override set


# --- Step 5a: sentiment ---


def test_analyze_sentiment_negative_case(monkeypatch):
    monkeypatch.setattr(sentiment, "_predict_sentiment_probs", lambda text: [0.9943, 0.0057])

    result = sentiment.analyze_sentiment("flood in my area need help urgently")
    _show("sentiment", "flood in my area need help urgently", result)

    assert result["sentiment_label"] == "negative"
    assert result["sentiment_confidence"] == 0.9943
    assert result["sentiment_negativity"] == 0.9943
    assert result["sentiment_probabilities"] == {"negative": 0.9943, "positive": 0.0057}
    assert result["sentiment_model"] == sentiment.SENTIMENT_MODEL_PATH
    assert "sentiment_predicted_at" in result


def test_analyze_sentiment_positive_case_still_reports_negativity(monkeypatch):
    monkeypatch.setattr(sentiment, "_predict_sentiment_probs", lambda text: [0.05, 0.95])

    result = sentiment.analyze_sentiment("things are looking up now")
    _show("sentiment", "things are looking up now", result)

    assert result["sentiment_label"] == "positive"
    assert result["sentiment_negativity"] == 0.05  # always P(negative), regardless of which class won


# --- Step 5b: need detection ---


def test_detect_needs_returns_raw_probabilities_and_max_confidence(monkeypatch):
    monkeypatch.setattr(
        need_detection,
        "_predict_need_probs",
        lambda text: {"healthcare": 0.011, "municipal": 0.998, "tourism": 0.015, "law": 0.013},
    )

    result = need_detection.detect_needs("road flooded, municipal please help")
    _show("need_detection", "road flooded, municipal please help", result)

    assert result["needs"] == {"healthcare": 0.011, "municipal": 0.998, "tourism": 0.015, "law": 0.013}
    assert result["need_confidence"] == 0.998


def test_active_needs_applies_the_documented_per_label_thresholds():
    needs = {"healthcare": 0.7, "municipal": 0.5, "tourism": 0.9, "law": 0.66}
    # thresholds from the handoff doc: healthcare 0.65, municipal 0.80, tourism 0.75, law 0.65
    assert need_detection.active_needs(needs) == ["healthcare", "tourism", "law"]


# --- Step 6: combine ---


def test_actionability_score_tiers():
    assert combine.actionability_score("please send help immediately, trapped") == 1.0
    assert combine.actionability_score("please help, someone check on them") == 0.6
    assert combine.actionability_score("thoughts and prayers to everyone") == 0.2
    assert combine.actionability_score("nice weather today") == 0.0


def test_compute_severity_matches_the_documented_formula():
    assert combine.compute_severity(sentiment_negativity=0.9943, need_confidence=0.998) == round(
        0.6 * 0.998 + 0.4 * 0.9943, 4
    )


def test_combine_tweet_record_merges_disaster_language_sentiment_and_needs():
    sentiment_result = {"sentiment_negativity": 0.9943}
    needs_result = {
        "needs": {"healthcare": 0.011, "municipal": 0.998, "tourism": 0.015, "law": 0.013},
        "need_confidence": 0.998,
    }

    combined = combine.combine_tweet_record(
        tweet_id="tw_00981",
        text="flood in my area need help urgently",
        lang="en",
        is_disaster=True,
        disaster_confidence=0.87,
        created_at="2026-09-02T00:58:10+00:00",
        sentiment=sentiment_result,
        needs=needs_result,
    )

    assert combined["tweet_id"] == "tw_00981"
    assert combined["lang"] == "en"
    assert combined["is_disaster"] is True
    assert combined["disaster_confidence"] == 0.87
    assert combined["needs"] == needs_result["needs"]
    assert combined["need_confidence"] == 0.998
    assert combined["actionability"] == 1.0  # "urgently" contains the "urgent" keyword
    assert combined["severity"] == combine.compute_severity(0.9943, 0.998)
    assert "combined_at" in combined


# --- End to end: POST /analysis/pipeline ---


def test_analysis_pipeline_endpoint_runs_steps_3_to_6(monkeypatch):
    monkeypatch.setattr(language, "_predict_with_classifier", lambda text: "en")
    monkeypatch.setattr(disaster_classification, "_predict_disaster_probability", lambda text: 0.87)
    monkeypatch.setattr(sentiment, "_predict_sentiment_probs", lambda text: [0.9943, 0.0057])
    monkeypatch.setattr(
        need_detection,
        "_predict_need_probs",
        lambda text: {"healthcare": 0.011, "municipal": 0.998, "tourism": 0.015, "law": 0.013},
    )

    response = client.post(
        "/analysis/pipeline",
        json={
            "tweet_id": "tw_00981",
            "text": "flood in my area need help urgently",
            "created_at": "2026-09-02T00:58:10+00:00",
        },
    )

    assert response.status_code == 200
    body = response.json()
    _show("/analysis/pipeline", "flood in my area need help urgently", body)

    assert body["tweet_id"] == "tw_00981"
    assert body["lang"] == "en"
    assert body["is_romanized"] is False
    assert body["is_code_mixed"] is False
    assert body["is_disaster"] is True
    assert body["disaster_confidence"] == 0.87
    assert body["needs"]["municipal"] == 0.998
    assert body["need_confidence"] == 0.998
    assert body["actionability"] == 1.0
    assert body["severity"] == combine.compute_severity(0.9943, 0.998)


def test_analysis_pipeline_endpoint_handles_romanized_code_mixed_text(monkeypatch):
    monkeypatch.setattr(language, "_predict_with_classifier", lambda text: "kn")
    monkeypatch.setattr(disaster_classification, "_predict_disaster_probability", lambda text: 0.3)
    monkeypatch.setattr(sentiment, "_predict_sentiment_probs", lambda text: [0.6, 0.4])
    monkeypatch.setattr(
        need_detection,
        "_predict_need_probs",
        lambda text: {"healthcare": 0.02, "municipal": 0.05, "tourism": 0.01, "law": 0.01},
    )

    response = client.post(
        "/analysis/pipeline",
        json={"tweet_id": "tw_1", "text": "nan yen madthidini gottilla", "created_at": "2026-09-02T00:00:00+00:00"},
    )

    assert response.status_code == 200
    body = response.json()
    _show("/analysis/pipeline", "nan yen madthidini gottilla", body)

    assert body["lang"] == "kn"
    assert body["is_romanized"] is True
    assert body["is_disaster"] is False  # 0.3 below default 0.5 threshold


# --- Wiring check: language detection inside POST /preprocessing/preprocess ---


def test_preprocess_endpoint_reports_language_for_valid_posts():
    response = client.post(
        "/preprocessing/preprocess", json={"text": "यह बहुत ज़रूरी है, please send help"}
    )
    body = response.json()

    assert body["is_valid"] is True
    assert body["lang"] == "hi"
    assert body["is_romanized"] is False
    assert body["is_code_mixed"] is True


def test_preprocess_endpoint_skips_language_detection_for_dropped_reposts():
    client.post("/preprocessing/preprocess", json={"text": "Flooding near MG Road, send help!"})
    repost = client.post(
        "/preprocessing/preprocess", json={"text": "RT @someone: Flooding near MG Road, send help!"}
    ).json()

    assert repost["dropped"] is True
    assert repost["lang"] is None
