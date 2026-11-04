import { Languages } from 'lucide-react'
import { LANGUAGES, type Language } from '@/i18n'
import { cn } from '@/lib/utils'

/** A compact native <select> of the supported languages, labelled in their own names. */
export function LanguageSelect({
  value,
  onChange,
  id,
  className,
  placeholder,
  'aria-label': ariaLabel,
}: {
  value: Language | ''
  onChange: (lang: Language) => void
  id?: string
  className?: string
  /** Shown as an empty first option when `value` is ''. */
  placeholder?: string
  'aria-label'?: string
}) {
  return (
    <div className={cn('relative inline-flex items-center', className)}>
      <Languages className="pointer-events-none absolute left-2.5 w-4 h-4 text-muted-foreground" />
      <select
        id={id}
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => e.target.value && onChange(e.target.value as Language)}
        className="w-full appearance-none text-sm bg-muted/50 rounded-md border border-border pl-8 pr-3 py-2 focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {value === '' && <option value="">{placeholder ?? ''}</option>}
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.native}
          </option>
        ))}
      </select>
    </div>
  )
}
