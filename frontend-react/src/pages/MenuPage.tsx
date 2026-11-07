import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  CalendarRange,
  ChefHat,
  FileDown,
  List,
  Minus,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  ShoppingCart,
  Trash2,
  X,
} from 'lucide-react'
import { api, type Menu, type MenuCourse } from '@/lib/api'
import { useMenu, type MenuApi } from '@/hooks/useMenu'
import { useDraft } from '@/hooks/useDraft'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Menu as DropMenu, MenuItem } from '@/components/ui/menu'
import { StepEditor } from '@/components/menu/StepEditor'
import { PlanTimeline } from '@/components/menu/PlanTimeline'
import { RunSheet } from '@/components/menu/RunSheet'
import {
  courseColor,
  durationLabel,
  findClashes,
  hhmm,
  parseHhmm,
  planStats,
  sortedCourses,
  workload,
} from '@/lib/menuPlan'
import { saveOrShare } from '@/lib/download'
import { cn } from '@/lib/utils'
import { useI18n, type MessageKey } from '@/i18n'

const COURSE_NAME_KEYS: MessageKey[] = ['menus.course.starter', 'menus.course.main', 'menus.course.dessert']

function useIsDesktop() {
  const query = '(min-width: 768px)'
  const [desktop, setDesktop] = useState(() => window.matchMedia?.(query).matches ?? true)
  useEffect(() => {
    const mq = window.matchMedia?.(query)
    if (!mq) return
    const on = () => setDesktop(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return desktop
}

export function MenuPage() {
  const { id } = useParams()
  const menuId = Number(id)
  const m = useMenu(menuId)
  const { t } = useI18n()

  if (m.isLoading) return <p className="p-4 text-sm text-muted-foreground">{t('common.loading')}</p>
  if (!m.menu) {
    return (
      <div className="p-4 text-sm">
        <p className="text-muted-foreground mb-3">{t('menus.notFound')}</p>
        <Link to="/plan" className="text-primary underline">
          {t('menus.backToMenus')}
        </Link>
      </div>
    )
  }
  return <MenuView menu={m.menu} m={m} />
}

function MenuView({ menu, m }: { menu: Menu; m: MenuApi }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const desktop = useIsDesktop()
  const [view, setView] = useState<'timeline' | 'list'>('timeline')
  const [selected, setSelected] = useState<number | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [picking, setPicking] = useState(false)
  const showTimeline = desktop && view === 'timeline'
  const selectedStep = menu.steps.find((s) => s.id === selected) ?? null
  const editingStep = menu.steps.find((s) => s.id === editing) ?? null

  async function addStep() {
    const course =
      menu.courses.find((c) => c.id === selectedStep?.course_id) ?? sortedCourses(menu)[menu.courses.length - 1]
    if (!course) return
    const updated = await m.run(() =>
      api.addMenuStep(menu.id, { course_id: course.id, name: t('menus.newStep'), duration: 15, lead: 15 }),
    )
    const added = updated.steps.reduce((a, b) => (b.id > a.id ? b : a))
    if (showTimeline) setSelected(added.id)
    else setEditing(added.id)
  }

  async function deleteStep(stepId: number) {
    await m.run(() => api.deleteMenuStep(menu.id, stepId))
    setSelected(null)
    setEditing(null)
  }

  return (
    <div className="flex flex-col h-full bg-[#F8FAFC]">
      {/* Header */}
      <div className="bg-white border-b border-border px-4 py-3 flex items-center gap-2">
        <Link to="/plan" className="text-muted-foreground hover:text-foreground" aria-label={t('menus.backToMenus')}>
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <h1 className="text-base font-semibold text-foreground truncate flex-1">{menu.title}</h1>
        {m.saving && <span className="text-xs text-muted-foreground">{t('common.saving')}</span>}
        <DropMenu trigger={<MoreHorizontal className="w-4 h-4" />} label={t('menus.more')}>
          <MenuItem
            icon={<Trash2 />}
            destructive
            onSelect={async () => {
              if (!window.confirm(t('menus.confirmDelete', { title: menu.title }))) return
              await api.deleteMenu(menu.id)
              navigate('/plan')
            }}
          >
            {t('menus.delete')}
          </MenuItem>
        </DropMenu>
      </div>

      {/* Actions */}
      <div className="bg-white border-b border-border px-4 py-2.5 flex flex-wrap items-center gap-2">
        <ShoppingListButton menu={menu} />
        <PdfButton menu={menu} />
        <Button size="sm" variant="outline" onClick={() => navigate(`/menus/${menu.id}/cook`)} disabled={!menu.steps.length}>
          <ChefHat className="w-4 h-4 mr-1.5" />
          {t('menus.startCooking')}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 md:p-4 space-y-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <MenuCardEditor menu={menu} m={m} onAddCourse={() => setPicking(true)} />
          <PlanSummary menu={menu} />
        </div>

        {/* Prep plan */}
        <section className="bg-white rounded-xl border border-border p-4">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <h2 className="font-semibold flex-1">{t('menus.prepPlan')}</h2>
            {desktop && (
              <div className="inline-flex rounded-md border border-input p-0.5 text-xs">
                <button
                  onClick={() => setView('timeline')}
                  className={cn('px-2.5 py-1 rounded flex items-center gap-1', view === 'timeline' && 'bg-primary/10 text-primary font-semibold')}
                >
                  <CalendarRange className="w-3.5 h-3.5" /> {t('menus.timeline')}
                </button>
                <button
                  onClick={() => setView('list')}
                  className={cn('px-2.5 py-1 rounded flex items-center gap-1', view === 'list' && 'bg-primary/10 text-primary font-semibold')}
                >
                  <List className="w-3.5 h-3.5" /> {t('menus.list')}
                </button>
              </div>
            )}
            <Button size="sm" variant="outline" onClick={addStep} disabled={!menu.courses.length}>
              <Plus className="w-4 h-4 mr-1" />
              {t('menus.addStep')}
            </Button>
          </div>

          {menu.courses.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">{t('menus.planEmpty')}</p>
          ) : showTimeline ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
              <PlanTimeline
                menu={menu}
                selectedId={selected}
                onSelect={setSelected}
                onMove={(stepId, lead) => m.updateStep(stepId, { lead })}
              />
              <div className="rounded-lg border border-border bg-slate-50/60 p-3">
                {selectedStep ? (
                  <StepEditor
                    key={selectedStep.id}
                    menu={menu}
                    step={selectedStep}
                    onChange={(patch) => m.updateStep(selectedStep.id, patch)}
                    onDelete={() => deleteStep(selectedStep.id)}
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">{t('menus.selectStep')}</p>
                )}
              </div>
            </div>
          ) : (
            <RunSheet menu={menu} onChange={(id, patch) => m.updateStep(id, patch)} onOpen={setEditing} />
          )}
        </section>
      </div>

      {editingStep && (
        <Dialog open onOpenChange={(o) => !o && setEditing(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('menus.editStep')}</DialogTitle>
            </DialogHeader>
            <StepEditor
              key={editingStep.id}
              menu={menu}
              step={editingStep}
              onChange={(patch) => m.updateStep(editingStep.id, patch)}
              onDelete={() => deleteStep(editingStep.id)}
            />
          </DialogContent>
        </Dialog>
      )}

      {picking && (
        <CoursePicker
          menu={menu}
          onClose={() => setPicking(false)}
          onPick={async (recipeUuid, name) => {
            await m.run(() => api.addMenuCourse(menu.id, { recipe_uuid: recipeUuid, name }))
            setPicking(false)
          }}
        />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------------- */
/* Menu card                                                                  */
/* ------------------------------------------------------------------------- */

function MenuCardEditor({ menu, m, onAddCourse }: { menu: Menu; m: MenuApi; onAddCourse: () => void }) {
  const { t, tp } = useI18n()
  const [title, setTitle] = useDraft(menu.title)
  const courses = sortedCourses(menu)

  return (
    <div className="relative bg-[#fffdf9] border border-[#f3e3cf] rounded-2xl px-5 py-6 text-center">
      <div className="pointer-events-none absolute inset-2 rounded-xl border border-[#f6dcbc]" />
      <input
        value={title}
        maxLength={120}
        onChange={(e) => setTitle(e.target.value)}
        onBlur={() => {
          const v = title.trim()
          if (!v) setTitle(menu.title)
          else if (v !== menu.title) m.updateMenu({ title: v })
        }}
        onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
        aria-label={t('menus.name')}
        className="relative w-full bg-transparent text-center font-serif text-2xl md:text-3xl focus:outline-none focus:ring-2 focus:ring-ring rounded"
      />
      <div className="relative mt-1 flex flex-wrap items-center justify-center gap-2 text-sm">
        <input
          type="date"
          value={menu.date ?? ''}
          onChange={(e) => m.updateMenu({ date: e.target.value })}
          aria-label={t('menus.date')}
          className="bg-transparent italic text-muted-foreground font-serif rounded px-1 focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <span className="inline-flex items-center gap-2 bg-white border border-border rounded-full pl-3 pr-1 py-0.5">
          <span className="text-xs">{tp('menus.guests', menu.guests)}</span>
          <button
            className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center disabled:opacity-40"
            onClick={() => m.updateMenu({ guests: menu.guests - 1 })}
            disabled={menu.guests <= 1}
            aria-label={t('menus.fewerGuests')}
          >
            <Minus className="w-3 h-3" />
          </button>
          <button
            className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center disabled:opacity-40"
            onClick={() => m.updateMenu({ guests: menu.guests + 1 })}
            disabled={menu.guests >= 50}
            aria-label={t('menus.moreGuests')}
          >
            <Plus className="w-3 h-3" />
          </button>
        </span>
      </div>

      {courses.map((c, i) => (
        <CourseBlock key={c.id} menu={menu} course={c} m={m} first={i === 0} />
      ))}

      <button
        onClick={onAddCourse}
        className="relative mt-5 w-full rounded-lg border border-dashed border-[#e8c9a6] py-2 text-sm font-semibold text-primary hover:bg-primary/5"
      >
        <Plus className="inline w-4 h-4 mr-1 -mt-0.5" />
        {t('menus.addCourse')}
      </button>
    </div>
  )
}

function CourseBlock({ menu, course, m, first }: { menu: Menu; course: MenuCourse; m: MenuApi; first: boolean }) {
  const { t } = useI18n()
  const color = courseColor(menu, course.id)
  const [name, setName] = useDraft(course.name)
  const redraft = useMutation({ mutationFn: () => m.run(() => api.redraftMenuCourse(menu.id, course.id)) })

  return (
    <div className="relative mt-5">
      {!first && <div className="text-[#f0b77c] tracking-[0.5em] mb-4 select-none">· · ·</div>}
      <div className="flex items-start gap-1">
        <div className="flex-1 min-w-0">
          <input
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => {
              const v = name.trim()
              if (!v) setName(course.name)
              else if (v !== course.name) m.updateCourse(course.id, { name: v })
            }}
            onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
            aria-label={t('menus.courseName')}
            className="w-full bg-transparent text-center text-[11px] font-bold uppercase tracking-[0.18em] focus:outline-none focus:ring-2 focus:ring-ring rounded"
            style={{ color }}
          />
          <Link to={`/recipes/${course.recipe_uuid}`} className="block font-serif text-xl leading-snug hover:underline">
            {course.recipe_title}
          </Link>
          <div className="mt-1 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <label className="inline-flex items-center gap-1">
              {t('menus.served')}
              <input
                type="time"
                step={300}
                value={hhmm(course.serve)}
                onChange={(e) => {
                  const v = parseHhmm(e.target.value)
                  if (v !== null && v !== course.serve) m.updateCourse(course.id, { serve: v })
                }}
                className="rounded border border-input bg-white px-1 py-0.5 text-xs text-foreground"
              />
            </label>
            <span>· {t('menus.scaled', { from: course.servings, to: menu.guests })}</span>
          </div>
        </div>
        <DropMenu trigger={<MoreHorizontal className="w-4 h-4" />} label={t('menus.courseActions')} className="flex-shrink-0">
          <MenuItem
            icon={<RefreshCw />}
            onSelect={() => {
              if (window.confirm(t('menus.confirmRedraft'))) redraft.mutate()
            }}
          >
            {t('menus.redraft')}
          </MenuItem>
          <MenuItem
            icon={<X />}
            destructive
            onSelect={() => {
              if (window.confirm(t('menus.confirmRemoveCourse', { title: course.recipe_title })))
                m.run(() => api.deleteMenuCourse(menu.id, course.id))
            }}
          >
            {t('menus.removeCourse')}
          </MenuItem>
        </DropMenu>
      </div>
      {redraft.isPending && <p className="text-xs text-muted-foreground mt-1">{t('menus.drafting')}</p>}
    </div>
  )
}

/* ------------------------------------------------------------------------- */
/* Summary: stats + workload chart                                            */
/* ------------------------------------------------------------------------- */

function PlanSummary({ menu }: { menu: Menu }) {
  const { t, tp } = useI18n()
  const stats = planStats(menu)
  const clashes = findClashes(menu)
  const buckets = workload(menu)
  // Bars scale to the busiest half hour (several people may cook at once).
  const peak = Math.max(30, ...buckets.map((b) => b.total))
  const scale = 110 / peak
  const courses = sortedCourses(menu)

  return (
    <div className="bg-white rounded-2xl border border-border p-4">
      <div className="grid grid-cols-2 gap-2 mb-4">
        <Stat value={stats.start === null ? '–' : hhmm(stats.start)} label={tp('menus.statStart', stats.dayBefore)} />
        <Stat value={durationLabel(stats.handsOn)} label={t('menus.statHands')} />
        <Stat value={durationLabel(stats.oven)} label={t('menus.statOven')} />
        <Stat
          value={clashes.length ? String(clashes.length) : '✓'}
          label={clashes.length ? t('menus.statClashes') : t('menus.statNoClashes')}
          alert={clashes.length > 0}
        />
      </div>
      <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">{t('menus.busyTitle')}</h3>
      {buckets.length === 0 || menu.courses.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('menus.planEmpty')}</p>
      ) : (
        <>
          <div className="relative flex items-end gap-0.5 h-[110px] border-b border-border">
            {buckets.map((b) => (
              <div key={b.start} className="flex-1 min-w-0 flex flex-col-reverse" title={`${hhmm(b.start)}: ${b.total} min`}>
                {courses.map((c) =>
                  b.byCourse[c.id] ? (
                    <div key={c.id} style={{ height: Math.min(110, b.byCourse[c.id] * scale), background: courseColor(menu, c.id) }} />
                  ) : null,
                )}
              </div>
            ))}
          </div>
          <div className="flex gap-0.5 text-[10px] text-muted-foreground">
            {buckets.map((b) => (
              <span key={b.start} className="flex-1 min-w-0 overflow-visible whitespace-nowrap">
                {b.start % 60 ? '' : hhmm(b.start).slice(0, 2)}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-3 mt-2 text-xs">
            {courses.map((c) => (
              <span key={c.id} className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: courseColor(menu, c.id) }} />
                {c.name}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ value, label, alert }: { value: string; label: string; alert?: boolean }) {
  return (
    <div className={cn('rounded-lg px-3 py-2', alert ? 'bg-destructive/10' : 'bg-slate-50')}>
      <div className={cn('text-lg font-bold tabular-nums', alert && 'text-destructive')}>{value}</div>
      <div className="text-xs text-muted-foreground leading-snug">{label}</div>
    </div>
  )
}

/* ------------------------------------------------------------------------- */
/* Actions                                                                    */
/* ------------------------------------------------------------------------- */

function ShoppingListButton({ menu }: { menu: Menu }) {
  const { t, lang } = useI18n()
  const mutation = useMutation({
    mutationFn: () => api.buildMenuShoppingList(menu.id),
    onSuccess: (data) => {
      const listUrl = `${window.location.origin}/api/meal-plan/shopping-list/${data.token}.html?lang=${lang}`
      window.location.href = `https://api.getbring.com/rest/bringrecipes/deeplink?url=${encodeURIComponent(listUrl)}&source=web`
    },
  })
  return (
    <Button size="sm" onClick={() => mutation.mutate()} disabled={!menu.courses.length || mutation.isPending}>
      <ShoppingCart className="w-4 h-4 mr-1.5" />
      {mutation.isPending ? t('plan.building') : t('plan.shoppingList')}
    </Button>
  )
}

function PdfButton({ menu }: { menu: Menu }) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={busy}
      onClick={async () => {
        setBusy(true)
        try {
          const { blob, filename } = await api.downloadMenuPdf(menu.id)
          await saveOrShare(blob, filename)
        } catch {
          window.alert(t('recipe.pdfFailed'))
        } finally {
          setBusy(false)
        }
      }}
    >
      <FileDown className="w-4 h-4 mr-1.5" />
      {busy ? t('menus.exporting') : t('menus.exportPdf')}
    </Button>
  )
}

/* ------------------------------------------------------------------------- */
/* Recipe picker                                                              */
/* ------------------------------------------------------------------------- */

function CoursePicker({
  menu,
  onClose,
  onPick,
}: {
  menu: Menu
  onClose: () => void
  onPick: (recipeUuid: string, name: string) => Promise<void>
}) {
  const { t } = useI18n()
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [name, setName] = useState(() => {
    const key = COURSE_NAME_KEYS[menu.courses.length]
    return key ? t(key) : t('menus.course.nth', { n: menu.courses.length + 1 })
  })
  const [busy, setBusy] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const h = setTimeout(() => setDebounced(search.trim()), 250)
    return () => clearTimeout(h)
  }, [search])
  const { data, isLoading } = useQuery({
    queryKey: ['recipes', 'picker', debounced],
    queryFn: () => api.listRecipes({ q: debounced || undefined, limit: 50 }),
  })
  const recipes = data?.items ?? []

  return (
    <Dialog open onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('menus.addCourse')}</DialogTitle>
        </DialogHeader>
        <label className="block text-xs font-medium text-muted-foreground mb-1" htmlFor="course-name">
          {t('menus.courseName')}
        </label>
        <input
          id="course-name"
          value={name}
          maxLength={60}
          onChange={(e) => setName(e.target.value)}
          className="w-full mb-3 px-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('plan.searchRecipes')}
            className="w-full pl-9 pr-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        {busy ? (
          <p className="text-sm text-muted-foreground py-6 text-center">{t('menus.drafting')}</p>
        ) : (
          <div className="space-y-1 max-h-[45dvh] overflow-y-auto">
            {failed && <p className="text-sm text-destructive">{t('menus.saveFailed')}</p>}
            {isLoading ? (
              <p className="text-sm text-muted-foreground py-4 text-center">{t('common.loading')}</p>
            ) : recipes.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">{t('plan.noRecipes')}</p>
            ) : (
              recipes.map((r) => (
                <button
                  key={r.uuid}
                  onClick={async () => {
                    setBusy(r.uuid)
                    setFailed(false)
                    try {
                      await onPick(r.uuid, name.trim() || t('menus.course.nth', { n: menu.courses.length + 1 }))
                    } catch {
                      setFailed(true)
                      setBusy(null)
                    }
                  }}
                  className="w-full text-left px-3 py-2.5 rounded-md hover:bg-accent transition-colors text-sm"
                >
                  {r.title}
                </button>
              ))
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
