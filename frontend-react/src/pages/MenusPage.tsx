import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Plus, Share2, UtensilsCrossed, Users, X } from 'lucide-react'
import { api, personName, type MenuInvitation, type MenuSummary } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatMenuDate, hhmm } from '@/lib/menuPlan'
import { useI18n, type MessageKey } from '@/i18n'

export function MenusPage() {
  const { t } = useI18n()
  const [creating, setCreating] = useState(false)
  const { data: menus = [], isLoading } = useQuery({ queryKey: ['menus'], queryFn: api.listMenus })
  const { data: invitations = [] } = useQuery({ queryKey: ['menuInvitations'], queryFn: api.listMenuInvitations })
  const mine = menus.filter((m) => m.role === 'owner')
  const shared = menus.filter((m) => m.role !== 'owner')

  return (
    <div className="flex flex-col h-full bg-[#F8FAFC]">
      <div className="bg-white border-b border-border px-4 py-3 flex items-center justify-between gap-2">
        <h1 className="text-base font-semibold text-foreground">{t('menus.title')}</h1>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="w-4 h-4 mr-1.5" />
          {t('menus.new')}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {invitations.length > 0 && <Invitations invitations={invitations} />}
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : mine.length === 0 && shared.length === 0 ? (
          <div className="max-w-md mx-auto text-center py-16">
            <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center">
              <UtensilsCrossed className="w-6 h-6" />
            </div>
            <h2 className="font-semibold mb-1">{t('menus.emptyTitle')}</h2>
            <p className="text-sm text-muted-foreground mb-5">{t('menus.emptyBody')}</p>
            <Button onClick={() => setCreating(true)}>
              <Plus className="w-4 h-4 mr-1.5" />
              {t('menus.new')}
            </Button>
          </div>
        ) : (
          <>
            {mine.length > 0 && (
              <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
                {mine.map((m) => (
                  <MenuCardLink key={m.id} menu={m} />
                ))}
              </div>
            )}
            {shared.length > 0 && (
              <section className="space-y-2">
                <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
                  {t('menus.sharedWithMe')}
                </h2>
                <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
                  {shared.map((m) => (
                    <MenuCardLink key={m.id} menu={m} />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>

      {creating && <NewMenuDialog onClose={() => setCreating(false)} />}
    </div>
  )
}

function MenuCardLink({ menu }: { menu: MenuSummary }) {
  const { t, tp, lang } = useI18n()
  return (
    <Link
      to={`/menus/${menu.id}`}
      className="block bg-[#fffdf9] rounded-xl border border-[#f3e3cf] p-4 hover:border-primary/50 hover:shadow-sm transition"
    >
      <div className="font-serif text-lg leading-snug text-foreground">{menu.title}</div>
      <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
        {menu.date && <span>{formatMenuDate(menu.date, lang, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}</span>}
        <span className="inline-flex items-center gap-1">
          <Users className="w-3 h-3" />
          {tp('menus.guests', menu.guests)}
        </span>
        {menu.role === 'owner' && menu.member_count > 0 && (
          <span className="inline-flex items-center gap-1" title={tp('menus.sharedCount', menu.member_count)}>
            <Share2 className="w-3 h-3" />
            {menu.member_count}
          </span>
        )}
      </div>
      {menu.role !== 'owner' && (
        <div className="text-xs text-muted-foreground mt-0.5">
          {t('menus.sharedBy', {
            name: personName(menu.owner.display_name, menu.owner.email),
            role: t(`role.${menu.role}` as MessageKey),
          })}
        </div>
      )}
      {menu.courses.length > 0 ? (
        <ul className="mt-3 space-y-1">
          {menu.courses.map((c, i) => (
            <li key={i} className="text-sm flex gap-2">
              <span className="text-muted-foreground tabular-nums">{hhmm(c.serve)}</span>
              <span className="truncate">{c.recipe_title}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">{t('menus.noCourses')}</p>
      )}
    </Link>
  )
}

function Invitations({ invitations }: { invitations: MenuInvitation[] }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['menuInvitations'] })
    qc.invalidateQueries({ queryKey: ['menus'] })
  }
  const accept = useMutation({ mutationFn: api.acceptMenuInvitation, onSuccess: refresh })
  const decline = useMutation({ mutationFn: api.declineMenuInvitation, onSuccess: refresh })

  return (
    <section className="space-y-2">
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
        {t('menus.invitations')}
      </h2>
      <div className="bg-white rounded-xl border border-border divide-y divide-border/50">
        {invitations.map((inv) => (
          <div key={inv.menu_id} className="flex items-center gap-3 px-4 py-3">
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{inv.title}</div>
              <div className="text-xs text-muted-foreground truncate">
                {t('menus.invitedBy', {
                  name: personName(inv.owner.display_name, inv.owner.email),
                  role: t(`role.${inv.role}` as MessageKey),
                })}
              </div>
            </div>
            <Button size="sm" onClick={() => accept.mutate(inv.menu_id)} disabled={accept.isPending}>
              <Check className="w-4 h-4 mr-1" />
              {t('menus.accept')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => decline.mutate(inv.menu_id)}
              disabled={decline.isPending}
              aria-label={t('menus.decline')}
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        ))}
      </div>
    </section>
  )
}

function NewMenuDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [date, setDate] = useState('')
  const [guests, setGuests] = useState(4)
  const create = useMutation({
    mutationFn: () => api.createMenu({ title: title.trim(), date: date || null, guests }),
    onSuccess: (menu) => navigate(`/menus/${menu.id}`),
  })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('menus.new')}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (title.trim()) create.mutate()
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="menu-title">{t('menus.name')}</Label>
            <Input
              id="menu-title"
              autoFocus
              value={title}
              maxLength={120}
              placeholder={t('menus.namePlaceholder')}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="menu-date">{t('menus.date')}</Label>
              <Input id="menu-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="menu-guests">{t('menus.guestsLabel')}</Label>
              <Input
                id="menu-guests"
                type="number"
                min={1}
                max={50}
                value={guests}
                onChange={(e) => setGuests(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
              />
            </div>
          </div>
          {create.isError && <p className="text-sm text-destructive">{t('menus.saveFailed')}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!title.trim() || create.isPending}>
              {create.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
