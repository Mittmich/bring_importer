import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { tagColor, tagChipStyle } from '@/lib/tagColors'

interface TagChipProps extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'color'> {
  name: string
  /** Explicit colour; when null/undefined a stable default is derived from the name. */
  color?: string | null
  /** Renders a remove (×) button and calls this when clicked. */
  onRemove?: () => void
  /** Dims the chip to indicate an unselected/toggleable state. */
  muted?: boolean
}

/**
 * A coloured tag pill used everywhere tags appear (list rows, detail, editor,
 * management page). Colour resolution lives in `tagColors` so every chip stays
 * consistent.
 */
export function TagChip({ name, color, onRemove, muted, className, ...props }: TagChipProps) {
  const resolved = tagColor(name, color)
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        muted && 'opacity-55',
        className,
      )}
      style={tagChipStyle(resolved)}
      {...props}
    >
      {name}
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onRemove()
          }}
          aria-label={`Remove tag ${name}`}
          className="-mr-0.5 rounded-full hover:bg-black/10"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  )
}
