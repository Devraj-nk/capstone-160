"""
Multilingual keyword lexicons used by the rule-based parts of the formulas.

Every category has lists for:
  en, hi, hi_rom, kn, kn_rom, ta, ta_rom, te, te_rom
(native script + romanized), and ALL lists are checked for EVERY tweet,
whatever language was detected. Reason: language detection is advisory and
code-mixed tweets mix languages ("ಮನೆಗೆ water bandide, help maadi").

Matching syntax for each term:
  "help"        exact token match
  "flood*"      prefix match   ("flooded", "ಸಹಾಯ*" -> "ಸಹಾಯಕ್ಕೆ")
  "*nagar"      suffix match   (place-name endings like "rajajinagar")
  "*ನಗರ*"       ending + case suffix ("ರಾಜಾಜಿನಗರದಲ್ಲಿ"); must NOT be at word start
  "need help"   phrase (multi-word) match; "share maadi*" lets the last word
                take a suffix

Rule of thumb for Indic stems: use a prefix (*) because of case/verb suffixes,
but avoid very short stems that create false hits (e.g. Kannada "ಗಾಯ*" would
also match "ಗಾಯಕ" = singer, so we use "ಗಾಯಗೊಂಡ*").

These lists are a STARTING POINT. Get a native speaker on the team to review
each language and add terms — and add a test for every term you add.
"""

URGENCY = {
    "en": ["help", "urgent*", "emergency", "sos", "rescue*", "asap", "immediately",
           "need help", "please help", "save us", "stuck"],
    "hi": ["मदद", "बचाओ", "बचाइए", "तुरंत", "जल्दी", "आपातकाल*", "इमरजेंसी", "फंसे हुए"],
    "hi_rom": ["madad", "bachao", "bachaiye", "bachalo", "turant", "jaldi", "help karo",
               "koi madad"],
    "kn": ["ಸಹಾಯ*", "ತುರ್ತು", "ಕಾಪಾಡಿ", "ರಕ್ಷಿಸಿ", "ಬೇಗ*", "ತಕ್ಷಣ*"],
    "kn_rom": ["sahaya*", "turtu", "thurthu", "kapadi", "kaapaadi", "rakshisi", "bega",
               "takshana"],
    "ta": ["உதவி*", "அவசர*", "காப்பாற்று*", "உடனே", "உடனடி*", "சீக்கிரம்"],
    "ta_rom": ["udhavi", "udavi", "avasaram", "kaapathunga", "kaapaathu*", "udane",
               "seekiram"],
    "te": ["సహాయ*", "సాయం", "అత్యవసర*", "కాపాడ*", "వెంటనే", "త్వరగా"],
    "te_rom": ["sahayam", "saayam", "atyavasaram", "kapadandi", "kaapaadandi", "ventane",
               "twaraga"],
}

SEVERITY = {  # casualties / people trapped / structural damage
    "en": ["dead", "death*", "died", "kill*", "injur*", "trapped", "stranded", "collaps*",
           "missing", "drown*", "washed away", "casualt*", "destroy*"],
    "hi": ["मौत", "मृत*", "मारे गए", "घायल", "फंस*", "लापता", "डूब*", "ढह*", "बह गए", "तबाह*"],
    "hi_rom": ["maut", "mare gaye", "ghayal", "phans*", "fans gaye", "lapata", "laapata",
               "doob*", "dub gaye", "dhah gaya", "beh gaye", "tabah*"],
    "kn": ["ಸಾವು", "ಸಾವನ್ನಪ್ಪಿ*", "ಮೃತ*", "ಗಾಯಗೊಂಡ*", "ಗಾಯಾಳು*", "ಸಿಲುಕಿ*", "ನಾಪತ್ತೆ",
           "ಮುಳುಗಿ*", "ಕುಸಿದ*", "ಕೊಚ್ಚಿ*"],
    "kn_rom": ["savu", "sattaru", "gayagonda*", "siluki*", "naapatte", "napatte",
               "mulugi*", "kusid*"],
    "ta": ["உயிரிழ*", "இறந்த*", "பலி", "காயமடைந்த*", "காயம்", "சிக்கி*", "காணவில்லை",
           "மூழ்கி*", "இடிந்து*"],
    "ta_rom": ["uyirizh*", "irandh*", "kaayam", "sikki*", "kaanavillai", "moozhgi*",
               "idindhu*"],
    "te": ["మృతి", "మృతు*", "చనిపో*", "మరణ*", "గాయపడ*", "గాయాలు", "చిక్కుకు*", "గల్లంతు*",
           "మునిగి*", "కూలిపో*", "కొట్టుకుపో*"],
    "te_rom": ["chanipoy*", "maranam", "gaayapad*", "gayapad*", "gayalu", "chikkuk*",
               "gallanthu", "munigi*", "koolipoy*"],
}

