import { useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { ImportPhotoModal } from './ImportPhotoModal'
import { ImportUrlModal } from './ImportUrlModal'

type ImportMode = 'none' | 'photo' | 'url'

export function AppShell() {
  const [importMode, setImportMode] = useState<ImportMode>('none')
  const navigate = useNavigate()

  function handleImportDone(uuid: string) {
    setImportMode('none')
    navigate(`/recipes/${uuid}`)
  }

  function openImport() {
    setImportMode('photo')
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar onImport={openImport} />
        <main className="flex-1 overflow-hidden">
          <Outlet context={{ onImport: openImport }} />
        </main>
      </div>
      <BottomNav onImport={openImport} />

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
