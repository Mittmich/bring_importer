import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

export function EditRecipePage() {
  const { uuid } = useParams<{ uuid: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: recipe, isLoading } = useQuery({
    queryKey: ['recipe', uuid],
    queryFn: () => api.getRecipe(uuid!),
    enabled: !!uuid,
  })

  const [title, setTitle] = useState('')
  const [yield_, setYield] = useState('')
  const [description, setDescription] = useState('')
  const [ingredients, setIngredients] = useState('')
  const [note, setNote] = useState('')

  useEffect(() => {
    if (!recipe) return
    setTitle(recipe.name ?? '')
    setYield(recipe.recipeYield ?? '')
    setDescription(recipe.description ?? '')
    setIngredients((recipe.recipeIngredient ?? []).join('\n'))
    setNote(recipe.note ?? '')
  }, [recipe])

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateRecipe(uuid!, {
        title: title,
        recipeYield: yield_,
        description,
        recipeIngredient: ingredients.split('\n').map((s) => s.trim()).filter(Boolean),
        note,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipe', uuid] })
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      navigate(`/recipes/${uuid}`)
    },
  })

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground bg-[#F8FAFC]">
        Loading…
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-[#F8FAFC]">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-border">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <span className="flex-1 text-sm font-semibold text-foreground truncate">Edit recipe</span>
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-5">
          {saveMutation.isError && (
            <p className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">
              {(saveMutation.error as any)?.message ?? 'Save failed.'}
            </p>
          )}

          <div className="bg-white rounded-xl border border-border p-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Recipe name"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="yield">Servings</Label>
              <Input
                id="yield"
                value={yield_}
                onChange={(e) => setYield(e.target.value)}
                placeholder="e.g. 4 servings"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief description…"
                rows={2}
              />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-border p-5 space-y-1.5">
            <Label htmlFor="ingredients">Ingredients</Label>
            <p className="text-xs text-muted-foreground">One ingredient per line</p>
            <Textarea
              id="ingredients"
              value={ingredients}
              onChange={(e) => setIngredients(e.target.value)}
              placeholder={'400g spaghetti\n200g guanciale\n4 egg yolks'}
              rows={8}
              className="font-mono text-sm"
            />
          </div>

          <div className="bg-white rounded-xl border border-border p-5 space-y-1.5">
            <Label htmlFor="note">Note</Label>
            <Textarea
              id="note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Personal notes about this recipe…"
              rows={3}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
