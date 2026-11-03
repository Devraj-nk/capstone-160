"""Step 10 — summary & evidence (app/scoring/summary_evidence.py), covering the
tests listed in docs/Step 10 — Summary & Evidence Spec.pdf."""

from __future__ import annotations

from collections import Counter

import pytest

from app.scoring import score_clusters, summarise_cluster
from app.scoring.lexicons import EVENT_LABELS, IMPACT
from app.scoring.summary_evidence import EVENT_LEX
from app.scoring.summary_templates import PHRASES, SUMMARY_LANGUAGES, render_summary
from app.scoring.text_utils import tokenize
from app.scoring.translate import translate_to_en

BASE_TS = 1_780_000_000
MUNICIPAL = {"healthcare": 0.1, "municipal": 0.9, "tourism": 0.02, "law": 0.05}


def emb(slot: int) -> list[float]:
    """Shared direction + one distinct axis: different slots are similar
    (cosine ~0.67, independent reports), equal slots are copies (cosine 1)."""
    vector = [1.0] + [0.0] * 8
    vector[1 + slot] = 0.7
    return vector


def post(tweet_id, text, lang="en", slot=0, minutes=0, embedding=True, **extra) -> dict:
    record = {
        "tweet_id": tweet_id,
        "text": text,
        "lang": lang,
        "is_romanized": False,
        "is_code_mixed": False,
        "cluster_id": 0,
        "created_at": BASE_TS + minutes * 60,
        "disaster_confidence": 0.9,
        "need_confidence": 0.9,
        "sentiment_negativity": 0.8,
        "needs": MUNICIPAL,
    }
    if embedding:
        record["embedding"] = emb(slot)
    record.update(extra)
    return record


def run(records, **kwargs):
    clusters, feats = score_clusters(records, {})
    assert len(clusters) == 1
    cluster = clusters[0]
    return summarise_cluster(cluster, records, feats, cluster["dup_groups"], now=0, **kwargs)


def evidence_ids(out) -> list[str]:
    return [e["tweet_id"] for e in out["evidence"]]


def test_one_post_per_copy_group_and_translated_copies_count_once():
    records = [
        post("a", "Flood near Rajajinagar, water entered 20 houses, need help", slot=0),
        post("a_copy", "Flood near Rajajinagar, water entered 20 houses, need help", slot=0, minutes=1),
        post("b", "ರಾಜಾಜಿನಗರದಲ್ಲಿ ಪ್ರವಾಹ, ಸಹಾಯ ಬೇಕು", lang="kn", slot=1, origin_id="src-1"),
        post("b_hi", "राजाजीनगर में बाढ़, मदद चाहिए", lang="hi", slot=2, origin_id="src-1"),
        post("c", "எங்கள் பகுதியில் வெள்ளம், உதவி தேவை", lang="ta", slot=3),
    ]
    ids = evidence_ids(run(records))
    assert len(ids) == 3
    assert not {"a", "a_copy"} <= set(ids)
    assert "b_hi" not in ids  # same origin_id as b -> one report
    assert "c" in ids


def test_at_most_two_posts_per_language_while_others_remain():
    records = [post(f"en{i}", f"Flood near Rajajinagar report {i} need help", slot=i) for i in range(4)]
    records += [
        post("kn0", "ರಾಜಾಜಿನಗರದಲ್ಲಿ ಪ್ರವಾಹ", lang="kn", slot=4),
        post("kn1", "ಮನೆಗಳಿಗೆ ನೀರು ನುಗ್ಗಿದೆ ಪ್ರವಾಹ", lang="kn", slot=5),
        post("hi0", "हमारे इलाके में बाढ़ आ गई है", lang="hi", slot=6),
    ]
    out = run(records)
    langs = Counter(e["lang"] for e in out["evidence"])
    assert len(out["evidence"]) == 5
    assert set(langs) == {"en", "kn", "hi"}
    assert max(langs.values()) <= 2
    assert any("different language" in e["why"] for e in out["evidence"])


def test_forward_chain_post_excluded_when_clean_reports_exist():
    records = [
        post("clean1", "Flood near Rajajinagar, need help", slot=0),
        post("clean2", "Water entering houses near Rajajinagar", slot=1),
        post("fwd", "Forward to all, flood is coming to the whole city", slot=2),
    ]
    out = run(records)
    assert "fwd" not in evidence_ids(out)
    assert out["representative"]["tweet_id"] != "fwd"


def test_forward_chain_posts_included_when_every_report_has_them():
    records = [
        post("f1", "Forward to all, dam broke near Rajajinagar", slot=0),
        post("f2", "Share this, flood coming to Rajajinagar tonight", slot=1),
    ]
    assert set(evidence_ids(run(records))) == {"f1", "f2"}


