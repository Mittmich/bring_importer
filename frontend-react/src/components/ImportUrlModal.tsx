import { useState } from 'react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'

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

  function reset() {
    setUrl('')
    setNote('')
    setError(null)
    setLoading(false)
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
      const result = await api.importUrl(url.trim(), note.trim() || undefined)
      reset()
      onDone(result.uuid)
    } catch (e: any) {
      setError(e.message ?? 'Failed to import recipe.')
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import from URL</DialogTitle>
          <DialogDescription>
            Paste a recipe page link and we'll fetch and extract the recipe.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="recipe-url">Recipe URL</Label>
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
            <Label htmlFor="recipe-note">Note (optional)</Label>
            <Textarea
              id="recipe-note"
              placeholder="Any notes about this recipe…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
            />
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
          )}

          {loading && (
            <p className="text-sm text-muted-foreground text-center">Fetching and parsing the page…</p>
          )}
        </div>

        <DialogFooter>
          <button
            onClick={onSwitchToPhoto}
            className="mr-auto text-xs text-muted-foreground hover:text-primary transition-colors"
          >
            Import from photo instead
          </button>
          <Button variant="outline" onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleImport} disabled={!url.trim() || loading}>
            {loading ? 'Importing…' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
