import { useState } from 'react'
import { Check, Copy, Share2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { useI18n } from '@/i18n'

/** Shows a freshly created one-time link once, with Copy and (where supported) Share. */
export function LinkDialog({
  url,
  title,
  description,
  onClose,
}: {
  url: string | null
  title: string
  description: string
  onClose: () => void
}) {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const canShare = typeof navigator !== 'undefined' && !!navigator.share

  async function copy() {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard blocked: the field is selectable as a fallback.
    }
  }

  async function share() {
    if (!url) return
    try {
      await navigator.share({ title, url })
    } catch {
      // Closing the share sheet is fine.
    }
  }

  return (
    <Dialog
      open={!!url}
      onOpenChange={(o) => {
        if (!o) {
          setCopied(false)
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <Input readOnly value={url ?? ''} onFocus={(e) => e.target.select()} className="font-mono text-xs" />
        <p className="text-xs text-amber-700 mt-2">{t('admin.linkOnce')}</p>
        <div className="flex gap-2 mt-3">
          <Button onClick={copy} className="flex-1">
            {copied ? <Check className="w-4 h-4 mr-1.5" /> : <Copy className="w-4 h-4 mr-1.5" />}
            {copied ? t('admin.copied') : t('admin.copy')}
          </Button>
          {canShare && (
            <Button variant="outline" onClick={share} className="flex-1">
              <Share2 className="w-4 h-4 mr-1.5" /> {t('admin.shareLink')}
            </Button>
          )}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              setCopied(false)
              onClose()
            }}
          >
            {t('admin.done')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
