import { useState } from 'react'
import { api } from '@/lib/api'
import { saveOrShare } from '@/lib/download'
import { useI18n } from '@/i18n'

/** Export logic shared by the button and the recipe "⋯" menu. */
export function useExportPdf(uuid: string, servings?: number) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)

  async function exportPdf() {
    setBusy(true)
    try {
      const { blob, filename } = await api.downloadRecipePdf(uuid, servings)
      await saveOrShare(blob, filename)
    } catch {
      window.alert(t('recipe.pdfFailed'))
    } finally {
      setBusy(false)
    }
  }

  return { busy, exportPdf }
}
