import { cn } from '@/lib/utils'

// Warm "food" gradients for recipes without a photo. Literal class strings so
// Tailwind's JIT picks them up.
const GRADIENTS = [
  'from-amber-200 via-orange-300 to-red-400',
  'from-yellow-200 via-amber-300 to-orange-400',
  'from-rose-200 via-pink-300 to-red-400',
  'from-lime-200 via-emerald-300 to-teal-400',
  'from-orange-200 via-rose-300 to-fuchsia-400',
  'from-sky-200 via-indigo-300 to-violet-400',
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
