import { NavLink, useNavigate } from 'react-router-dom'
import { Home, BookOpen, BookHeart, CalendarDays, Plus, User, LogOut, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getUserEmail, logout } from '@/hooks/useAuth'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'
import { useNotifications } from '@/hooks/useNotifications'
import { useI18n, type MessageKey } from '@/i18n'

function NavBadge({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span className="ml-auto min-w-[18px] h-[18px] px-1 rounded-full bg-primary text-primary-foreground text-[11px] font-semibold flex items-center justify-center">
      {count}
    </span>
  )
}

const navItems: Array<{ to: string; icon: typeof Home; label: MessageKey; end?: boolean }> = [
  { to: '/', icon: Home, label: 'nav.home', end: true },
  { to: '/plan', icon: CalendarDays, label: 'nav.plan' },
  { to: '/recipes', icon: BookOpen, label: 'nav.recipes' },
  { to: '/cookbooks', icon: BookHeart, label: 'nav.cookbooks' },
  { to: '/import', icon: Plus, label: 'nav.import' },
]

export function Sidebar({ onImport }: { onImport: () => void }) {
  const email = getUserEmail()
  const navigate = useNavigate()
  const { canInstall, triggerInstall } = useInstallPrompt()
  const { friendRequests, cookbookInvites } = useNotifications()
  const { t } = useI18n()

  return (
    <aside className="hidden md:flex flex-col w-[220px] min-w-[220px] border-r border-border bg-white">
      <div className="px-4 py-5 border-b border-border">
        <span className="text-sm font-bold text-foreground flex items-center gap-2">
          <span className="w-2 h-2 rounded-sm bg-primary inline-block" />
          {t('common.appName')}
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
              {t(label)}
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
              {t(label)}
              {to === '/cookbooks' && <NavBadge count={cookbookInvites} />}
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
            {t('nav.installApp')}
          </button>
        )}
        <button
          onClick={() => navigate('/account')}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <User className="w-4 h-4 flex-shrink-0" />
          <span className="truncate">{email || t('nav.account')}</span>
          <NavBadge count={friendRequests} />
        </button>
        <button
          onClick={logout}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {t('nav.logout')}
        </button>
      </div>
    </aside>
  )
}
