import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The active search that defines which recipes get added. */
  q?: string
  tags: string[]
  /** How many recipes currently match (shown in the description). */
  total: number
}

export function BulkAddToCookbookModal({ open, onOpenChange, q, tags, total }: Props) {
  const queryClient = useQueryClient()
  const [newName, setNewName] = useState('')
  const [result, setResult] = useState<{ name: string; added: number; matched: number } | null>(
    null,
  )

  const { data: cookbooks = [], isLoading } = useQuery({
    queryKey: ['cookbooks'],
    queryFn: () => api.listCookbooks(),
    enabled: open,
  })

  // Reset the result each time the picker reopens.
  useEffect(() => {
    if (open) setResult(null)
  }, [open])

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['cookbooks'] })
    queryClient.invalidateQueries({ queryKey: ['cookbook'] })
  }

  const addTo = useMutation({
    mutationFn: (target: { id: number; name: string }) =>
      api.bulkAddToCookbook(target.id, { q, tags }).then((res) => ({ ...res, name: target.name })),
    onSuccess: (res) => {
      setResult(res)
      invalidate()
    },
  })

  const createAndAdd = useMutation({
    mutationFn: async (name: string) => {
      const cb = await api.createCookbook(name)
      const res = await api.bulkAddToCookbook(cb.id, { q, tags })
      return { ...res, name }
    },
    onSuccess: (res) => {
      setResult(res)
      setNewName('')
      invalidate()
    },
  })

  const busy = addTo.isPending || createAndAdd.isPending
  const label = q ? `matching “${q}”` : tags.length ? `tagged ${tags.join(', ')}` : ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add results to a cookbook</DialogTitle>
          <DialogDescription>
            {total} {total === 1 ? 'recipe' : 'recipes'} {label} will be added.
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="py-2 space-y-3 text-center">
            <p className="text-sm text-foreground">
              Added <strong>{result.added}</strong> to <strong>{result.name}</strong>
              {result.added !== result.matched && (
                <span className="text-muted-foreground">
                  {' '}
                  ({result.matched - result.added} already there)
                </span>
              )}
              .
            </p>
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        ) : (
          <>
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {isLoading ? (
                <p className="text-sm text-muted-foreground py-2">Loading…</p>
              ) : cookbooks.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">
                  No cookbooks yet — create one below.
                </p>
              ) : (
                cookbooks.map((cb) => (
                  <button
                    key={cb.id}
                    type="button"
                    onClick={() => addTo.mutate({ id: cb.id, name: cb.name })}
                    disabled={busy}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border border-border hover:bg-muted/40 transition-colors text-left disabled:opacity-50"
                  >
                    <span className="flex-1 text-sm font-medium text-foreground truncate">
                      {cb.name}
                    </span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {cb.recipe_count}
                    </span>
                  </button>
                ))
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                const n = newName.trim()
                if (n) createAndAdd.mutate(n)
              }}
              className="flex gap-2 pt-3 border-t border-border"
            >
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="New cookbook"
              />
              <Button type="submit" disabled={!newName.trim() || busy}>
                <Plus className="w-4 h-4 mr-1" /> Create
              </Button>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
