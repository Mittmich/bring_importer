import type { Menu, MenuCourse, MenuStep } from '@/lib/api'

/** Course colours from the Zestry palette, by course order. */
export const COURSE_COLORS = ['#d98a1c', '#bf560b', '#6f9a45', '#e06b3f', '#93b56c', '#f08a24']

export function courseColor(menu: Menu, courseId: number): string {
  const i = sortedCourses(menu).findIndex((c) => c.id === courseId)
  return COURSE_COLORS[(i < 0 ? 0 : i) % COURSE_COLORS.length]
}

export function sortedCourses(menu: Menu): MenuCourse[] {
  return [...menu.courses].sort((a, b) => a.position - b.position || a.serve - b.serve || a.id - b.id)
}

/** "19:05" from minutes after midnight (wraps around midnight). */
export function hhmm(minutes: number): string {
  const m = (((Math.round(minutes) % 1440) + 1440) % 1440)
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

export function parseHhmm(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value)
  if (!match) return null
  const h = Number(match[1])
  const m = Number(match[2])
  return h < 24 && m < 60 ? h * 60 + m : null
}

/** "45 min", "1 h", "3 h 30 min". */
export function durationLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h} h ${m} min` : `${h} h`
}

export function serveOf(menu: Menu, step: MenuStep): number {
  return menu.courses.find((c) => c.id === step.course_id)?.serve ?? 0
}

export function stepStart(menu: Menu, step: MenuStep): number {
  if (step.day === -1) return step.at ?? 18 * 60
  return serveOf(menu, step) - step.lead - step.duration
}

export function stepEnd(menu: Menu, step: MenuStep): number {
  return stepStart(menu, step) + step.duration
}

/** Steps whose course still exists. */
export function liveSteps(menu: Menu): MenuStep[] {
  const ids = new Set(menu.courses.map((c) => c.id))
  return menu.steps.filter((s) => ids.has(s.course_id))
}

export function dayBeforeSteps(menu: Menu): MenuStep[] {
  return liveSteps(menu)
    .filter((s) => s.day === -1)
    .sort((a, b) => stepStart(menu, a) - stepStart(menu, b))
}

export function dayOfSteps(menu: Menu): MenuStep[] {
  return liveSteps(menu)
    .filter((s) => s.day !== -1)
    .sort((a, b) => stepStart(menu, a) - stepStart(menu, b) || a.position - b.position)
}

/**
 * An equipment clash on the cooking day. Several people may cook, so only shared
 * equipment counts: the oven needed at two temperatures at once.
 */
export interface Clash {
  kind: 'oven'
  a: MenuStep
  b: MenuStep
  start: number
  end: number
}

export function findClashes(menu: Menu): Clash[] {
  const steps = dayOfSteps(menu).filter((s) => s.equipment === 'oven')
  const out: Clash[] = []
  for (let i = 0; i < steps.length; i++) {
    for (let j = i + 1; j < steps.length; j++) {
      const a = steps[i]
      const b = steps[j]
      const start = Math.max(stepStart(menu, a), stepStart(menu, b))
      const end = Math.min(stepEnd(menu, a), stepEnd(menu, b))
      if (end > start && a.temp !== b.temp) out.push({ kind: 'oven', a, b, start, end })
    }
  }
  return out
}

export function clashesFor(clashes: Clash[], stepId: number): Clash[] {
  return clashes.filter((c) => c.a.id === stepId || c.b.id === stepId)
}

/** Steps that run by themselves for longer than this don't widen the timeline. */
export const LONG_PASSIVE = 180

export function isLongPassive(step: MenuStep): boolean {
  return !step.hands && step.duration > LONG_PASSIVE
}

/**
 * The cooking day's visible window: whole hours around the active steps and the
 * serving times. Long passive steps (resting, marinating overnight) don't pull
 * it back to the early morning; they're drawn cut off at the left edge instead.
 */
export function dayRange(menu: Menu): [number, number] {
  const steps = dayOfSteps(menu)
  const anchors = steps.filter((s) => !isLongPassive(s)).map((s) => stepStart(menu, s))
  const serves = menu.courses.map((c) => c.serve)
  const lo = Math.floor(Math.min(...anchors, ...serves, 17 * 60) / 60) * 60
  const ends = [...steps.map((s) => stepEnd(menu, s)), ...serves.map((m) => m + 15)]
  const hi = Math.max(...ends, lo + 120)
  return [lo, Math.ceil(hi / 30) * 30]
}

/** When a day-before step that runs overnight ends on the cooking day, else null. */
export function overnightEnd(step: MenuStep): number | null {
  if (step.day !== -1) return null
  const end = (step.at ?? 18 * 60) + step.duration - 1440
  return end > 0 ? end : null
}

/** A bar on the cooking-day timeline: steps of the day plus overnight steps still running. */
export interface TimelineBar {
  step: MenuStep
  start: number
  end: number
  /** Starts before the window (or the day before): drawn cut off at the left edge. */
  clipped: boolean
  /** Started the day before. */
  overnight: boolean
}

export function timelineBars(menu: Menu): TimelineBar[] {
  const [lo] = dayRange(menu)
  const bars: TimelineBar[] = []
  for (const step of dayBeforeSteps(menu)) {
    const end = overnightEnd(step)
    if (end !== null && end > lo) bars.push({ step, start: lo, end, clipped: true, overnight: true })
  }
  for (const step of dayOfSteps(menu)) {
    const start = stepStart(menu, step)
    const end = start + step.duration
    if (end <= lo) continue
    bars.push({ step, start: Math.max(start, lo), end, clipped: start < lo, overnight: false })
  }
  return bars
}

export interface PlanEvent {
  time: number
  step?: MenuStep
  course?: MenuCourse
}

/** The cooking day in time order, serving times placed between steps (first on ties). */
export function dayEvents(menu: Menu): PlanEvent[] {
  const events: PlanEvent[] = [
    ...dayOfSteps(menu).map((step) => ({ time: stepStart(menu, step), step })),
    ...menu.courses.map((course) => ({ time: course.serve, course })),
  ]
  return events.sort((x, y) => x.time - y.time || (x.course ? 0 : 1) - (y.course ? 0 : 1))
}

export interface WorkloadBucket {
  start: number
  /** Hands-on minutes in this bucket per course id. */
  byCourse: Record<number, number>
  total: number
}

/** Hands-on minutes per `size`-minute bucket across the cooking day. */
export function workload(menu: Menu, size = 30): WorkloadBucket[] {
  const [lo, hi] = dayRange(menu)
  const steps = dayOfSteps(menu).filter((s) => s.hands)
  const out: WorkloadBucket[] = []
  for (let start = lo; start < hi; start += size) {
    const byCourse: Record<number, number> = {}
    let total = 0
    for (const s of steps) {
      const overlap = Math.min(stepEnd(menu, s), start + size) - Math.max(stepStart(menu, s), start)
      if (overlap > 0) {
        byCourse[s.course_id] = (byCourse[s.course_id] ?? 0) + overlap
        total += overlap
      }
    }
    out.push({ start, byCourse, total })
  }
  return out
}

export interface PlanStats {
  start: number | null
  handsOn: number
  oven: number
  dayBefore: number
}

export function planStats(menu: Menu): PlanStats {
  const day = dayOfSteps(menu)
  const live = liveSteps(menu)
  return {
    start: day.length ? Math.min(...day.map((s) => stepStart(menu, s))) : null,
    handsOn: live.filter((s) => s.hands).reduce((sum, s) => sum + s.duration, 0),
    oven: day.filter((s) => s.equipment === 'oven').reduce((sum, s) => sum + s.duration, 0),
    dayBefore: dayBeforeSteps(menu).length,
  }
}

/** Minutes after midnight, now. */
export function nowMinutes(d = new Date()): number {
  return d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60
}

/** A menu's ISO date in the UI language ("Saturday, 14 November 2026" by default). */
export function formatMenuDate(iso: string | null, lang: string, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return ''
  return new Date(`${iso}T00:00:00`).toLocaleDateString(
    lang,
    opts ?? { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' },
  )
}
