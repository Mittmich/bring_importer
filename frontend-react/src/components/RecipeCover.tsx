import { cn } from '@/lib/utils'

// Citrus gradients from the Zestry palette for recipes without a photo:
// peach, apricot, honey, tangerine, blood orange and a lime-peel accent.
// Literal class strings so Tailwind's JIT picks them up.
const GRADIENTS = [
  'from-[#ffe2ba] via-[#f8b26a] to-[#f08a24]', // peach → zest orange
  'from-[#fff2e3] via-[#ffd29e] to-[#f5a04a]', // cream → apricot
  'from-[#fff0c7] via-[#f9cf72] to-[#e9a23b]', // honey
  'from-[#ffd3a8] via-[#f08a24] to-[#bf560b]', // tangerine → burnt orange
  'from-[#ffe0d1] via-[#f7a582] to-[#e06b3f]', // blood orange
  'from-[#f3f6e6] via-[#d3e3b4] to-[#93b56c]', // lime peel
]

/** A stable gradient for `seed` (the recipe uuid), so a recipe keeps its colours. */
function coverGradient(seed: string): string {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0
  return GRADIENTS[Math.abs(h) % GRADIENTS.length]
}

/**
 * A recipe's cover: the photo when there is one, otherwise a gradient.
 * `loading` (the recipe has an image whose bytes aren't here yet) shows a
 * neutral pulse instead, so a photo doesn't flash in over a gradient.
 * The caller sizes it (aspect ratio, rounding) via `className`.
 */
export function RecipeCover({
  seed,
  src,
  loading = false,
  alt = '',
  className,
  imgClassName,
}: {
  seed: string
  src?: string
  loading?: boolean
  alt?: string
  className?: string
  imgClassName?: string
}) {
  return (
    <div
      className={cn(
        'overflow-hidden',
        src || loading ? 'bg-muted' : cn('bg-gradient-to-br', coverGradient(seed)),
        loading && !src && 'animate-pulse',
        className,
      )}
    >
      {src && <img src={src} alt={alt} className={cn('w-full h-full object-cover', imgClassName)} />}
    </div>
  )
}
