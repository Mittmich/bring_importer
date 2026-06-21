import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  ShoppingCart,
  CalendarPlus,
  RefreshCw,
  Settings2,
  X,
  Search,
} from 'lucide-react'
import { api, type MealPlanEntry, type EntrySyncState } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

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

  // Pick up the OAuth callback redirect (?google=connected|error&reason=…), then clean the URL.
  const [connectError, setConnectError] = useState<string | null>(null)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const g = params.get('google')
    if (!g) return
    if (g === 'connected') queryClient.invalidateQueries({ queryKey: ['google-status'] })
    if (g === 'error') setConnectError(params.get('reason') || 'unknown')
    params.delete('google')
    params.delete('reason')
    const qs = params.toString()
    window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''))
  }, [queryClient])

  const { data: gStatus } = useQuery({
    queryKey: ['google-status'],
    queryFn: api.googleStatus,
  })
  const connected = gStatus?.connected ?? false

  const { data: entries = [] } = useQuery({
    queryKey: ['meal-plan', startISO, endISO],
    queryFn: () => api.getMealPlan(startISO, endISO),
  })

  // On load / week change (when connected), check which meals are still synced.
  const { data: syncStatus } = useQuery({
    queryKey: ['sync-status', startISO, endISO],
    queryFn: () => api.weekSyncStatus(startISO, endISO),
    enabled: connected,
  })
  const statuses = syncStatus?.statuses ?? {}

  const entriesByDate = useMemo(() => {
    const map: Record<string, MealPlanEntry[]> = {}
    for (const e of entries) (map[e.date] ??= []).push(e)
    return map
  }, [entries])

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['meal-plan'] })
    queryClient.invalidateQueries({ queryKey: ['sync-status'] })
  }

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
        <GoogleSyncControls
          startISO={startISO}
          endISO={endISO}
          status={gStatus}
          statuses={statuses}
          entryCount={entries.length}
          connectError={connectError}
        />
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
                      {connected && <SyncDot state={statuses[String(entry.id)]} />}
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

// Small per-meal sync indicator: amber when it needs a (re)sync, green when synced.
function SyncDot({ state }: { state?: EntrySyncState }) {
  const color =
    state === 'synced' ? 'bg-green-500' : state === 'missing' ? 'bg-amber-500' : 'bg-muted-foreground/40'
  const title =
    state === 'synced'
      ? 'Synced to calendar'
      : state === 'missing'
        ? 'Was deleted in Google — Sync now to recreate'
        : 'Not synced yet'
  return <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${color}`} title={title} />
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

function GoogleSyncControls({
  startISO,
  endISO,
  status,
  statuses,
  entryCount,
  connectError,
}: {
  startISO: string
  endISO: string
  status?: { configured: boolean; connected: boolean; calendar_id: string | null }
  statuses: Record<string, EntrySyncState>
  entryCount: number
  connectError: string | null
}) {
  const queryClient = useQueryClient()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [connecting, setConnecting] = useState(false)

  const syncMutation = useMutation({
    mutationFn: () => api.syncWeek(startISO, endISO),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sync-status'] }),
  })

  if (!status?.configured) return null

  async function connect() {
    setConnecting(true)
    try {
      const { url } = await api.googleConnectUrl()
      window.location.href = url
    } catch {
      setConnecting(false)
    }
  }

  if (!status.connected) {
    return (
      <>
        <Button variant="outline" size="sm" onClick={connect} disabled={connecting}>
          <CalendarPlus className="w-4 h-4 mr-1.5" />
          {connecting ? 'Connecting…' : 'Connect calendar'}
        </Button>
        {connectError && (
          <span className="text-xs text-destructive">
            Couldn&apos;t connect{connectError !== 'unknown' ? ` (${connectError})` : ''}. Try again.
          </span>
        )}
      </>
    )
  }

  const pending = Object.values(statuses).filter((s) => s !== 'synced').length

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => syncMutation.mutate()}
        disabled={entryCount === 0 || syncMutation.isPending}
      >
        <RefreshCw className={`w-4 h-4 mr-1.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
        {syncMutation.isPending ? 'Syncing…' : 'Sync now'}
      </Button>
      <span className="text-xs text-muted-foreground">
        {syncMutation.isSuccess && pending === 0
          ? 'All synced'
          : pending > 0
            ? `${pending} not synced`
            : 'All synced'}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setSettingsOpen(true)}
        aria-label="Calendar settings"
      >
        <Settings2 className="w-4 h-4" />
      </Button>

      <CalendarSettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        calendarId={status.calendar_id}
      />
    </>
  )
}

function CalendarSettingsDialog({
  open,
  onClose,
  calendarId,
}: {
  open: boolean
  onClose: () => void
  calendarId: string | null
}) {
  const queryClient = useQueryClient()
  const { data: calendars = [], isLoading } = useQuery({
    queryKey: ['google-calendars'],
    queryFn: api.googleCalendars,
    enabled: open,
  })

  const selectMutation = useMutation({
    mutationFn: (id: string) => api.setGoogleCalendar(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['google-status'] }),
  })

  const disconnectMutation = useMutation({
    mutationFn: () => api.googleDisconnect(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['google-status'] })
      queryClient.invalidateQueries({ queryKey: ['sync-status'] })
      onClose()
    },
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Calendar settings</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground mb-2">Sync target calendar</p>
        <div className="space-y-1 max-h-[40dvh] overflow-y-auto mb-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground py-2">Loading…</p>
          ) : (
            calendars.map((cal) => {
              const active = cal.id === calendarId
              return (
                <button
                  key={cal.id}
                  onClick={() => selectMutation.mutate(cal.id)}
                  disabled={selectMutation.isPending}
                  className={`w-full text-left px-3 py-2.5 rounded-md text-sm flex items-center justify-between transition-colors ${active ? 'bg-primary/10 text-primary' : 'hover:bg-accent'}`}
                >
                  <span>{cal.summary}</span>
                  {active && <span className="text-xs">selected</span>}
                </button>
              )
            })
          )}
        </div>
        <Button
          variant="outline"
          className="w-full text-destructive"
          onClick={() => disconnectMutation.mutate()}
          disabled={disconnectMutation.isPending}
        >
          {disconnectMutation.isPending ? 'Disconnecting…' : 'Disconnect Google Calendar'}
        </Button>
      </DialogContent>
    </Dialog>
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
