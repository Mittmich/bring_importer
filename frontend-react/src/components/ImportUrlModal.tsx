import { useState } from 'react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { ImportLanguageField } from '@/components/ImportPhotoModal'
import { useI18n, type Language } from '@/i18n'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSwitchToPhoto: () => void
  onDone: (uuid: string) => void
}

export function ImportUrlModal({ open, onOpenChange, onSwitchToPhoto, onDone }: Props) {
  const [url, setUrl] = useState('')
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t, lang } = useI18n()
  // Override of the target language; null = follow the UI language.
  const [langOverride, setLangOverride] = useState<Language | null>(null)
  const importLang = langOverride ?? lang

  function reset() {
    setUrl('')
    setNote('')
    setError(null)
    setLoading(false)
    setLangOverride(null)
  }

  function handleClose() {
    reset()
    onOpenChange(false)
  }

  async function handleImport() {
    if (!url.trim()) return
    setLoading(true)
    setError(null)
    try {
      const result = await api.importUrl(url.trim(), note.trim() || undefined, importLang)
      reset()
      onDone(result.uuid)
    } catch (e: any) {
      setError(e.message ?? t('import.urlFailed'))
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('import.urlTitle')}</DialogTitle>
          <DialogDescription>{t('import.urlDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="recipe-url">{t('import.urlLabel')}</Label>
            <Input
              id="recipe-url"
              type="url"
              placeholder="https://www.example.com/pasta-carbonara"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleImport()}
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="recipe-note">{t('import.noteLabel')}</Label>
            <Textarea
              id="recipe-note"
              placeholder={t('import.notePlaceholder')}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
            />
          </div>

          <ImportLanguageField value={importLang} onChange={setLangOverride} />

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
          )}

          {loading && (
            <p className="text-sm text-muted-foreground text-center">{t('import.fetching')}</p>
          )}
        </div>

        <DialogFooter>
          <button
            onClick={onSwitchToPhoto}
            className="mr-auto text-xs text-muted-foreground hover:text-primary transition-colors"
          >
            {t('import.switchToPhoto')}
          </button>
          <Button variant="outline" onClick={handleClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleImport} disabled={!url.trim() || loading}>
            {loading ? t('common.importing') : t('common.import')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
