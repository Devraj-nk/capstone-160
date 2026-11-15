from app.preprocessing.language import ID2LANG, label_to_lang


def test_generic_model_labels_map_to_language_codes():
    # The published model's config says LABEL_0..LABEL_4; lang2id.json gives the order.
    assert [label_to_lang(f"LABEL_{i}", i) for i in range(5)] == ["en", "hi", "kn", "ta", "te"]


def test_real_language_labels_are_kept_and_unknown_ids_are_flagged():
    assert label_to_lang("kn", 0) == "kn"
    assert label_to_lang("LABEL_9", 9) == "unknown"
    assert set(ID2LANG.values()) == {"en", "hi", "kn", "ta", "te"}
