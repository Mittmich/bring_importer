import { useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, GripVertical, Plus, Trash2 } from 'lucide-react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { api, type Ingredient, type InstructionStep } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { TagChip } from '@/components/ui/tag-chip'

// Local rows carry a stable client-side id so drag-and-drop has a key that
// follows the item (not its position). Stripped before saving.
type IngredientRow = Ingredient & { _id: string }
type StepRow = InstructionStep & { _id: string }

const uid = () => crypto.randomUUID()

// Build an old-index -> new-index map for a single move within a list of
// length `len`, so instruction→ingredient references can be remapped after an
// ingredient is dragged to a new position.
function remapIndices(len: number, oldIndex: number, newIndex: number): number[] {
  const positions = Array.from({ length: len }, (_, i) => i)
  const moved = arrayMove(positions, oldIndex, newIndex) // moved[newPos] = oldPos
  const map = new Array<number>(len)
  moved.forEach((oldPos, newPos) => {
    map[oldPos] = newPos
  })
  return map
}

function SortableRow({
  id,
  align = 'start',
  children,
}: {
  id: string
  align?: 'start' | 'center'
  children: ReactNode
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id })
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 10 : undefined,
    position: 'relative',
  }
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex gap-2 ${align === 'center' ? 'items-center' : 'items-start'}`}
    >
      <button
        ref={setActivatorNodeRef}
        type="button"
        {...attributes}
        {...listeners}
        aria-label="Drag to reorder"
        className={`shrink-0 touch-none cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground ${align === 'center' ? '' : 'mt-2.5'}`}
      >
        <GripVertical className="w-4 h-4" />
      </button>
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  )
}

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
  const [ingredients, setIngredients] = useState<IngredientRow[]>([])
  const [instructions, setInstructions] = useState<StepRow[]>([])
  const [note, setNote] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')

  const { data: allTags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: api.getTags,
  })

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  useEffect(() => {
    if (!recipe) return
    setTitle(recipe.name ?? '')
    setYield(recipe.recipeYield ?? '')
    setDescription(recipe.description ?? '')
    setIngredients((recipe.ingredients ?? []).map((ing) => ({ ...ing, _id: uid() })))
    setInstructions((recipe.instructions ?? []).map((step) => ({ ...step, _id: uid() })))
    setNote(recipe.note ?? '')
    setIsPublic(recipe.is_public ?? false)
    setTags((recipe.tags ?? []).map((t) => t.name))
  }, [recipe])

  function addTag(raw: string) {
    const name = raw.trim().replace(/\s+/g, ' ')
    setTagInput('')
    if (!name) return
    setTags((prev) => (prev.some((t) => t.toLowerCase() === name.toLowerCase()) ? prev : [...prev, name]))
  }

  function removeTag(name: string) {
    setTags((prev) => prev.filter((t) => t !== name))
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateRecipe(uuid!, {
        title,
        recipeYield: yield_,
        description,
        // Strip the client-side _id before sending.
        ingredients: ingredients.map((ing) => ({ amount: ing.amount, name: ing.name })),
        instructions: instructions.map((step) => ({ text: step.text, ingredients: step.ingredients })),
        note,
        is_public: isPublic,
        tags,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recipe', uuid] })
      queryClient.invalidateQueries({ queryKey: ['recipes'] })
      queryClient.invalidateQueries({ queryKey: ['tags'] })
      navigate(`/recipes/${uuid}`)
    },
  })

  // --- Ingredient helpers ---

  function updateIngredient(index: number, field: keyof Ingredient, value: string) {
    setIngredients((prev) => prev.map((ing, i) => (i === index ? { ...ing, [field]: value } : ing)))
  }

  function addIngredient() {
    setIngredients((prev) => [...prev, { amount: '', name: '', _id: uid() }])
  }

  function handleIngredientDragEnd(e: DragEndEvent) {
    const { active, over } = e
    if (!over || active.id === over.id) return
    const oldIndex = ingredients.findIndex((x) => x._id === active.id)
    const newIndex = ingredients.findIndex((x) => x._id === over.id)
    if (oldIndex < 0 || newIndex < 0) return
    // Reorder the ingredients, then remap every instruction's ingredient-index
    // references so they keep pointing at the same ingredients.
    const map = remapIndices(ingredients.length, oldIndex, newIndex)
    setIngredients((prev) => arrayMove(prev, oldIndex, newIndex))
    setInstructions((prev) =>
      prev.map((step) => ({
        ...step,
        ingredients: step.ingredients.map((idx) => map[idx]).sort((a, b) => a - b),
      })),
    )
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
    setInstructions((prev) => [...prev, { text: '', ingredients: [], _id: uid() }])
  }

  function removeInstruction(index: number) {
    setInstructions((prev) => prev.filter((_, i) => i !== index))
  }

  function handleInstructionDragEnd(e: DragEndEvent) {
    const { active, over } = e
    if (!over || active.id === over.id) return
    const oldIndex = instructions.findIndex((x) => x._id === active.id)
    const newIndex = instructions.findIndex((x) => x._id === over.id)
    if (oldIndex < 0 || newIndex < 0) return
    setInstructions((prev) => arrayMove(prev, oldIndex, newIndex))
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

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="tags">Tags</Label>
                <Link to="/account/tags" className="text-xs font-medium text-primary hover:underline">
                  Manage tags →
                </Link>
              </div>

              {/* Selected tags */}
              {tags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-1">
                  {tags.map((t) => {
                    const info = allTags.find((a) => a.name.toLowerCase() === t.toLowerCase())
                    return (
                      <TagChip key={t} name={t} color={info?.color} onRemove={() => removeTag(t)} />
                    )
                  })}
                </div>
              )}

              <Input
                id="tags"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault()
                    addTag(tagInput)
                  }
                }}
                onBlur={() => addTag(tagInput)}
                placeholder="Add a tag and press Enter"
              />

              {/* Quick-select from existing tags */}
              {allTags.some((t) => !tags.some((sel) => sel.toLowerCase() === t.name.toLowerCase())) && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  <span className="text-xs text-muted-foreground self-center mr-0.5">Existing:</span>
                  {allTags
                    .filter((t) => !tags.some((sel) => sel.toLowerCase() === t.name.toLowerCase()))
                    .map((t) => (
                      <button key={t.id} type="button" onClick={() => addTag(t.name)}>
                        <TagChip name={t.name} color={t.color} muted />
                      </button>
                    ))}
                </div>
              )}
            </div>
          </div>

          {/* Ingredients */}
          <div className="bg-white rounded-xl border border-border p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <Label>Ingredients</Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Amount and name separately · drag <GripVertical className="w-3 h-3 inline -mt-0.5" /> to reorder
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={addIngredient}>
                <Plus className="w-3.5 h-3.5 mr-1" /> Add
              </Button>
            </div>

            {ingredients.length === 0 && (
              <p className="text-sm text-muted-foreground italic">No ingredients yet.</p>
            )}

            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleIngredientDragEnd}
            >
              <SortableContext
                items={ingredients.map((x) => x._id)}
                strategy={verticalListSortingStrategy}
              >
                <div className="space-y-2">
                  {ingredients.map((ing, i) => (
                    <SortableRow key={ing._id} id={ing._id} align="center">
                      <div className="flex items-center gap-2">
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
                    </SortableRow>
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </div>

          {/* Instructions */}
          <div className="bg-white rounded-xl border border-border p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <Label>Instructions</Label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Check which ingredients each step uses · drag{' '}
                  <GripVertical className="w-3 h-3 inline -mt-0.5" /> to reorder
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={addInstruction}>
                <Plus className="w-3.5 h-3.5 mr-1" /> Add
              </Button>
            </div>

            {instructions.length === 0 && (
              <p className="text-sm text-muted-foreground italic">No steps yet.</p>
            )}

            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleInstructionDragEnd}
            >
              <SortableContext
                items={instructions.map((x) => x._id)}
                strategy={verticalListSortingStrategy}
              >
                <div className="space-y-4">
                  {instructions.map((step, stepIdx) => (
                    <SortableRow key={step._id} id={step._id} align="start">
                      <div className="space-y-2 border border-border/60 rounded-lg p-3">
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
                                  key={ing._id}
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
                    </SortableRow>
                  ))}
                </div>
              </SortableContext>
            </DndContext>
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
