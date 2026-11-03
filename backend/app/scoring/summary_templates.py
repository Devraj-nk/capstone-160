"""
Step 10 summary rendered in each project language from the same slots.

The summary is still a template filled only from computed fields (no model,
no translation): `summary_evidence.summary_slots()` extracts the facts once and
`render_summary(slots, lang)` writes them in English, Hindi, Kannada, Tamil or
Telugu. A slot with no data is left out in every language, so no sentence is
left with a dangling postposition. Place names stay as extracted (e.g.
"Rajajinagar") and digits stay ASCII.

FIRST DRAFT: the non-English phrases below need a native-speaker review, the
same as the keyword lexicons. Fix wording here only — never add facts that
aren't a slot.
"""
from .lexicons import EVENT_LABELS, IMPACT

SUMMARY_LANGUAGES = ("en", "hi", "kn", "ta", "te")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _span_first(span, langs, reports) -> str:
    """Indic word order: time, languages, then the count."""
    return " ".join(part for part in (span, langs, reports) if part)


PHRASES = {
    "en": {
        "events": dict(EVENT_LABELS),
        "incident": "Incident",
        "first": "{event} reported{near}{details}",
        "near": " near {loc}",
        "impacts": {phrase: phrase for phrase in IMPACT},
        "urgent": "people asking for urgent help",
        "span": lambda unit, n: "over the last hour" if unit == "hour" else f"over the last {n} {unit}",
        "count": lambda n, k, span: (
            _plural(n, "independent report")
            + (f" in {_plural(k, 'language')}" if k else "")
            + (f" {span}" if span else "")
        ),
        "need": "Main need: {main}",
        "also": "; also {second}",
        "departments": {
            "healthcare": "Healthcare",
            "municipal": "Municipal",
            "law": "Law & Order",
            "tourism": "Tourism",
        },
        "warning": "Warning: possible copy-paste rumour",
        "list_sep": ", ",
        "end": ".",
    },
    "hi": {
        "events": {
            "flood": "बाढ़",
            "fire": "आग",
            "earthquake": "भूकंप",
            "landslide": "भूस्खलन",
            "cyclone": "चक्रवात",
            "collapse": "इमारत ढहने",
            "rain": "भारी बारिश",
        },
        "incident": "घटना",
        "first": "{near}{event} की सूचना{details}",
        "near": "{loc} के पास ",
        "impacts": {
            "people trapped": "लोग फंसे हुए हैं",
            "people killed": "लोगों की मौत",
            "people injured": "लोग घायल",
            "water entering houses": "घरों में पानी घुस रहा है",
            "bridge damaged": "पुल क्षतिग्रस्त",
            "roads blocked": "सड़कें बंद",
            "power outage": "बिजली गुल",
            "water shortage": "पानी की कमी",
        },
        "urgent": "लोग तुरंत मदद मांग रहे हैं",
        "span": lambda unit, n: {"hour": "पिछले एक घंटे में", "hours": f"पिछले {n} घंटों में",
                                 "days": f"पिछले {n} दिनों में"}[unit],
        "count": lambda n, k, span: _span_first(
            span, (f"{k} भाषा में" if k == 1 else f"{k} भाषाओं में") if k else None, f"{n} स्वतंत्र रिपोर्ट"
        ),
        "need": "मुख्य ज़रूरत: {main}",
        "also": "; साथ ही {second}",
        "departments": {
            "healthcare": "स्वास्थ्य सेवा",
            "municipal": "नगरपालिका",
            "law": "कानून व्यवस्था",
            "tourism": "पर्यटन",
        },
        "warning": "चेतावनी: संभवतः कॉपी-पेस्ट अफ़वाह",
        "list_sep": ", ",
        "end": "।",
    },
    "kn": {
        "events": {
            "flood": "ಪ್ರವಾಹ",
            "fire": "ಬೆಂಕಿ ಅವಘಡ",
            "earthquake": "ಭೂಕಂಪ",
            "landslide": "ಭೂಕುಸಿತ",
            "cyclone": "ಚಂಡಮಾರುತ",
            "collapse": "ಕಟ್ಟಡ ಕುಸಿತ",
            "rain": "ಭಾರೀ ಮಳೆ",
        },
        "incident": "ಘಟನೆ",
        "first": "{near}{event} ವರದಿಯಾಗಿದೆ{details}",
        "near": "{loc} ಬಳಿ ",
        "impacts": {
            "people trapped": "ಜನರು ಸಿಲುಕಿದ್ದಾರೆ",
            "people killed": "ಜನರು ಮೃತಪಟ್ಟಿದ್ದಾರೆ",
            "people injured": "ಜನರು ಗಾಯಗೊಂಡಿದ್ದಾರೆ",
            "water entering houses": "ಮನೆಗಳಿಗೆ ನೀರು ನುಗ್ಗುತ್ತಿದೆ",
            "bridge damaged": "ಸೇತುವೆಗೆ ಹಾನಿ",
            "roads blocked": "ರಸ್ತೆಗಳು ಬಂದ್",
            "power outage": "ವಿದ್ಯುತ್ ಕಡಿತ",
            "water shortage": "ನೀರಿನ ಕೊರತೆ",
        },
        "urgent": "ಜನರು ತುರ್ತು ಸಹಾಯ ಕೇಳುತ್ತಿದ್ದಾರೆ",
        "span": lambda unit, n: {"hour": "ಕಳೆದ ಒಂದು ಗಂಟೆಯಲ್ಲಿ", "hours": f"ಕಳೆದ {n} ಗಂಟೆಗಳಲ್ಲಿ",
                                 "days": f"ಕಳೆದ {n} ದಿನಗಳಲ್ಲಿ"}[unit],
        "count": lambda n, k, span: _span_first(
            span,
            (f"{k} ಭಾಷೆಯಲ್ಲಿ" if k == 1 else f"{k} ಭಾಷೆಗಳಲ್ಲಿ") if k else None,
            f"{n} ಸ್ವತಂತ್ರ ವರದಿ" if n == 1 else f"{n} ಸ್ವತಂತ್ರ ವರದಿಗಳು",
        ),
        "need": "ಮುಖ್ಯ ಅಗತ್ಯ: {main}",
        "also": "; ಜೊತೆಗೆ {second}",
        "departments": {
            "healthcare": "ಆರೋಗ್ಯ",
            "municipal": "ಪೌರ ಸೇವೆಗಳು",
            "law": "ಕಾನೂನು ಮತ್ತು ಸುವ್ಯವಸ್ಥೆ",
            "tourism": "ಪ್ರವಾಸೋದ್ಯಮ",
        },
        "warning": "ಎಚ್ಚರಿಕೆ: ಕಾಪಿ-ಪೇಸ್ಟ್ ವದಂತಿ ಇರಬಹುದು",
        "list_sep": ", ",
        "end": ".",
    },
    "ta": {
        "events": {
            "flood": "வெள்ளம்",
            "fire": "தீ விபத்து",
            "earthquake": "நிலநடுக்கம்",
            "landslide": "நிலச்சரிவு",
            "cyclone": "புயல்",
            "collapse": "கட்டட இடிபாடு",
            "rain": "கனமழை",
        },
        "incident": "சம்பவம்",
        "first": "{near}{event} பதிவாகியுள்ளது{details}",
        "near": "{loc} அருகே ",
        "impacts": {
            "people trapped": "மக்கள் சிக்கியுள்ளனர்",
            "people killed": "உயிரிழப்புகள்",
            "people injured": "மக்கள் காயமடைந்துள்ளனர்",
            "water entering houses": "வீடுகளுக்குள் தண்ணீர் புகுகிறது",
            "bridge damaged": "பாலம் சேதமடைந்துள்ளது",
            "roads blocked": "சாலைகள் மூடப்பட்டுள்ளன",
            "power outage": "மின்வெட்டு",
            "water shortage": "தண்ணீர் பற்றாக்குறை",
        },
        "urgent": "மக்கள் அவசர உதவி கேட்கின்றனர்",
        "span": lambda unit, n: {"hour": "கடந்த ஒரு மணி நேரத்தில்", "hours": f"கடந்த {n} மணி நேரத்தில்",
                                 "days": f"கடந்த {n} நாட்களில்"}[unit],
        "count": lambda n, k, span: _span_first(
            span,
            (f"{k} மொழியில்" if k == 1 else f"{k} மொழிகளில்") if k else None,
            f"{n} தனி அறிக்கை" if n == 1 else f"{n} தனி அறிக்கைகள்",
        ),
        "need": "முக்கிய தேவை: {main}",
        "also": "; மேலும் {second}",
        "departments": {
            "healthcare": "சுகாதாரம்",
            "municipal": "நகராட்சி",
            "law": "சட்டம் ஒழுங்கு",
            "tourism": "சுற்றுலா",
        },
        "warning": "எச்சரிக்கை: நகலெடுத்துப் பரப்பப்பட்ட வதந்தியாக இருக்கலாம்",
        "list_sep": ", ",
        "end": ".",
    },
    "te": {
        "events": {
            "flood": "వరద",
            "fire": "అగ్నిప్రమాదం",
            "earthquake": "భూకంపం",
            "landslide": "కొండచరియలు విరిగిపడటం",
            "cyclone": "తుఫాను",
            "collapse": "భవనం కూలిపోవడం",
            "rain": "భారీ వర్షం",
        },
        "incident": "సంఘటన",
        "first": "{near}{event} నమోదైంది{details}",
        "near": "{loc} దగ్గర ",
        "impacts": {
            "people trapped": "ప్రజలు చిక్కుకున్నారు",
            "people killed": "ప్రాణనష్టం",
            "people injured": "ప్రజలు గాయపడ్డారు",
            "water entering houses": "ఇళ్లలోకి నీరు చేరుతోంది",
            "bridge damaged": "వంతెన దెబ్బతింది",
            "roads blocked": "రోడ్లు మూసుకుపోయాయి",
            "power outage": "విద్యుత్ అంతరాయం",
            "water shortage": "నీటి కొరత",
        },
        "urgent": "ప్రజలు అత్యవసర సహాయం కోరుతున్నారు",
        "span": lambda unit, n: {"hour": "గత గంటలో", "hours": f"గత {n} గంటల్లో",
                                 "days": f"గత {n} రోజుల్లో"}[unit],
        "count": lambda n, k, span: _span_first(
            span,
            (f"{k} భాషలో" if k == 1 else f"{k} భాషల్లో") if k else None,
            f"{n} స్వతంత్ర నివేదిక" if n == 1 else f"{n} స్వతంత్ర నివేదికలు",
        ),
        "need": "ప్రధాన అవసరం: {main}",
        "also": "; అలాగే {second}",
        "departments": {
            "healthcare": "ఆరోగ్యం",
            "municipal": "మున్సిపల్ సేవలు",
            "law": "శాంతిభద్రతలు",
            "tourism": "పర్యాటకం",
        },
        "warning": "హెచ్చరిక: కాపీ-పేస్ట్ పుకారు కావచ్చు",
        "list_sep": ", ",
        "end": ".",
    },
}


