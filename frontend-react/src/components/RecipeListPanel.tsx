import { useEffect, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { NavLink, useLocation, useOutletContext } from 'react-router-dom'
import { Search, ChevronRight, ChevronDown, Plus, BookHeart } from 'lucide-react'
import { api, type RecipeListItem } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useRecipeImage } from '@/hooks/useRecipeImage'
import { BulkAddToCookbookModal } from '@/components/BulkAddToCookbookModal'
import { TagChip } from '@/components/ui/tag-chip'
import { tagColor } from '@/lib/tagColors'

const MAX_ROW_TAGS = 3

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
  // The home screen hands off intent via navigation state: focus the search
  // box, or arrive with a tag preselected (from a shelf's "See all").
  const navState = useLocation().state as { focusSearch?: boolean; tag?: string } | null
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [selectedTags, setSelectedTags] = useState<string[]>(() =>
    navState?.tag ? [navState.tag] : [],
  )
  const [tagsExpanded, setTagsExpanded] = useState(false)
  const [bulkOpen, setBulkOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement | null>(null)
  const { onImport } = useOutletContext<{ onImport: () => void }>()

  // Focus the search box when arriving from the home screen's search button.
  useEffect(() => {
    if (navState?.focusSearch) searchRef.current?.focus()
    // Run once on mount for the initial navigation intent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Debounce the search term so each keystroke doesn't hit the server.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250)
    return () => clearTimeout(t)
  }, [search])

  // Filter scope: tag names on any recipe I can see (mine + shared), so shared
  // recipes' tags are selectable here too.
  const { data: tags = [] } = useQuery({
    queryKey: ['tags', 'filter'],
    queryFn: () => api.getTags('filter'),
  })
  // Only offer tags that are actually on a recipe as filters. Orphaned tags
  // (count 0 — e.g. left behind when their last recipe was deleted) can never
  // match anything, so filtering by one just yields an empty list that reads
  // like a broken search. They remain editable/removable on the Tags page.
  const filterTags = tags.filter((t) => t.count > 0)

  function toggleTag(name: string) {
    setSelectedTags((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name],
    )
  }

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['recipes', 'list', debounced, selectedTags],
    queryFn: ({ pageParam }) =>
      api.listRecipes({
        limit: PAGE_SIZE,
        offset: pageParam,
        q: debounced || undefined,
        tags: selectedTags.length ? selectedTags : undefined,
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0)
      return loaded < lastPage.total ? loaded : undefined
    },
  })

  const recipes = data?.pages.flatMap((p) => p.items) ?? []
  const total = data?.pages[0]?.total ?? 0
  // Offer bulk "add to cookbook" only when a search/tag filter is narrowing
  // the list, so it's a deliberate set rather than "all my recipes".
  const hasFilter = debounced.length > 0 || selectedTags.length > 0

  // Auto-load the next page when the sentinel scrolls into view. The list
  // scrolls inside `scrollRef` (an overflow-y-auto container), not the page,
  // so the observer must use that container as its root — a viewport-rooted
  // observer never sees the sentinel and pages past the first never load.
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasNextPage) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isFetchingNextPage) fetchNextPage()
      },
      { root: scrollRef.current, rootMargin: '200px' },
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
            ref={searchRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search recipes & ingredients…"
            className="w-full pl-9 pr-3 py-2.5 text-base bg-muted/50 rounded-md border border-transparent focus:outline-none focus:border-ring focus:bg-white transition-colors placeholder:text-muted-foreground"
          />
        </div>
      </div>

      {/* Tag filter — collapsed by default; only selected tags stay visible
          until expanded via the toggle. */}
      {filterTags.length > 0 && (
        <div className="px-3 py-2 border-b border-border/50 flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setTagsExpanded((v) => !v)}
            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border border-border text-muted-foreground hover:border-primary/40 transition-colors"
            aria-expanded={tagsExpanded}
          >
            Tags
            <ChevronDown
              className={cn('w-3.5 h-3.5 transition-transform', tagsExpanded && 'rotate-180')}
            />
          </button>

          {(tagsExpanded ? filterTags : filterTags.filter((t) => selectedTags.includes(t.name))).map((t) => {
            const active = selectedTags.includes(t.name)
            const resolved = tagColor(t.name, t.color)
            return (
              <button
                key={t.name}
                onClick={() => toggleTag(t.name)}
                className="text-xs px-2 py-1 rounded-full border font-medium transition-colors"
                style={
                  active
                    ? { backgroundColor: resolved, color: '#fff', borderColor: resolved }
                    : { backgroundColor: '#fff', color: resolved, borderColor: resolved }
                }
              >
                {t.name}
              </button>
            )
          })}

          {selectedTags.length > 0 && (
            <button
              onClick={() => setSelectedTags([])}
              className="text-xs px-2 py-1 rounded-full text-primary hover:underline"
            >
              Clear
            </button>
          )}
        </div>
      )}

      {/* Bulk add the current results to a cookbook. */}
      {hasFilter && !isLoading && recipes.length > 0 && (
        <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground tabular-nums">
            {total} {total === 1 ? 'result' : 'results'}
          </span>
          <button
            onClick={() => setBulkOpen(true)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
          >
            <BookHeart className="w-3.5 h-3.5" /> Add to cookbook
          </button>
        </div>
      )}

      {/* List */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {isLoading && (
          <div aria-busy="true" aria-label="Loading recipes">
            {Array.from({ length: 8 }).map((_, i) => (
              <RecipeRowSkeleton key={i} />
            ))}
          </div>
        )}
        {error && (
          <div className="p-4 text-sm text-destructive text-center">Could not load recipes.</div>
        )}
        {!isLoading && !error && recipes.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground text-center">
            {debounced || selectedTags.length
              ? 'No recipes match your filters.'
              : 'No recipes yet. Import one to get started.'}
          </div>
        )}
        {recipes.map((recipe) => (
          <RecipeRow key={recipe.uuid} recipe={recipe} isActive={recipe.uuid === activeUuid} />
        ))}
        <div ref={sentinelRef} />
        {isFetchingNextPage &&
          Array.from({ length: 3 }).map((_, i) => <RecipeRowSkeleton key={i} />)}
      </div>

      <BulkAddToCookbookModal
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        q={debounced || undefined}
        tags={selectedTags}
        total={total}
      />
    </div>
  )
}

