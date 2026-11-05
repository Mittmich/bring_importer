import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookHeart, Check, ChevronDown, Copy, ExternalLink, FileDown, Languages, Link2, MoreHorizontal, Pencil, Trash2, UserPlus } from 'lucide-react'
import { api, type Recipe, type Ingredient, type InstructionStep } from '@/lib/api'
import { useRecipeImage } from '@/hooks/useRecipeImage'
import { AddToCookbookModal } from '@/components/AddToCookbookModal'
import { ShareRecipeModal } from '@/components/ShareRecipeModal'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { TagChip } from '@/components/ui/tag-chip'
import { KeepAwakeButton } from '@/components/KeepAwakeButton'
import { useExportPdf } from '@/hooks/useExportPdf'
import { RecipeCover } from '@/components/RecipeCover'
import { Menu, MenuItem, MenuSeparator } from '@/components/ui/menu'
import { parseServings, servingsUnit, formatIngredient } from '@/lib/scaling'
import { nativeName, useI18n } from '@/i18n'

interface Props {
  uuid: string
  recipe: Recipe
}

export function RecipeDetail({ uuid, recipe }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [ingredientsOpen, setIngredientsOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [cookbookOpen, setCookbookOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const { t, lang } = useI18n()

  // The viewer owns this recipe, or can edit it via a shared cookbook.
  const isOwner = recipe.owned ?? false
  const canEdit = isOwner || recipe.role === 'editor' || recipe.role === 'manager'

  function handleShare() {
    navigator.clipboard.writeText(`${window.location.origin}/share/${uuid}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Own recipe → a "(copy)" duplicate; someone else's → your own copy of it.
  const duplicateMutation = useMutation({
    mutationFn: () => api.cloneRecipe(uuid),
    onSuccess: (copy) => {
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      navigate(`/recipes/${copy.uuid}`)
    },
    onError: () => window.alert(t('recipe.duplicateFailed')),
  })

  const heroSrc = useRecipeImage(recipe.image_url)

  const baseServings = parseServings(recipe.recipeYield)
  const unit = servingsUnit(recipe.recipeYield, t('recipe.servings'))
  const [servings, setServings] = useState(baseServings)
  const scale = servings / baseServings
  const pdf = useExportPdf(uuid, servings)

  // Secondary actions, shared by the mobile top bar and the desktop action row.
  const moreMenu = (
    <Menu label={t('recipe.moreActions')} trigger={<MoreHorizontal className="w-4 h-4" />}>
      <MenuItem
        icon={<Copy />}
        onSelect={() => duplicateMutation.mutate()}
        disabled={duplicateMutation.isPending}
      >
        {duplicateMutation.isPending
          ? t('recipe.duplicating')
          : isOwner
            ? t('recipe.duplicate')
            : t('recipe.saveCopy')}
      </MenuItem>
      <MenuItem icon={<FileDown />} onSelect={pdf.exportPdf} disabled={pdf.busy}>
        {pdf.busy ? t('recipe.exportingPdf') : t('recipe.exportPdfLabel')}
      </MenuItem>
      {isOwner && (
        <MenuItem icon={<UserPlus />} onSelect={() => setShareOpen(true)}>
          {t('recipe.shareWithFriend')}
        </MenuItem>
      )}
      {recipe.is_public && (
        <MenuItem icon={<Link2 />} onSelect={handleShare}>
          {t('recipe.copyLink')}
        </MenuItem>
      )}
      {isOwner && (
        <>
          <MenuSeparator />
          <MenuItem icon={<Trash2 />} destructive onSelect={() => setConfirmDelete(true)}>
            {t('recipe.deleteRecipe')}
          </MenuItem>
        </>
      )}
    </Menu>
  )

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteRecipe(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      navigate('/recipes')
    },
  })

  // Bring fetches this server-side, so pass the language explicitly.
  const bringUrl = `${window.location.origin}/api/recipes/${uuid}.html?lang=${lang}`
  const bringImportUrl =
    `https://api.getbring.com/rest/bringrecipes/deeplink` +
    `?url=${encodeURIComponent(bringUrl)}` +
    `&baseQuantity=${baseServings}&requestedQuantity=${servings}&source=web`

  return (
    <div className="flex flex-col h-full bg-[#F8FAFC]">
      {/* Mobile top bar */}
      <div className="md:hidden flex items-center gap-2 px-4 py-4 bg-white border-b border-border">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-base font-medium text-primary"
        >
          <ArrowLeft className="w-5 h-5" /> {t('nav.recipes')}
        </button>
        <span className="flex-1" />
        <KeepAwakeButton />
        {canEdit && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/recipes/${uuid}/edit`)}
            aria-label={t('common.edit')}
          >
            <Pencil className="w-4 h-4" />
          </Button>
        )}
        {moreMenu}
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Hero image banner */}
        {/* No photo → a gradient band (shorter, so it doesn't push the recipe down). */}
        <RecipeCover
          seed={uuid}
          src={heroSrc}
          loading={!!recipe.has_image}
          alt={recipe.name}
          className={recipe.has_image ? 'w-full aspect-video' : 'w-full aspect-[5/2] md:aspect-[4/1]'}
        />

        {/* Not available in the UI language: say so, and offer translation to editors. */}
        {recipe.translation_available === false && (
          <div className="flex items-center gap-3 px-6 py-3 bg-amber-50 border-b border-amber-200 text-sm text-amber-900">
            <Languages className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1">
              {t('recipe.notInLanguage', {
                language: nativeName(lang),
                original: nativeName(recipe.language),
              })}
            </span>
            {canEdit && (
              <Button
                size="sm"
                variant="outline"
                className="bg-white"
                onClick={() => navigate(`/recipes/${uuid}/edit`)}
              >
                {t('recipe.translateInEditor')}
              </Button>
            )}
          </div>
        )}

        {/* Hero card */}
        <div className="bg-white border-b border-border px-6 py-6">
          <h1 className="text-xl font-bold text-foreground mb-3">{recipe.name}</h1>

          <div className="flex flex-wrap gap-2 mb-4">
            {recipe.recipeYield && (
              <div className="flex items-center gap-1 px-2 py-1 rounded-full border border-border bg-muted/50 text-sm font-medium text-muted-foreground select-none">
                <button
                  onClick={() => setServings((s) => Math.max(1, s - 1))}
                  className="w-7 h-7 flex items-center justify-center rounded hover:bg-muted transition-colors text-lg leading-none"
                  aria-label={t('recipe.fewerServings')}
                >−</button>
                <span className="px-1">🍽 {servings} {unit}</span>
                <button
                  onClick={() => setServings((s) => s + 1)}
                  className="w-7 h-7 flex items-center justify-center rounded hover:bg-muted transition-colors text-lg leading-none"
                  aria-label={t('recipe.moreServings')}
                >+</button>
              </div>
            )}
            {recipe.source?.kind === 'url' && recipe.source.value && (
              <Badge variant="muted">
                <a
                  href={recipe.source.value}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 hover:text-primary"
                >
                  {new URL(recipe.source.value).hostname.replace('www.', '')}
                  <ExternalLink className="w-3 h-3" />
                </a>
              </Badge>
            )}
            {isOwner === false && (recipe.owner_name || recipe.owner_email) && (
              <Badge variant="muted">
                <span className="flex items-center gap-1 text-primary">
                  <UserPlus className="w-3 h-3" />{' '}
                  {t('recipe.sharedBy', { name: recipe.owner_name || recipe.owner_email || '' })}
                </span>
              </Badge>
            )}
          </div>

          {recipe.description && (
            <p className="text-base text-muted-foreground mb-4 leading-relaxed">{recipe.description}</p>
          )}

          <div className="flex flex-wrap gap-2">
            <a
              href={bringImportUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 h-9 px-4 py-2 transition-colors"
            >
              {t('recipe.addToBring')}
            </a>
            <KeepAwakeButton className="hidden md:flex" />
            <Button variant="outline" size="sm" onClick={() => setCookbookOpen(true)}>
              <BookHeart className="w-3.5 h-3.5 mr-1" /> {t('recipe.cookbook')}
            </Button>
            {canEdit && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => navigate(`/recipes/${uuid}/edit`)}
                className="hidden md:flex"
              >
                <Pencil className="w-3.5 h-3.5 mr-1" /> {t('common.edit')}
              </Button>
            )}
            <div className="hidden md:block">{moreMenu}</div>
            {isOwner &&
              (confirmDelete ? (
                <>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => deleteMutation.mutate()}
                    disabled={deleteMutation.isPending}
                  >
                    {deleteMutation.isPending ? t('common.deleting') : t('recipe.confirmDelete')}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                    {t('common.cancel')}
                  </Button>
                </>
              ) : null)}
          </div>

          {recipe.tags && recipe.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-4">
              {recipe.tags.map((t) => (
                <TagChip key={t.name} name={t.name} />
              ))}
            </div>
          )}
        </div>

        <div className="p-4 md:p-6 space-y-4">
          {/* Ingredients */}
          {recipe.ingredients && recipe.ingredients.length > 0 && (
            <div className="bg-white rounded-lg border border-border overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                {/* Mobile: tap to expand */}
                <button
                  className="md:hidden w-full flex items-center justify-between"
                  onClick={() => setIngredientsOpen((o) => !o)}
                  aria-expanded={ingredientsOpen}
                >
                  <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    {t('recipe.ingredients')}
                  </h2>
                  <ChevronDown
                    className={`w-4 h-4 text-muted-foreground transition-transform duration-200 ${ingredientsOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                {/* Desktop: always visible, non-interactive */}
                <h2 className="hidden md:block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('recipe.ingredients')}
                </h2>
              </div>
              <div className={`${ingredientsOpen ? '' : 'hidden'} md:block`}>
                <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x-0">
                  {recipe.ingredients.map((ing, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3 px-4 py-3.5 border-b border-border/50 last:border-0"
                    >
                      <span className="w-2 h-2 rounded-full bg-primary/40 flex-shrink-0" />
                      <span className="text-base text-foreground">{formatIngredient(ing, scale)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Instructions */}
          {recipe.instructions && recipe.instructions.length > 0 && (
            <div className="bg-white rounded-lg border border-border overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('recipe.instructions')}
                </h2>
              </div>
              <StructuredInstructions
                steps={recipe.instructions}
                ingredients={recipe.ingredients}
                scale={scale}
              />
            </div>
          )}

          {/* Note */}
          {recipe.note && (
            <div className="bg-white rounded-lg border border-border p-4">
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                {t('recipe.note')}
              </h2>
              <p className="text-sm text-foreground">{recipe.note}</p>
            </div>
          )}

        </div>
      </div>

      <AddToCookbookModal open={cookbookOpen} onOpenChange={setCookbookOpen} recipeUuid={uuid} />
      <ShareRecipeModal open={shareOpen} onOpenChange={setShareOpen} recipeUuid={uuid} />
      {copied && (
        <div
          role="status"
          className="fixed left-1/2 -translate-x-1/2 bottom-24 md:bottom-6 z-50 flex items-center gap-2 rounded-lg bg-foreground text-background text-sm px-4 py-2.5 shadow-lg"
        >
          <Check className="w-4 h-4" /> {t('recipe.copied')}
        </div>
      )}
    </div>
  )
}

function StructuredInstructions({
  steps,
  ingredients,
  scale,
}: {
  steps: InstructionStep[]
  ingredients: Ingredient[]
  scale: number
}) {
  return (
    <ol className="divide-y divide-border/50">
      {steps.map((step, i) => (
        <li key={i} className="px-4 py-3 space-y-1.5">
          <div className="flex gap-3">
            <span className="text-xs font-bold text-primary min-w-[20px] pt-0.5 tabular-nums">
              {String(i + 1).padStart(2, '0')}
            </span>
            <span className="text-base text-foreground leading-relaxed">{step.text}</span>
          </div>
          {step.ingredients.length > 0 && (
            <div className="ml-8 flex flex-wrap gap-1">
              {step.ingredients.map((idx) => {
                const ing = ingredients[idx]
                return ing ? (
                  <span
                    key={idx}
                    className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium"
                  >
                    {formatIngredient(ing, scale)}
                  </span>
                ) : null
              })}
            </div>
          )}
        </li>
      ))}
    </ol>
  )
}