def render_summary(slots: dict, lang: str = "en") -> str:
    """Write the summary slots in one language (unknown language -> English).

    slots: event, location, impact (keys or None), urgent (bool), n_unique,
    n_langs (ints), span (("hour"|"hours"|"days", n) or None), main_dept,
    second_dept (need keys or None), warning (bool)."""
    p = PHRASES.get(lang, PHRASES["en"])

    def department(key):
        return p["departments"].get(key, key.title())

    event = p["events"][slots["event"]] if slots.get("event") else p["incident"]
    near = p["near"].format(loc=slots["location"]) if slots.get("location") else ""
    items = ([p["impacts"][slots["impact"]]] if slots.get("impact") else []) + (
        [p["urgent"]] if slots.get("urgent") else []
    )
    details = ": " + p["list_sep"].join(items) if items else ""
    sentences = [p["first"].format(near=near, event=event, details=details)]

    span = p["span"](*slots["span"]) if slots.get("span") else None
    sentences.append(p["count"](slots["n_unique"], slots.get("n_langs") or 0, span))

    if slots.get("main_dept"):
        need = p["need"].format(main=department(slots["main_dept"]))
        if slots.get("second_dept"):
            need += p["also"].format(second=department(slots["second_dept"]))
        sentences.append(need)

    if slots.get("warning"):
        sentences.append(p["warning"])
    return " ".join(sentence + p["end"] for sentence in sentences)
