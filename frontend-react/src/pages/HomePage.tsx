import { useQuery } from '@tanstack/react-query'
import { NavLink, useOutletContext } from 'react-router-dom'
import { ChevronRight, Plus } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'

export function HomePage() {
  const { onImport } = useOutletContext<{ onImport: () => void }>()
  const { data, isLoading } = useQuery({
    queryKey: ['recipes', 'recent'],
    queryFn: () => api.listRecipes({ limit: 5 }),
  })

  const recent = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-2xl w-full mx-auto p-4 md:p-6 space-y-6">
        {/* Import action */}
        <div className="bg-white rounded-xl border border-border p-5">
          <h2 className="text-sm font-semibold text-foreground mb-3">Add a recipe</h2>
          <Button onClick={onImport} size="sm" className="w-full sm:w-auto">
            <Plus className="w-4 h-4 mr-1.5" /> Import recipe
          </Button>
        </div>

        {/* Recent recipes */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-foreground">Recent</h2>
            {total > 5 && (
              <NavLink to="/recipes" className="text-xs text-primary hover:underline">
                See all
              </NavLink>
            )}
          </div>

          <div className="bg-white rounded-xl border border-border divide-y divide-border/50 overflow-hidden">
            {isLoading && (
              <div className="p-4 text-sm text-muted-foreground text-center">Loading…</div>
            )}
            {!isLoading && recent.length === 0 && (
              <div className="p-6 text-sm text-muted-foreground text-center">
                No recipes yet. Import one above to get started.
              </div>
            )}
            {recent.map((recipe) => (
              <NavLink
                key={recipe.uuid}
                to={`/recipes/${recipe.uuid}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
              >
                <span className="text-sm font-medium text-foreground truncate">{recipe.title}</span>
                <ChevronRight className="w-4 h-4 text-muted-foreground/50 flex-shrink-0 ml-2" />
              </NavLink>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
