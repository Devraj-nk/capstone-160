"""English translation for reviewers (step 10 `text_en`).

Hook for IndicTrans2 (ai4bharat indic->en), not wired in yet: non-English
text returns None and the console shows the original only. The original text
is always kept next to any translation, because a translation can be wrong.
"""
from functools import lru_cache


@lru_cache(maxsize=4096)
def _translate(text: str, lang: str):
    return None                      # TODO: IndicTrans2 inference


def translate_to_en(text, lang, translate: bool = True):
    if not text:
        return None
    if (lang or "").lower() == "en":
        return text
    if not translate:
        return None
    try:
        return _translate(text, lang)
    except Exception:                # translation failure -> original only
        return None
