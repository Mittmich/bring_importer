import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Home, BookOpen, BookHeart, CalendarDays, UtensilsCrossed, User, Download, Share, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'
import { useNotifications } from '@/hooks/useNotifications'
import { useI18n, type MessageKey } from '@/i18n'
import { useFeatures } from '@/hooks/useFeatures'

const tabs: Array<{ to: string; icon: typeof Home; label: MessageKey; end?: boolean }> = [
  { to: '/', icon: Home, label: 'nav.home', end: true },
  { to: '/recipes', icon: BookOpen, label: 'nav.recipes' },
  { to: '/cookbooks', icon: BookHeart, label: 'nav.cookbooks' },
  { to: '/plan', icon: CalendarDays, label: 'nav.plan' },
  { to: '/account', icon: User, label: 'nav.account' },
]

export function BottomNav() {
  const { canInstall, triggerInstall, showIosInstructions } = useInstallPrompt()
  const [iosBannerDismissed, setIosBannerDismissed] = useState(false)
  const { friendRequests, cookbookInvites } = useNotifications()
  const { t, tx } = useI18n()
  const { features } = useFeatures()
  const { pathname } = useLocation()
  const items = tabs.map((tab) =>
    tab.to === '/plan' && features?.planner === 'menus'
      ? { ...tab, icon: UtensilsCrossed, label: 'nav.menus' as MessageKey }
      : tab,
  )
  const badgeFor = (to: string) =>
    to === '/account' ? friendRequests : to === '/cookbooks' ? cookbookInvites : 0

  return (
    <>
      {showIosInstructions && !iosBannerDismissed && (
        <div className="md:hidden flex items-center gap-2 px-4 py-3 bg-primary text-primary-foreground text-sm">
          <Share className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1">
            {tx('nav.iosInstall', {
              icon: <Share className="w-3.5 h-3.5 inline mb-0.5" />,
              action: <strong>{t('nav.iosAddToHome')}</strong>,
            })}
          </span>
          <button onClick={() => setIosBannerDismissed(true)} aria-label={t('common.dismiss')}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      <nav className="md:hidden flex border-t border-border bg-white safe-area-bottom">
        {items.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'relative flex-1 flex flex-col items-center justify-center gap-1 py-3.5 transition-colors',
                isActive || (to === '/plan' && pathname.startsWith('/menus/'))
                  ? 'text-primary'
                  : 'text-muted-foreground',
              )
            }
          >
            <span className="relative">
              <Icon className="w-6 h-6" />
              {badgeFor(to) > 0 && (
                <span className="absolute -top-1.5 -right-2 min-w-[16px] h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-semibold flex items-center justify-center">
                  {badgeFor(to)}
                </span>
              )}
            </span>
            <span className="text-xs font-medium">{t(label)}</span>
          </NavLink>
        ))}
        {canInstall && (
          <button
            onClick={triggerInstall}
            className="flex-1 flex flex-col items-center justify-center gap-1 py-3.5 text-primary"
          >
            <Download className="w-6 h-6" />
            <span className="text-xs font-medium">{t('nav.install')}</span>
          </button>
        )}
      </nav>
    </>
  )
}
