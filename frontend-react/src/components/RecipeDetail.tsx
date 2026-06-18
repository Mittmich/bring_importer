import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Pencil, Trash2, ExternalLink } from 'lucide-react'
import { api, type Recipe } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { config } from '@/lib/config'

interface Props {
  uuid: string
  recipe: Recipe
}

export function RecipeDetail({ uuid, recipe }: Props) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteRecipe(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      navigate('/recipes')
    },
  })

  const bringUrl = `${config.frontendUrl}/api/recipes/${uuid}.json`
  const bringImportUrl = `https://www.getbring.com/excuse?source=bringrecipe&url=${encodeURIComponent(bringUrl)}`

  return (
    <div className="flex flex-col h-full bg-[#F8FAFC]">
      {/* Mobile top bar */}
      <div className="md:hidden flex items-center gap-2 px-4 py-3 bg-white border-b border-border">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm font-medium text-primary"
        >
          <ArrowLeft className="w-4 h-4" /> Recipes
        </button>
        <span className="flex-1" />
        <Button variant="outline" size="sm" onClick={() => navigate(`/recipes/${uuid}/edit`)}>
          <Pencil className="w-3.5 h-3.5" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Hero card */}
        <div className="bg-white border-b border-border px-6 py-6">
          <h1 className="text-xl font-bold text-foreground mb-3">{recipe.name}</h1>

          <div className="flex flex-wrap gap-2 mb-4">
            {recipe.recipeYield && (
              <Badge variant="muted">🍽 {recipe.recipeYield}</Badge>
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
            <p className="text-sm text-muted-foreground mb-4 leading-relaxed">{recipe.description}</p>
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
          {recipe.recipeIngredient && recipe.recipeIngredient.length > 0 && (
            <div className="bg-white rounded-lg border border-border overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Ingredients
                </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x-0">
                {recipe.recipeIngredient.map((ing, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-3 px-4 py-2.5 border-b border-border/50 last:border-0"
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-primary/40 flex-shrink-0" />
                    <span className="text-sm text-foreground">{ing}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Instructions */}
          {(recipe.recipeInstructions?.length || recipe.html_content) && (
            <div className="bg-white rounded-lg border border-border overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Instructions
                </h2>
              </div>
              {recipe.recipeInstructions?.length
                ? <StructuredInstructions steps={recipe.recipeInstructions} />
                : <InstructionsDisplay html={recipe.html_content!} />
              }
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

function StructuredInstructions({ steps }: { steps: string[] }) {
  return (
    <ol className="divide-y divide-border/50">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3 px-4 py-3">
          <span className="text-xs font-bold text-primary min-w-[20px] pt-0.5 tabular-nums">
            {String(i + 1).padStart(2, '0')}
          </span>
          <span className="text-sm text-foreground leading-relaxed">{step}</span>
        </li>
      ))}
    </ol>
  )
}

function InstructionsDisplay({ html }: { html: string }) {
  // Extract steps from HTML or render as numbered paragraphs
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')

  // Try to get <li> items first (common recipe format)
  const steps: string[] = []
  const listItems = doc.querySelectorAll('li')
  if (listItems.length > 0) {
    listItems.forEach((li) => {
      const text = li.textContent?.trim()
      if (text) steps.push(text)
    })
  } else {
    // Fall back to paragraphs
    doc.querySelectorAll('p').forEach((p) => {
      const text = p.textContent?.trim()
      if (text) steps.push(text)
    })
  }

  if (steps.length === 0) {
    // Last resort: render raw text
    const text = doc.body.textContent?.trim() ?? ''
    return <p className="px-4 py-3 text-sm text-foreground">{text}</p>
  }

  return (
    <ol className="divide-y divide-border/50">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3 px-4 py-3">
          <span className="text-xs font-bold text-primary min-w-[20px] pt-0.5 tabular-nums">
            {String(i + 1).padStart(2, '0')}
          </span>
          <span className="text-sm text-foreground leading-relaxed">{step}</span>
        </li>
      ))}
    </ol>
  )
}
