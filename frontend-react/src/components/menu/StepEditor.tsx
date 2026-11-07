import { useDraft } from '@/hooks/useDraft'
import { AlertTriangle, Trash2 } from 'lucide-react'
import type { Equipment, Menu, MenuStep, MenuStepPatch } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  clashesFor,
  courseColor,
  findClashes,
  hhmm,
  parseHhmm,
  stepEnd,
  stepStart,
} from '@/lib/menuPlan'
import { useI18n } from '@/i18n'

const selectClass =
  'w-full h-9 rounded-md border border-input bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring'

/** A number field that commits on blur/Enter, so typing "45" isn't saved as "4" first. */
function NumberField({
  id,
  value,
  min,
  max,
  step = 5,
  onCommit,
}: {
  id: string
  value: number
  min: number
  max: number
  step?: number
  onCommit: (n: number) => void
}) {
  const [text, setText] = useDraft(String(value))
  const commit = () => {
    const n = Math.round(Number(text))
    if (!Number.isFinite(n) || text.trim() === '') return setText(String(value))
    const clamped = Math.max(min, Math.min(max, n))
    setText(String(clamped))
    if (clamped !== value) onCommit(clamped)
  }
  return (
    <Input
      id={id}
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      step={step}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
    />
  )
}

export function StepEditor({
  menu,
  step,
  onChange,
  onDelete,
}: {
  menu: Menu
  step: MenuStep
  onChange: (patch: MenuStepPatch) => void
  onDelete: () => void
}) {
  const { t } = useI18n()
  const [name, setName] = useDraft(step.name)
  const course = menu.courses.find((c) => c.id === step.course_id)
  const clashes = clashesFor(findClashes(menu), step.id)
  const color = courseColor(menu, step.course_id)
  const fid = (f: string) => `step-${step.id}-${f}`

  const commitName = () => {
    const v = name.trim()
    if (!v) return setName(step.name)
    if (v !== step.name) onChange({ name: v })
  }

  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center gap-2 text-xs font-semibold" style={{ color }}>
        <span className="w-2 h-2 rounded-full" style={{ background: color }} />
        <span className="truncate">
          {course?.name} · {course?.recipe_title}
        </span>
      </div>
      <div className="text-xl font-bold tabular-nums">
        {hhmm(stepStart(menu, step))} → {hhmm(stepEnd(menu, step))}
        {step.day === -1 && (
          <span className="ml-2 align-middle text-[11px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
            {t('menus.dayBefore')}
          </span>
        )}
      </div>

      <div className="space-y-1">
        <Label htmlFor={fid('name')}>{t('menus.step')}</Label>
        <Input
          id={fid('name')}
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
          onBlur={commitName}
          onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor={fid('dur')}>{t('menus.durationMin')}</Label>
          <NumberField id={fid('dur')} value={step.duration} min={1} max={1440} onCommit={(n) => onChange({ duration: n })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor={fid('day')}>{t('menus.when')}</Label>
          <select
            id={fid('day')}
            className={selectClass}
            value={step.day}
            onChange={(e) => onChange({ day: Number(e.target.value) as 0 | -1 })}
          >
            <option value={0}>{t('menus.onTheDay')}</option>
            <option value={-1}>{t('menus.dayBefore')}</option>
          </select>
        </div>
      </div>

      {step.day === 0 ? (
        <div className="space-y-1">
          <Label htmlFor={fid('lead')}>
            {t('menus.readyBefore', { course: course?.name ?? '', time: hhmm(course?.serve ?? 0) })}
          </Label>
          <NumberField id={fid('lead')} value={step.lead} min={0} max={1440} onCommit={(n) => onChange({ lead: n })} />
        </div>
      ) : (
        <div className="space-y-1">
          <Label htmlFor={fid('at')}>{t('menus.startDayBefore')}</Label>
          <Input
            id={fid('at')}
            type="time"
            step={300}
            value={hhmm(step.at ?? 18 * 60)}
            onChange={(e) => {
              const m = parseHhmm(e.target.value)
              if (m !== null) onChange({ at: m })
            }}
          />
        </div>
      )}

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          className="w-4 h-4 accent-[hsl(var(--primary))]"
          checked={step.hands}
          onChange={(e) => onChange({ hands: e.target.checked })}
        />
        {t('menus.needsYouLong')}
      </label>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor={fid('eq')}>{t('menus.equipment')}</Label>
          <select
            id={fid('eq')}
            className={selectClass}
            value={step.equipment}
            onChange={(e) => onChange({ equipment: e.target.value as Equipment })}
          >
            <option value="">{t('menus.eq.none')}</option>
            <option value="oven">{t('menus.eq.oven')}</option>
            <option value="stove">{t('menus.eq.stove')}</option>
            <option value="fridge">{t('menus.eq.fridge')}</option>
          </select>
        </div>
        {step.equipment === 'oven' && (
          <div className="space-y-1">
            <Label htmlFor={fid('temp')}>{t('menus.ovenTemp')}</Label>
            <NumberField
              id={fid('temp')}
              value={step.temp ?? 180}
              min={50}
              max={300}
              step={10}
              onCommit={(n) => onChange({ temp: n })}
            />
          </div>
        )}
      </div>

      {clashes.map((c, i) => {
        const other = c.a.id === step.id ? c.b : c.a
        return (
          <div key={i} className="flex gap-2 text-xs text-destructive bg-destructive/10 rounded-md px-2.5 py-2">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-px" />
            <span>
              {c.kind === 'oven'
                ? t('menus.clashOven', { other: other.name, a: step.temp ?? '', b: other.temp ?? '' })
                : t('menus.clashHands', { other: other.name })}{' '}
              ({hhmm(c.start)}–{hhmm(c.end)})
            </span>
          </div>
        )
      })}

      <Button variant="outline" size="sm" className="text-destructive" onClick={onDelete}>
        <Trash2 className="w-3.5 h-3.5 mr-1.5" />
        {t('menus.removeStep')}
      </Button>
    </div>
  )
}
