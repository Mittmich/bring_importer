import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, useOutletContext } from 'react-router-dom'
import { Search, ChevronRight, Plus } from 'lucide-react'
import { api, type RecipeListItem } from '@/lib/api'
import { cn } from '@/lib/utils'

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

interface Props {
  activeUuid?: string
}

export function RecipeListPanel({ activeUuid }: Props) {
  const [search, setSearch] = useState('')
  const { onImport } = useOutletContext<{ onImport: () => void }>()

  const { data: recipes = [], isLoading, error } = useQuery({
    queryKey: ['recipes'],
    queryFn: api.listRecipes,
  })

  const filtered = recipes.filter((r) =>
    r.title.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div className="flex flex-col w-full md:w-[300px] md:min-w-[300px] border-r border-border bg-white h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-border">
        <span className="text-sm font-semibold text-foreground">Recipes</span>
        <button
          onClick={onImport}
          className="flex items-center gap-1.5 text-xs font-semibold text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> Import
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2 border-b border-border/50">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search recipes…"
            className="w-full pl-8 pr-3 py-1.5 text-sm bg-muted/50 rounded-md border border-transparent focus:outline-none focus:border-ring focus:bg-white transition-colors placeholder:text-muted-foreground"
          />
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-4 text-sm text-muted-foreground text-center">Loading…</div>
        )}
        {error && (
          <div className="p-4 text-sm text-destructive text-center">Could not load recipes.</div>
        )}
        {!isLoading && !error && filtered.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground text-center">
            {search ? 'No recipes match your search.' : 'No recipes yet. Import one to get started.'}
          </div>
        )}
        {filtered.map((recipe) => (
          <RecipeRow key={recipe.uuid} recipe={recipe} isActive={recipe.uuid === activeUuid} />
        ))}
      </div>
    </div>
  )
}

function RecipeRow({ recipe, isActive }: { recipe: RecipeListItem; isActive: boolean }) {
  return (
    <NavLink
      to={`/recipes/${recipe.uuid}`}
      className={cn(
        'flex items-center justify-between px-4 py-3 border-b border-border/50 transition-colors',
        isActive ? 'bg-primary/5' : 'hover:bg-muted/40',
      )}
    >
      <div className="min-w-0">
        <p
          className={cn(
            'text-sm font-medium truncate',
            isActive ? 'text-primary' : 'text-foreground',
          )}
        >
          {recipe.title}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {relativeDate(recipe.datePublished)}
          {recipe.source?.kind === 'url' && recipe.source.value && (
            <> · {new URL(recipe.source.value).hostname.replace('www.', '')}</>
          )}
        </p>
      </div>
      <ChevronRight className={cn('w-4 h-4 flex-shrink-0 ml-2', isActive ? 'text-primary' : 'text-muted-foreground/50')} />
    </NavLink>
  )
}
