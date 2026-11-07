import { useRef, useState } from 'react'
import { FileText, Loader2, Upload } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { ImportLanguageField } from '@/components/ImportPhotoModal'
import { useI18n, type Language } from '@/i18n'

/** Matches the backend's MAX_PDF_BYTES. */
const MAX_PDF_BYTES = 15 * 1024 * 1024

function sizeLabel(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSwitchToPhoto: () => void
  onDone: (uuid: string) => void
}

/** Import a recipe from a PDF (saved recipe, cookbook excerpt, scan). */
export function ImportDocumentModal({ open, onOpenChange, onSwitchToPhoto, onDone }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t, lang } = useI18n()
  const [langOverride, setLangOverride] = useState<Language | null>(null)
  const importLang = langOverride ?? lang

  function reset() {
    setFile(null)
    setError(null)
    setLoading(false)
    setLangOverride(null)
  }

  function handleClose() {
    reset()
    onOpenChange(false)
  }

  function handleFile(f: File) {
    setError(null)
    const isPdf = f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')
    if (!isPdf) return setError(t('import.notPdf'))
    if (f.size > MAX_PDF_BYTES) return setError(t('import.pdfTooLarge'))
    setFile(f)
  }

  async function handleImport() {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const result = await api.importDocument(file, importLang)
      reset()
      onDone(result.uuid)
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : t('import.documentFailed'))
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('import.documentTitle')}</DialogTitle>
          <DialogDescription>{t('import.documentDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center gap-3 py-8">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
              <p className="text-sm text-muted-foreground">{t('import.readingDocument')}</p>
            </div>
          ) : !file ? (
            <div className="space-y-2">
              <button
                onClick={() => fileRef.current?.click()}
                className="w-full flex flex-col items-center gap-2 p-6 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-primary/5 transition-colors"
              >
                <Upload className="w-8 h-8 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">{t('import.choosePdf')}</span>
              </button>
              <p className="text-xs text-muted-foreground text-center">{t('import.pdfLimit')}</p>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-lg border border-border p-3">
              <span className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                <FileText className="w-5 h-5" />
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-medium truncate">{file.name}</span>
                <span className="block text-xs text-muted-foreground">{sizeLabel(file.size)}</span>
              </span>
              <button
                onClick={() => fileRef.current?.click()}
                className="text-xs text-muted-foreground hover:text-foreground flex-shrink-0"
              >
                {t('import.changeDocument')}
              </button>
            </div>
          )}

          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (f) handleFile(f)
            }}
          />

          {!loading && <ImportLanguageField value={importLang} onChange={setLangOverride} />}

          {error && <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>}
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
          <Button onClick={handleImport} disabled={!file || loading}>
            {loading ? t('import.parsing') : t('import.parse')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