def test_summary_never_contains_a_slot_without_data():
    out = run([
        post("a", "Something bad happening here", slot=0, needs={"municipal": 0.1, "healthcare": 0.05}),
        post("b", "Something strange going on", slot=1, needs={"municipal": 0.1, "healthcare": 0.05}),
    ])
    text = out["summary"]["text_en"]
    assert text == "Incident reported. 2 independent reports in 1 language."
    for absent in ("near", "Main need", "urgent", "Warning", "over the last"):
        assert absent not in text


def test_summary_fills_every_slot_when_data_exists():
    records = [
        post("a", "Flood near Rajajinagar, water entered 20 houses, need urgent help", slot=0),
        post("b", "ರಾಜಾಜಿನಗರದಲ್ಲಿ ಪ್ರವಾಹ, ಮನೆಗಳಿಗೆ ನೀರು ನುಗ್ಗಿದೆ, ತುರ್ತು ಸಹಾಯ ಬೇಕು", lang="kn", slot=1, minutes=30),
        post("c", "Rajajinagar flooded, water entering houses, please help", slot=2, minutes=50,
             needs={"healthcare": 0.6, "municipal": 0.9, "tourism": 0.0, "law": 0.0}),
    ]
    assert run(records)["summary"]["text_en"] == (
        "Flooding reported near Rajajinagar: water entering houses, people asking for urgent help. "
        "3 independent reports in 2 languages over the last hour. Main need: Municipal."
    )


def test_second_department_shown_only_at_or_above_half():
    needs = {"healthcare": 0.6, "municipal": 0.9}
    out = run([post("a", "Flood here", slot=0, needs=needs), post("b", "Flood there", slot=1, needs=needs)])
    assert "Main need: Municipal; also Healthcare." in out["summary"]["text_en"]


@pytest.mark.parametrize(
    "text",
    [
        "Flood in our area, water everywhere",          # en
        "हमारे इलाके में बाढ़ आ गई है",                    # hi
        "hamare area me baadh aa gayi hai",             # hi_rom
        "ನಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ಪ್ರವಾಹ ಬಂದಿದೆ",                  # kn
        "namma pradeshadalli pravaha bandide",          # kn_rom
        "எங்கள் பகுதியில் வெள்ளம் வந்துள்ளது",              # ta
        "engal pagudhiyil vellam vandhirukku",          # ta_rom
        "మా ప్రాంతంలో వరదలు వచ్చాయి",                      # te
        "maa prantham lo varadalu vachayi",             # te_rom
    ],
)
def test_event_word_found_in_all_nine_language_forms(text):
    assert EVENT_LEX["flood"].match(tokenize(text))


def test_same_input_gives_same_output():
    records = [post(f"p{i}", f"Flood near Rajajinagar update {i}", slot=i, minutes=i) for i in range(6)]
    assert run(records) == run([dict(r) for r in records])


def test_singleton_cluster_gets_one_evidence_post():
    out = run([post("only", "Flood near Rajajinagar, need help")])
    assert evidence_ids(out) == ["only"]
    assert out["representative"]["tweet_id"] == "only"
    assert "1 independent report in 1 language." in out["summary"]["text_en"]


def test_all_copies_gives_one_post_and_rumour_warning():
    text = "Dam broke near Rajajinagar, whole city will flood tonight"
    records = [post(f"c{i}", text, slot=0, minutes=i) for i in range(4)]
    out = run(records)
    assert evidence_ids(out) == ["c0"]  # the original, not a later copy
    assert out["summary"]["text_en"].endswith("Warning: possible copy-paste rumour.")


def test_without_embeddings_similarity_is_skipped_and_scores_stay_in_range():
    records = [
        post("a", "Flood near Rajajinagar, 20 houses, need help", embedding=False),
        post("b", "Flooding in our area near Rajajinagar", embedding=False),
        post("c", "Water entering houses near Rajajinagar", embedding=False),
    ]
    out = run(records)
    assert len(out["evidence"]) == 3
    assert all(0.0 <= e["score"] <= 1.0 for e in out["evidence"])
    assert all("closest to event" not in e["why"] for e in out["evidence"])


def test_evidence_reasons_and_output_shape():
    out = run([
        post("a", "Flood near Rajajinagar, water entered 20 houses, need help", slot=0),
        post("b", "ರಾಜಾಜಿನಗರದಲ್ಲಿ ಪ್ರವಾಹ", lang="kn", slot=1),
    ])
    assert set(out) == {"cluster_id", "summary", "representative", "evidence", "evidence_version"}
    assert out["summary"]["method"] == "template_v1"
    first, second = out["evidence"]
    assert first["tweet_id"] == "a" and "location + number" in first["why"]
    assert second["tweet_id"] == "b" and "different language" in second["why"]
    assert all(1 <= len(e["why"]) <= 2 for e in out["evidence"])


