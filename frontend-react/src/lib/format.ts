/** Locale-aware formatting helpers. */

const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 365],
  ['month', 30],
  ['week', 7],
  ['day', 1],
]

/** "today", "yesterday", "3 days ago", "2 wk. ago" … in the given language. */
export function relativeDate(dateStr: string | undefined, lang: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return ''
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000)
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto', style: 'short' })
  for (const [unit, size] of UNITS) {
    if (days >= size || unit === 'day') return rtf.format(-Math.floor(days / size), unit)
  }
  return ''
}
