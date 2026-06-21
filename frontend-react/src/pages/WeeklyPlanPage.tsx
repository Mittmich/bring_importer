import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Plus, ShoppingCart, CalendarPlus, X, Search } from 'lucide-react'
import { api, type MealPlanEntry } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useGoogleCalendar, loadGis, type GoogleCalendar } from '@/hooks/useGoogleCalendar'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function startOfWeek(d: Date): Date {
  const date = new Date(d)
  const isoDay = (date.getDay() + 6) % 7 // 0 = Monday
  date.setDate(date.getDate() - isoDay)
  date.setHours(0, 0, 0, 0)
  return date
}

function addDays(d: Date, n: number): Date {
  const date = new Date(d)
  date.setDate(date.getDate() + n)
  return date
}

// Local ISO date (YYYY-MM-DD) — avoids the UTC shift of toISOString().
function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function WeeklyPlanPage() {
  const queryClient = useQueryClient()
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()))
  const [pickerDate, setPickerDate] = useState<string | null>(null)

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart])
  const startISO = toISO(weekStart)
  const endISO = toISO(addDays(weekStart, 6))
  const todayISO = toISO(new Date())

  // Preload the Google script so the consent popup isn't blocked at export time.
  const { supported: googleSupported } = useGoogleCalendar()
  useEffect(() => {
    if (googleSupported) loadGis().catch(() => {})
  }, [googleSupported])

  const { data: entries = [] } = useQuery({
    queryKey: ['meal-plan', startISO, endISO],
    queryFn: () => api.getMealPlan(startISO, endISO),
  })

  const entriesByDate = useMemo(() => {
    const map: Record<string, MealPlanEntry[]> = {}
    for (const e of entries) (map[e.date] ??= []).push(e)
    return map
  }, [entries])

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['meal-plan'] })

  const addMutation = useMutation({
    mutationFn: ({ date, recipeUuid }: { date: string; recipeUuid: string }) =>
      api.addMealPlanEntry(date, recipeUuid),
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: (entryId: number) => api.deleteMealPlanEntry(entryId),
    onSuccess: invalidate,
  })

  const rangeLabel = `${weekStart.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} – ${addDays(weekStart, 6).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`

  return (
    <div className="flex flex-col h-full bg-[#F8FAFC]">
      {/* Header */}
      <div className="bg-white border-b border-border px-4 py-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-base font-semibold text-foreground">Weekly Plan</h1>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setWeekStart((w) => addDays(w, -7))} aria-label="Previous week">
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm font-medium text-muted-foreground min-w-[120px] text-center tabular-nums">
            {rangeLabel}
          </span>
          <Button variant="ghost" size="sm" onClick={() => setWeekStart((w) => addDays(w, 7))} aria-label="Next week">
            <ChevronRight className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(new Date()))}>
            Today
          </Button>
        </div>
      </div>

      {/* Action bar */}
      <div className="bg-white border-b border-border px-4 py-2.5 flex flex-wrap items-center gap-2">
        <ShoppingListButton startISO={startISO} endISO={endISO} disabled={entries.length === 0} />
        {googleSupported && (
          <ExportToCalendarButton entries={entries} disabled={entries.length === 0} />
        )}
      </div>

      {/* Week grid */}
      <div className="flex-1 overflow-y-auto p-3">
        <div className="grid grid-cols-1 md:grid-cols-7 gap-3">
          {days.map((day, i) => {
            const iso = toISO(day)
            const dayEntries = entriesByDate[iso] ?? []
            const isToday = iso === todayISO
            return (
              <div
                key={iso}
                className={`bg-white rounded-lg border ${isToday ? 'border-primary' : 'border-border'} flex flex-col min-h-[120px]`}
              >
                <div className="px-3 py-2 border-b border-border/60 flex items-center justify-between">
                  <span className={`text-xs font-semibold uppercase tracking-wider ${isToday ? 'text-primary' : 'text-muted-foreground'}`}>
                    {DAY_LABELS[i]} {day.getDate()}
                  </span>
                </div>
                <div className="flex-1 p-2 space-y-1.5">
                  {dayEntries.map((entry) => (
                    <div
                      key={entry.id}
                      className="group flex items-center gap-1.5 px-2 py-1.5 rounded bg-primary/5 border border-primary/10"
                    >
                      <span className="flex-1 text-sm text-foreground leading-snug">{entry.recipe_title}</span>
                      <button
                        onClick={() => deleteMutation.mutate(entry.id)}
                        className="text-muted-foreground hover:text-destructive flex-shrink-0"
                        aria-label={`Remove ${entry.recipe_title}`}
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                  <button
                    onClick={() => setPickerDate(iso)}
                    className="w-full flex items-center justify-center gap-1 px-2 py-1.5 rounded text-xs font-medium text-muted-foreground hover:text-primary hover:bg-muted/50 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {pickerDate && (
        <RecipePickerDialog
          date={pickerDate}
          onClose={() => setPickerDate(null)}
          onPick={(recipeUuid) => {
            addMutation.mutate({ date: pickerDate, recipeUuid })
            setPickerDate(null)
          }}
        />
      )}
    </div>
  )
}

function ShoppingListButton({
  startISO,
  endISO,
  disabled,
}: {
  startISO: string
  endISO: string
  disabled: boolean
}) {
  const mutation = useMutation({
    mutationFn: () => api.buildShoppingList(startISO, endISO),
    onSuccess: (data) => {
      const listUrl = `${window.location.origin}/api/meal-plan/shopping-list/${data.token}.html`
      const bringUrl = `https://api.getbring.com/rest/bringrecipes/deeplink?url=${encodeURIComponent(listUrl)}&source=web`
      window.location.href = bringUrl
    },
  })

  return (
    <Button size="sm" onClick={() => mutation.mutate()} disabled={disabled || mutation.isPending}>
      <ShoppingCart className="w-4 h-4 mr-1.5" />
      {mutation.isPending ? 'Building…' : 'Shopping list → Bring'}
    </Button>
  )
}

function ExportToCalendarButton({
  entries,
  disabled,
}: {
  entries: MealPlanEntry[]
  disabled: boolean
}) {
  const { requestAccess, listCalendars, insertEvent } = useGoogleCalendar()
  const [token, setToken] = useState<string | null>(null)
  const [calendars, setCalendars] = useState<GoogleCalendar[] | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleClick() {
    setStatus(null)
    setBusy(true)
    try {
      const t = await requestAccess()
      setToken(t)
      const cals = await listCalendars(t)
      setCalendars(cals)
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Authorization failed')
    } finally {
      setBusy(false)
    }
  }

  async function handlePick(calendarId: string) {
    if (!token) return
    setBusy(true)
    setStatus(null)
    let created = 0
    try {
      for (const entry of entries) {
        await insertEvent(token, calendarId, entry.recipe_title, entry.date)
        created++
      }
      setStatus(`Created ${created} event${created === 1 ? '' : 's'}.`)
    } catch (e) {
      setStatus(
        `${e instanceof Error ? e.message : 'Export failed'} (created ${created} of ${entries.length}).`,
      )
    } finally {
      setBusy(false)
      setCalendars(null)
    }
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={handleClick} disabled={disabled || busy}>
        <CalendarPlus className="w-4 h-4 mr-1.5" />
        {busy && !calendars ? 'Connecting…' : 'Export to calendar'}
      </Button>
      {status && <span className="text-xs text-muted-foreground">{status}</span>}

      <Dialog open={!!calendars} onOpenChange={(o) => !o && setCalendars(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Choose a calendar</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground mb-3">
            Creates one all-day event per meal this week. Re-exporting adds duplicates.
          </p>
          <div className="space-y-1 max-h-[50dvh] overflow-y-auto">
            {(calendars ?? []).map((cal) => (
              <button
                key={cal.id}
                onClick={() => handlePick(cal.id)}
                disabled={busy}
                className="w-full text-left px-3 py-2.5 rounded-md hover:bg-accent transition-colors text-sm flex items-center justify-between"
              >
                <span>{cal.summary}</span>
                {cal.primary && <span className="text-xs text-muted-foreground">primary</span>}
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function RecipePickerDialog({
  date,
  onClose,
  onPick,
}: {
  date: string
  onClose: () => void
  onPick: (recipeUuid: string) => void
}) {
  const [search, setSearch] = useState('')
  const { data: recipes = [], isLoading } = useQuery({
    queryKey: ['recipes'],
    queryFn: api.listRecipes,
  })

  const filtered = recipes.filter((r) => r.title.toLowerCase().includes(search.toLowerCase()))
  const dayLabel = new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add recipe to {dayLabel}</DialogTitle>
        </DialogHeader>
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            autoFocus
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search recipes…"
            className="w-full pl-9 pr-3 py-2 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <div className="space-y-1 max-h-[50dvh] overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-muted-foreground py-4 text-center">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No recipes found.</p>
          ) : (
            filtered.map((r) => (
              <button
                key={r.uuid}
                onClick={() => onPick(r.uuid)}
                className="w-full text-left px-3 py-2.5 rounded-md hover:bg-accent transition-colors text-sm"
              >
                {r.title}
              </button>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
