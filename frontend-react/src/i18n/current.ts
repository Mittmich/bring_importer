import { DEFAULT_LANGUAGE, isLanguage, normalizeLanguage, type Language } from './languages'

const STORAGE_KEY = 'ui_language'

/** Initial language: saved choice → browser preference → default. */
export function detectLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (isLanguage(saved)) return saved
  } catch {
    // storage unavailable — fall through
  }
  for (const tag of navigator.languages ?? [navigator.language]) {
    const lang = normalizeLanguage(tag)
    if (lang) return lang
  }
  return DEFAULT_LANGUAGE
}

// Module-level mirror of the provider's state so non-React code (the API
// client's Accept-Language header) can read the current language.
let current: Language = detectLanguage()

export function getLanguage(): Language {
  return current
}

export function setCurrentLanguage(lang: Language) {
  current = lang
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // ignore
  }
  document.documentElement.lang = lang
}
