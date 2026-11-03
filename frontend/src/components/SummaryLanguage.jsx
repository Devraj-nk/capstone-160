import { useState } from "react";

export const SUMMARY_LANGUAGES = [
  ["en", "English"],
  ["hi", "हिन्दी"],
  ["kn", "ಕನ್ನಡ"],
  ["ta", "தமிழ்"],
  ["te", "తెలుగు"],
];

const STORAGE_KEY = "summaryLanguage";

function readStored() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "en";
  } catch {
    return "en";
  }
}

/** Summary language chosen by the viewer, remembered across visits. */
export function useSummaryLanguage() {
  const [lang, setLang] = useState(readStored);
  function choose(next) {
    setLang(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable: keep the choice for this visit only */
    }
  }
  return [lang, choose];
}

/** The item's summary in `lang`, falling back to the English summary. */
export function summaryIn(item, lang) {
  return item.summary_i18n?.[lang] ?? item.summary ?? item.text;
}

export function SummaryLanguageSelect({ value, onChange }) {
  return (
    <label>
      Summary language:{" "}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {SUMMARY_LANGUAGES.map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}
