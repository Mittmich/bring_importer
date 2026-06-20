import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ChevronDown, ExternalLink, Pencil, Share2, Trash2 } from 'lucide-react'
import { api, type Recipe, type Ingredient, type InstructionStep } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

function parseServings(recipeYield?: string): number {
  if (!recipeYield) return 4
  const m = recipeYield.match(/\d+/)
  return m ? parseInt(m[0], 10) : 4
}

function servingsUnit(recipeYield?: string): string {
  if (!recipeYield) return 'servings'
  return recipeYield.replace(/^\d+\s*/, '').trim() || 'servings'
}

// Scale a number to a readable form, using Unicode fraction symbols for
// common values (½, ⅓, ¼ …) and one decimal place otherwise.
function formatAmount(n: number): string {
  n = Math.round(n * 100) / 100
  const whole = Math.floor(n)
  const frac = n - whole
  const FRACS: [number, string][] = [
    [1 / 4, '¼'], [1 / 3, '⅓'], [1 / 2, '½'], [2 / 3, '⅔'], [3 / 4, '¾'],
  ]
  for (const [val, sym] of FRACS) {
    if (Math.abs(frac - val) < 0.06) return whole > 0 ? `${whole}${sym}` : sym
  }
  if (frac < 0.05) return String(whole)
  const fixed = Math.round(n * 10) / 10
  return fixed % 1 === 0 ? String(fixed) : fixed.toFixed(1)
}

// Scale all numbers in a string by `factor`.
// Handles: integers ("2"), decimals ("1.5", "1,5"), fractions ("1/2"),
// and mixed numbers ("1 1/2").
function scaleText(text: string, factor: number): string {
  if (Math.abs(factor - 1) < 0.001) return text
  return text.replace(
    /(\d+)\s+(\d+)\s*\/\s*(\d+)|(\d+)\s*\/\s*(\d+)|(\d+(?:[.,]\d+)?)/g,
    (_m, mW, mN, mD, fN, fD, num) => {
      const value =
        mW !== undefined ? parseInt(mW) + parseInt(mN) / parseInt(mD)
        : fN !== undefined ? parseInt(fN) / parseInt(fD)
        : parseFloat(num.replace(',', '.'))
      return formatAmount(value * factor)
    },
  )
}

function formatIngredient(ing: Ingredient, scale: number): string {
  const scaledAmount = scaleText(ing.amount, scale)
  return `${scaledAmount} ${ing.name}`.trim()
}

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

  function handleShare() {
    navigator.clipboard.writeText(`${window.location.origin}/share/${uuid}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const baseServings = parseServings(recipe.recipeYield)
  const unit = servingsUnit(recipe.recipeYield)
  const [servings, setServings] = useState(baseServings)
  const scale = servings / baseServings

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteRecipe(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      navigate('/recipes')
    },
  })

  const bringUrl = `${window.location.origin}/api/recipes/${uuid}.html`
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
          <ArrowLeft className="w-5 h-5" /> Recipes
        </button>
        <span className="flex-1" />
        {recipe.is_public && (
          <Button variant="outline" size="sm" onClick={handleShare}>
            <Share2 className="w-4 h-4" />
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={() => navigate(`/recipes/${uuid}/edit`)}>
          <Pencil className="w-4 h-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Hero card */}
        <div className="bg-white border-b border-border px-6 py-6">
          <h1 className="text-xl font-bold text-foreground mb-3">{recipe.name}</h1>

          <div className="flex flex-wrap gap-2 mb-4">
            {recipe.recipeYield && (
              <div className="flex items-center gap-1 px-2 py-1 rounded-full border border-border bg-muted/50 text-sm font-medium text-muted-foreground select-none">
                <button
                  onClick={() => setServings((s) => Math.max(1, s - 1))}
                  className="w-7 h-7 flex items-center justify-center rounded hover:bg-muted transition-colors text-lg leading-none"
                  aria-label="Fewer servings"
                >−</button>
                <span className="px-1">🍽 {servings} {unit}</span>
                <button
                  onClick={() => setServings((s) => s + 1)}
                  className="w-7 h-7 flex items-center justify-center rounded hover:bg-muted transition-colors text-lg leading-none"
                  aria-label="More servings"
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
          </div>

          {recipe.description && (
            <p className="text-base text-muted-foreground mb-4 leading-relaxed">{recipe.description}</p>
          )}

          <div className="flex gap-2">
            <a
              href={bringImportUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 h-9 px-4 py-2 transition-colors"
            >
              Add to Bring
            </a>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate(`/recipes/${uuid}/edit`)}
              className="hidden md:flex"
            >
              <Pencil className="w-3.5 h-3.5 mr-1" /> Edit
            </Button>
            {recipe.is_public && (
              <Button variant="outline" size="sm" onClick={handleShare} className="hidden md:flex">
                <Share2 className="w-3.5 h-3.5 mr-1" />
                {copied ? 'Copied!' : 'Share'}
              </Button>
            )}
            {confirmDelete ? (
              <>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Confirm delete'}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmDelete(true)}
                className="hidden md:flex text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>
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
                    Ingredients
                  </h2>
                  <ChevronDown
                    className={`w-4 h-4 text-muted-foreground transition-transform duration-200 ${ingredientsOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                {/* Desktop: always visible, non-interactive */}
                <h2 className="hidden md:block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Ingredients
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
                  Instructions
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
                Note
              </h2>
              <p className="text-sm text-foreground">{recipe.note}</p>
            </div>
          )}

          {/* Mobile delete */}
          <div className="md:hidden pt-2">
            {confirmDelete ? (
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  className="flex-1"
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? 'Deleting…' : 'Confirm delete'}
                </Button>
                <Button variant="outline" onClick={() => setConfirmDelete(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                variant="outline"
                className="w-full text-muted-foreground"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 className="w-4 h-4 mr-2" /> Delete recipe
              </Button>
            )}
          </div>
        </div>
      </div>
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
