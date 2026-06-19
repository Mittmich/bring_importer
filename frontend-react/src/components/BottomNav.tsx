import { NavLink } from 'react-router-dom'
import { Home, BookOpen, Plus, User, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'

const tabs = [
  { to: '/', icon: Home, label: 'Home', end: true },
  { to: '/recipes', icon: BookOpen, label: 'Recipes' },
  { to: '/import', icon: Plus, label: 'Import' },
  { to: '/account', icon: User, label: 'Account' },
]

export function BottomNav({ onImport }: { onImport: () => void }) {
  const { canInstall, triggerInstall } = useInstallPrompt()

  return (
    <nav className="md:hidden flex border-t border-border bg-white safe-area-bottom">
      {tabs.map(({ to, icon: Icon, label, end }) =>
        to === '/import' ? (
          <button
            key={to}
            onClick={onImport}
            className="flex-1 flex flex-col items-center justify-center gap-1 py-3.5 text-muted-foreground"
          >
            <Icon className="w-6 h-6" />
            <span className="text-xs font-medium">{label}</span>
          </button>
        ) : (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex-1 flex flex-col items-center justify-center gap-1 py-3.5 transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground',
              )
            }
          >
            <Icon className="w-6 h-6" />
            <span className="text-xs font-medium">{label}</span>
          </NavLink>
        ),
      )}
      {canInstall && (
        <button
          onClick={triggerInstall}
          className="flex-1 flex flex-col items-center justify-center gap-1 py-3.5 text-primary"
        >
          <Download className="w-6 h-6" />
          <span className="text-xs font-medium">Install</span>
        </button>
      )}
    </nav>
  )
}
