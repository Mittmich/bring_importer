import { useMemo, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Ban,
  CheckCircle2,
  KeyRound,
  LogOut,
  MoreHorizontal,
  Search,
  Shield,
  ShieldOff,
  Trash2,
} from 'lucide-react'
import { api, type AdminUser, type Invite } from '@/lib/api'
import { formatDateTime, relativeDate } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Menu, MenuItem, MenuSeparator } from '@/components/ui/menu'
import { LinkDialog } from '@/components/LinkDialog'
import { cn } from '@/lib/utils'
import { useI18n, type MessageKey } from '@/i18n'

type Tab = 'users' | 'invites'

/** A one-time link to show once: built client-side from the returned token. */
interface ShownLink {
  url: string
  title: string
  description: string
}

export function AdminPage() {
  const { t } = useI18n()
  const { data: profile, isLoading } = useQuery({ queryKey: ['profile'], queryFn: api.getProfile })
  const [tab, setTab] = useState<Tab>('users')
  const [shown, setShown] = useState<ShownLink | null>(null)

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">{t('common.loading')}</div>
  }
  if (!profile?.is_admin) return <Navigate to="/account" replace />

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-2xl mx-auto w-full p-4 md:p-6 space-y-4 pt-6 pb-10">
        <Link
          to="/account"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-4 h-4" /> {t('tags.back')}
        </Link>
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t('admin.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('admin.subtitle')}</p>
        </div>

        <div role="tablist" className="inline-flex rounded-lg border border-border bg-white p-1">
          {(['users', 'invites'] as const).map((key) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={cn(
                'px-3.5 py-1.5 text-sm font-medium rounded-md transition-colors',
                tab === key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {key === 'users' ? t('admin.tabUsers') : t('admin.tabInvites')}
            </button>
          ))}
        </div>

        {tab === 'users' ? <UsersTab onLink={setShown} /> : <InvitesTab onLink={setShown} />}
      </div>

      <LinkDialog
        url={shown?.url ?? null}
        title={shown?.title ?? ''}
        description={shown?.description ?? ''}
        onClose={() => setShown(null)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

function UsersTab({ onLink }: { onLink: (link: ShownLink) => void }) {
  const { t } = useI18n()
  const { data: users = [], isLoading } = useQuery({ queryKey: ['admin', 'users'], queryFn: api.adminListUsers })
  const [query, setQuery] = useState('')
  const [deleting, setDeleting] = useState<AdminUser | null>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return users
    return users.filter((u) => u.email.toLowerCase().includes(q) || u.display_name.toLowerCase().includes(q))
  }, [users, query])

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('admin.search')}
          className="pl-9 bg-white"
        />
      </div>
      {isLoading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
      {!isLoading && filtered.length === 0 && <p className="text-sm text-muted-foreground">{t('admin.noUsers')}</p>}
      {filtered.map((user) => (
        <UserRow key={user.id} user={user} onLink={onLink} onDelete={() => setDeleting(user)} />
      ))}
      <DeleteUserDialog user={deleting} onClose={() => setDeleting(null)} />
    </div>
  )
}

