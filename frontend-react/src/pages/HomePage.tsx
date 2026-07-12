import { useQuery } from '@tanstack/react-query'
import { NavLink, useNavigate, useOutletContext } from 'react-router-dom'
import { ChevronRight, Plus, Search, Utensils } from 'lucide-react'
import { api, type RecipeListItem, type TagInfo } from '@/lib/api'
import { useRecipeImage } from '@/hooks/useRecipeImage'
import { tagColor } from '@/lib/tagColors'
import { Button } from '@/components/ui/button'

// How many tag shelves to show, and how many recipes to pull per shelf.
const MAX_SHELVES = 8
const SHELF_SIZE = 12

function relativeDate(dateStr?: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return ''
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days}d ago`
  if (days < 30) return `${Math.floor(days / 7)}w ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

export function HomePage() {
  const { onImport } = useOutletContext<{ onImport: () => void }>()
  const navigate = useNavigate()

  const { data: tagData = [] } = useQuery({ queryKey: ['tags'], queryFn: () => api.getTags() })
  const { data: recentData, isLoading } = useQuery({
    queryKey: ['recipes', 'recent'],
    queryFn: () => api.listRecipes({ limit: SHELF_SIZE }),
  })

  const recent = recentData?.items ?? []
  const total = recentData?.total ?? 0
  const shelfTags = tagData
    .filter((t) => t.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, MAX_SHELVES)

  const openSearch = () => navigate('/recipes', { state: { focusSearch: true } })

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      {/* Header: title, one-tap search, import */}
      <div className="sticky top-0 z-10 bg-[#F8FAFC]/85 backdrop-blur-sm border-b border-border/60">
        <div className="max-w-3xl mx-auto w-full px-4 pt-4 pb-3 space-y-3">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-bold text-foreground">Recipes</h1>
            <Button variant="outline" size="sm" onClick={onImport}>
              <Plus className="w-4 h-4 mr-1.5" /> Import
            </Button>
          </div>
          <button
            onClick={openSearch}
            className="w-full flex items-center gap-2.5 pl-3.5 pr-3 py-3 rounded-xl bg-white border border-border text-muted-foreground text-sm hover:border-ring transition-colors"
          >
            <Search className="w-4 h-4 flex-shrink-0" />
            Search recipes &amp; ingredients…
          </button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto w-full px-4 py-5 space-y-7">
        {isLoading ? (
          <>
            <ShelfSkeleton />
            <ShelfSkeleton />
          </>
        ) : total === 0 ? (
          <EmptyHome onImport={onImport} />
        ) : (
          <>
            <Shelf
              title="Recently added"
              seeAll={() => navigate('/recipes')}
              recipes={recent}
            />
            {shelfTags.map((tag) => (
              <TagShelf key={tag.id} tag={tag} onSeeAll={() => navigate('/recipes', { state: { tag: tag.name } })} />
            ))}
            {shelfTags.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-2">
                Tag your recipes to group them into shelves here.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function TagShelf({ tag, onSeeAll }: { tag: TagInfo; onSeeAll: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['recipes', 'byTag', tag.name],
    queryFn: () => api.listRecipes({ tags: [tag.name], limit: SHELF_SIZE }),
  })
  if (isLoading) return <ShelfSkeleton label={tag.name} />
  const recipes = data?.items ?? []
  if (recipes.length === 0) return null
  return (
    <Shelf
      title={tag.name}
      dotColor={tagColor(tag.name, tag.color)}
      count={data?.total}
      seeAll={onSeeAll}
      recipes={recipes}
    />
  )
}

function Shelf({
  title,
  dotColor,
  count,
  seeAll,
  recipes,
}: {
  title: string
  dotColor?: string
  count?: number
  seeAll: () => void
  recipes: RecipeListItem[]
}) {
  return (
    <section>
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          {dotColor && (
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: dotColor }} />
          )}
          <h2 className="text-base font-semibold text-foreground truncate">{title}</h2>
          {count != null && (
            <span className="text-xs text-muted-foreground tabular-nums flex-shrink-0">{count}</span>
          )}
        </div>
        <button
          onClick={seeAll}
          className="flex items-center gap-0.5 text-xs font-medium text-primary hover:underline flex-shrink-0"
        >
          See all <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
      {/* Bleed to the screen edges so cards can scroll under the padding. */}
      <div className="flex gap-3 overflow-x-auto pb-1 -mx-4 px-4 snap-x scroll-px-4">
        {recipes.map((recipe) => (
          <RecipeCard key={recipe.uuid} recipe={recipe} />
        ))}
      </div>
    </section>
  )
}

function RecipeCard({ recipe }: { recipe: RecipeListItem }) {
  const src = useRecipeImage(recipe.image_url)
  return (
    <NavLink
      to={`/recipes/${recipe.uuid}`}
      className="w-40 flex-shrink-0 snap-start group"
    >
      <div className="w-40 aspect-video rounded-xl overflow-hidden bg-muted border border-border/60 mb-1.5">
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
      <p className="text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
        {recipe.title}
      </p>
      <p className="text-xs text-muted-foreground mt-0.5 truncate">
        {recipe.owned === false && (recipe.owner_name || recipe.owner_email)
          ? recipe.owner_name || recipe.owner_email
          : relativeDate(recipe.datePublished ?? recipe.createdAt)}
      </p>
    </NavLink>
  )
}

function ShelfSkeleton({ label }: { label?: string }) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-2.5">
        {label ? (
          <h2 className="text-base font-semibold text-foreground">{label}</h2>
        ) : (
          <div className="h-5 w-32 rounded bg-muted animate-pulse" />
        )}
      </div>
      <div className="flex gap-3 overflow-hidden -mx-4 px-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="w-40 flex-shrink-0">
            <div className="w-40 aspect-video rounded-xl bg-muted animate-pulse mb-1.5" />
            <div className="h-4 w-3/4 rounded bg-muted animate-pulse" />
          </div>
        ))}
      </div>
    </section>
  )
}

function EmptyHome({ onImport }: { onImport: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-3 py-16">
      <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center text-primary">
        <Utensils className="w-7 h-7" />
      </div>
      <div>
        <p className="text-base font-semibold text-foreground">No recipes yet</p>
        <p className="text-sm text-muted-foreground mt-1">Import one to start building your collection.</p>
      </div>
      <Button onClick={onImport}>
        <Plus className="w-4 h-4 mr-1.5" /> Import your first recipe
      </Button>
    </div>
  )
}
