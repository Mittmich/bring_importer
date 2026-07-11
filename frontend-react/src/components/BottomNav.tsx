import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Home, BookOpen, BookHeart, CalendarDays, User, Download, Share, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'

const tabs = [
  { to: '/', icon: Home, label: 'Home', end: true },
  { to: '/recipes', icon: BookOpen, label: 'Recipes' },
  { to: '/cookbooks', icon: BookHeart, label: 'Cookbooks' },
  { to: '/plan', icon: CalendarDays, label: 'Plan' },
  { to: '/account', icon: User, label: 'Account' },
]

export function BottomNav() {
  const { canInstall, triggerInstall, showIosInstructions } = useInstallPrompt()
  const [iosBannerDismissed, setIosBannerDismissed] = useState(false)

  return (
    <>
      {showIosInstructions && !iosBannerDismissed && (
        <div className="md:hidden flex items-center gap-2 px-4 py-3 bg-primary text-primary-foreground text-sm">
          <Share className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1">
            Tap <Share className="w-3.5 h-3.5 inline mb-0.5" /> then <strong>Add to Home Screen</strong> to install
          </span>
          <button onClick={() => setIosBannerDismissed(true)} aria-label="Dismiss">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      <nav className="md:hidden flex border-t border-border bg-white safe-area-bottom">
        {tabs.map(({ to, icon: Icon, label, end }) => (
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
        ))}
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
    </>
  )
}
