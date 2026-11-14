import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, BookOpen, Search, Users, UtensilsCrossed, X } from 'lucide-react'
import {
  api,
  personName,
  type AdminFriendship,
  type AdminShare,
  type AdminUser,
  type Person,
  type ShareType,
} from '@/lib/api'
import { relativeDate } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { useI18n, type MessageKey } from '@/i18n'

const ROLES: Record<ShareType, Array<'viewer' | 'editor' | 'manager'>> = {
  menu: ['viewer', 'editor'],
  cookbook: ['viewer', 'editor', 'manager'],
}

const selectClass = 'w-full text-sm bg-white rounded-md border border-input px-2 py-2'

const who = (p: Person) => personName(p.display_name, p.email)

function matches(q: string, ...people: Person[]) {
  return people.some((p) => p.email.toLowerCase().includes(q) || (p.display_name ?? '').toLowerCase().includes(q))
}

function useUsers() {
  const { data: users = [] } = useQuery({ queryKey: ['admin', 'users'], queryFn: api.adminListUsers })
  return users
}

function UserSelect({
  id,
  users,
  value,
  onChange,
  exclude,
}: {
  id: string
  users: AdminUser[]
  value: number | ''
  onChange: (id: number | '') => void
  exclude?: number | ''
}) {
  const { t } = useI18n()
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
      className={selectClass}
    >
      <option value="">{t('admin.chooseUser')}</option>
      {users
        .filter((u) => u.id !== exclude)
        .map((u) => (
          <option key={u.id} value={u.id}>
            {personName(u.display_name, u.email)}
          </option>
        ))}
    </select>
  )
}

