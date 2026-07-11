import { useState } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, Pencil, Trash2, Utensils, X } from 'lucide-react'
import { api, type RecipeListItem } from '@/lib/api'
import { useRecipeImage } from '@/hooks/useRecipeImage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function CookbookDetailPage() {
  const { id } = useParams<{ id: string }>()
  const cookbookId = Number(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['cookbook', cookbookId],
    queryFn: () => api.getCookbook(cookbookId),
    enabled: !!id,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['cookbook', cookbookId] })
    queryClient.invalidateQueries({ queryKey: ['cookbooks'] })
  }

  const rename = useMutation({
    mutationFn: (n: string) => api.renameCookbook(cookbookId, n),
    onSuccess: () => {
      setEditing(false)
      invalidate()
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteCookbook(cookbookId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cookbooks'] })
      navigate('/cookbooks')
    },
  })
  const removeRecipe = useMutation({
    mutationFn: (uuid: string) => api.removeRecipeFromCookbook(cookbookId, uuid),
    onSuccess: invalidate,
  })

  if (isLoading) {
    return <Centered>Loading…</Centered>
  }
  if (isError || !data) {
    return (
      <Centered>
        <div className="text-center space-y-3">
          <p className="text-sm text-muted-foreground">Cookbook not found.</p>
          <Button variant="outline" size="sm" onClick={() => navigate('/cookbooks')}>
            Back to cookbooks
          </Button>
        </div>
      </Centered>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-3xl mx-auto w-full p-4 md:p-6 space-y-4 pt-6 pb-10">
        <Link
          to="/cookbooks"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> Cookbooks
        </Link>

        <div className="flex items-center gap-2">
          {editing ? (
            <form
              className="flex items-center gap-2 flex-1"
              onSubmit={(e) => {
                e.preventDefault()
                const n = name.trim()
                if (n) rename.mutate(n)
              }}
            >
              <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} />
              <Button type="submit" size="icon" disabled={rename.isPending || !name.trim()}>
                <Check className="w-4 h-4" />
              </Button>
              <Button type="button" size="icon" variant="ghost" onClick={() => setEditing(false)}>
                <X className="w-4 h-4" />
              </Button>
            </form>
          ) : (
            <>
              <h1 className="text-xl font-bold text-foreground flex-1 truncate">{data.name}</h1>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => {
                  setName(data.name)
                  setEditing(true)
                }}
                aria-label="Rename cookbook"
              >
                <Pencil className="w-4 h-4" />
              </Button>
              {confirmDelete ? (
                <>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => remove.mutate()}
                    disabled={remove.isPending}
                  >
                    {remove.isPending ? 'Deleting…' : 'Delete'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  size="icon"
                  variant="ghost"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => setConfirmDelete(true)}
                  aria-label="Delete cookbook"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              )}
            </>
          )}
        </div>

        <p className="text-sm text-muted-foreground -mt-2">
          {data.recipe_count} {data.recipe_count === 1 ? 'recipe' : 'recipes'}
        </p>

        {data.recipes.length === 0 ? (
          <div className="text-center py-14">
            <Utensils className="w-8 h-8 text-primary/30 mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">
              No recipes yet. Open a recipe and use “Add to cookbook”.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {data.recipes.map((r) => (
              <RecipeCard
                key={r.uuid}
                recipe={r}
                onRemove={() => removeRecipe.mutate(r.uuid)}
                removing={removeRecipe.isPending}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center bg-[#F8FAFC] text-sm text-muted-foreground p-6">
      {children}
    </div>
  )
}

function RecipeCard({
  recipe,
  onRemove,
  removing,
}: {
  recipe: RecipeListItem
  onRemove: () => void
  removing: boolean
}) {
  const src = useRecipeImage(recipe.image_url)
  return (
    <div className="group relative rounded-xl border border-border bg-white overflow-hidden">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault()
          onRemove()
        }}
        disabled={removing}
        aria-label="Remove from cookbook"
        className="absolute top-1.5 right-1.5 z-10 w-7 h-7 rounded-full bg-black/45 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity hover:bg-black/65"
      >
        <X className="w-4 h-4" />
      </button>
      <NavLink to={`/recipes/${recipe.uuid}`} className="block">
        <div className="aspect-video bg-muted overflow-hidden">
          {src ? (
            <img
              src={src}
              alt=""
              className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center bg-primary/5 text-primary/30">
              <Utensils className="w-6 h-6" />
            </div>
          )}
        </div>
        <p className="text-sm font-medium text-foreground truncate p-2.5">{recipe.title}</p>
      </NavLink>
    </div>
  )
}
