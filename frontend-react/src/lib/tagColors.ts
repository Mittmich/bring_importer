import type { CSSProperties } from 'react'

/**
 * Tag colour palette — the single source of truth for tag colours, kept next
 * to the theme so it stays harmonious with it.
 *
 * The app's primary is indigo (`hsl(239 84% 67%)` ≈ `#6366f1`). These ten
 * swatches sit at a consistent saturation/lightness around that anchor so any
 * mix of tags reads as one family on the white background.
 *
 * A tag's colour can be set explicitly (persisted by the backend). When it
 * isn't, `tagColor` derives a *stable* default from the tag name, so an
 * uncoloured tag always looks the same everywhere without any server state.
 */
export const TAG_PALETTE = [
  '#6366f1', // indigo (primary)
  '#8b5cf6', // violet
  '#3b82f6', // blue
  '#06b6d4', // cyan
  '#14b8a6', // teal
  '#10b981', // emerald
  '#f59e0b', // amber
  '#f97316', // orange
  '#f43f5e', // rose
  '#ec4899', // pink
] as const

/** Stable, non-cryptographic string hash (djb2). */
function hashString(s: string): number {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i)
  return h >>> 0
}

/** Deterministic default swatch for a tag name. */
export function defaultTagColor(name: string): string {
  return TAG_PALETTE[hashString(name.trim().toLowerCase()) % TAG_PALETTE.length]
}

/** Resolve the colour to render: explicit if set, else the stable default. */
export function tagColor(name: string, explicit?: string | null): string {
  return explicit || defaultTagColor(name)
}

/**
 * Inline styles for a soft, legible chip: a faint tint of the colour behind
 * colour-toned text with a subtle border. Reads well on white across the
 * whole palette (unlike solid fills, which fight light swatches).
 */
export function tagChipStyle(color: string): CSSProperties {
  return {
    backgroundColor: `${color}1f`, // ~12% alpha
    color,
    borderColor: `${color}59`, // ~35% alpha
  }
}
