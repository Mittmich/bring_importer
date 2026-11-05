import { useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { normalizeLanguage, useI18n } from '@/i18n'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { ImportPhotoModal } from './ImportPhotoModal'
import { ImportUrlModal } from './ImportUrlModal'
import { AddRecipeModal, ManualRecipeModal } from './AddRecipeModal'

type ImportMode = 'none' | 'choose' | 'photo' | 'url' | 'manual'

/**
 * Keep the UI language in step with the signed-in user's profile: a language
 * saved on the server wins (so it follows the user across devices); if none is
 * saved yet, seed it with the current (browser/local) choice so imports
 * default to it server-side too.
 */
function useProfileLanguageSync() {
  const { lang, setLanguage } = useI18n()
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: api.getProfile })
  const serverLang = profile ? normalizeLanguage(profile.language) : undefined

  useEffect(() => {
    if (serverLang === undefined) return
    if (serverLang === null) setLanguage(lang, { persist: true })
    else if (serverLang !== lang) setLanguage(serverLang)
    // Only react to what the server says, not to local switches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverLang])
}

export function AppShell() {
  const [importMode, setImportMode] = useState<ImportMode>('none')
  const navigate = useNavigate()
  useProfileLanguageSync()

  function handleImportDone(uuid: string) {
    setImportMode('none')
    navigate(`/recipes/${uuid}`)
  }

  function handleManualDone(uuid: string) {
    setImportMode('none')
    // A hand-entered recipe is just a stub: continue in the editor.
    navigate(`/recipes/${uuid}/edit`)
  }

  function openImport() {
    setImportMode('choose')
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar onImport={openImport} />
        <main className="flex-1 overflow-hidden">
          <Outlet context={{ onImport: openImport }} />
        </main>
      </div>
      <BottomNav />

      <AddRecipeModal
        open={importMode === 'choose'}
        onOpenChange={(o) => setImportMode(o ? 'choose' : 'none')}
        onChoose={setImportMode}
      />
      <ManualRecipeModal
        open={importMode === 'manual'}
        onOpenChange={(o) => setImportMode(o ? 'manual' : 'none')}
        onBack={() => setImportMode('choose')}
        onDone={handleManualDone}
      />
      <ImportPhotoModal
        open={importMode === 'photo'}
        onOpenChange={(o) => setImportMode(o ? 'photo' : 'none')}
        onSwitchToUrl={() => setImportMode('url')}
        onDone={handleImportDone}
      />
      <ImportUrlModal
        open={importMode === 'url'}
        onOpenChange={(o) => setImportMode(o ? 'url' : 'none')}
        onSwitchToPhoto={() => setImportMode('photo')}
        onDone={handleImportDone}
      />
    </div>
  )
}
