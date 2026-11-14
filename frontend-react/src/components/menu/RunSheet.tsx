import { useDraft } from '@/hooks/useDraft'
import { AlertTriangle, UtensilsCrossed } from 'lucide-react'
import type { Menu, MenuStep, MenuStepPatch } from '@/lib/api'
import {
  courseColor,
  dayBeforeSteps,
  dayEvents,
  findClashes,
  hhmm,
  stepStart,
} from '@/lib/menuPlan'
import { cn } from '@/lib/utils'
import { useI18n, type MessageKey } from '@/i18n'

/**
 * The plan as a checklist in time order, with serving times placed between the
 * steps. Durations are editable inline; tapping a step opens the full editor.
 */
export function RunSheet({
  menu,
  onChange,
  onOpen,
  readOnly = false,
}: {
  menu: Menu
  onChange: (stepId: number, patch: MenuStepPatch) => void
  onOpen: (stepId: number) => void
  /** Viewer of a shared menu: no ticking, no duration edits. */
  readOnly?: boolean
}) {
  const { t } = useI18n()
  const clashing = new Set(findClashes(menu).flatMap((c) => [c.a.id, c.b.id]))
  const before = dayBeforeSteps(menu)
  const events = dayEvents(menu)
  const firstServe = Math.min(...menu.courses.map((c) => c.serve))

  const phaseOf = (time: number): MessageKey =>
    time < firstServe - 120 ? 'menus.phase.earlier' : time < firstServe ? 'menus.phase.final' : 'menus.phase.dinner'

  let lastPhase: MessageKey | null = null
  const rows: React.ReactNode[] = []
  for (const e of events) {
    const phase = phaseOf(e.time)
    if (phase !== lastPhase) {
      rows.push(<Heading key={`h-${phase}`}>{t(phase)}</Heading>)
      lastPhase = phase
    }
    if (e.course) {
      const color = courseColor(menu, e.course.id)
      rows.push(
        <div
          key={`c-${e.course.id}`}
          className="flex items-center gap-2 my-1.5 px-3 py-2 rounded-lg text-sm font-bold"
          style={{ background: `color-mix(in srgb, ${color} 14%, white)` }}
        >
          <span className="tabular-nums">{hhmm(e.course.serve)}</span>
          <UtensilsCrossed className="w-3.5 h-3.5 flex-shrink-0" style={{ color }} />
          <span className="truncate">
            {t('menus.serveCourse', { course: e.course.name })}: {e.course.recipe_title}
          </span>
        </div>,
      )
    } else if (e.step) {
      rows.push(
        <Row key={e.step.id} menu={menu} step={e.step} clash={clashing.has(e.step.id)} onChange={onChange} onOpen={onOpen} readOnly={readOnly} />,
      )
    }
  }

  return (
    <div>
      {before.length > 0 && (
        <>
          <Heading>{t('menus.dayBefore')}</Heading>
          {before.map((s) => (
            <Row key={s.id} menu={menu} step={s} clash={false} onChange={onChange} onOpen={onOpen} readOnly={readOnly} />
          ))}
        </>
      )}
      {rows}
    </div>
  )
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground border-b border-border pb-1 mt-4 mb-1 first:mt-0">
      {children}
    </div>
  )
}

function Row({
  menu,
  step,
  clash,
  onChange,
  onOpen,
  readOnly,
}: {
  menu: Menu
  step: MenuStep
  clash: boolean
  onChange: (stepId: number, patch: MenuStepPatch) => void
  onOpen: (stepId: number) => void
  readOnly: boolean
}) {
  const { t } = useI18n()
  const course = menu.courses.find((c) => c.id === step.course_id)
  const color = courseColor(menu, step.course_id)
  const [dur, setDur] = useDraft(String(step.duration))
  const commitDur = () => {
    const n = Math.round(Number(dur))
    if (!Number.isFinite(n) || n < 1) return setDur(String(step.duration))
    const v = Math.min(1440, n)
    if (v !== step.duration) onChange(step.id, { duration: v })
  }
  const eq =
    step.equipment === 'oven'
      ? `${t('menus.eq.oven')} ${step.temp ?? 180}°`
      : step.equipment
        ? t(`menus.eq.${step.equipment}` as MessageKey)
        : ''

  return (
    <div className="grid grid-cols-[20px_44px_1fr_auto] gap-2 items-center px-1 py-1.5 rounded-lg hover:bg-muted/50">
      <input
        type="checkbox"
        className="w-4 h-4 accent-[hsl(var(--primary))]"
        checked={step.done}
        disabled={readOnly}
        onChange={(e) => onChange(step.id, { done: e.target.checked })}
        aria-label={step.name}
      />
      <span
        className={cn(
          'text-sm font-bold tabular-nums',
          clash && 'text-destructive',
          step.done && 'line-through text-muted-foreground',
        )}
      >
        {hhmm(stepStart(menu, step))}
      </span>
      <button type="button" onClick={() => onOpen(step.id)} className="min-w-0 text-left">
        <span className={cn('flex items-center gap-1.5 text-sm font-semibold', step.done && 'line-through text-muted-foreground')}>
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
          <span className="truncate">{step.name}</span>
          {clash && <AlertTriangle className="w-3.5 h-3.5 text-destructive flex-shrink-0" />}
        </span>
        <span className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground mt-0.5">
          <span className="truncate max-w-[12rem]">{course?.recipe_title}</span>
          <span
            className={cn(
              'px-1.5 rounded-full text-[10.5px] font-semibold',
              step.hands ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground',
            )}
          >
            {step.hands ? t('menus.needsYou') : t('menus.runsByItself')}
          </span>
          {eq && <span className="px-1.5 rounded-full text-[10.5px] font-semibold bg-muted">{eq}</span>}
        </span>
      </button>
      <label className="flex items-center gap-1 text-xs text-muted-foreground">
        <input
          type="number"
          inputMode="numeric"
          min={1}
          max={1440}
          step={5}
          value={dur}
          disabled={readOnly}
          onChange={(e) => setDur(e.target.value)}
          onBlur={commitDur}
          onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
          className="w-14 h-8 rounded-md border border-input bg-background px-1.5 text-right text-sm text-foreground"
          aria-label={t('menus.durationMin')}
        />
        min
      </label>
    </div>
  )
}
