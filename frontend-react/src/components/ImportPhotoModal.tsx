import { useRef, useState } from 'react'
import { Camera, Loader2, Upload } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useI18n, type Language } from '@/i18n'

const MAX_PX = 1024
const JPEG_QUALITY = 0.82

function downscaleImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const url = URL.createObjectURL(file)
    img.onload = () => {
      URL.revokeObjectURL(url)
      let { width, height } = img
      if (width > MAX_PX || height > MAX_PX) {
        if (width >= height) {
          height = Math.round((height * MAX_PX) / width)
          width = MAX_PX
        } else {
          width = Math.round((width * MAX_PX) / height)
          height = MAX_PX
        }
      }
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      canvas.getContext('2d')!.drawImage(img, 0, 0, width, height)
      resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY))
    }
    img.onerror = reject
    img.src = url
  })
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSwitchToUrl: () => void
  onDone: (uuid: string) => void
}

export function ImportPhotoModal({ open, onOpenChange, onSwitchToUrl, onDone }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t, lang } = useI18n()
  // Target language for the extracted recipe; defaults to the UI language.
  // Override of the target language; null = follow the UI language.
  const [langOverride, setLangOverride] = useState<Language | null>(null)
  const importLang = langOverride ?? lang

  function reset() {
    setPreview(null)
    setError(null)
    setLoading(false)
    setLangOverride(null)
  }

  function handleClose() {
    reset()
    onOpenChange(false)
  }

  async function handleFile(file: File) {
    setError(null)
    try {
      const dataUrl = await downscaleImage(file)
      setPreview(dataUrl)
    } catch {
      setError(t('import.readImageFailed'))
    }
  }

  async function handleParse() {
    if (!preview) return
    setLoading(true)
    setError(null)
    try {
      const base64 = preview.split(',')[1]
      const result = await api.parsePhoto(base64, importLang)
      reset()
      onDone(result.uuid)
    } catch (e: any) {
      setError(e.message ?? t('import.parseFailed'))
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('import.photoTitle')}</DialogTitle>
          <DialogDescription>{t('import.photoDescription')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center gap-3 py-8">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
              <p className="text-sm text-muted-foreground">{t('import.analyzing')}</p>
            </div>
          ) : !preview ? (
            <div className="space-y-3">
              <button
                onClick={() => {
                  if (fileRef.current) {
                    fileRef.current.capture = 'environment'
                    fileRef.current.click()
                  }
                }}
                className="w-full flex flex-col items-center gap-2 p-6 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-primary/5 transition-colors"
              >
                <Camera className="w-8 h-8 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">{t('import.takePhoto')}</span>
              </button>
              <button
                onClick={() => {
                  if (fileRef.current) {
                    fileRef.current.removeAttribute('capture')
                    fileRef.current.click()
                  }
                }}
                className="w-full flex items-center justify-center gap-2 p-3 border border-border rounded-lg hover:bg-muted/50 transition-colors text-sm text-muted-foreground"
              >
                <Upload className="w-4 h-4" /> {t('import.uploadFromLibrary')}
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <img
                src={preview}
                alt={t('import.previewAlt')}
                className="w-full max-h-48 object-cover rounded-lg border border-border"
              />
              <button
                onClick={() => setPreview(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                {t('import.changePhoto')}
              </button>
            </div>
          )}

          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />

          {!loading && (
            <ImportLanguageField value={importLang} onChange={setLangOverride} />
          )}

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
          )}
        </div>

        <DialogFooter>
          <button
            onClick={onSwitchToUrl}
            className="mr-auto text-xs text-muted-foreground hover:text-primary transition-colors"
          >
            {t('import.switchToUrl')}
          </button>
          <Button variant="outline" onClick={handleClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleParse} disabled={!preview || loading}>
            {loading ? t('import.parsing') : t('import.parse')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** "Recipe language" picker shared by both import dialogs. */
export function ImportLanguageField({
  value,
  onChange,
}: {
  value: Language
  onChange: (lang: Language) => void
}) {
  const { t } = useI18n()
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <label htmlFor="import-language" className="text-sm font-medium text-foreground">
          {t('import.language')}
        </label>
        <p className="text-xs text-muted-foreground">{t('import.languageHint')}</p>
      </div>
      <LanguageSelect id="import-language" value={value} onChange={onChange} className="shrink-0" />
    </div>
  )
}
