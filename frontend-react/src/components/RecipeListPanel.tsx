import { useEffect, useRef, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { NavLink, useOutletContext } from 'react-router-dom'
import { Search, ChevronRight, Plus } from 'lucide-react'
import { api, type RecipeListItem } from '@/lib/api'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 30

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
  const [debounced, setDebounced] = useState('')
  const { onImport } = useOutletContext<{ onImport: () => void }>()

  // Debounce the search term so each keystroke doesn't hit the server.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250)
    return () => clearTimeout(t)
  }, [search])

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['recipes', 'list', debounced],
    queryFn: ({ pageParam }) =>
      api.listRecipes({ limit: PAGE_SIZE, offset: pageParam, q: debounced || undefined }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0)
      return loaded < lastPage.total ? loaded : undefined
    },
  })

  const recipes = data?.pages.flatMap((p) => p.items) ?? []

  // Auto-load the next page when the sentinel scrolls into view.
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasNextPage) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isFetchingNextPage) fetchNextPage()
      },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  return (
    <div className="flex flex-col w-full md:w-[300px] md:min-w-[300px] border-r border-border bg-white h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-border">
        <span className="text-base font-semibold text-foreground">Recipes</span>
        <button
          onClick={onImport}
          className="flex items-center gap-1.5 text-sm font-semibold text-primary hover:text-primary/80 transition-colors"
        >
          <Plus className="w-4 h-4" /> Import
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2.5 border-b border-border/50">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search recipes…"
            className="w-full pl-9 pr-3 py-2.5 text-base bg-muted/50 rounded-md border border-transparent focus:outline-none focus:border-ring focus:bg-white transition-colors placeholder:text-muted-foreground"
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
        {!isLoading && !error && recipes.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground text-center">
            {debounced ? 'No recipes match your search.' : 'No recipes yet. Import one to get started.'}
          </div>
        )}
        {recipes.map((recipe) => (
          <RecipeRow key={recipe.uuid} recipe={recipe} isActive={recipe.uuid === activeUuid} />
        ))}
        <div ref={sentinelRef} />
        {isFetchingNextPage && (
          <div className="p-3 text-xs text-muted-foreground text-center">Loading more…</div>
        )}
      </div>
    </div>
  )
}

function RecipeRow({ recipe, isActive }: { recipe: RecipeListItem; isActive: boolean }) {
  return (
    <NavLink
      to={`/recipes/${recipe.uuid}`}
      className={cn(
        'flex items-center justify-between px-4 py-4 border-b border-border/50 transition-colors',
        isActive ? 'bg-primary/5' : 'hover:bg-muted/40',
      )}
    >
      <div className="min-w-0">
        <p
          className={cn(
            'text-base font-medium truncate',
            isActive ? 'text-primary' : 'text-foreground',
          )}
        >
          {recipe.title}
        </p>
        <p className="text-sm text-muted-foreground mt-1">
          {relativeDate(recipe.datePublished ?? recipe.createdAt)}
          {recipe.source?.kind === 'url' && recipe.source.value && (
            <> · {new URL(recipe.source.value).hostname.replace('www.', '')}</>
          )}
        </p>
      </div>
      <ChevronRight className={cn('w-5 h-5 flex-shrink-0 ml-2', isActive ? 'text-primary' : 'text-muted-foreground/50')} />
    </NavLink>
  )
}
