/** The Zestry logo: a citrus slice on an orange tile (same artwork as the app icon). */
export function BrandMark({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="#f08a24" />
      <g transform="translate(32 32) scale(.62) translate(-32 -32)">
        <circle cx="32" cy="32" r="24" fill="#f08a24" stroke="#fff" strokeWidth="4" />
        <circle cx="32" cy="32" r="19.5" fill="#ffe2ba" />
        <g stroke="#f08a24" strokeWidth="3.2">
        <path d="M32 32L49.75 42.25" />
        <path d="M32 32L32.00 52.50" />
        <path d="M32 32L14.25 42.25" />
        <path d="M32 32L14.25 21.75" />
        <path d="M32 32L32.00 11.50" />
        <path d="M32 32L49.75 21.75" />
        </g>
        <circle cx="32" cy="32" r="3.6" fill="#f08a24" />
      </g>
    </svg>
  )
}
