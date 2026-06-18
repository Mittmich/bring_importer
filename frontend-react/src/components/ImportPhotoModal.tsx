import { useRef, useState } from 'react'
import { Camera, Upload } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'

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

  function reset() {
    setPreview(null)
    setError(null)
    setLoading(false)
  }

  function handleClose() {
    reset()
    onOpenChange(false)
  }

  function handleFile(file: File) {
    const reader = new FileReader()
    reader.onload = (e) => setPreview(e.target?.result as string)
    reader.readAsDataURL(file)
    setError(null)
  }

  async function handleParse() {
    if (!preview) return
    setLoading(true)
    setError(null)
    try {
      const base64 = preview.split(',')[1]
      const result = await api.parsePhoto(base64)
      reset()
      onDone(result.uuid)
    } catch (e: any) {
      setError(e.message ?? 'Failed to parse recipe.')
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import from photo</DialogTitle>
          <DialogDescription>
            Take or upload a photo of a recipe and we'll extract it automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {!preview ? (
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
                <span className="text-sm font-medium text-foreground">Take a photo</span>
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
                <Upload className="w-4 h-4" /> Upload from library
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <img
                src={preview}
                alt="Recipe preview"
                className="w-full max-h-48 object-cover rounded-lg border border-border"
              />
              <button
                onClick={() => setPreview(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Change photo
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

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
          )}
        </div>

        <DialogFooter>
          <button
            onClick={onSwitchToUrl}
            className="mr-auto text-xs text-muted-foreground hover:text-primary transition-colors"
          >
            Import from URL instead
          </button>
          <Button variant="outline" onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleParse} disabled={!preview || loading}>
            {loading ? 'Parsing…' : 'Parse recipe'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
