import { Lightbulb, LightbulbOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useWakeLock } from '@/hooks/useWakeLock'

/**
 * Toggles a screen wake lock so the phone display stays on while reading the
 * recipe. Renders nothing when the Wake Lock API is unavailable (e.g. desktop
 * browsers or insecure contexts).
 */
export function KeepAwakeButton({ className }: { className?: string }) {
  const { supported, active, toggle } = useWakeLock()

  if (!supported) return null

  return (
    <Button
      variant={active ? 'default' : 'outline'}
      size="sm"
      onClick={toggle}
      aria-pressed={active}
      aria-label={active ? 'Allow screen to sleep' : 'Keep screen awake'}
      title={active ? 'Screen stays on — tap to allow sleep' : 'Keep screen awake'}
      className={className}
    >
      {active ? <Lightbulb className="w-4 h-4" /> : <LightbulbOff className="w-4 h-4" />}
    </Button>
  )
}