// Placeholder row shown while recipes load. Matches RecipeRow's geometry
// (thumbnail box + two text lines) so the list doesn't jump when real rows
// replace it.
function RecipeRowSkeleton() {
  return (
    <div className="flex items-center px-4 py-4 border-b border-border/50">
      <div className="w-14 h-14 rounded-lg bg-muted animate-pulse flex-shrink-0 mr-3" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-2/3 rounded bg-muted animate-pulse" />
        <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
      </div>
    </div>
  )
}

function RecipeRow({ recipe, isActive }: { recipe: RecipeListItem; isActive: boolean }) {
  const thumbSrc = useRecipeImage(recipe.image_url)
  return (
    <NavLink
      to={`/recipes/${recipe.uuid}`}
      className={cn(
        'flex items-center justify-between px-4 py-4 border-b border-border/50 transition-colors',
        isActive ? 'bg-primary/5' : 'hover:bg-muted/40',
      )}
    >
      {/* Reserve the thumbnail box up front for recipes that have an image
          (known from the list payload) so the picture doesn't shift the row
          when its bytes finish loading. */}
      {recipe.has_image && (
        <div
          className={cn(
            'w-14 h-14 rounded-lg overflow-hidden flex-shrink-0 mr-3 border border-border/50 bg-muted',
            !thumbSrc && 'animate-pulse',
          )}
        >
          {thumbSrc && <img src={thumbSrc} alt="" className="w-full h-full object-cover" />}
        </div>
      )}
      <div className="min-w-0 flex-1">
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
          {recipe.owned === false && (recipe.owner_name || recipe.owner_email) && (
            <> · <span className="text-primary">{recipe.owner_name || recipe.owner_email}</span></>
          )}
        </p>
        {recipe.tags && recipe.tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 mt-1.5">
            {recipe.tags.slice(0, MAX_ROW_TAGS).map((t) => (
              <TagChip key={t.name} name={t.name} color={t.color} />
            ))}
            {recipe.tags.length > MAX_ROW_TAGS && (
              <span className="text-xs text-muted-foreground">
                +{recipe.tags.length - MAX_ROW_TAGS}
              </span>
            )}
          </div>
        )}
      </div>
      <ChevronRight className={cn('w-5 h-5 flex-shrink-0 ml-2', isActive ? 'text-primary' : 'text-muted-foreground/50')} />
    </NavLink>
  )
}
