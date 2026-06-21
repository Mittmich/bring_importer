import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, type UseMutationResult } from '@tanstack/react-query'
import { ChevronDown, ExternalLink, LogIn, BookmarkPlus } from 'lucide-react'
import { api, type Recipe, type Ingredient, type InstructionStep } from '@/lib/api'
import { isAuthenticated } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { KeepAwakeButton } from '@/components/KeepAwakeButton'
import { parseServings, servingsUnit, formatIngredient } from '@/lib/scaling'

export function PublicRecipePage() {
  const { uuid } = useParams<{ uuid: string }>()
  const navigate = useNavigate()
  const loggedIn = isAuthenticated()

  const { data: recipe, isLoading, isError } = useQuery({
    queryKey: ['public-recipe', uuid],
    queryFn: () => api.getRecipe(uuid!),
    enabled: !!uuid,
    retry: false,
  })

  // The recipe payload tells us whether the viewer owns it (no extra fetch).
  const isOwner = (loggedIn && recipe?.owned) ?? false

  const cloneMutation = useMutation({
    mutationFn: () => api.cloneRecipe(uuid!),
    onSuccess: (data) => navigate(`/recipes/${data.uuid}`),
  })

  if (isLoading) {
    return (
      <div className="h-[100svh] bg-[#F8FAFC] flex items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    )
  }

  if (isError || !recipe) {
    return (
      <div className="h-[100svh] bg-[#F8FAFC] flex flex-col items-center justify-center gap-3">
        <p className="text-base font-medium text-foreground">Recipe not found</p>
        <p className="text-sm text-muted-foreground">This recipe is private or doesn't exist.</p>
        {loggedIn && (
          <Button variant="outline" size="sm" onClick={() => navigate('/recipes')}>
            Go to my recipes
          </Button>
        )}
      </div>
    )
  }

  return (
    <PublicRecipeView
      uuid={uuid!}
      recipe={recipe}
      isOwner={isOwner}
      loggedIn={loggedIn}
      cloneMutation={cloneMutation}
    />
  )
}

interface ViewProps {
  uuid: string
  recipe: Recipe
  isOwner: boolean
  loggedIn: boolean
  cloneMutation: UseMutationResult<{ uuid: string; url: string }, Error, void, unknown>
}

function PublicRecipeView({ uuid, recipe, isOwner, loggedIn, cloneMutation }: ViewProps) {
  const navigate = useNavigate()
  const [ingredientsOpen, setIngredientsOpen] = useState(false)

  const baseServings = parseServings(recipe.recipeYield)
  const unit = servingsUnit(recipe.recipeYield)
  const [servings, setServings] = useState(baseServings)
  const scale = servings / baseServings

  return (
    <div className="flex flex-col h-[100svh] bg-[#F8FAFC]">
      {/* Header */}
      <div className="bg-white border-b border-border px-4 py-3 flex items-center justify-between gap-2 max-w-2xl mx-auto w-full">
        <span className="text-sm font-semibold text-primary">Recipe</span>
        <div className="flex items-center gap-2">
          <KeepAwakeButton />
          {isOwner ? (
            <Button size="sm" variant="outline" onClick={() => navigate(`/recipes/${uuid}`)}>
              Open in my recipes
            </Button>
          ) : loggedIn ? (
            <Button
              size="sm"
              onClick={() => cloneMutation.mutate()}
              disabled={cloneMutation.isPending || cloneMutation.isSuccess}
            >
              <BookmarkPlus className="w-3.5 h-3.5 mr-1.5" />
              {cloneMutation.isPending ? 'Saving…' : cloneMutation.isSuccess ? 'Saved!' : 'Save to my recipes'}
            </Button>
          ) : (
            <Button size="sm" onClick={() => navigate('/login')}>
              <LogIn className="w-3.5 h-3.5 mr-1.5" />
              Log in to save
            </Button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-4">
          {/* Hero card */}
          <div className="bg-white rounded-xl border border-border px-6 py-6">
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
              <p className="text-base text-muted-foreground leading-relaxed">{recipe.description}</p>
            )}
          </div>

          {/* Ingredients */}
          {recipe.ingredients && recipe.ingredients.length > 0 && (
            <div className="bg-white rounded-xl border border-border overflow-hidden">
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
          )}

          {/* Instructions */}
          {recipe.instructions && recipe.instructions.length > 0 && (
            <div className="bg-white rounded-xl border border-border overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Instructions
                </h2>
              </div>
              <PublicInstructions steps={recipe.instructions} ingredients={recipe.ingredients} scale={scale} />
            </div>
          )}

          {/* Save CTA at bottom */}
          {!isOwner && (
            <div className="bg-white rounded-xl border border-border p-5 flex flex-col items-center gap-3 text-center">
              <p className="text-sm text-muted-foreground">Like this recipe? Save it to your collection.</p>
              {loggedIn ? (
                <Button
                  onClick={() => cloneMutation.mutate()}
                  disabled={cloneMutation.isPending || cloneMutation.isSuccess}
                >
                  <BookmarkPlus className="w-4 h-4 mr-1.5" />
                  {cloneMutation.isPending ? 'Saving…' : cloneMutation.isSuccess ? 'Saved!' : 'Save to my recipes'}
                </Button>
              ) : (
                <Button onClick={() => navigate('/login')}>
                  <LogIn className="w-4 h-4 mr-1.5" />
                  Log in to save
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function PublicInstructions({
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
