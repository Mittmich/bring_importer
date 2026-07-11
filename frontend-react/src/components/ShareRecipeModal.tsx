import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

const ROLES: Array<'viewer' | 'editor' | 'manager'> = ['viewer', 'editor', 'manager']

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  recipeUuid: string
}

export function ShareRecipeModal({ open, onOpenChange, recipeUuid }: Props) {
  const [role, setRole] = useState<'viewer' | 'editor' | 'manager'>('viewer')
  const [sharedWith, setSharedWith] = useState<string | null>(null)

  const { data: friends = [], isLoading } = useQuery({
    queryKey: ['friends'],
    queryFn: api.listFriends,
    enabled: open,
  })

  useEffect(() => {
    if (open) setSharedWith(null)
  }, [open])

  const share = useMutation({
    mutationFn: ({ friendId }: { friendId: number; email: string }) =>
      api.shareRecipe(recipeUuid, friendId, role),
    onSuccess: (_res, vars) => setSharedWith(vars.email),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Share with a friend</DialogTitle>
          <DialogDescription>
            They'll get an invitation and can open it once they accept.
          </DialogDescription>
        </DialogHeader>

        {sharedWith ? (
          <div className="py-2 space-y-3 text-center">
            <p className="text-sm text-foreground">
              Invitation sent to <strong>{sharedWith}</strong> ({role}).
            </p>
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Access</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as 'viewer' | 'editor' | 'manager')}
                className="text-sm bg-muted/50 rounded-md border border-border px-2 py-1.5"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r === 'viewer' ? 'Can view' : r === 'editor' ? 'Can edit' : 'Can manage'}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {isLoading ? (
                <p className="text-sm text-muted-foreground py-2">Loading…</p>
              ) : friends.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">
                  No friends yet. Add friends under Account → Friends first.
                </p>
              ) : (
                friends.map((f) => (
                  <button
                    key={f.user_id}
                    type="button"
                    onClick={() => share.mutate({ friendId: f.user_id, email: f.email })}
                    disabled={share.isPending}
                    className="w-full flex items-center px-3 py-2.5 rounded-lg border border-border hover:bg-muted/40 transition-colors text-left disabled:opacity-50"
                  >
                    <span className="text-sm font-medium text-foreground truncate">{f.email}</span>
                  </button>
                ))
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
