import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Plus, Trash2 } from 'lucide-react'
import { api, type Ingredient, type InstructionStep } from '@/lib/api'
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
  const [ingredients, setIngredients] = useState<Ingredient[]>([])
  const [instructions, setInstructions] = useState<InstructionStep[]>([])
  const [note, setNote] = useState('')
  const [isPublic, setIsPublic] = useState(false)

  useEffect(() => {
    if (!recipe) return
    setTitle(recipe.name ?? '')
    setYield(recipe.recipeYield ?? '')
    setDescription(recipe.description ?? '')
    setIngredients(recipe.ingredients ?? [])
    setInstructions(recipe.instructions ?? [])
    setNote(recipe.note ?? '')
    setIsPublic(recipe.is_public ?? false)
  }, [recipe])

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateRecipe(uuid!, {
        title,
        recipeYield: yield_,
        description,
        ingredients,
        instructions,
        note,
        is_public: isPublic,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipe', uuid] })
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      navigate(`/recipes/${uuid}`)
    },
  })

  // --- Ingredient helpers ---

  function updateIngredient(index: number, field: keyof Ingredient, value: string) {
    setIngredients((prev) => prev.map((ing, i) => (i === index ? { ...ing, [field]: value } : ing)))
  }

  function addIngredient() {
    setIngredients((prev) => [...prev, { amount: '', name: '' }])
  }

  function removeIngredient(index: number) {
    setIngredients((prev) => prev.filter((_, i) => i !== index))
    // Remove deleted index from all instruction ingredient refs, shift higher indices down
    setInstructions((prev) =>
      prev.map((step) => ({
        ...step,
        ingredients: step.ingredients
          .filter((idx) => idx !== index)
          .map((idx) => (idx > index ? idx - 1 : idx)),
      })),
    )
  }

  // --- Instruction helpers ---

  function updateInstructionText(index: number, text: string) {
    setInstructions((prev) =>
      prev.map((step, i) => (i === index ? { ...step, text } : step)),
    )
  }

  function toggleIngredientForStep(stepIndex: number, ingIndex: number) {
    setInstructions((prev) =>
      prev.map((step, i) => {
        if (i !== stepIndex) return step
        const has = step.ingredients.includes(ingIndex)
        const next = has
          ? step.ingredients.filter((idx) => idx !== ingIndex)
          : [...step.ingredients, ingIndex].sort((a, b) => a - b)
        return { ...step, ingredients: next }
      }),
    )
  }

  function addInstruction() {
    setInstructions((prev) => [...prev, { text: '', ingredients: [] }])
  }

  function removeInstruction(index: number) {
    setInstructions((prev) => prev.filter((_, i) => i !== index))
  }

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

          {/* Basic info */}
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

          {/* Ingredients */}
          <div className="bg-white rounded-xl border border-border p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <Label>Ingredients</Label>
                <p className="text-xs text-muted-foreground mt-0.5">Amount and name separately</p>
              </div>
              <Button variant="outline" size="sm" onClick={addIngredient}>
                <Plus className="w-3.5 h-3.5 mr-1" /> Add
              </Button>
            </div>

            {ingredients.length === 0 && (
              <p className="text-sm text-muted-foreground italic">No ingredients yet.</p>
            )}

            <div className="space-y-2">
              {ingredients.map((ing, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground w-5 text-right shrink-0">{i + 1}.</span>
                  <Input
                    value={ing.amount}
                    onChange={(e) => updateIngredient(i, 'amount', e.target.value)}
                    placeholder="Amount (e.g. 2 cups)"
                    className="w-32 shrink-0 text-sm"
                  />
                  <Input
                    value={ing.name}
                    onChange={(e) => updateIngredient(i, 'name', e.target.value)}
                    placeholder="Ingredient name"
                    className="flex-1 text-sm"
                  />
                  <button
                    onClick={() => removeIngredient(i)}
                    className="text-muted-foreground hover:text-destructive transition-colors shrink-0"
                    aria-label="Remove ingredient"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Instructions */}
          <div className="bg-white rounded-xl border border-border p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <Label>Instructions</Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Check which ingredients each step uses
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={addInstruction}>
                <Plus className="w-3.5 h-3.5 mr-1" /> Add
              </Button>
            </div>

            {instructions.length === 0 && (
              <p className="text-sm text-muted-foreground italic">No steps yet.</p>
            )}

            <div className="space-y-4">
              {instructions.map((step, stepIdx) => (
                <div key={stepIdx} className="space-y-2 border border-border/60 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-bold text-primary min-w-[20px] pt-2.5 tabular-nums shrink-0">
                      {String(stepIdx + 1).padStart(2, '0')}
                    </span>
                    <Textarea
                      value={step.text}
                      onChange={(e) => updateInstructionText(stepIdx, e.target.value)}
                      placeholder="Describe this step…"
                      rows={2}
                      className="flex-1 text-sm"
                    />
                    <button
                      onClick={() => removeInstruction(stepIdx)}
                      className="text-muted-foreground hover:text-destructive transition-colors shrink-0 mt-2"
                      aria-label="Remove step"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {ingredients.length > 0 && (
                    <div className="ml-7 flex flex-wrap gap-1.5">
                      {ingredients.map((ing, ingIdx) => {
                        const checked = step.ingredients.includes(ingIdx)
                        return (
                          <button
                            key={ingIdx}
                            type="button"
                            onClick={() => toggleIngredientForStep(stepIdx, ingIdx)}
                            className={
                              `text-xs px-2 py-0.5 rounded-full border transition-colors ` +
                              (checked
                                ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                                : 'bg-muted/50 border-border text-muted-foreground hover:border-primary/30')
                            }
                          >
                            {`${ing.amount} ${ing.name}`.trim() || `Ingredient ${ingIdx + 1}`}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Note */}
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

          {/* Sharing */}
          <div className="bg-white rounded-xl border border-border p-5">
            <div className="flex items-center justify-between">
              <div>
                <Label>Sharing</Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {isPublic ? 'Anyone with the link can view this recipe.' : 'Only you can see this recipe.'}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={isPublic}
                onClick={() => setIsPublic((v) => !v)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${isPublic ? 'bg-primary' : 'bg-input'}`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${isPublic ? 'translate-x-6' : 'translate-x-1'}`}
                />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
