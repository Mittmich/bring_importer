import { NavLink } from 'react-router-dom'
import { Home, BookOpen, Plus, User } from 'lucide-react'
import { cn } from '@/lib/utils'

const tabs = [
  { to: '/', icon: Home, label: 'Home', end: true },
  { to: '/recipes', icon: BookOpen, label: 'Recipes' },
  { to: '/import', icon: Plus, label: 'Import' },
  { to: '/account', icon: User, label: 'Account' },
]

export function BottomNav({ onImport }: { onImport: () => void }) {
  return (
    <nav className="md:hidden flex border-t border-border bg-white safe-area-bottom">
      {tabs.map(({ to, icon: Icon, label, end }) =>
        to === '/import' ? (
          <button
            key={to}
            onClick={onImport}
            className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-muted-foreground"
          >
            <Icon className="w-5 h-5" />
            <span className="text-[10px] font-medium">{label}</span>
          </button>
        ) : (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground',
              )
            }
          >
            <Icon className="w-5 h-5" />
            <span className="text-[10px] font-medium">{label}</span>
          </NavLink>
        ),
      )}
    </nav>
  )
}
