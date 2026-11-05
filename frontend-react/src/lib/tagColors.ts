import type { CSSProperties } from 'react'

/** Every tag uses the app's primary orange — tags aren't individually coloured. */
export const TAG_COLOR = '#bf560b'

/**
 * Inline styles for a soft, legible chip: a faint tint behind colour-toned
 * text with a subtle border.
 */
export function tagChipStyle(color: string = TAG_COLOR): CSSProperties {
  return {
    backgroundColor: `${color}1f`, // ~12% alpha
    color,
    borderColor: `${color}59`, // ~35% alpha
  }
}
