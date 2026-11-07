import { useRef, useState } from 'react'
import type { Menu, MenuStep } from '@/lib/api'
import {
  courseColor,
  dayBeforeSteps,
  dayOfSteps,
  dayRange,
  durationLabel,
  findClashes,
  hhmm,
  sortedCourses,
  stepStart,
} from '@/lib/menuPlan'
import { cn } from '@/lib/utils'
import { useI18n } from '@/i18n'

const LABEL_W = 170
const SNAP = 5

/**
 * Gantt view of the cooking day: one row per step, grouped by course, with the
 * serving times as dashed lines. Drag a bar to move a step (5-minute steps; it
 * can't end after its course is served); click it to select it. The Oven and
 * You lanes mark clashes in red.
 */
export function PlanTimeline({
  menu,
  selectedId,
  onSelect,
  onMove,
}: {
  menu: Menu
  selectedId: number | null
  onSelect: (stepId: number) => void
  /** New `lead` for a same-day step. */
  onMove: (stepId: number, lead: number) => void
}) {
  const { t } = useI18n()
  const [lo, hi] = dayRange(menu)
  const span = hi - lo
  const pct = (m: number) => `${((m - lo) / span) * 100}%`
  const width = (m: number) => `${(m / span) * 100}%`
  const clashes = findClashes(menu)
  const clashing = new Set(clashes.flatMap((c) => [c.a.id, c.b.id]))
  const courses = sortedCourses(menu)
  const day = dayOfSteps(menu)
  const before = dayBeforeSteps(menu)

  const drag = useRef<{ step: MenuStep; x0: number; w: number; start0: number; moved: boolean } | null>(null)
  const [preview, setPreview] = useState<{ id: number; start: number } | null>(null)

  const startOf = (s: MenuStep) => (preview?.id === s.id ? preview.start : stepStart(menu, s))
  const serveOf = (s: MenuStep) => menu.courses.find((c) => c.id === s.course_id)?.serve ?? 0

  function onPointerDown(e: React.PointerEvent<HTMLButtonElement>, step: MenuStep) {
    const track = e.currentTarget.parentElement
    if (!track) return
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = {
      step,
      x0: e.clientX,
      w: track.getBoundingClientRect().width,
      start0: stepStart(menu, step),
      moved: false,
    }
  }

  function onPointerMove(e: React.PointerEvent<HTMLButtonElement>) {
    const d = drag.current
    if (!d) return
    if (Math.abs(e.clientX - d.x0) > 3) d.moved = true
    if (!d.moved) return
    const delta = Math.round((((e.clientX - d.x0) / d.w) * span) / SNAP) * SNAP
    const latest = serveOf(d.step) - d.step.duration // must be ready by serving
    setPreview({ id: d.step.id, start: Math.min(d.start0 + delta, latest) })
  }

  function onPointerUp() {
    const d = drag.current
    drag.current = null
    if (!d) return
    if (d.moved && preview && preview.id === d.step.id) {
      const lead = serveOf(d.step) - d.step.duration - preview.start
      if (lead !== d.step.lead) onMove(d.step.id, lead)
    }
    setPreview(null)
    onSelect(d.step.id)
  }

  const hours: number[] = []
  for (let m = lo; m <= hi; m += 60) hours.push(m)
  const halves: number[] = []
  for (let m = lo; m <= hi; m += 30) halves.push(m)

  return (
    <div>
      {before.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3 text-xs">
          <span className="text-muted-foreground mr-1">{t('menus.dayBefore')}:</span>
          {before.map((s) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={cn(
                'rounded-md border px-2 py-1 bg-white',
                selectedId === s.id ? 'border-primary bg-primary/5' : 'border-dashed border-border',
              )}
            >
              <span className="font-semibold tabular-nums">{hhmm(stepStart(menu, s))}</span> {s.name} ·{' '}
              {durationLabel(s.duration)}
            </button>
          ))}
        </div>
      )}

      <div className="overflow-x-auto">
        <div className="relative min-w-[640px] select-none">
          {/* Axis */}
          <div className="flex h-6">
            <div style={{ width: LABEL_W }} className="flex-shrink-0" />
            <div className="relative flex-1">
              {hours.map((m) => (
                <span key={m} className="absolute top-0.5 -translate-x-1/2 text-[11px] text-muted-foreground tabular-nums" style={{ left: pct(m) }}>
                  {hhmm(m)}
                </span>
              ))}
            </div>
          </div>

          {/* Grid lines + serving times */}
          <div className="absolute top-6 bottom-0 right-0 pointer-events-none" style={{ left: LABEL_W }}>
            {halves.map((m) => (
              <div key={m} className={cn('absolute top-0 bottom-0 border-l', m % 60 ? 'border-slate-100' : 'border-slate-200')} style={{ left: pct(m) }} />
            ))}
            {courses.map((c, i) => {
              const color = courseColor(menu, c.id)
              const last = i === courses.length - 1
              return (
                <div key={c.id} className="absolute top-0 bottom-0 border-l-2 border-dashed" style={{ left: pct(c.serve), borderColor: color }}>
                  <span
                    className="absolute z-10 whitespace-nowrap text-[11px] font-semibold bg-white/90 px-1 rounded"
                    style={{ top: 4 + i * 15, color, ...(last ? { right: 4 } : { left: 4 }) }}
                  >
                    {hhmm(c.serve)} {c.name}
                  </span>
                </div>
              )
            })}
          </div>

          {courses.map((c) => {
            const color = courseColor(menu, c.id)
            const rows = day.filter((s) => s.course_id === c.id)
            return (
              <div key={c.id}>
                <div className="flex items-center h-8 pt-2">
                  <div style={{ width: LABEL_W }} className="flex-shrink-0 flex items-center gap-1.5 text-[13px] font-bold truncate pr-2">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
                    <span className="truncate">{c.name}</span>
                  </div>
                </div>
                {rows.map((s) => {
                  const start = startOf(s)
                  return (
                    <div key={s.id} className="flex items-center h-7">
                      <div style={{ width: LABEL_W }} className="flex-shrink-0 text-xs truncate pr-2" title={s.name}>
                        {s.name}
                      </div>
                      <div className="relative flex-1 h-6">
                        <button
                          type="button"
                          onPointerDown={(e) => onPointerDown(e, s)}
                          onPointerMove={onPointerMove}
                          onPointerUp={onPointerUp}
                          onClick={() => onSelect(s.id)}
                          onPointerCancel={() => {
                            drag.current = null
                            setPreview(null)
                          }}
                          title={`${s.name} · ${durationLabel(s.duration)}`}
                          className={cn(
                            'absolute top-[3px] h-[18px] rounded-[5px] px-1.5 text-[10.5px] font-semibold whitespace-nowrap overflow-hidden text-left cursor-grab active:cursor-grabbing touch-none',
                            s.hands ? 'text-white' : 'text-foreground',
                            selectedId === s.id && 'outline outline-2 outline-offset-1 outline-foreground',
                            clashing.has(s.id) && 'ring-2 ring-destructive',
                          )}
                          style={{
                            left: pct(start),
                            width: width(s.duration),
                            minWidth: 6,
                            background: s.hands
                              ? color
                              : `repeating-linear-gradient(135deg, ${color} 0 6px, color-mix(in srgb, ${color} 45%, white) 6px 12px)`,
                            textShadow: s.hands ? undefined : '0 0 3px white',
                          }}
                        >
                          {hhmm(start)}–{hhmm(start + s.duration)}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            )
          })}

          {/* Lanes */}
          <Lane label={`🔥 ${t('menus.eq.oven')}`} className="mt-3">
            {day
              .filter((s) => s.equipment === 'oven')
              .map((s) => (
                <span
                  key={s.id}
                  className="absolute top-[5px] h-[14px] rounded px-1 text-[10px] overflow-hidden whitespace-nowrap"
                  style={{ left: pct(startOf(s)), width: width(s.duration), background: `color-mix(in srgb, ${courseColor(menu, s.course_id)} 30%, white)` }}
                >
                  {s.temp}°
                </span>
              ))}
            {clashes
              .filter((c) => c.kind === 'oven')
              .map((c, i) => (
                <span key={i} className="absolute top-0.5 h-5 rounded bg-destructive/25 border border-destructive" style={{ left: pct(c.start), width: width(c.end - c.start) }} />
              ))}
          </Lane>
          <Lane label={`🙋 ${t('menus.you')}`} className="mt-1">
            {day
              .filter((s) => s.hands)
              .map((s) => (
                <span
                  key={s.id}
                  className="absolute top-[5px] h-[14px] rounded"
                  style={{ left: pct(startOf(s)), width: width(s.duration), background: `color-mix(in srgb, ${courseColor(menu, s.course_id)} 30%, white)` }}
                />
              ))}
            {clashes
              .filter((c) => c.kind === 'hands')
              .map((c, i) => (
                <span key={i} className="absolute top-0.5 h-5 rounded bg-destructive/25 border border-destructive" style={{ left: pct(c.start), width: width(c.end - c.start) }} />
              ))}
          </Lane>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <i className="inline-block w-5 h-2.5 rounded-sm bg-primary" /> {t('menus.needsYou')}
        </span>
        <span className="flex items-center gap-1.5">
          <i
            className="inline-block w-5 h-2.5 rounded-sm"
            style={{ background: 'repeating-linear-gradient(135deg, #bf560b 0 5px, #e6b48f 5px 10px)' }}
          />{' '}
          {t('menus.runsByItself')}
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block w-5 h-2.5 rounded-sm bg-destructive/25 border border-destructive" /> {t('menus.clash')}
        </span>
        <span>{t('menus.dragHint')}</span>
      </div>
    </div>
  )
}

function Lane({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn('flex items-center h-6', className)}>
      <div style={{ width: LABEL_W }} className="flex-shrink-0 text-xs font-semibold">
        {label}
      </div>
      <div className="relative flex-1 h-6 rounded bg-slate-50">{children}</div>
    </div>
  )
}
