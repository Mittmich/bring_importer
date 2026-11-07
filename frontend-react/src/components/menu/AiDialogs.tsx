import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { useI18n, type MessageKey } from '@/i18n'

export const AI_TEXT_MAX = 500

/** Optional instructions for the AI draft, used when adding or redrafting a course. */
export function AiNotesField({ value, onChange, id }: { value: string; onChange: (v: string) => void; id: string }) {
  const { t } = useI18n()
  return (
    <div className="mb-3">
      <label className="block text-xs font-medium text-muted-foreground mb-1" htmlFor={id}>
        {t('menus.aiNotes')}
      </label>
      <Textarea
        id={id}
        value={value}
        maxLength={AI_TEXT_MAX}
        rows={2}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t('menus.aiNotesPlaceholder')}
        className="bg-background"
      />
    </div>
  )
}

/**
 * A dialog with a text box that runs an AI call. `onSubmit` rejects on failure;
 * the dialog then stays open with an error so the text can be tweaked.
 */
export function AiDialog({
  title,
  hint,
  placeholder,
  examples = [],
  submitLabel,
  required,
  onSubmit,
  onClose,
}: {
  title: string
  hint?: string
  placeholder: string
  examples?: MessageKey[]
  submitLabel: string
  /** Text is required (Edit with AI) rather than optional notes (redraft). */
  required?: boolean
  onSubmit: (text: string) => Promise<unknown>
  onClose: () => void
}) {
  const { t } = useI18n()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  async function submit() {
    if (busy || (required && !text.trim())) return
    setBusy(true)
    setFailed(false)
    try {
      await onSubmit(text.trim())
      onClose()
    } catch {
      setFailed(true)
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" /> {title}
          </DialogTitle>
        </DialogHeader>
        {hint && <p className="text-sm text-muted-foreground -mt-1 mb-3">{hint}</p>}
        <Textarea
          autoFocus
          value={text}
          maxLength={AI_TEXT_MAX}
          rows={3}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit()
          }}
          placeholder={placeholder}
          className="bg-background"
        />
        {examples.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {examples.map((k) => (
              <button
                key={k}
                type="button"
                disabled={busy}
                onClick={() => setText(t(k))}
                className="rounded-full border border-border bg-slate-50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                {t(k)}
              </button>
            ))}
          </div>
        )}
        {failed && <p className="text-sm text-destructive mt-2">{t('menus.aiFailed')}</p>}
        <div className="flex items-center justify-end gap-2 mt-4">
          {busy && <span className="text-xs text-muted-foreground mr-auto">{t('menus.aiWorking')}</span>}
          <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
            {t('common.cancel')}
          </Button>
          <Button size="sm" onClick={submit} disabled={busy || (required && !text.trim())}>
            <Sparkles className="w-4 h-4 mr-1.5" />
            {submitLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
