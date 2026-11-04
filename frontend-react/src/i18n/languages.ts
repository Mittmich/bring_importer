/**
 * Supported languages — keep in sync with SUPPORTED_LANGUAGES in
 * backend/api/i18n.py. Adding a language = an entry here, a dictionary file in
 * this folder, and an entry in the backend registry.
 */
export const LANGUAGES = [
  { code: 'en', native: 'English' },
  { code: 'de', native: 'Deutsch' },
] as const

export type Language = (typeof LANGUAGES)[number]['code']

export const DEFAULT_LANGUAGE: Language = 'en'

export function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && LANGUAGES.some((l) => l.code === value)
}

/** Map a BCP-47 tag ("de-AT") to a supported language, or null. */
export function normalizeLanguage(tag?: string | null): Language | null {
  if (!tag) return null
  const code = tag.toLowerCase().split(/[-_]/)[0]
  return isLanguage(code) ? code : null
}

/** A language's own name ("Deutsch"), or the code when unknown. */
export function nativeName(code?: string | null): string {
  return LANGUAGES.find((l) => l.code === code)?.native ?? code ?? ''
}
