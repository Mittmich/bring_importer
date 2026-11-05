import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * A small dropdown menu: a trigger button plus a popover of actions.
 * Closes on outside click, Escape, or after an item is chosen.
 */
export function Menu({
  trigger,
  label,
  align = 'end',
  className,
  children,
}: {
  trigger: React.ReactNode
  label: string
  align?: 'start' | 'end'
  className?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = React.useState(false)
  const ref = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!open) return
    const onPointer = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={ref} className={cn('relative', className)}>
      <button
        type="button"
        aria-label={label}
        title={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex items-center justify-center rounded-md border border-input bg-background h-9 px-2.5 text-sm transition-colors hover:bg-accent hover:text-accent-foreground',
          open && 'bg-accent',
        )}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          onClick={() => setOpen(false)}
          className={cn(
            'absolute z-40 mt-1.5 min-w-[13rem] rounded-lg border border-border bg-white py-1.5 shadow-xl',
            align === 'end' ? 'right-0' : 'left-0',
          )}
        >
          {children}
        </div>
      )}
    </div>
  )
}

export function MenuItem({
  icon,
  onSelect,
  disabled,
  destructive,
  children,
}: {
  icon?: React.ReactNode
  onSelect: () => void
  disabled?: boolean
  destructive?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        'w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors hover:bg-muted disabled:opacity-50 disabled:pointer-events-none [&>svg]:w-4 [&>svg]:h-4 [&>svg]:flex-shrink-0',
        destructive ? 'text-destructive' : 'text-foreground',
      )}
    >
      {icon}
      {children}
    </button>
  )
}

export function MenuSeparator() {
  return <div role="separator" className="my-1.5 border-t border-border" />
}
