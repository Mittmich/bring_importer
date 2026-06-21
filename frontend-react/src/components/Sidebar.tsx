import { NavLink, useNavigate } from 'react-router-dom'
import { Home, BookOpen, CalendarDays, Plus, User, LogOut, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getUserEmail, logout } from '@/hooks/useAuth'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'

const navItems = [
  { to: '/', icon: Home, label: 'Home', end: true },
  { to: '/plan', icon: CalendarDays, label: 'Plan' },
  { to: '/recipes', icon: BookOpen, label: 'Recipes' },
  { to: '/import', icon: Plus, label: 'Import' },
]

export function Sidebar({ onImport }: { onImport: () => void }) {
  const email = getUserEmail()
  const navigate = useNavigate()
  const { canInstall, triggerInstall } = useInstallPrompt()

  return (
    <aside className="hidden md:flex flex-col w-[220px] min-w-[220px] border-r border-border bg-white">
      <div className="px-4 py-5 border-b border-border">
        <span className="text-sm font-bold text-foreground flex items-center gap-2">
          <span className="w-2 h-2 rounded-sm bg-primary inline-block" />
          My Recipes
        </span>
      </div>

      <nav className="flex-1 p-2 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label, end }) =>
          to === '/import' ? (
            <button
              key={to}
              onClick={onImport}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </button>
          ) : (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ),
        )}
      </nav>

      <div className="p-2 border-t border-border space-y-0.5">
        {canInstall && (
          <button
            onClick={triggerInstall}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-primary hover:bg-primary/10 transition-colors"
          >
            <Download className="w-4 h-4 flex-shrink-0" />
            Install App
          </button>
        )}
        <button
          onClick={() => navigate('/account')}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <User className="w-4 h-4 flex-shrink-0" />
          <span className="truncate">{email || 'Account'}</span>
        </button>
        <button
          onClick={logout}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          Log out
        </button>
      </div>
    </aside>
  )
}
