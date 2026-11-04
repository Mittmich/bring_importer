import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookHeart, Check, Plus, Share2, Users, X } from 'lucide-react'
import { api, type Cookbook } from '@/lib/api'
import { useRecipeImage } from '@/hooks/useRecipeImage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useI18n, type MessageKey } from '@/i18n'

export function CookbooksPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const { t } = useI18n()

  const { data: cookbooks = [], isLoading } = useQuery({
    queryKey: ['cookbooks'],
    queryFn: () => api.listCookbooks(),
  })
  const { data: invitations = [] } = useQuery({
    queryKey: ['cookbookInvitations'],
    queryFn: api.listCookbookInvitations,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['cookbooks'] })
    queryClient.invalidateQueries({ queryKey: ['cookbookInvitations'] })
  }

  const create = useMutation({
    mutationFn: (n: string) => api.createCookbook(n),
    onSuccess: () => {
      setName('')
      setCreating(false)
      invalidate()
    },
  })
  const accept = useMutation({
    mutationFn: (id: number) => api.acceptCookbookInvitation(id),
    onSuccess: invalidate,
  })
  const decline = useMutation({
    mutationFn: (id: number) => api.declineCookbookInvitation(id),
    onSuccess: invalidate,
  })
  const shareAll = useMutation({
    mutationFn: () => api.createAllCookbook(),
    onSuccess: (cb) => {
      queryClient.invalidateQueries({ queryKey: ['cookbooks'] })
      navigate(`/cookbooks/${cb.id}`)
    },
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const n = name.trim()
    if (n) create.mutate(n)
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-[#F8FAFC]">
      <div className="max-w-3xl mx-auto w-full p-4 md:p-6 space-y-5 pt-6 pb-10">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-foreground">{t('cookbooks.title')}</h1>
          {!creating && (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="w-4 h-4 mr-1.5" /> {t('cookbooks.new')}
            </Button>
          )}
        </div>

        <button
          onClick={() => shareAll.mutate()}
          disabled={shareAll.isPending}
          className="w-full flex items-center gap-3 bg-white rounded-xl border border-border p-4 hover:border-primary/40 transition-colors text-left"
        >
          <Share2 className="w-4 h-4 text-primary flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">{t('cookbooks.shareAll')}</p>
            <p className="text-xs text-muted-foreground">{t('cookbooks.shareAllHint')}</p>
          </div>
        </button>

        {creating && (
          <form onSubmit={submit} className="bg-white rounded-xl border border-border p-4 flex gap-2">
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('cookbooks.namePlaceholder')}
            />
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              {create.isPending ? t('common.creating') : t('common.create')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => {
                setCreating(false)
                setName('')
              }}
            >
              <X className="w-4 h-4" />
            </Button>
          </form>
        )}

        {invitations.length > 0 && (
          <div className="space-y-1.5">
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
              {t('cookbooks.invitations')}
            </h2>
            <div className="bg-white rounded-xl border border-border divide-y divide-border/50 overflow-hidden">
              {invitations.map((inv) => (
                <div key={inv.cookbook_id} className="flex items-center gap-2 px-4 py-3">
                  <Users className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{inv.name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {t('cookbooks.from', {
                        name: inv.owner_name || inv.owner_email,
                        role: t(`role.${inv.role}` as MessageKey),
                      })}
                    </p>
                  </div>
                  <Button size="sm" onClick={() => accept.mutate(inv.cookbook_id)} disabled={accept.isPending}>
                    <Check className="w-4 h-4 mr-1" /> {t('common.accept')}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => decline.mutate(inv.cookbook_id)}
                    disabled={decline.isPending}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : cookbooks.length === 0 ? (
          <div className="text-center py-14 space-y-1">
            <BookHeart className="w-8 h-8 text-primary/30 mx-auto mb-2" />
            <p className="text-base font-semibold text-foreground">{t('cookbooks.emptyTitle')}</p>
            <p className="text-sm text-muted-foreground">{t('cookbooks.emptyBody')}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {cookbooks.map((cb) => (
              <CookbookCard key={cb.id} cookbook={cb} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function CookbookCard({ cookbook }: { cookbook: Cookbook }) {
  const cover = useRecipeImage(cookbook.cover_image_url)
  const { t, tp } = useI18n()
  return (
    <NavLink
      to={`/cookbooks/${cookbook.id}`}
      className="group rounded-xl border border-border bg-white overflow-hidden hover:border-primary/40 transition-colors"
    >
      <div className="aspect-video bg-muted overflow-hidden">
        {cover ? (
          <img
            src={cover}
            alt=""
            className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-primary/5 text-primary/30">
            <BookHeart className="w-7 h-7" />
          </div>
        )}
      </div>
      <div className="p-3">
        <p className="text-sm font-semibold text-foreground truncate group-hover:text-primary transition-colors">
          {cookbook.name}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5 tabular-nums flex items-center gap-1.5">
          <span>{tp('common.recipes', cookbook.recipe_count)}</span>
          {cookbook.shared && (
            <span className="inline-flex items-center gap-1 text-primary">
              <Users className="w-3 h-3" />{' '}
              {t('cookbooks.shared', { role: t(`role.${cookbook.role ?? 'viewer'}` as MessageKey) })}
            </span>
          )}
        </p>
      </div>
    </NavLink>
  )
}
