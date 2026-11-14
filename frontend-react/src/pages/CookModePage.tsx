import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Check, Moon } from 'lucide-react'
import { useMenu } from '@/hooks/useMenu'
import { KeepAwakeButton } from '@/components/KeepAwakeButton'
import {
  courseColor,
  dayBeforeSteps,
  dayOfSteps,
  dayRange,
  durationLabel,
  formatMenuDate,
  hhmm,
  nowMinutes,
  overnightEnd,
  sortedCourses,
  stepEnd,
  stepStart,
} from '@/lib/menuPlan'
import { useI18n } from '@/i18n'

function todayISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * The plan on the night: what needs you now, what's running by itself, what's
 * next — driven by the clock. Ticking a step off saves it to the plan.
 */
export function CookModePage() {
  const { id } = useParams()
  const m = useMenu(Number(id))
  const { t, lang } = useI18n()
  const [now, setNow] = useState(nowMinutes)
  useEffect(() => {
    const h = setInterval(() => setNow(nowMinutes()), 15_000)
    return () => clearInterval(h)
  }, [])

  const menu = m.menu
  if (!menu) return <p className="p-4 text-sm text-muted-foreground">{m.isLoading ? t('common.loading') : t('menus.notFound')}</p>

  const steps = dayOfSteps(menu).filter((s) => !s.done)
  const active = steps.filter((s) => stepStart(menu, s) <= now && now < stepEnd(menu, s))
  const doing = active.filter((s) => s.hands)
  // Overnight steps from the day before still running this morning count too.
  const overnight = dayBeforeSteps(menu)
    .filter((s) => !s.done && (overnightEnd(s) ?? 0) > now)
    .map((s) => ({ step: s, end: overnightEnd(s) ?? 0 }))
  const background = [
    ...overnight,
    ...active.filter((s) => !s.hands).map((s) => ({ step: s, end: stepEnd(menu, s) })),
  ]
  const overdue = steps.filter((s) => stepEnd(menu, s) <= now && s.hands)
  const next = steps.filter((s) => stepStart(menu, s) > now).slice(0, 4)
  const nextServe = sortedCourses(menu)
    .filter((c) => c.serve >= now)
    .sort((a, b) => a.serve - b.serve)[0]
  const [lo, hi] = dayRange(menu)
  const span = hi - lo
  const courses = sortedCourses(menu)
  const otherDay = menu.date && menu.date !== todayISO()

  const done = (stepId: number) => m.updateStep(stepId, { done: true })

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="bg-gradient-to-br from-[#ffe2ba] via-[#f8b26a] to-[#f08a24] px-4 pt-3 pb-4">
        <div className="flex items-center gap-2 mb-2">
          <Link to={`/menus/${menu.id}`} className="text-foreground/70 hover:text-foreground" aria-label={t('common.back')}>
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <span className="flex-1 text-xs font-bold uppercase tracking-wider text-foreground/70 truncate">
            {menu.title} · {t('menus.cookMode')}
          </span>
          <KeepAwakeButton className="bg-white/70" />
        </div>
        <div className="text-5xl font-extrabold tabular-nums leading-none">{hhmm(now)}</div>
        <div className="text-sm font-semibold mt-1">
          {nextServe
            ? t('menus.serveIn', { course: nextServe.name, time: durationLabel(Math.max(0, Math.round(nextServe.serve - now))) })
            : t('menus.allServed')}
        </div>
        {otherDay && (
          <div className="text-xs mt-1 text-foreground/70">
            {t('menus.plannedFor', { date: formatMenuDate(menu.date, lang) })}
          </div>
        )}
        <div className="relative h-[30px] mt-3 bg-white/55 rounded-md overflow-hidden" aria-hidden>
          {courses.map((c, i) =>
            dayOfSteps(menu)
              .filter((s) => s.course_id === c.id)
              .map((s) => (
                <div
                  key={s.id}
                  className="absolute h-1.5 rounded-full"
                  style={{
                    left: `${((stepStart(menu, s) - lo) / span) * 100}%`,
                    width: `${(s.duration / span) * 100}%`,
                    top: 4 + (i % 3) * 8,
                    background: courseColor(menu, c.id),
                    opacity: s.done ? 0.25 : s.hands ? 1 : 0.5,
                  }}
                />
              )),
          )}
          {now >= lo && now <= hi && (
            <div className="absolute top-0 bottom-0 w-0.5 bg-foreground" style={{ left: `${((now - lo) / span) * 100}%` }} />
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 max-w-xl w-full mx-auto">
        <Section title={t('menus.now')}>
          {doing.length === 0 && overdue.length === 0 ? (
            <p className="text-sm text-muted-foreground py-1">{t('menus.nothingNow')}</p>
          ) : (
            [...overdue, ...doing].map((s) => {
              const color = courseColor(menu, s.course_id)
              const course = menu.courses.find((c) => c.id === s.course_id)
              const late = stepEnd(menu, s) <= now
              const progress = Math.min(100, ((now - stepStart(menu, s)) / s.duration) * 100)
              return (
                <div
                  key={s.id}
                  className="rounded-xl p-3 mb-2 border"
                  style={{ background: `color-mix(in srgb, ${color} 12%, white)`, borderColor: `color-mix(in srgb, ${color} 40%, white)` }}
                >
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-muted-foreground">
                        {course?.name} · {t('menus.until', { time: hhmm(stepEnd(menu, s)) })}
                      </div>
                      <div className="font-bold text-base leading-snug">{s.name}</div>
                      <div className={`text-xs ${late ? 'text-destructive font-semibold' : 'text-muted-foreground'}`}>
                        {late ? t('menus.overdue') : t('menus.left', { time: durationLabel(Math.ceil(stepEnd(menu, s) - now)) })}
                      </div>
                    </div>
                    {menu.role !== 'viewer' && (
                      <button
                        onClick={() => done(s.id)}
                        className="flex-shrink-0 inline-flex items-center gap-1 rounded-full bg-white border border-border px-3 py-1.5 text-xs font-semibold"
                      >
                        <Check className="w-3.5 h-3.5" /> {t('menus.markDone')}
                      </button>
                    )}
                  </div>
                  <div className="h-1.5 rounded-full bg-foreground/10 mt-2 overflow-hidden">
                    <div className="h-full" style={{ width: `${progress}%`, background: color }} />
                  </div>
                </div>
              )
            })
          )}
        </Section>

        <Section title={t('menus.runningByItself')}>
          {background.length === 0 ? (
            <p className="text-sm text-muted-foreground py-1">{t('menus.nothingRunning')}</p>
          ) : (
            background.map(({ step: s, end }) => (
              <div key={s.id} className="flex items-center justify-between gap-2 py-2 border-b border-border/60 text-sm">
                <span className="flex items-center gap-2 min-w-0">
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: courseColor(menu, s.course_id) }} />
                  <span className="truncate">{s.name}</span>
                  {s.day === -1 && <Moon className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />}
                </span>
                <span className="font-semibold tabular-nums">{durationLabel(Math.ceil(end - now))}</span>
              </div>
            ))
          )}
        </Section>

        <Section title={t('menus.upNext')}>
          {next.length === 0 ? (
            <p className="text-sm text-muted-foreground py-1">{t('menus.thatsAll')}</p>
          ) : (
            next.map((s) => (
              <div key={s.id} className="flex items-center gap-3 py-2 text-sm">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: courseColor(menu, s.course_id) }} />
                <span className="flex-1 min-w-0">
                  <span className="block truncate font-medium">{s.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {hhmm(stepStart(menu, s))} · {durationLabel(s.duration)}
                    {s.hands ? '' : ` · ${t('menus.runsByItself')}`}
                  </span>
                </span>
                <span className="font-bold text-primary tabular-nums whitespace-nowrap">
                  {t('menus.inTime', { time: durationLabel(Math.max(1, Math.round(stepStart(menu, s) - now))) })}
                </span>
              </div>
            ))
          )}
        </Section>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h2 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-2">{title}</h2>
      {children}
    </section>
  )
}
