import { Lightbulb, LightbulbOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useWakeLock } from '@/hooks/useWakeLock'
import { useI18n } from '@/i18n'

/**
 * Toggles a screen wake lock so the phone display stays on while reading the
 * recipe. Renders nothing when the Wake Lock API is unavailable (e.g. desktop
 * browsers or insecure contexts).
 */
export function KeepAwakeButton({ className }: { className?: string }) {
  const { supported, active, toggle } = useWakeLock()
  const { t } = useI18n()

  if (!supported) return null

  return (
    <Button
      variant={active ? 'default' : 'outline'}
      size="sm"
      onClick={toggle}
      aria-pressed={active}
      aria-label={active ? t('recipe.allowSleep') : t('recipe.keepAwake')}
      title={active ? t('recipe.screenStaysOn') : t('recipe.keepAwake')}
      className={className}
    >
      {active ? <Lightbulb className="w-4 h-4" /> : <LightbulbOff className="w-4 h-4" />}
    </Button>
  )
}
