import { FileDown, Loader2 } from 'lucide-react'
import { useExportPdf } from '@/hooks/useExportPdf'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'

/**
 * Downloads (desktop) or shares (phone) a PDF of the recipe, rendered by the
 * backend in the current UI language and scaled to the shown servings.
 * `iconOnly` is the compact variant for the mobile top bar.
 */
export function ExportPdfButton({
  uuid,
  servings,
  iconOnly = false,
  className,
}: {
  uuid: string
  servings?: number
  iconOnly?: boolean
  className?: string
}) {
  const { t } = useI18n()
  const { busy, exportPdf } = useExportPdf(uuid, servings)

  const icon = busy ? (
    <Loader2 className={`animate-spin ${iconOnly ? 'w-4 h-4' : 'w-3.5 h-3.5 mr-1'}`} />
  ) : (
    <FileDown className={iconOnly ? 'w-4 h-4' : 'w-3.5 h-3.5 mr-1'} />
  )

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={exportPdf}
      disabled={busy}
      aria-label={busy ? t('recipe.exportingPdf') : t('recipe.exportPdfLabel')}
      title={t('recipe.exportPdfLabel')}
      className={className}
    >
      {icon}
      {!iconOnly && t('recipe.exportPdf')}
    </Button>
  )
}