def test_translation_hook():
    assert translate_to_en("Flood here", "en") == "Flood here"
    assert translate_to_en("ಪ್ರವಾಹ", "kn") is None          # IndicTrans2 not wired in yet
    assert translate_to_en("Flood here", "en", translate=False) == "Flood here"
    out = run([post("a", "Flood here", slot=0), post("b", "ಪ್ರವಾಹ ಬಂದಿದೆ", lang="kn", slot=1)])
    by_id = {e["tweet_id"]: e for e in out["evidence"]}
    assert by_id["a"]["text_en"] == "Flood here"
    assert by_id["b"]["text_en"] is None


# --- summary in every project language ---

FULL_SLOT_FLOOD = [
    post("a", "Flood near Rajajinagar, water entered 20 houses, need urgent help", slot=0),
    post("b", "ರಾಜಾಜಿನಗರದಲ್ಲಿ ಪ್ರವಾಹ, ಮನೆಗಳಿಗೆ ನೀರು ನುಗ್ಗಿದೆ, ತುರ್ತು ಸಹಾಯ ಬೇಕು", lang="kn", slot=1, minutes=30),
    post("c", "Rajajinagar flooded, water entering houses, please help", slot=2, minutes=50,
         needs={"healthcare": 0.6, "municipal": 0.9, "tourism": 0.0, "law": 0.0}),
]


def test_summary_is_rendered_in_all_five_languages():
    summary = run(FULL_SLOT_FLOOD)["summary"]
    assert set(summary["text"]) == set(SUMMARY_LANGUAGES) == {"en", "hi", "kn", "ta", "te"}
    assert summary["text"]["en"] == summary["text_en"] == (
        "Flooding reported near Rajajinagar: water entering houses, people asking for urgent help. "
        "3 independent reports in 2 languages over the last hour. Main need: Municipal."
    )
    for lang in ("hi", "kn", "ta", "te"):
        text = summary["text"][lang]
        assert PHRASES[lang]["events"]["flood"] in text
        assert PHRASES[lang]["impacts"]["water entering houses"] in text
        assert PHRASES[lang]["departments"]["municipal"] in text
        assert "Rajajinagar" in text and "3" in text and "2" in text
        for english in ("reported", "Main need", "independent", "language", "Flooding"):
            assert english not in text
    assert summary["text"]["hi"].endswith("।")


def test_empty_slots_leave_no_orphan_phrases_in_any_language():
    summary = run([
        post("a", "Something bad happening here", slot=0, needs={"municipal": 0.1}),
        post("b", "Something strange going on", slot=1, needs={"municipal": 0.1}),
    ])["summary"]
    for lang in SUMMARY_LANGUAGES:
        text = summary["text"][lang]
        p = PHRASES[lang]
        assert text.startswith(p["incident"])
        near_word = p["near"].replace("{loc}", "").strip()
        need_word = p["need"].split(":")[0]
        for absent in (near_word, need_word, p["warning"], p["urgent"]):
            assert absent not in text


def test_every_event_impact_and_department_has_a_phrase_in_every_language():
    for lang in SUMMARY_LANGUAGES:
        p = PHRASES[lang]
        assert set(p["events"]) == set(EVENT_LABELS)
        assert set(p["impacts"]) == set(IMPACT)
        assert set(p["departments"]) == {"healthcare", "municipal", "law", "tourism"}


def test_render_all_slots_and_fallback_to_english():
    slots = {
        "event": "fire", "location": "Majestic", "impact": "people trapped", "urgent": True,
        "n_unique": 4, "n_langs": 3, "span": ("hours", 5), "main_dept": "healthcare",
        "second_dept": "law", "warning": True,
    }
    assert render_summary(slots, "en") == (
        "Fire reported near Majestic: people trapped, people asking for urgent help. "
        "4 independent reports in 3 languages over the last 5 hours. "
        "Main need: Healthcare; also Law & Order. Warning: possible copy-paste rumour."
    )
    assert render_summary(slots, "xx") == render_summary(slots, "en")
    kannada = render_summary(slots, "kn")
    assert kannada.startswith("Majestic ಬಳಿ ಬೆಂಕಿ ಅವಘಡ ವರದಿಯಾಗಿದೆ: ")
    assert "ಕಳೆದ 5 ಗಂಟೆಗಳಲ್ಲಿ 3 ಭಾಷೆಗಳಲ್ಲಿ 4 ಸ್ವತಂತ್ರ ವರದಿಗಳು." in kannada
    assert "; ಜೊತೆಗೆ ಕಾನೂನು ಮತ್ತು ಸುವ್ಯವಸ್ಥೆ." in kannada