function UserRow({
  user,
  onLink,
  onDelete,
}: {
  user: AdminUser
  onLink: (link: ShownLink) => void
  onDelete: () => void
}) {
  const { t, tp, lang } = useI18n()
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
  const fail = (e: Error) => window.alert(e.message || t('admin.failed'))

  const patch = useMutation({
    mutationFn: (body: { is_admin?: boolean; disabled?: boolean }) => api.adminUpdateUser(user.id, body),
    onSuccess: refresh,
    onError: fail,
  })
  const logout = useMutation({
    mutationFn: () => api.adminLogoutUser(user.id),
    onSuccess: () => window.alert(t('admin.loggedOut', { email: user.email })),
    onError: fail,
  })
  const reset = useMutation({
    mutationFn: () => api.adminResetLink(user.id),
    onSuccess: (link) =>
      onLink({
        url: `${window.location.origin}/reset/${link.token}`,
        title: t('admin.resetTitle'),
        description: t('admin.resetBody', { email: link.email, expires: formatDateTime(link.expires_at, lang) }),
      }),
    onError: fail,
  })

  const facts = [
    tp('common.recipes', user.recipe_count),
    user.created_at ? t('admin.joined', { date: relativeDate(user.created_at, lang) }) : t('admin.joinedUnknown'),
    user.last_login_at
      ? t('admin.lastLogin', { date: relativeDate(user.last_login_at, lang) })
      : t('admin.neverLoggedIn'),
    user.invited_by && t('admin.invitedBy', { email: user.invited_by }),
  ].filter(Boolean)

  return (
    <div className={cn('bg-white rounded-xl border border-border p-4 flex items-start gap-3', user.disabled && 'opacity-70')}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="text-sm font-semibold text-foreground truncate">{user.display_name || user.email}</p>
          {user.is_self && <span className="text-xs text-muted-foreground">({t('admin.you')})</span>}
          {user.is_admin && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 text-primary text-[11px] font-semibold px-2 py-0.5">
              <Shield className="w-3 h-3" /> {t('admin.badgeAdmin')}
            </span>
          )}
          {user.disabled && (
            <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 text-destructive text-[11px] font-semibold px-2 py-0.5">
              <Ban className="w-3 h-3" /> {t('admin.badgeDisabled')}
            </span>
          )}
        </div>
        {user.display_name && <p className="text-xs text-muted-foreground truncate">{user.email}</p>}
        <p className="text-xs text-muted-foreground mt-1">{facts.join(' · ')}</p>
      </div>

      <Menu label={t('admin.actions', { email: user.email })} trigger={<MoreHorizontal className="w-4 h-4" />}>
        <MenuItem icon={<KeyRound />} onSelect={() => reset.mutate()} disabled={user.disabled || reset.isPending}>
          {t('admin.resetLink')}
        </MenuItem>
        <MenuItem
          icon={<LogOut />}
          onSelect={() => window.confirm(t('admin.confirmLogout', { email: user.email })) && logout.mutate()}
        >
          {t('admin.logoutEverywhere')}
        </MenuItem>
        {!user.is_self && (
          <>
            {user.disabled ? (
              <MenuItem icon={<CheckCircle2 />} onSelect={() => patch.mutate({ disabled: false })}>
                {t('admin.enable')}
              </MenuItem>
            ) : (
              <MenuItem
                icon={<Ban />}
                onSelect={() =>
                  window.confirm(t('admin.confirmDisable', { email: user.email })) && patch.mutate({ disabled: true })
                }
              >
                {t('admin.disable')}
              </MenuItem>
            )}
            {user.is_admin ? (
              <MenuItem icon={<ShieldOff />} onSelect={() => patch.mutate({ is_admin: false })}>
                {t('admin.removeAdmin')}
              </MenuItem>
            ) : (
              <MenuItem icon={<Shield />} onSelect={() => patch.mutate({ is_admin: true })}>
                {t('admin.makeAdmin')}
              </MenuItem>
            )}
            <MenuSeparator />
            <MenuItem icon={<Trash2 />} destructive onSelect={onDelete}>
              {t('admin.delete')}
            </MenuItem>
          </>
        )}
      </Menu>
    </div>
  )
}