function SearchBox({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useI18n()
  return (
    <div className="relative flex-1">
      <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={t('admin.search')} className="pl-9 bg-white" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Friends
// ---------------------------------------------------------------------------

export function FriendsTab() {
  const { t, lang } = useI18n()
  const queryClient = useQueryClient()
  const users = useUsers()
  const { data: pairs = [], isLoading } = useQuery({
    queryKey: ['admin', 'friendships'],
    queryFn: api.adminListFriendships,
  })
  const [a, setA] = useState<number | ''>('')
  const [b, setB] = useState<number | ''>('')
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['admin', 'friendships'] })
    queryClient.invalidateQueries({ queryKey: ['admin', 'shares'] })
  }
  const connect = useMutation({
    mutationFn: () => api.adminCreateFriendship(Number(a), Number(b)),
    onSuccess: () => {
      setA('')
      setB('')
      setError(null)
      refresh()
    },
    onError: (e: Error) => setError(e.message || t('admin.failed')),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.adminDeleteFriendship(id),
    onSuccess: refresh,
    onError: (e: Error) => window.alert(e.message || t('admin.failed')),
  })

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? pairs.filter((p) => matches(q, p.requester, p.addressee)) : pairs
  }, [pairs, query])

  function confirmRemove(p: AdminFriendship) {
    if (window.confirm(t('admin.confirmUnfriend', { a: who(p.requester), b: who(p.addressee) }))) remove.mutate(p.id)
  }

  return (
    <div className="space-y-4">
      <form
        className="bg-white rounded-xl border border-border p-5 space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          if (a && b) connect.mutate()
        }}
      >
        <div>
          <p className="text-sm font-semibold text-foreground">{t('admin.connectTitle')}</p>
          <p className="text-xs text-muted-foreground">{t('admin.connectHint')}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="friend-a">{t('admin.person')}</Label>
            <UserSelect id="friend-a" users={users} value={a} onChange={setA} exclude={b} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="friend-b">{t('admin.andPerson')}</Label>
            <UserSelect id="friend-b" users={users} value={b} onChange={setB} exclude={a} />
          </div>
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" disabled={!a || !b || connect.isPending}>
          <Users className="w-4 h-4 mr-1.5" />
          {t('admin.connect')}
        </Button>
      </form>

      <SearchBox value={query} onChange={setQuery} />
      {isLoading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
      {!isLoading && filtered.length === 0 && <p className="text-sm text-muted-foreground">{t('admin.noFriendships')}</p>}
      {filtered.length > 0 && (
        <div className="bg-white rounded-xl border border-border divide-y divide-border/50">
          {filtered.map((p) => (
            <div key={p.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="text-sm text-foreground flex flex-wrap items-center gap-x-1.5">
                  <span className="truncate">{who(p.requester)}</span>
                  <span className="text-muted-foreground">↔</span>
                  <span className="truncate">{who(p.addressee)}</span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {p.status === 'pending'
                    ? t('admin.friendPending')
                    : p.responded_at
                      ? t('admin.friendsSince', { date: relativeDate(p.responded_at, lang) })
                      : t('admin.friends')}
                </div>
              </div>
              <button
                onClick={() => confirmRemove(p)}
                className="text-muted-foreground hover:text-destructive"
                aria-label={t('admin.removeFriendship')}
                title={t('admin.removeFriendship')}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shares
// ---------------------------------------------------------------------------

function resourceLabel(s: AdminShare, t: (k: MessageKey) => string) {
  if (s.type === 'cookbook' && s.cookbook_kind === 'all') return t('admin.allRecipes')
  return s.resource_name
}

function kindLabel(s: AdminShare): MessageKey {
  if (s.type === 'menu') return 'admin.kindMenu'
  if (s.cookbook_kind === 'quickshare') return 'admin.kindRecipe'
  return 'admin.kindCookbook'
}

export function SharesTab() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const { data: shares = [], isLoading } = useQuery({ queryKey: ['admin', 'shares'], queryFn: api.adminListShares })
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<ShareType | ''>('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin', 'shares'] })
  const fail = (e: Error) => window.alert(e.message || t('admin.failed'))
  const setRole = useMutation({
    mutationFn: ({ s, role }: { s: AdminShare; role: string }) =>
      api.adminUpdateShare(s.type, s.resource_id, s.grantee.user_id, role),
    onSuccess: refresh,
    onError: fail,
  })
  const revoke = useMutation({
    mutationFn: (s: AdminShare) => api.adminDeleteShare(s.type, s.resource_id, s.grantee.user_id),
    onSuccess: refresh,
    onError: fail,
  })

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return shares.filter(
      (s) =>
        (!typeFilter || s.type === typeFilter) &&
        (!q || matches(q, s.owner, s.grantee) || s.resource_name.toLowerCase().includes(q)),
    )
  }, [shares, query, typeFilter])

  return (
    <div className="space-y-4">
      <NewShareForm onCreated={refresh} />

      <div className="flex gap-2">
        <SearchBox value={query} onChange={setQuery} />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as ShareType | '')}
          className="text-sm bg-white rounded-md border border-input px-2"
          aria-label={t('admin.shareType')}
        >
          <option value="">{t('admin.allTypes')}</option>
          <option value="menu">{t('admin.kindMenu')}</option>
          <option value="cookbook">{t('admin.kindCookbook')}</option>
        </select>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
      {!isLoading && filtered.length === 0 && <p className="text-sm text-muted-foreground">{t('admin.noShares')}</p>}
      {filtered.length > 0 && (
        <div className="bg-white rounded-xl border border-border divide-y divide-border/50">
          {filtered.map((s) => {
            const Icon = s.type === 'menu' ? UtensilsCrossed : BookOpen
            return (
              <div key={`${s.type}-${s.resource_id}-${s.grantee.user_id}`} className="flex items-center gap-3 px-4 py-3">
                <Icon className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-foreground truncate">
                    {resourceLabel(s, t)}
                    <span className="ml-1.5 text-xs font-normal text-muted-foreground">{t(kindLabel(s))}</span>
                  </div>
                  <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-1">
                    <span className="truncate">{who(s.owner)}</span>
                    <ArrowRight className="w-3 h-3" />
                    <span className="truncate">{who(s.grantee)}</span>
                    {s.status === 'pending' && <span>{t('cookbook.pendingSuffix')}</span>}
                  </div>
                </div>
                <select
                  value={s.role}
                  onChange={(e) => setRole.mutate({ s, role: e.target.value })}
                  className="text-xs bg-muted/50 rounded-md border border-border px-1.5 py-1"
                  aria-label={t('menus.shareRole')}
                >
                  {ROLES[s.type].map((r) => (
                    <option key={r} value={r}>
                      {t(`role.${r}` as MessageKey)}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => {
                    if (window.confirm(t('admin.confirmRevokeShare', { what: resourceLabel(s, t), name: who(s.grantee) })))
                      revoke.mutate(s)
                  }}
                  className="text-muted-foreground hover:text-destructive"
                  aria-label={t('admin.revoke')}
                  title={t('admin.revoke')}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function NewShareForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const users = useUsers()
  const [owner, setOwner] = useState<number | ''>('')
  const [type, setType] = useState<ShareType>('menu')
  const [resource, setResource] = useState<number | ''>('')
  const [grantee, setGrantee] = useState<number | ''>('')
  const [role, setRole] = useState<string>('viewer')
  const [ensureFriends, setEnsureFriends] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { data: resources = [] } = useQuery({
    queryKey: ['admin', 'resources', owner, type],
    queryFn: () => api.adminUserResources(Number(owner), type),
    enabled: owner !== '',
  })

  const create = useMutation({
    mutationFn: () =>
      api.adminCreateShare({
        type,
        resource_id: Number(resource),
        user_id: Number(grantee),
        role,
        ensure_friends: ensureFriends,
      }),
    onSuccess: () => {
      setResource('')
      setGrantee('')
      setError(null)
      onCreated()
      queryClient.invalidateQueries({ queryKey: ['admin', 'friendships'] })
    },
    onError: (e: Error) => setError(e.message || t('admin.failed')),
  })

  const resourceName = (r: { name: string; detail: string | null }) =>
    type === 'cookbook' && r.detail === 'all'
      ? t('admin.allRecipes')
      : type === 'cookbook' && r.detail === 'quickshare'
        ? `${r.name} (${t('admin.kindRecipe')})`
        : r.name

  return (
    <form
      className="bg-white rounded-xl border border-border p-5 space-y-3"
      onSubmit={(e) => {
        e.preventDefault()
        if (resource && grantee) create.mutate()
      }}
    >
      <div>
        <p className="text-sm font-semibold text-foreground">{t('admin.newShare')}</p>
        <p className="text-xs text-muted-foreground">{t('admin.newShareHint')}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="share-owner">{t('admin.shareOwner')}</Label>
          <UserSelect
            id="share-owner"
            users={users}
            value={owner}
            onChange={(v) => {
              setOwner(v)
              setResource('')
            }}
          />
        </div>
        <div className="space-y-1.5">
          <Label>{t('admin.shareType')}</Label>
          <div className="inline-flex w-full rounded-md border border-input p-0.5 text-sm">
            {(['menu', 'cookbook'] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  setType(k)
                  setResource('')
                  if (!ROLES[k].includes(role as 'viewer')) setRole('viewer')
                }}
                className={cn(
                  'flex-1 px-2 py-1.5 rounded',
                  type === k ? 'bg-primary/10 text-primary font-semibold' : 'text-muted-foreground',
                )}
              >
                {t(k === 'menu' ? 'admin.kindMenu' : 'admin.kindCookbook')}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="share-resource">{t(type === 'menu' ? 'admin.kindMenu' : 'admin.kindCookbook')}</Label>
          <select
            id="share-resource"
            value={resource}
            disabled={owner === ''}
            onChange={(e) => setResource(e.target.value ? Number(e.target.value) : '')}
            className={selectClass}
          >
            <option value="">
              {owner !== '' && resources.length === 0 ? t('admin.noResources') : t('admin.chooseResource')}
            </option>
            {resources.map((r) => (
              <option key={r.id} value={r.id}>
                {resourceName(r)}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="share-grantee">{t('admin.shareWith')}</Label>
          <UserSelect id="share-grantee" users={users} value={grantee} onChange={setGrantee} exclude={owner} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="share-role">{t('menus.shareRole')}</Label>
          <select id="share-role" value={role} onChange={(e) => setRole(e.target.value)} className={selectClass}>
            {ROLES[type].map((r) => (
              <option key={r} value={r}>
                {t(`role.${r}` as MessageKey)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={ensureFriends}
          onChange={(e) => setEnsureFriends(e.target.checked)}
          className="w-4 h-4 accent-[hsl(var(--primary))]"
        />
        {t('admin.ensureFriends')}
      </label>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Button type="submit" disabled={!resource || !grantee || create.isPending}>
        {t('admin.createShare')}
      </Button>
    </form>
  )
}
