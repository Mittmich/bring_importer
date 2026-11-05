import { useState, type ReactNode } from 'react'
import { ArrowLeft, Camera, ChevronRight, Link2, PenLine } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { LanguageSelect } from '@/components/LanguageSelect'
import { useI18n, type Language } from '@/i18n'

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

/** "Write it yourself": title, servings, language, ingredients (one per line) → editor. */
export function ManualRecipeModal({
  open,
  onOpenChange,
  onBack,
  onDone,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onBack: () => void
  onDone: (uuid: string) => void
}) {
  const { t, lang } = useI18n()
  const [title, setTitle] = useState('')
  const [servings, setServings] = useState('4')
  const [ingredients, setIngredients] = useState('')
  // Override of the recipe language; null = follow the UI language.
  const [langOverride, setLangOverride] = useState<Language | null>(null)
  const recipeLang = langOverride ?? lang
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setTitle('')
    setServings('4')
    setIngredients('')
    setLangOverride(null)
    setSaving(false)
    setError(null)
  }

  function close() {
    reset()
    onOpenChange(false)
  }

  async function create() {
    if (!title.trim() || saving) return
    setSaving(true)
    setError(null)
    const count = parseInt(servings, 10)
    try {
      const result = await api.createRecipe({
        title: title.trim(),
        language: recipeLang,
        recipeYield: count > 0 ? `${count} ${t('recipe.servings')}` : '',
        ingredients_text: ingredients.trim() || undefined,
      })
      reset()
      onDone(result.uuid)
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : t('manual.failed'))
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <button
          type="button"
          onClick={() => {
            reset()
            onBack()
          }}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3"
        >
          <ArrowLeft className="w-4 h-4" /> {t('add.back')}
        </button>
        <DialogHeader>
          <DialogTitle>{t('add.manual')}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="manual-title">{t('manual.titleLabel')}</Label>
            <Input
              id="manual-title"
              value={title}
              placeholder={t('manual.titlePlaceholder')}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && create()}
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="manual-servings">{t('manual.servings')}</Label>
              <Input
                id="manual-servings"
                type="number"
                inputMode="numeric"
                min={1}
                max={99}
                value={servings}
                onChange={(e) => setServings(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="manual-language">{t('manual.language')}</Label>
              <LanguageSelect id="manual-language" value={recipeLang} onChange={setLangOverride} className="w-full" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="manual-ingredients">
              {t('manual.ingredients')}{' '}
              <span className="font-normal text-muted-foreground">{t('manual.ingredientsOptional')}</span>
            </Label>
            <Textarea
              id="manual-ingredients"
              rows={5}
              value={ingredients}
              placeholder={t('manual.ingredientsPlaceholder')}
              onChange={(e) => setIngredients(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t('manual.ingredientsHint')}</p>
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={close} disabled={saving}>
            {t('common.cancel')}
          </Button>
          <Button onClick={create} disabled={!title.trim() || saving}>
            {saving ? t('common.creating') : t('manual.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
