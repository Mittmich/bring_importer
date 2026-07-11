import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LogOut, UserPlus, X } from 'lucide-react'
import { api, type CookbookRole } from '@/lib/api'
import { getUserEmail } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'

const ROLES: Array<'viewer' | 'editor' | 'manager'> = ['viewer', 'editor', 'manager']

export function CookbookMembersSection({
  cookbookId,
  role,
}: {
  cookbookId: number
  role?: CookbookRole
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const canManage = role === 'owner' || role === 'manager'
  const myEmail = getUserEmail()
  const [inviteId, setInviteId] = useState<number | ''>('')
  const [inviteRole, setInviteRole] = useState<'viewer' | 'editor' | 'manager'>('viewer')
  const [error, setError] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['cookbookMembers', cookbookId],
    queryFn: () => api.getCookbookMembers(cookbookId),
  })
  const { data: friends = [] } = useQuery({
    queryKey: ['friends'],
    queryFn: api.listFriends,
    enabled: canManage,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['cookbookMembers', cookbookId] })
  }

  const invite = useMutation({
    mutationFn: () => api.inviteCookbookMember(cookbookId, Number(inviteId), inviteRole),
    onSuccess: () => {
      setInviteId('')
      setError(null)
      invalidate()
    },
    onError: (e: Error) => setError(e.message),
  })
  const changeRole = useMutation({
    mutationFn: ({ userId, r }: { userId: number; r: string }) =>
      api.updateCookbookMemberRole(cookbookId, userId, r),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (userId: number) => api.removeCookbookMember(cookbookId, userId),
    onSuccess: invalidate,
  })
  const leave = useMutation({
    mutationFn: (userId: number) => api.removeCookbookMember(cookbookId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cookbooks'] })
      navigate('/cookbooks')
    },
  })

  if (!data) return null

  // A shared cookbook (I'm a member, not the owner) can be left.
  const myMembership = data.members.find((m) => m.email === myEmail)

  const memberIds = new Set(data.members.map((m) => m.user_id))
  const invitable = friends.filter(
    (f) => f.user_id !== data.owner.user_id && !memberIds.has(f.user_id),
  )

  return (
    <div className="space-y-1.5">
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
        Shared with
      </h2>
      <div className="bg-white rounded-xl border border-border divide-y divide-border/50 overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3">
          <span className="text-sm text-foreground truncate flex-1">{data.owner.email}</span>
          <span className="text-xs text-muted-foreground">Owner</span>
        </div>
        {data.members.map((m) => (
          <div key={m.user_id} className="flex items-center gap-2 px-4 py-3">
            <span className="text-sm text-foreground truncate flex-1">
              {m.email}
              {m.status === 'pending' && (
                <span className="text-xs text-muted-foreground"> · pending</span>
              )}
            </span>
            {canManage ? (
              <>
                <select
                  value={m.role}
                  onChange={(e) => changeRole.mutate({ userId: m.user_id, r: e.target.value })}
                  className="text-xs bg-muted/50 rounded-md border border-border px-1.5 py-1"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => remove.mutate(m.user_id)}
                  className="text-muted-foreground hover:text-destructive"
                  aria-label="Remove member"
                >
                  <X className="w-4 h-4" />
                </button>
              </>
            ) : (
              <span className="text-xs text-muted-foreground">{m.role}</span>
            )}
          </div>
        ))}
      </div>

      {canManage && (
        <div className="bg-white rounded-xl border border-border p-4 space-y-2 mt-2">
          <p className="text-sm font-medium text-foreground">Invite a friend</p>
          {invitable.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No friends to invite. Add friends under Account → Friends first.
            </p>
          ) : (
            <div className="flex gap-2">
              <select
                value={inviteId}
                onChange={(e) => setInviteId(e.target.value ? Number(e.target.value) : '')}
                className="flex-1 text-sm bg-muted/50 rounded-md border border-border px-2 py-2"
              >
                <option value="">Choose a friend…</option>
                {invitable.map((f) => (
                  <option key={f.user_id} value={f.user_id}>
                    {f.email}
                  </option>
                ))}
              </select>
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as 'viewer' | 'editor' | 'manager')}
                className="text-sm bg-muted/50 rounded-md border border-border px-2 py-2"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <Button onClick={() => invite.mutate()} disabled={!inviteId || invite.isPending}>
                <UserPlus className="w-4 h-4" />
              </Button>
            </div>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
      )}

      {role !== 'owner' && myMembership && (
        <Button
          variant="outline"
          className="w-full mt-2 text-muted-foreground hover:text-destructive"
          onClick={() => leave.mutate(myMembership.user_id)}
          disabled={leave.isPending}
        >
          <LogOut className="w-4 h-4 mr-1.5" /> Leave this cookbook
        </Button>
      )}
    </div>
  )
}
