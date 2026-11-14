import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UserPlus, X } from 'lucide-react'
import { api, personName, type Menu } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n, type MessageKey } from '@/i18n'

type MenuShareRole = 'viewer' | 'editor'
const ROLES: MenuShareRole[] = ['viewer', 'editor']

/** The owner shares a menu with friends: invite at a role, change roles, remove. */
export function ShareMenuDialog({ menu, onClose }: { menu: Menu; onClose: () => void }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [friendId, setFriendId] = useState<number | ''>('')
  const [role, setRole] = useState<MenuShareRole>('viewer')
  const [error, setError] = useState<string | null>(null)
  const roleName = (r: string) => t(`role.${r}` as MessageKey)

  const key = ['menuMembers', menu.id]
  const { data } = useQuery({ queryKey: key, queryFn: () => api.listMenuMembers(menu.id) })
  const { data: friends = [] } = useQuery({ queryKey: ['friends'], queryFn: api.listFriends })

  function refresh() {
    queryClient.invalidateQueries({ queryKey: key })
    queryClient.invalidateQueries({ queryKey: ['menu', menu.id] })
    queryClient.invalidateQueries({ queryKey: ['menus'] })
  }

  const invite = useMutation({
    mutationFn: () => api.inviteMenuMember(menu.id, Number(friendId), role),
    onSuccess: () => {
      setFriendId('')
      setError(null)
      refresh()
    },
    onError: (e: Error) => setError(e.message),
  })
  const changeRole = useMutation({
    mutationFn: ({ userId, r }: { userId: number; r: MenuShareRole }) => api.updateMenuMember(menu.id, userId, r),
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: (userId: number) => api.removeMenuMember(menu.id, userId),
    onSuccess: refresh,
  })

  const members = data?.members ?? []
  const memberIds = new Set(members.map((m) => m.user_id))
  const invitable = friends.filter((f) => f.user_id !== menu.owner.user_id && !memberIds.has(f.user_id))

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('menus.shareTitle', { title: menu.title })}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">{t('menus.shareHint')}</p>

        <div className="rounded-xl border border-border divide-y divide-border/50 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2.5">
            <span className="text-sm truncate flex-1">{personName(menu.owner.display_name, menu.owner.email)}</span>
            <span className="text-xs text-muted-foreground">{t('cookbook.owner')}</span>
          </div>
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center gap-2 px-3 py-2.5">
              <span className="text-sm truncate flex-1">
                {personName(m.display_name, m.email)}
                {m.status === 'pending' && (
                  <span className="text-xs text-muted-foreground">{t('cookbook.pendingSuffix')}</span>
                )}
              </span>
              <select
                value={m.role}
                onChange={(e) => changeRole.mutate({ userId: m.user_id, r: e.target.value as MenuShareRole })}
                className="text-xs bg-muted/50 rounded-md border border-border px-1.5 py-1"
                aria-label={t('menus.shareRole')}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {roleName(r)}
                  </option>
                ))}
              </select>
              <button
                onClick={() => remove.mutate(m.user_id)}
                className="text-muted-foreground hover:text-destructive"
                aria-label={t('cookbook.removeMember')}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">{t('cookbook.inviteFriend')}</p>
          {invitable.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('cookbook.noFriendsToInvite')}</p>
          ) : (
            <div className="flex gap-2">
              <select
                value={friendId}
                onChange={(e) => setFriendId(e.target.value ? Number(e.target.value) : '')}
                className="flex-1 min-w-0 text-sm bg-muted/50 rounded-md border border-border px-2 py-2"
                aria-label={t('cookbook.chooseFriend')}
              >
                <option value="">{t('cookbook.chooseFriend')}</option>
                {invitable.map((f) => (
                  <option key={f.user_id} value={f.user_id}>
                    {personName(f.display_name, f.email)}
                  </option>
                ))}
              </select>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as MenuShareRole)}
                className="text-sm bg-muted/50 rounded-md border border-border px-2 py-2"
                aria-label={t('menus.shareRole')}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {roleName(r)}
                  </option>
                ))}
              </select>
              <Button onClick={() => invite.mutate()} disabled={!friendId || invite.isPending} aria-label={t('cookbook.inviteFriend')}>
                <UserPlus className="w-4 h-4" />
              </Button>
            </div>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
          <p className="text-xs text-muted-foreground">{t('menus.shareRoles')}</p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
