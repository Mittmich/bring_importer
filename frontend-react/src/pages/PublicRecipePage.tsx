import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ExternalLink, LogIn, BookmarkPlus } from 'lucide-react'
import { api, type Ingredient, type InstructionStep } from '@/lib/api'
import { isAuthenticated } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

function formatIngredient(ing: Ingredient): string {
  return `${ing.amount} ${ing.name}`.trim()
}

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

  // Only check ownership if the user is authenticated (avoids a 401 redirect).
  const { data: myRecipes } = useQuery({
    queryKey: ['recipes'],
    queryFn: () => api.listRecipes(),
    enabled: loggedIn,
  })

  const isOwner = myRecipes?.some((r) => r.uuid === uuid) ?? false

  const cloneMutation = useMutation({
    mutationFn: () => api.cloneRecipe(uuid!),
    onSuccess: (data) => navigate(`/recipes/${data.uuid}`),
  })

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    )
  }

  if (isError || !recipe) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center gap-3">
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
    <div className="min-h-screen bg-[#F8FAFC]">
      {/* Header */}
      <div className="bg-white border-b border-border px-4 py-3 flex items-center justify-between max-w-2xl mx-auto">
        <span className="text-sm font-semibold text-primary">Recipe</span>
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

      <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-4">
        {/* Hero card */}
        <div className="bg-white rounded-xl border border-border px-6 py-6">
          <h1 className="text-xl font-bold text-foreground mb-3">{recipe.name}</h1>

          <div className="flex flex-wrap gap-2 mb-4">
            {recipe.recipeYield && (
              <span className="px-2.5 py-1 rounded-full border border-border bg-muted/50 text-sm text-muted-foreground">
                🍽 {recipe.recipeYield}
              </span>
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
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Ingredients
              </h2>
            </div>
            <div>
              {recipe.ingredients.map((ing, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 px-4 py-3.5 border-b border-border/50 last:border-0"
                >
                  <span className="w-2 h-2 rounded-full bg-primary/40 flex-shrink-0" />
                  <span className="text-base text-foreground">{formatIngredient(ing)}</span>
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
            <PublicInstructions steps={recipe.instructions} ingredients={recipe.ingredients} />
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
  )
}

function PublicInstructions({
  steps,
  ingredients,
}: {
  steps: InstructionStep[]
  ingredients: Ingredient[]
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
                    {formatIngredient(ing)}
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