LOCATION = {  # "where" cues
    "en": ["near", "nearby", "area*", "street", "colony", "village", "district", "ward",
           "locality", "layout", "in my area"],
    "hi": ["पास", "इलाक*", "गांव*", "गाँव*", "मोहल्ल*", "जिले", "जिला", "कॉलोनी"],
    "hi_rom": ["paas", "ilaake", "ilaka", "ilake", "gaon", "gaanv", "mohalla", "mohalle",
               "jile", "zila"],
    "kn": ["ಹತ್ತಿರ", "ಬಳಿ", "ಪ್ರದೇಶ*", "ಗ್ರಾಮ*", "ಏರಿಯಾ*", "ಬಡಾವಣೆ*", "ಜಿಲ್ಲೆ*", "ಊರ*"],
    "kn_rom": ["hattira", "pradesha", "grama", "ooru", "oorige", "badavane", "jille"],
    "ta": ["அருகில்", "அருகே", "பகுதி*", "கிராம*", "தெரு*", "ஏரியா*", "மாவட்ட*"],
    "ta_rom": ["pakkathula", "pakkam", "pagudhi", "gramam", "theru", "maavattam"],
    "te": ["దగ్గర", "ప్రాంత*", "గ్రామ*", "వీధి*", "ఏరియా*", "జిల్లా*", "కాలనీ*"],
    "te_rom": ["daggara", "prantham", "gramam", "veedhi", "jilla"],
}

# Place names and Indian place-name endings (common to all languages)
PLACE_NAMES = {
    "all_latin": ["bengaluru", "bangalore", "mysuru", "mysore", "mangaluru", "mangalore",
                  "hubli", "chennai", "madurai", "coimbatore", "hyderabad", "vijayawada",
                  "visakhapatnam", "vizag", "mumbai", "delhi", "kolkata", "pune", "patna",
                  "guwahati", "kochi", "lucknow",
                  "*nagar", "*pura", "*puram", "*halli", "*palli", "*abad", "*guda"],
    "hi": ["बेंगलुरु", "मुंबई", "दिल्ली", "पटना", "लखनऊ", "कोलकाता", "*नगर", "*पुर"],
    "kn": ["ಬೆಂಗಳೂರು*", "ಮೈಸೂರು*", "ಮಂಗಳೂರು*", "ಹುಬ್ಬಳ್ಳಿ*", "*ನಗರ*", "*ಪುರ*", "*ಹಳ್ಳಿ*"],
    "ta": ["சென்னை*", "மதுரை*", "கோவை*", "கோயம்புத்தூர்*", "*புரம்*", "*நகர்*"],
    "te": ["హైదరాబాద్*", "విజయవాడ*", "విశాఖ*", "*పల్లి*", "*నగర్*", "*పేట*"],
}

INFRASTRUCTURE = {  # concrete objects affected
    "en": ["road*", "bridge*", "hospital*", "school*", "house*", "home*", "building*",
           "power", "electricity", "water", "dam", "railway", "highway", "shelter*"],
    "hi": ["सड़क*", "पुल", "अस्पताल*", "स्कूल*", "घर*", "मकान*", "बिजली", "पानी", "बांध",
           "इमारत*", "रेलवे"],
    "hi_rom": ["sadak*", "sadke", "pul", "aspatal*", "ghar*", "makaan", "bijli", "paani",
               "pani", "imarat"],
    "kn": ["ರಸ್ತೆ*", "ಸೇತುವೆ*", "ಆಸ್ಪತ್ರೆ*", "ಶಾಲೆ*", "ಮನೆ*", "ಕಟ್ಟಡ*", "ವಿದ್ಯುತ್*",
           "ಕರೆಂಟ್*", "ನೀರು*", "ನೀರಿನ*", "ಅಣೆಕಟ್ಟ*"],
    "kn_rom": ["raste", "rasthe", "setuve", "aspatre", "shaale", "mane", "manege",
               "maneyalli", "current", "neeru", "neerige"],
    "ta": ["சாலை*", "பாலம்*", "மருத்துவமனை*", "பள்ளி*", "வீடு*", "வீட்டு*", "வீடுக*",
           "கட்டிட*", "மின்சார*", "கரண்ட்*", "தண்ணீர்*", "அணைக்கட்டு*"],
    "ta_rom": ["salai", "paalam", "veedu", "veetla", "veedugal", "current", "thanni",
               "thanneer"],
    "te": ["రోడ్డు*", "రహదారి*", "వంతెన*", "ఆసుపత్రి*", "పాఠశాల*", "ఇల్లు", "ఇళ్ల*", "ఇంట్లో",
           "భవన*", "విద్యుత్*", "కరెంట్*", "నీరు", "నీళ్ళు", "ఆనకట్ట*"],
    "te_rom": ["roddu", "vantena", "aasupatri", "illu", "intlo", "illalo", "current",
               "neellu", "neeru"],
}

