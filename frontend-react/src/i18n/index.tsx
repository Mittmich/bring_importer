import {
  createContext,
  Fragment,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { isAuthenticated } from '@/hooks/useAuth'
import { en, type MessageKey } from './en'
import { de } from './de'
import { getLanguage, setCurrentLanguage } from './current'
import type { Language } from './languages'

export { LANGUAGES, nativeName, normalizeLanguage, type Language } from './languages'
export type { MessageKey } from './en'

const DICTIONARIES: Record<Language, Record<MessageKey, string>> = { en, de }

type Params = Record<string, string | number>
/** Base keys that have `_one` / `_other` plural variants. */
type PluralKey = MessageKey extends infer K
  ? K extends `${infer Base}_other`
    ? Base
    : never
  : never

function interpolate(template: string, params?: Params): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (m, name) =>
    name in params ? String(params[name]) : m,
  )
}

export interface I18n {
  lang: Language
  /** Translate a key, interpolating `{placeholders}`. */
  t: (key: MessageKey, params?: Params) => string
  /** Plural-aware translate: picks `${key}_one` / `${key}_other`; `{count}` is set. */
  tp: (key: PluralKey, count: number, params?: Params) => string
  /** Translate with React nodes (e.g. icons) as placeholder values. */
  tx: (key: MessageKey, nodes: Record<string, ReactNode>) => ReactNode
  /** Switch language. With `persist`, also saves it to the signed-in user's profile. */
  setLanguage: (lang: Language, opts?: { persist?: boolean }) => void
}

const I18nContext = createContext<I18n | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [lang, setLang] = useState<Language>(getLanguage)

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLanguage = useCallback(
    (next: Language, opts?: { persist?: boolean }) => {
      if (opts?.persist && isAuthenticated()) {
        // Optimistically record the choice so the profile→language sync in
        // AppShell doesn't flip it back before the PUT lands.
        queryClient.setQueryData(['profile'], (p: object | undefined) =>
          p ? { ...p, language: next } : p,
        )
        api.updateProfile({ language: next }).catch(() => {
          queryClient.invalidateQueries({ queryKey: ['profile'] })
        })
      }
      if (next === getLanguage()) return
      setCurrentLanguage(next)
      setLang(next)
      // Server data (recipe titles, ingredients…) is localized by the
      // Accept-Language header — refetch it in the new language.
      queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'profile' })
    },
    [queryClient],
  )

  const value = useMemo<I18n>(() => {
    const dict = DICTIONARIES[lang]
    const lookup = (key: MessageKey) => dict[key] ?? en[key] ?? key
    const plural = new Intl.PluralRules(lang)
    return {
      lang,
      t: (key, params) => interpolate(lookup(key), params),
      tp: (key, count, params) => {
        const form = plural.select(count) === 'one' ? 'one' : 'other'
        return interpolate(lookup(`${key}_${form}` as MessageKey), { count, ...params })
      },
      tx: (key, nodes) => {
        const parts = lookup(key).split(/(\{\w+\})/)
        return parts.map((part, i) => {
          const m = part.match(/^\{(\w+)\}$/)
          return <Fragment key={i}>{m && m[1] in nodes ? nodes[m[1]] : part}</Fragment>
        })
      },
      setLanguage,
    }
  }, [lang, setLanguage])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}
