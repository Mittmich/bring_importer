import { useRef, useState } from 'react'
import { Camera, ImagePlus, Loader2, Upload, X } from 'lucide-react'
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

/** Photos per recipe; matches the backend's MAX_IMAGES. */
export const MAX_PHOTOS = 8

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSwitchToUrl: () => void
  onDone: (uuid: string) => void
}

/**
 * Import from one or more photos of the same recipe (e.g. two cookbook pages):
 * they are sent together, in order, and become one recipe.
 */
export function ImportPhotoModal({ open, onOpenChange, onSwitchToUrl, onDone }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [photos, setPhotos] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t, lang } = useI18n()
  // Override of the target language; null = follow the UI language.
  const [langOverride, setLangOverride] = useState<Language | null>(null)
  const importLang = langOverride ?? lang

  function reset() {
    setPhotos([])
    setError(null)
    setLoading(false)
    setLangOverride(null)
  }

  function handleClose() {
    reset()
    onOpenChange(false)
  }

  function pick(camera: boolean) {
    const input = fileRef.current
    if (!input) return
    if (camera) input.capture = 'environment'
    else input.removeAttribute('capture')
    input.click()
  }

  async function handleFiles(files: File[]) {
    setError(null)
    const room = MAX_PHOTOS - photos.length
    if (files.length > room) setError(t('import.tooManyPhotos', { max: MAX_PHOTOS }))
    try {
      const added = await Promise.all(files.slice(0, Math.max(0, room)).map(downscaleImage))
      setPhotos((p) => [...p, ...added].slice(0, MAX_PHOTOS))
    } catch {
      setError(t('import.readImageFailed'))
    }
  }

  async function handleParse() {
    if (!photos.length) return
    setLoading(true)
    setError(null)
    try {
      const result = await api.parsePhoto(
        photos.map((p) => p.split(',')[1]),
        importLang,
      )
      reset()
      onDone(result.uuid)
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : t('import.parseFailed'))
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
          ) : photos.length === 0 ? (
            <div className="space-y-3">
              <button
                onClick={() => pick(true)}
                className="w-full flex flex-col items-center gap-2 p-6 border-2 border-dashed border-border rounded-lg hover:border-primary/50 hover:bg-primary/5 transition-colors"
              >
                <Camera className="w-8 h-8 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">{t('import.takePhoto')}</span>
              </button>
              <button
                onClick={() => pick(false)}
                className="w-full flex items-center justify-center gap-2 p-3 border border-border rounded-lg hover:bg-muted/50 transition-colors text-sm text-muted-foreground"
              >
                <Upload className="w-4 h-4" /> {t('import.uploadFromLibrary')}
              </button>
              <p className="text-xs text-muted-foreground text-center">{t('import.multiHint')}</p>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {photos.map((src, i) => (
                  <div key={i} className="relative aspect-[3/4] rounded-lg overflow-hidden border border-border bg-muted">
                    <img src={src} alt={t('import.previewAlt')} className="w-full h-full object-cover" />
                    <span className="absolute left-1 top-1 min-w-5 h-5 px-1 rounded-full bg-black/60 text-white text-[11px] font-semibold flex items-center justify-center">
                      {i + 1}
                    </span>
                    <button
                      onClick={() => setPhotos((p) => p.filter((_, j) => j !== i))}
                      aria-label={t('import.removePhoto')}
                      title={t('import.removePhoto')}
                      className="absolute right-1 top-1 w-6 h-6 rounded-full bg-white/90 text-foreground flex items-center justify-center shadow hover:bg-white"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
                {photos.length < MAX_PHOTOS && (
                  <button
                    onClick={() => pick(false)}
                    aria-label={t('import.addPhoto')}
                    title={t('import.addPhoto')}
                    className="aspect-[3/4] rounded-lg border-2 border-dashed border-border flex flex-col items-center justify-center gap-1 text-muted-foreground hover:border-primary/50 hover:bg-primary/5 hover:text-primary transition-colors"
                  >
                    <ImagePlus className="w-6 h-6" />
                    <span className="text-[11px] font-medium px-1 text-center leading-tight">{t('import.addPhoto')}</span>
                  </button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {t('import.photoCount', { n: photos.length, max: MAX_PHOTOS })}
              </p>
            </div>
          )}

          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              e.target.value = '' // allow picking the same file again
              if (files.length) handleFiles(files)
            }}
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
          <Button onClick={handleParse} disabled={!photos.length || loading}>
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
