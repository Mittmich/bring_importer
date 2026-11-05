import type { ReactNode } from 'react'
import { Camera, ChevronRight, Link2, PenLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { useI18n } from '@/i18n'

export type AddSource = 'photo' | 'url' | 'manual'

/** "Add a recipe" chooser: photo, website, or write it yourself. */
export function AddRecipeModal({
  open,
  onOpenChange,
  onChoose,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onChoose: (source: AddSource) => void
}) {
  const { t } = useI18n()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('add.title')}</DialogTitle>
          <DialogDescription>{t('add.description')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2.5">
          <SourceCard icon={<Camera />} title={t('add.photo')} hint={t('add.photoHint')} onClick={() => onChoose('photo')} />
          <SourceCard icon={<Link2 />} title={t('add.url')} hint={t('add.urlHint')} onClick={() => onChoose('url')} />
          <SourceCard icon={<PenLine />} title={t('add.manual')} hint={t('add.manualHint')} onClick={() => onChoose('manual')} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function SourceCard({
  icon,
  title,
  hint,
  onClick,
}: {
  icon: ReactNode
  title: string
  hint: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-3 rounded-lg border border-border bg-white p-3.5 text-left transition-colors hover:border-primary/50 hover:bg-primary/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 [&>svg]:w-5 [&>svg]:h-5">
        {icon}
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-medium text-foreground">{title}</span>
        <span className="block text-xs text-muted-foreground truncate">{hint}</span>
      </span>
      <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
    </button>
  )
}
