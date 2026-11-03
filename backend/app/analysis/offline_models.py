"""Offline, keyword/hashing stand-ins for the five Hugging Face models.

Used when torch/transformers aren't installed (MODEL_BACKEND=auto) or when
forced with MODEL_BACKEND=offline, so the full pipeline can run on a laptop
with no model downloads. These are NOT trained models — every output they
produce is a heuristic and must be reported as such. They replace exactly the
same private `_predict_*` hooks the test suite monkeypatches, so every piece
of schema/threshold logic around them is still the real code.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging

import numpy as np

from ..scoring.lexicons import SEVERITY, URGENCY
from ..scoring.text_utils import CompiledLexicon, normalize, saturating_score, tokenize

logger = logging.getLogger(__name__)

# Disaster-event words. URGENCY/SEVERITY (multilingual, from the scoring
# module) are reused alongside these for the disaster gate.
_DISASTER_EVENTS = CompiledLexicon({
    "en": ["flood*", "fire*", "earthquake*", "cyclone*", "landslide*", "storm*", "rain*",
           "collapse*", "blaze", "smoke", "accident*", "outage", "evacuat*", "tsunami",
           "drought", "waterlog*", "submerged", "shortage", "damage*", "blocked",
           "stranded", "trapped", "relief", "rescue*", "emergency", "ambulance",
           "landslip", "winds", "overcrowded", "no beds", "oxygen"],
    "hi": ["बाढ़*", "आग", "भूकंप", "तूफान", "बारिश", "पानी", "एम्बुलेंस", "पुल", "टूट*",
           "गंभीर", "बचाव", "सुरक्षित"],
    "kn": ["ಪ್ರವಾಹ*", "ಬೆಂಕಿ", "ಮಳೆ*", "ನೀರು*", "ನೀರಿನ", "ಅವಘಡ*", "ಮುಳುಗಿ*", "ವಿದ್ಯುತ್"],
    "ta": ["வெள்ள*", "தீ", "மழை*", "நிலநடுக்க*"],
    "te": ["వరద*", "అగ్ని*", "వర్ష*", "భూకంప*"],
})
_SEVERITY = CompiledLexicon(SEVERITY)
_URGENCY = CompiledLexicon(URGENCY)

_NEGATIVE = CompiledLexicon({
    "en": ["no", "not", "dead", "death*", "injur*", "trapped", "worse*", "severe", "danger*",
           "damage*", "lost", "loss", "scared", "afraid", "worried", "unsafe", "struggl*",
           "delay*", "complain*", "protest*", "shortage", "broken", "collapse*", "stuck",
           "stranded", "full", "lacks", "poor", "foul", "gone", "massive", "heavy"],
    "hi": ["नहीं", "गंभीर", "खराब", "परेशान", "समस्या", "मौत", "घायल", "टूट*"],
    "kn": ["ಇಲ್ಲ", "ಸಮಸ್ಯೆ", "ತೀವ್ರ*", "ಬಂದಿಲ್ಲ"],
    "ta": ["இல்லை", "பிரச்சனை"],
    "te": ["లేదు", "సమస్య"],
})
_POSITIVE = CompiledLexicon({
    "en": ["safe", "safely", "thanks", "thank", "restored", "resolved", "relief", "good",
           "fine", "ok", "okay", "great", "recovered", "rescued"],
    "hi": ["सुरक्षित", "धन्यवाद", "ठीक"],
    "kn": ["ಸುರಕ್ಷಿತ*", "ಧನ್ಯವಾದ*"],
    "ta": ["பாதுகாப்பா*", "நன்றி"],
    "te": ["సురక్షిత*", "ధన్యవాద*"],
})

_NEEDS = {
    "healthcare": CompiledLexicon({
        "en": ["hospital*", "doctor*", "medic*", "ambulance*", "injur*", "blood", "oxygen",
               "health", "fever", "beds", "patient*", "ward", "medicine*", "sanitation"],
        "hi": ["अस्पताल", "डॉक्टर", "दवा*", "एम्बुलेंस", "घायल"],
        "kn": ["ಆಸ್ಪತ್ರೆ*", "ವೈದ್ಯ*", "ಔಷಧ*", "ಆಂಬ್ಯುಲೆನ್ಸ್"],
        "ta": ["மருத்துவ*", "ஆம்புலன்ஸ்"],
        "te": ["ఆసుపత్రి*", "వైద్య*"],
    }),
    "municipal": CompiledLexicon({
        "en": ["water", "flood*", "road*", "power", "electric*", "drain*", "garbage", "sewage",
               "outage", "pipeline", "supply", "bridge", "tree*", "wires", "logging",
               "submerged", "buses", "traffic", "fire*", "blaze", "warehouse", "buildings",
               "evacuat*", "relief", "shelter*", "rescue*", "landslide*", "collapse*"],
        "hi": ["पानी", "सड़क", "बिजली", "पुल", "बाढ़*", "बारिश", "यातायात", "आग"],
        "kn": ["ನೀರು*", "ನೀರಿನ", "ರಸ್ತೆ*", "ವಿದ್ಯುತ್", "ಮಳೆ*", "ಬೆಂಕಿ", "ಟ್ರಾಫಿಕ್"],
        "ta": ["தண்ணீர்", "சாலை*", "மின்*", "வெள்ள*"],
        "te": ["నీరు", "రోడ్డు*", "విద్యుత్", "వరద*"],
    }),
    "law": CompiledLexicon({
        "en": ["police", "theft", "loot*", "violence", "riot*", "attack*", "robbery", "crime",
               "fight*", "protest*", "complaint*", "officials", "authorities", "safety"],
        "hi": ["पुलिस", "चोरी", "हिंसा", "अधिकारी"],
        "kn": ["ಪೊಲೀಸ್", "ಕಳ್ಳತನ", "ಸರ್ಕಾರಿ"],
        "ta": ["காவல்*", "போலீஸ்"],
        "te": ["పోలీస్*", "దొంగ*"],
    }),
    "tourism": CompiledLexicon({
        "en": ["tourist*", "tourism", "trek*", "hotel*", "pilgrim*", "hill", "station",
               "resort*", "travel*", "visitors"],
        "hi": ["पर्यटक*", "यात्री*"],
        "kn": ["ಪ್ರವಾಸಿ*"],
        "ta": ["சுற்றுலா*"],
        "te": ["పర్యాటక*"],
    }),
}

# Romanized-Indic function words for the Latin-script language fallback.
_ROMANIZED_MARKERS = {
    "hi": {"hai", "hain", "nahi", "nahin", "kya", "mein", "madad", "paani", "bahut", "kar",
           "karo", "bachao", "jaldi", "raha", "rahi", "gaya", "koi", "aur", "ho"},
    "kn": {"illi", "maadi", "madi", "ide", "beku", "nimma", "namma", "yenu", "illa", "bandide",
           "sahaya", "neeru", "gottilla", "madthidini", "nan", "yen"},
    "ta": {"romba", "enna", "vandhu", "irukku", "udhavi", "tanni", "seekiram", "illai"},
    "te": {"ledu", "undi", "emi", "kavali", "sahayam", "neellu", "chala", "ikkada"},
}

# Coarse multilingual topics shared across languages, so the offline
# embedding can put a Kannada fire report next to an English one.
_TOPICS = {
    "flood": CompiledLexicon({
        "en": ["flood*", "waterlog*", "logging", "submerged", "inundat*", "river"],
        "hi": ["बाढ़*", "घुस*"], "kn": ["ಪ್ರವಾಹ*", "ಮುಳುಗಿ*", "ತುಂಬಿದೆ"],
        "ta": ["வெள்ள*"], "te": ["వరద*"],
    }),
    "rain_storm": CompiledLexicon({
        "en": ["rain*", "storm*", "cyclone*", "winds", "weather"],
        "hi": ["बारिश", "तूफान"], "kn": ["ಮಳೆ*"], "ta": ["மழை*"], "te": ["వర్ష*"],
    }),
    "fire": CompiledLexicon({
        "en": ["fire*", "blaze", "smoke", "burn*"],
        "hi": ["आग"], "kn": ["ಬೆಂಕಿ*"], "ta": ["தீ"], "te": ["అగ్ని*"],
    }),
    "water_supply": CompiledLexicon({
        "en": ["drinking", "shortage", "pipeline", "supply"],
        "hi": ["पानी"], "kn": ["ನೀರಿನ"], "ta": ["தண்ணீர்"], "te": ["నీరు"],
    }),
    "power": CompiledLexicon({
        "en": ["power", "electric*", "outage", "wires"],
        "hi": ["बिजली"], "kn": ["ವಿದ್ಯುತ್"], "ta": ["மின்*"], "te": ["విద్యుత్"],
    }),
    "road_traffic": CompiledLexicon({
        "en": ["road*", "traffic", "highway", "bridge", "buses", "jam"],
        "hi": ["सड़क", "पुल", "यातायात"], "kn": ["ರಸ್ತೆ*", "ಟ್ರಾಫಿಕ್"], "ta": ["சாலை*"], "te": ["రోడ్డు*"],
    }),
    "medical": CompiledLexicon({
        "en": ["hospital*", "ambulance*", "oxygen", "beds", "injur*", "medical", "ward"],
        "hi": ["अस्पताल", "एम्बुलेंस"], "kn": ["ಆಸ್ಪತ್ರೆ*"], "ta": ["மருத்துவ*"], "te": ["ఆసుపత్రి*"],
    }),
    "sanitation": CompiledLexicon({"en": ["garbage", "sanitation", "sewage", "drain*", "smell"]}),
    "landslide": CompiledLexicon({"en": ["landslide*", "landslip*"]}),
    "tourism": CompiledLexicon({
        "en": ["tourist*", "tourism", "hill", "trek*"], "hi": ["पर्यटक*"], "kn": ["ಪ್ರವಾಸಿ*"],
    }),
    "public_order": CompiledLexicon({
        "en": ["police", "protest*", "riot*", "officials", "authorities"],
        "hi": ["पुलिस", "अधिकारी"], "kn": ["ಪೊಲೀಸ್", "ಸರ್ಕಾರಿ"],
    }),
}

EMBEDDING_DIM = 384


def _hits(lex: CompiledLexicon, tokens: list[str]) -> int:
    return len(lex.match(tokens))


def predict_disaster_probability(text: str) -> float:
    tokens = tokenize(text)
    hits = _hits(_DISASTER_EVENTS, tokens) + _hits(_SEVERITY, tokens) + _hits(_URGENCY, tokens)
    hits += sum(_hits(lex, tokens) for lex in _NEEDS.values())
    return round(0.15 + 0.8 * saturating_score(hits, 0.4), 4)


def predict_sentiment_probs(text: str) -> list[float]:
    tokens = tokenize(text)
    neg_hits = _hits(_NEGATIVE, tokens) + _hits(_SEVERITY, tokens) + _hits(_URGENCY, tokens)
    pos_hits = _hits(_POSITIVE, tokens)
    negativity = 0.5 + 0.45 * saturating_score(neg_hits, 0.5) - 0.45 * saturating_score(pos_hits, 0.5)
    negativity = min(0.98, max(0.02, negativity))
    return [negativity, 1.0 - negativity]


def predict_need_probs(text: str) -> dict[str, float]:
    tokens = tokenize(text)
    return {
        name: round(0.03 + 0.94 * saturating_score(_hits(lex, tokens), 0.25), 4)
        for name, lex in _NEEDS.items()
    }


def predict_language(text: str) -> str:
    tokens = set(tokenize(text))
    scores = {lang: len(tokens & markers) for lang, markers in _ROMANIZED_MARKERS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "en"


def _hashed(features: list[str]) -> np.ndarray:
    vector = np.zeros(EMBEDDING_DIM)
    for feature in features:
        digest = hashlib.md5(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % EMBEDDING_DIM
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector


def generate_embedding(text: str) -> list[float]:
    """Unit-length surface vector (hashed word + character-trigram bag) plus
    one unit per matched multilingual topic, L2-normalised. Only a crude
    stand-in for IndicSBERT's learned cross-lingual semantics."""
    if not text.strip():
        raise ValueError("Cannot embed empty text")
    norm_text = normalize(text)
    tokens = tokenize(norm_text)
    padded = f" {norm_text} "
    surface = _hashed([f"w:{tok}" for tok in tokens] + [f"c:{padded[i:i + 3]}" for i in range(len(padded) - 2)])
    topics = [f"t:{name}" for name, lex in _TOPICS.items() if lex.match(tokens)]
    vector = surface + (_hashed(topics) * np.sqrt(len(topics)) if topics else 0.0)
    norm = np.linalg.norm(vector)
    return (vector / norm).tolist() if norm else vector.tolist()


def install() -> None:
    """Swap every model hook for its offline stand-in."""
    from . import clustering, disaster_classification, embedding, need_detection, sentiment
    from ..preprocessing import language

    language._predict_with_classifier = predict_language
    disaster_classification._predict_disaster_probability = predict_disaster_probability
    sentiment._predict_sentiment_probs = predict_sentiment_probs
    need_detection._predict_need_probs = predict_need_probs
    embedding.generate_embedding = generate_embedding
    embedding.EMBEDDING_MODEL_ID = f"offline-hashing-{EMBEDDING_DIM}"
    clustering.generate_embedding = generate_embedding


def hf_stack_available() -> bool:
    return all(importlib.util.find_spec(name) for name in ("torch", "transformers", "sentence_transformers"))


def configure_model_backend(mode: str) -> str:
    """Resolve MODEL_BACKEND (auto|hf|offline) to the backend actually used."""
    mode = (mode or "auto").lower()
    if mode == "offline" or (mode == "auto" and not hf_stack_available()):
        install()
        logger.warning(
            "MODEL_BACKEND=%s: using OFFLINE heuristic models (keyword/hashing), "
            "not the fine-tuned Hugging Face models.",
            mode,
        )
        return "offline"
    return "hf"
