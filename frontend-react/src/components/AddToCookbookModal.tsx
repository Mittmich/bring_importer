import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Plus } from 'lucide-react'
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
  recipeUuid: string
}

export function AddToCookbookModal({ open, onOpenChange, recipeUuid }: Props) {
  const queryClient = useQueryClient()
  const [newName, setNewName] = useState('')

  const listKey = ['cookbooks', 'for-recipe', recipeUuid]
  const { data: cookbooks = [], isLoading } = useQuery({
    queryKey: listKey,
    queryFn: () => api.listCookbooks(recipeUuid),
    enabled: open,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['cookbooks'] })
    queryClient.invalidateQueries({ queryKey: listKey })
  }

  const toggle = useMutation({
    mutationFn: async ({ id, contains }: { id: number; contains: boolean }) => {
      if (contains) await api.removeRecipeFromCookbook(id, recipeUuid)
      else await api.addRecipeToCookbook(id, recipeUuid)
    },
    onSuccess: invalidate,
  })

  const createAndAdd = useMutation({
    mutationFn: async (name: string) => {
      const cb = await api.createCookbook(name)
      await api.addRecipeToCookbook(cb.id, recipeUuid)
    },
    onSuccess: () => {
      setNewName('')
      invalidate()
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add to cookbook</DialogTitle>
          <DialogDescription>Tap a cookbook to add or remove this recipe.</DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5 max-h-72 overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-muted-foreground py-2">Loading…</p>
          ) : cookbooks.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              No cookbooks yet — create one below.
            </p>
          ) : (
            cookbooks.map((cb) => {
              const contains = !!cb.contains
              return (
                <button
                  key={cb.id}
                  type="button"
                  onClick={() => toggle.mutate({ id: cb.id, contains })}
                  disabled={toggle.isPending}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border border-border hover:bg-muted/40 transition-colors text-left"
                >
                  <span className="flex-1 text-sm font-medium text-foreground truncate">
                    {cb.name}
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {cb.recipe_count}
                  </span>
                  <span
                    className={
                      'w-5 h-5 rounded-md border flex items-center justify-center flex-shrink-0 ' +
                      (contains ? 'bg-primary border-primary text-white' : 'border-border')
                    }
                  >
                    {contains && <Check className="w-3.5 h-3.5" />}
                  </span>
                </button>
              )
            })
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
          <Button type="submit" disabled={!newName.trim() || createAndAdd.isPending}>
            <Plus className="w-4 h-4 mr-1" /> Create
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
