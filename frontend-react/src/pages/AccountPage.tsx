import { Link } from 'react-router-dom'
import { ChevronRight, Tag } from 'lucide-react'
import { getUserEmail, logout } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'

export function AccountPage() {
  const email = getUserEmail()

  return (
    <div className="flex flex-col h-full bg-[#F8FAFC]">
      <div className="max-w-sm mx-auto w-full p-4 md:p-6 space-y-4 pt-8">
        <div className="bg-white rounded-xl border border-border p-5">
          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-1">
            Signed in as
          </p>
          <p className="text-sm font-semibold text-foreground">{email}</p>
        </div>
        <Link
          to="/account/tags"
          className="flex items-center gap-3 bg-white rounded-xl border border-border p-5 hover:bg-muted/40 transition-colors"
        >
          <Tag className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Manage tags</span>
          <ChevronRight className="w-4 h-4 text-muted-foreground/50 ml-auto" />
        </Link>
        <Button variant="outline" className="w-full text-destructive hover:text-destructive" onClick={logout}>
          Log out
        </Button>
      </div>
    </div>
  )
}