function DeleteUserDialog({ user, onClose }: { user: AdminUser | null; onClose: () => void }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState('')
  const remove = useMutation({
    mutationFn: () => api.adminDeleteUser(user!.id, typed.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
      close()
    },
  })

  function close() {
    setTyped('')
    remove.reset()
    onClose()
  }

  const matches = !!user && typed.trim().toLowerCase() === user.email.toLowerCase()

  return (
    <Dialog open={!!user} onOpenChange={(o) => !o && close()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('admin.deleteTitle', { email: user?.email ?? '' })}</DialogTitle>
          <DialogDescription>{t('admin.deleteBody', { count: user?.recipe_count ?? 0 })}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="confirm-delete">{t('admin.deleteConfirmLabel')}</Label>
          <Input
            id="confirm-delete"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={user?.email}
            autoComplete="off"
            autoFocus
          />
        </div>
        {remove.isError && (
          <p className="text-sm text-destructive mt-3">{remove.error.message || t('admin.failed')}</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={close} disabled={remove.isPending}>
            {t('common.cancel')}
          </Button>
          <Button variant="destructive" onClick={() => remove.mutate()} disabled={!matches || remove.isPending}>
            {remove.isPending ? t('admin.deleting') : t('admin.delete')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Sign-up links
// ---------------------------------------------------------------------------

const VALIDITY_DAYS = [1, 7, 14, 30]

const STATUS_STYLE: Record<Invite['status'], string> = {
  active: 'bg-emerald-50 text-emerald-700',
  used: 'bg-primary/10 text-primary',
  expired: 'bg-muted text-muted-foreground',
  revoked: 'bg-destructive/10 text-destructive',
}

function InvitesTab({ onLink }: { onLink: (link: ShownLink) => void }) {
  const { t, lang } = useI18n()
  const queryClient = useQueryClient()
  const { data: invites = [], isLoading } = useQuery({ queryKey: ['admin', 'invites'], queryFn: api.adminListInvites })
  const [email, setEmail] = useState('')
  const [note, setNote] = useState('')
  const [days, setDays] = useState(7)

  const create = useMutation({
    mutationFn: () =>
      api.adminCreateInvite({ email: email.trim() || undefined, note: note.trim() || undefined, expires_in_days: days }),
    onSuccess: (invite) => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'invites'] })
      setEmail('')
      setNote('')
      const expires = formatDateTime(invite.expires_at, lang)
      onLink({
        url: `${window.location.origin}/signup/${invite.token}`,
        title: t('admin.inviteTitle'),
        description: invite.email
          ? t('admin.inviteBodyLocked', { email: invite.email, expires })
          : t('admin.inviteBody', { expires }),
      })
    },
  })
  const revoke = useMutation({
    mutationFn: (id: number) => api.adminRevokeInvite(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'invites'] }),
    onError: (e: Error) => window.alert(e.message || t('admin.failed')),
  })

  return (
    <div className="space-y-4">
      <form
        className="bg-white rounded-xl border border-border p-5 space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <p className="text-sm font-semibold text-foreground">{t('admin.newInvite')}</p>
        <div className="space-y-1.5">
          <Label htmlFor="invite-email">{t('admin.inviteEmail')}</Label>
          <Input
            id="invite-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="anna@example.com"
          />
          <p className="text-xs text-muted-foreground">{t('admin.inviteEmailHint')}</p>
        </div>
        <div className="grid grid-cols-[1fr_auto] gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="invite-note">{t('admin.inviteNote')}</Label>
            <Input
              id="invite-note"
              value={note}
              maxLength={200}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t('admin.inviteNotePlaceholder')}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="invite-days">{t('admin.inviteValidity')}</Label>
            <select
              id="invite-days"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {VALIDITY_DAYS.map((d) => (
                <option key={d} value={d}>
                  {d === 1 ? t('admin.day') : t('admin.days', { count: d })}
                </option>
              ))}
            </select>
          </div>
        </div>
        {create.isError && <p className="text-sm text-destructive">{create.error.message || t('admin.failed')}</p>}
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? t('admin.creatingInvite') : t('admin.createInvite')}
        </Button>
      </form>

      {isLoading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
      {!isLoading && invites.length === 0 && <p className="text-sm text-muted-foreground">{t('admin.noInvites')}</p>}
      <div className="space-y-2">
        {invites.map((invite) => (
          <div key={invite.id} className="bg-white rounded-xl border border-border p-4 flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <p className="text-sm font-semibold text-foreground truncate">{invite.email ?? t('admin.anyone')}</p>
                <span className={cn('rounded-full text-[11px] font-semibold px-2 py-0.5', STATUS_STYLE[invite.status])}>
                  {t(`admin.status.${invite.status}` as MessageKey)}
                </span>
              </div>
              {invite.note && <p className="text-xs text-foreground mt-0.5">{invite.note}</p>}
              <p className="text-xs text-muted-foreground mt-1">
                {[
                  t('admin.inviteCreated', {
                    date: relativeDate(invite.created_at, lang),
                    email: invite.created_by ?? '—',
                  }),
                  invite.status === 'used' && invite.used_by
                    ? t('admin.inviteUsedBy', { email: invite.used_by })
                    : invite.status === 'active'
                      ? t('admin.inviteExpires', { date: formatDateTime(invite.expires_at, lang) })
                      : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            </div>
            {invite.status === 'active' && (
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => revoke.mutate(invite.id)}
                disabled={revoke.isPending}
              >
                {t('admin.revoke')}
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
