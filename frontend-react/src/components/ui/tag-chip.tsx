import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { tagChipStyle } from '@/lib/tagColors'
import { useI18n } from '@/i18n'

interface TagChipProps extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'color'> {
  name: string
  /** Renders a remove (×) button and calls this when clicked. */
  onRemove?: () => void
  /** Dims the chip to indicate an unselected/toggleable state. */
  muted?: boolean
}

/**
 * The tag pill used everywhere tags appear (list rows, detail, editor,
 * management page). All tags share one colour (`TAG_COLOR`).
 */
export function TagChip({ name, onRemove, muted, className, ...props }: TagChipProps) {
  const { t } = useI18n()
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        muted && 'opacity-55',
        className,
      )}
      style={tagChipStyle()}
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
          aria-label={t('tags.removeLabel', { name })}
          className="-mr-0.5 rounded-full hover:bg-black/10"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  )
}