TIME = {  # "when" cues
    "en": ["now", "right now", "since morning", "last night", "today", "tonight",
           "minutes ago", "hours ago", "still"],
    "hi": ["अभी", "आज", "सुबह से", "कल रात", "अब तक"],
    "hi_rom": ["abhi", "aaj", "subah se", "kal raat", "ab tak"],
    "kn": ["ಈಗ", "ಇಂದು", "ಬೆಳಿಗ್ಗೆಯಿಂದ", "ನಿನ್ನೆ ರಾತ್ರಿ", "ಇನ್ನೂ"],
    "kn_rom": ["iga", "eega", "indu", "belaggeyinda", "ninne ratri"],
    "ta": ["இப்போது", "இப்ப", "இன்று", "காலையிலிருந்து", "நேற்று இரவு"],
    "ta_rom": ["ippo", "ippodhu", "indru", "innaiku", "kaalaila irundhu"],
    "te": ["ఇప్పుడు", "ఈరోజు", "ఉదయం నుండి", "నిన్న రాత్రి", "ఇంకా"],
    "te_rom": ["ippudu", "eeroju", "udayam nundi", "ninna ratri"],
}

FORWARD_CHAIN = {  # misinformation-style "spread this" markers
    "en": ["forward*", "share this", "share maximum", "share to all", "viral", "100% true",
           "100% sure", "breaking", "must watch", "media won't show", "they are hiding"],
    "hi": ["फॉरवर्ड*", "शेयर करें", "शेयर करो", "सभी को भेजें", "सबको भेजो", "वायरल",
           "100% सच", "छुपा रही"],
    "hi_rom": ["forward karo", "share karo", "sabko bhejo", "sab ko bhejo", "sach hai",
               "chupa rahi", "chhupa rahi"],
    "kn": ["ಶೇರ್ ಮಾಡಿ*", "ಫಾರ್ವರ್ಡ್*", "ಎಲ್ಲರಿಗೂ ಕಳುಹಿಸಿ*", "ವೈರಲ್*"],
    "kn_rom": ["share maadi", "share madi", "forward maadi", "ellarigu kalisi"],
    "ta": ["பகிரவும்", "ஷேர் பண்ணுங்க*", "ஃபார்வர்ட்*", "அனைவருக்கும் அனுப்பு*", "வைரல்*"],
    "ta_rom": ["share pannunga", "ellarukum anuppunga", "forward pannunga"],
    "te": ["షేర్ చేయండి", "ఫార్వర్డ్*", "అందరికీ పంపండి", "వైరల్*"],
    "te_rom": ["share cheyandi", "andariki pampandi", "forward cheyandi"],
}

HEARSAY = {  # "I heard that..." — unverified, secondhand
    "en": ["heard", "rumor*", "rumour*", "apparently", "unconfirmed", "someone said",
           "people saying"],
    "hi": ["सुना है", "अफवाह*", "कहा जा रहा"],
    "hi_rom": ["suna hai", "afwah", "afvah", "keh rahe"],
    "kn": ["ಕೇಳಿದೆ", "ವದಂತಿ*", "*ಯಂತೆ"],
    "kn_rom": ["vadanti", "kelide"],
    "ta": ["வதந்தி*", "சொல்றாங்க", "கேள்விப்பட்டேன்"],
    "ta_rom": ["vadhandhi", "solranga", "kelvipatten"],
    "te": ["పుకారు*", "అంట", "విన్నాను"],
    "te_rom": ["pukaru", "vinnanu"],
}

ALL_CATEGORIES = {
    "urgency": URGENCY,
    "severity": SEVERITY,
    "location": LOCATION,
    "place_names": PLACE_NAMES,
    "infrastructure": INFRASTRUCTURE,
    "time": TIME,
    "forward_chain": FORWARD_CHAIN,
    "hearsay": HEARSAY,
}
